"""Execution logic for ChromaSQL plans.

The executor is intentionally thin: given a :class:`chromasql.plan.QueryPlan`
it orchestrates the calls against a Chroma collection (either ``query`` or
``get``) and post-processes the results so that they match the projection /
ordering / pagination requested by the caller.

The file is structured in three layers:

``execute_plan``
    Public entry point used by the CLI / REPL.  Decides whether we need the
    vector or the filter code path.
``_run_*`` functions
    Handle the direct interaction with the Chroma client and wrap error cases
    into :class:`chromasql.errors.ChromaSQLExecutionError` so callers get a
    predictable exception type.
``_apply_*`` helpers
    Pure post-processing helpers (ordering, limit/offset, projections) that are
    easy to unit test in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, Dict, List, Optional, Sequence

from .errors import ChromaSQLExecutionError, ChromaSQLPlanningError
from .plan import PlanProjectionItem, QueryPlan

EmbedFunction = Callable[[str, Optional[str]], Sequence[float]]


@dataclass(frozen=True)
class ExecutionResult:
    """Convenience wrapper for executor output.

    ``rows``
        The tabular payload after limit/offset/projection have been applied.
    ``raw``
        The original Chroma response.  Useful for debugging / ``EXPLAIN`` flows.
    """

    rows: List[Dict[str, Any]]
    raw: Dict[str, Any]


def execute_plan(
    plan: QueryPlan,
    collection: Any,
    *,
    embed_fn: Optional[EmbedFunction] = None,
) -> ExecutionResult:
    """Execute a :class:`QueryPlan` against a ChromaDB collection.

    Parameters
    ----------
    plan:
        The validated plan produced by the planner.
    collection:
        The Chroma collection object.  We rely on duck typing so both sync and
        async stubs can be passed during tests.
    embed_fn:
        Optional callable used to turn ``TEXT '...'`` clauses into embedding
        vectors.  Required whenever the plan references textual queries.
    """

    if plan.mode == "vector":
        raw = _run_vector_query(plan, collection, embed_fn)
    else:
        raw = _run_filter_query(plan, collection)

    rows = _materialize_rows(plan, raw)
    return ExecutionResult(rows=rows, raw=raw)


def _run_vector_query(
    plan: QueryPlan,
    collection: Any,
    embed_fn: Optional[EmbedFunction],
) -> Dict[str, Any]:
    """Execute ``collection.query`` for plans that require embeddings."""
    if plan.embedding_texts and embed_fn is None:
        raise ChromaSQLExecutionError("Embedding text requires an embed_fn")
    if plan.embedding_text and embed_fn is None:
        raise ChromaSQLExecutionError("Embedding text requires an embed_fn")

    query_embeddings: List[Sequence[float]] = []
    if plan.embedding_texts:
        for text, model in plan.embedding_texts:
            assert embed_fn is not None  # for type-checkers
            query_embeddings.append(list(embed_fn(text, model)))
    if plan.query_vector_batch:
        query_embeddings.extend([list(vector) for vector in plan.query_vector_batch])

    if not query_embeddings:
        if plan.embedding_text:
            assert embed_fn is not None  # Validated above
            embedded = embed_fn(plan.embedding_text, plan.embedding_model)  # type: ignore[arg-type]
            query_embeddings = [list(embedded)]
        elif plan.query_vector is not None:
            query_embeddings = [list(plan.query_vector)]
        else:
            raise ChromaSQLExecutionError(
                "Vector queries require embeddings or vectors"
            )
    elif plan.embedding_text and embed_fn is not None:
        # If both single and batch are provided, append the single item.
        query_embeddings.append(
            list(embed_fn(plan.embedding_text, plan.embedding_model))
        )
    elif plan.query_vector is not None:
        query_embeddings.append(list(plan.query_vector))

    include = list(plan.include) if plan.include else None

    try:
        result = collection.query(
            query_embeddings=query_embeddings,
            ids=list(plan.ids) if plan.ids else None,
            where=plan.where,
            where_document=plan.where_document,
            include=include,
            n_results=plan.n_results,
        )
    except Exception as exc:
        raise ChromaSQLExecutionError(f"Chroma query failed: {exc}") from exc

    if not isinstance(result, dict):
        raise ChromaSQLExecutionError("Unexpected result format from collection.query")
    return result


def _run_filter_query(plan: QueryPlan, collection: Any) -> Dict[str, Any]:
    """Execute ``collection.get`` for metadata-only retrieval."""
    include = list(plan.include) if plan.include else None

    limit = None if plan.order_by else plan.limit
    offset = None if plan.order_by else plan.offset

    try:
        result = collection.get(
            ids=list(plan.ids) if plan.ids else None,
            where=plan.where,
            where_document=plan.where_document,
            include=include,
            limit=limit,
            offset=offset,
        )
    except Exception as exc:
        raise ChromaSQLExecutionError(f"Chroma get failed: {exc}") from exc

    if not isinstance(result, dict):
        raise ChromaSQLExecutionError("Unexpected result format from collection.get")
    return result


def _materialize_rows(plan: QueryPlan, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply rerank filters, order-by, pagination, and projection."""
    base_rows = (
        _extract_vector_rows(plan, raw)
        if plan.mode == "vector"
        else _extract_filter_rows(raw)
    )

    if plan.mode == "vector" and plan.score_threshold is not None:
        base_rows = [
            row
            for row in base_rows
            if row["distance"] is None or row["distance"] <= plan.score_threshold
        ]

    ordered = _apply_order(base_rows, plan.order_by)
    sliced = _apply_limit_offset(ordered, plan.limit, plan.offset, plan.mode)
    return [_project_row(plan, row) for row in sliced]


def _extract_vector_rows(plan: QueryPlan, raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise the nested Chroma response into row dictionaries."""
    ids_rows = raw.get("ids") or []
    if not ids_rows:
        return []
    ids = ids_rows[0]
    distances_rows = raw.get("distances") or [[]]
    documents_rows = raw.get("documents") or [[]]
    metadatas_rows = raw.get("metadatas") or [[]]
    embeddings_rows = raw.get("embeddings") or [[]]

    rows: List[Dict[str, Any]] = []
    for index, ident in enumerate(ids):
        rows.append(
            {
                "id": ident,
                "distance": _safe_get(distances_rows, index),
                "document": _safe_get(documents_rows, index),
                "metadata": _safe_get(metadatas_rows, index) or {},
                "embedding": _safe_get(embeddings_rows, index),
            }
        )
    return rows


def _extract_filter_rows(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise ``get`` responses into row dictionaries (no distances)."""
    ids = raw.get("ids") or []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    embeddings = raw.get("embeddings") or []

    max_len = max(len(ids), len(documents), len(metadatas), len(embeddings))
    rows: List[Dict[str, Any]] = []
    for index in range(max_len):
        rows.append(
            {
                "id": ids[index] if index < len(ids) else None,
                "distance": None,
                "document": documents[index] if index < len(documents) else None,
                "metadata": metadatas[index] if index < len(metadatas) else {},
                "embedding": embeddings[index] if index < len(embeddings) else None,
            }
        )
    return rows


def _safe_get(items: Sequence[Sequence[Any]], index: int) -> Any:
    """Return ``items[0][index]`` handling short / missing sequences."""
    if not items:
        return None
    row = items[0]
    if index >= len(row):
        return None
    return row[index]


def _apply_order(
    rows: List[Dict[str, Any]], order_by: Sequence[Any]
) -> List[Dict[str, Any]]:
    """Apply ORDER BY semantics using stable Python sorts."""
    if not order_by:
        return rows

    # Python's sort does not support per-column direction, so we sort iteratively
    ordered = rows[:]
    for item in reversed(order_by):
        ordered.sort(
            key=partial(_order_value, order=item),
            reverse=item.direction == "DESC",
        )
    return ordered


def _order_value(row: Dict[str, Any], order: Any) -> Any:
    """Read the value used for ordering from a row."""
    field = order.field
    root = field.root
    if root == "distance":
        return row.get("distance")
    if root == "id":
        return row.get("id")
    if root == "metadata":
        return _dig_metadata(row.get("metadata") or {}, field.path)
    raise ChromaSQLPlanningError(f"Unsupported ORDER BY field {field.dotted()}")


def _apply_limit_offset(
    rows: List[Dict[str, Any]],
    limit: Optional[int],
    offset: Optional[int],
    mode: str,
) -> List[Dict[str, Any]]:
    """Slice the list of rows according to LIMIT/OFFSET semantics."""
    offset_val = offset or 0
    start = offset_val
    end = start + limit if limit is not None else None
    sliced = rows[start:end]
    if mode == "filter" and limit is None and offset is None:
        return rows
    return sliced


def _project_row(plan: QueryPlan, row: Dict[str, Any]) -> Dict[str, Any]:
    """Materialise the final projection for a single row."""
    columns: Sequence[PlanProjectionItem]
    if plan.select_all:
        columns = [
            PlanProjectionItem("id"),
            PlanProjectionItem("distance"),
            PlanProjectionItem("document"),
            PlanProjectionItem("metadata"),
        ]
    else:
        columns = plan.projection
    projected: Dict[str, Any] = {}
    for item in columns:
        key = item.alias or item.field
        projected[key] = _resolve_projection_value(row, item.field)
    return projected


def _resolve_projection_value(row: Dict[str, Any], field: str) -> Any:
    """Resolve dotted metadata projection paths and built-in columns."""
    if field == "id":
        return row.get("id")
    if field == "distance":
        return row.get("distance")
    if field == "document":
        return row.get("document")
    if field == "metadata":
        return row.get("metadata")
    if field == "embedding":
        return row.get("embedding")
    if field.startswith("metadata."):
        metadata = row.get("metadata") or {}
        path = field.split(".")[1:]
        return _dig_metadata(metadata, tuple(path))
    raise ChromaSQLPlanningError(f"Unsupported projection field {field}")


def _dig_metadata(metadata: Dict[str, Any], path: Sequence[str]) -> Any:
    """Traverse nested metadata dictionaries, returning ``None`` when missing."""
    current: Any = metadata
    for component in path:
        if not isinstance(current, dict):
            return None
        current = current.get(component)
    return current
