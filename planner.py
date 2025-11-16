"""Translate ChromaSQL AST nodes into executable plans.

The planner is the semantic heart of the system.  It takes a syntactically
valid :class:`chromasql.ast.Query` and checks whether it can be expressed with
ChromaDB's query primitives.  The output is a :class:`chromasql.plan.QueryPlan`
which is purposely close to ``collection.query`` / ``collection.get`` arguments.

High-level responsibilities:

* Validate mutually exclusive clauses (e.g. ``TOPK`` requires embeddings).
* Resolve which pieces need to be materialised from Chroma (``include`` set).
* Translate boolean expressions into the nested ``where`` JSON understood by
  ChromaDB.
* Normalise helper hints such as ``RERANK BY`` into a plan field the executor
  can inspect.

Whenever we add new language features, the planner is the place where we codify
the business rules that go beyond syntactic correctness.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple, cast

from ._ast_nodes import (
    BooleanPredicate,
    ComparisonPredicate,
    ContainsPredicate,
    EmbeddingBatch,
    EmbeddingText,
    EmbeddingVector,
    Field,
    InPredicate,
    BetweenPredicate,
    LikePredicate,
    OrderItem,
    Predicate,
    Projection,
    Query,
)
from .errors import ChromaSQLPlanningError
from .plan import PlanProjectionItem, QueryPlan


INCLUDE_MAPPING = {
    "document": "documents",
    "metadata": "metadatas",
    "embedding": "embeddings",
    "distance": "distances",
}

DEFAULT_TOPK = 10


def build_plan(query: Query) -> QueryPlan:
    """Convert a parsed query into an executable plan.

    Parameters
    ----------
    query:
        The AST produced by :func:`chromasql.parser.parse`.

    Returns
    -------
    QueryPlan
        A validated plan that the executor can hand to ChromaDB.

    Raises
    ------
    ChromaSQLPlanningError
        If the query expresses something that ChromaSQL cannot model (invalid
        TOPK usage, unsupported ORDER BY field, illegal metadata predicate, …).
    """
    mode = "vector" if query.embedding is not None else "filter"

    if mode == "filter" and query.topk is not None:
        raise ChromaSQLPlanningError("TOPK can only be used with EMBEDDING queries")

    if query.limit is not None and query.limit < 0:
        raise ChromaSQLPlanningError("LIMIT must be non-negative")
    if query.offset is not None and query.offset < 0:
        raise ChromaSQLPlanningError("OFFSET must be non-negative")
    if query.topk is not None and query.topk <= 0:
        raise ChromaSQLPlanningError("TOPK must be greater than zero")

    projection_items = _projection_to_plan_items(query.projection)
    include = _resolve_includes(query, projection_items)
    if mode == "vector" and "distances" not in include:
        include = tuple(sorted(set(include) | {"distances"}))

    where, where_document, ids = _translate_predicate(query.where)

    if query.where_document is not None:
        document_filter = _build_document_filter(query.where_document)
        if where_document is None:
            where_document = document_filter
        else:
            where_document = _merge_conjunctive_filters(
                [where_document, document_filter]
            )

    order_by = query.order_by
    if mode == "vector":
        if not order_by:
            order_by = (OrderItem(field=Field("distance"), direction="ASC"),)
        for item in order_by:
            if item.field.root == "distance":
                continue
            if item.field.root not in ("metadata", "id"):
                raise ChromaSQLPlanningError(
                    "ORDER BY supports distance, metadata.*, or id for vector queries"
                )
    else:
        for item in order_by:
            if item.field.root == "distance":
                raise ChromaSQLPlanningError(
                    "ORDER BY distance requires an EMBEDDING query"
                )

    n_results = query.topk or DEFAULT_TOPK if mode == "vector" else 0
    if mode == "vector" and query.limit is not None:
        offset = query.offset or 0
        n_results = max(n_results, query.limit + offset)

    embedding_text: Optional[str] = None
    embedding_model: Optional[str] = None
    query_vector: Optional[Tuple[float, ...]] = None
    embedding_texts: List[Tuple[str, Optional[str]]] = []
    query_vector_batch: List[Tuple[float, ...]] = []
    if isinstance(query.embedding, EmbeddingText):
        embedding_text = query.embedding.text
        embedding_model = query.embedding.model
    elif isinstance(query.embedding, EmbeddingVector):
        query_vector = query.embedding.values
    elif isinstance(query.embedding, EmbeddingBatch):
        for emb_item in query.embedding.items:
            if isinstance(emb_item, EmbeddingText):
                embedding_texts.append((emb_item.text, emb_item.model))
            elif isinstance(emb_item, EmbeddingVector):
                query_vector_batch.append(emb_item.values)

    similarity = query.similarity.upper() if query.similarity else "COSINE"

    return QueryPlan(
        explain=query.explain,
        mode=mode,
        collection=query.collection,
        projection=tuple(projection_items),
        select_all=query.projection.select_all,
        include=include,
        embedding_text=embedding_text,
        embedding_model=embedding_model,
        query_vector=query_vector,
        embedding_texts=tuple(embedding_texts) if embedding_texts else None,
        query_vector_batch=tuple(query_vector_batch) if query_vector_batch else None,
        where=where,
        where_document=where_document,
        ids=tuple(ids) if ids is not None else None,
        n_results=n_results,
        similarity=similarity,
        order_by=order_by,
        limit=query.limit,
        offset=query.offset,
        score_threshold=query.score_threshold,
        rerank=query.rerank.params if query.rerank else None,
    )


def _projection_to_plan_items(projection: Projection) -> List[PlanProjectionItem]:
    """Normalise the projection clause into :class:`PlanProjectionItem` objects."""
    fields = projection.requested_fields()
    items: List[PlanProjectionItem] = []

    if projection.select_all:
        for field in fields:
            items.append(PlanProjectionItem(field=field.root))
        return items

    for item in projection.items:
        items.append(PlanProjectionItem(field=item.field.dotted(), alias=item.alias))

    return items


def _resolve_includes(
    query: Query, projection_items: Sequence[PlanProjectionItem]
) -> Tuple[str, ...]:
    """Determine which result components must be requested from ChromaDB."""
    include: Set[str] = set()

    for item in projection_items:
        base = item.field.split(".")[0]
        include_name = INCLUDE_MAPPING.get(base)
        if include_name:
            include.add(include_name)

    if query.order_by:
        for order in query.order_by:
            if order.field.root == "metadata":
                include.add("metadatas")
            elif order.field.root == "distance":
                include.add("distances")

    if query.where:
        roots = _predicate_roots(query.where)
        if "metadata" in roots:
            include.add("metadatas")
        if "document" in roots:
            include.add("documents")

    if query.where_document is not None:
        include.add("documents")

    if query.projection.select_all:
        include.update(("documents", "metadatas", "distances"))

    if query.embedding is None and "distances" in include:
        include.remove("distances")

    return tuple(sorted(include))


def _translate_predicate(
    predicate: Optional[Predicate],
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[List[str]]]:
    """Split the high-level WHERE clause into metadata/document/id filters."""
    if predicate is None:
        return None, None, None

    terms = _split_conjunction(predicate)
    metadata_filters: List[Dict[str, Any]] = []
    document_filters: List[Dict[str, Any]] = []
    ids_lists: List[List[str]] = []

    for term in terms:
        roots = _predicate_roots(term)
        if roots == {"metadata"}:
            metadata_filters.append(_build_metadata_filter(term))
        elif roots == {"document"}:
            document_filters.append(_build_document_filter(term))
        elif roots == {"id"}:
            ids_lists.append(_ids_from_predicate(term))
        else:
            raise ChromaSQLPlanningError(
                "WHERE clauses may only combine metadata, document, and id filters with AND"
            )

    metadata = _merge_conjunctive_filters(metadata_filters)
    document = _merge_conjunctive_filters(document_filters)
    ids: Optional[List[str]] = None
    for candidate in ids_lists:
        if ids is None:
            ids = candidate
        else:
            candidate_set = set(candidate)
            ids = [value for value in ids if value in candidate_set]
    return metadata, document, ids


def _merge_conjunctive_filters(
    filters: Sequence[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Compact a list of ``$and`` dictionaries into a single dictionary."""
    if not filters:
        return None
    flattened: List[Dict[str, Any]] = []
    for flt in filters:
        if "$and" in flt and len(flt) == 1:
            flattened.extend(flt["$and"])
        else:
            flattened.append(flt)
    if not flattened:
        return None
    if len(flattened) == 1:
        return flattened[0]
    return {"$and": flattened}


def _split_conjunction(predicate: Predicate) -> List[Predicate]:
    """Flatten nested ``AND`` nodes so we can reason about each scalar filter."""
    if isinstance(predicate, BooleanPredicate) and predicate.operator == "AND":
        terms: List[Predicate] = []
        for sub in predicate.predicates:
            terms.extend(_split_conjunction(sub))
        return terms
    return [predicate]


def _predicate_roots(predicate: Predicate) -> Set[str]:
    """Return the top-level field roots referenced by a predicate tree."""
    if isinstance(predicate, BooleanPredicate):
        roots: Set[str] = set()
        for sub in predicate.predicates:
            roots.update(_predicate_roots(sub))
        return roots
    field = _field_from_predicate(predicate)
    return {field.root}


def _field_from_predicate(predicate: Predicate) -> Field:
    """Extract the field referenced by predicates that carry a field operand."""
    if isinstance(
        predicate,
        (
            ComparisonPredicate,
            InPredicate,
            BetweenPredicate,
            LikePredicate,
            ContainsPredicate,
        ),
    ):
        return predicate.field
    raise ChromaSQLPlanningError("Unsupported predicate structure")


def _build_metadata_filter(predicate: Predicate) -> Dict[str, Any]:
    """Translate a predicate tree into the JSON payload expected by ``where``."""
    if isinstance(predicate, BooleanPredicate):
        key = "$and" if predicate.operator == "AND" else "$or"
        items = [_build_metadata_filter(child) for child in predicate.predicates]
        if len(items) == 1:
            return items[0]
        return {key: items}

    if isinstance(predicate, ComparisonPredicate):
        operator = _comparison_operator(predicate.operator)
        payload = {operator: predicate.value}
        return _nest_metadata_field(predicate.field, payload)

    if isinstance(predicate, InPredicate):
        op = "$nin" if predicate.negated else "$in"
        # Cast to Any to avoid mypy complaining about list type
        payload = {op: cast(Any, list(predicate.values))}
        return _nest_metadata_field(predicate.field, payload)

    if isinstance(predicate, BetweenPredicate):
        payload = {"$gte": predicate.lower, "$lte": predicate.upper}
        return _nest_metadata_field(predicate.field, payload)

    if isinstance(predicate, ContainsPredicate):
        payload = {"$contains": predicate.value}
        return _nest_metadata_field(predicate.field, payload)

    if isinstance(predicate, LikePredicate):
        substring = _extract_contains_pattern(predicate.pattern)
        payload = {"$contains": substring}
        return _nest_metadata_field(predicate.field, payload)

    raise ChromaSQLPlanningError("Unsupported metadata predicate")


def _build_document_filter(predicate: Predicate) -> Dict[str, Any]:
    """Translate document predicates into the ``where_document`` format."""
    if isinstance(predicate, BooleanPredicate):
        key = "$and" if predicate.operator == "AND" else "$or"
        items = [_build_document_filter(child) for child in predicate.predicates]
        if len(items) == 1:
            return items[0]
        return {key: items}

    if isinstance(predicate, ContainsPredicate):
        return {"$contains": predicate.value}

    if isinstance(predicate, LikePredicate):
        substring = _extract_contains_pattern(predicate.pattern)
        return {"$contains": substring}

    raise ChromaSQLPlanningError("Documents support CONTAINS or simple LIKE predicates")


def _ids_from_predicate(predicate: Predicate) -> List[str]:
    """Collect explicit id values from a predicate tree, preserving order."""
    if isinstance(predicate, BooleanPredicate):
        lists = [_ids_from_predicate(child) for child in predicate.predicates]
        if predicate.operator == "AND":
            if not lists:
                return []
            intersection = lists[0]
            for subset in lists[1:]:
                subset_set = set(subset)
                intersection = [value for value in intersection if value in subset_set]
            return intersection
        if predicate.operator == "OR":
            ordered: List[str] = []
            for subset in lists:
                for value in subset:
                    if value not in ordered:
                        ordered.append(value)
            return ordered
        raise ChromaSQLPlanningError("Unsupported boolean operator for id predicates")

    if isinstance(predicate, ComparisonPredicate):
        if predicate.operator != "=":
            raise ChromaSQLPlanningError("id comparisons only support equality")
        id_value: str = cast(str, predicate.value)
        if not isinstance(id_value, str):
            raise ChromaSQLPlanningError("id comparisons require string literals")
        return [id_value]

    if isinstance(predicate, InPredicate):
        if predicate.negated:
            raise ChromaSQLPlanningError("NOT IN is not supported for id filters")
        invalid = [value for value in predicate.values if not isinstance(value, str)]
        if invalid:
            raise ChromaSQLPlanningError("id IN list must contain only strings")
        seen: List[str] = []
        for val in predicate.values:
            # After validation above, all values are strings
            id_str: str = cast(str, val)
            if id_str not in seen:
                seen.append(id_str)
        return seen

    raise ChromaSQLPlanningError("Unsupported expression for id filters")


def _comparison_operator(symbol: str) -> str:
    """Map CSQL comparison operators to the Chroma ``$`` prefixed names."""
    mapping = {
        "=": "$eq",
        "!=": "$ne",
        "<": "$lt",
        "<=": "$lte",
        ">": "$gt",
        ">=": "$gte",
    }
    try:
        return mapping[symbol]
    except KeyError as exc:
        raise ChromaSQLPlanningError(
            f"Unsupported comparison operator {symbol}"
        ) from exc


def _nest_metadata_field(field: Field, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Nest a payload under the dotted metadata path (e.g. ``metadata.a.b``)."""
    if field.root != "metadata":
        raise ChromaSQLPlanningError("Metadata filter expected metadata field")
    if not field.path:
        raise ChromaSQLPlanningError("Metadata filters require a field path")

    result = payload
    for component in reversed(field.path):
        result = {component: result}
    return result


def _extract_contains_pattern(pattern: str) -> str:
    if (
        pattern.startswith("%")
        and pattern.endswith("%")
        and pattern.count("%") == 2
        and "_" not in pattern
    ):
        return pattern.strip("%")
    raise ChromaSQLPlanningError("LIKE patterns are limited to %%value%% form")
