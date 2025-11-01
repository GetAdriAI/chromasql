"""Multi-collection query execution for ChromaSQL.

This module provides generic abstractions for executing ChromaSQL queries across
multiple collections with custom routing strategies. It is designed to be
extended by developers who need to fan out queries to partitioned data.

The core abstraction is the ``CollectionRouter`` protocol, which lets you
implement arbitrary routing logic based on the parsed query. A common pattern
is to extract metadata filters from the WHERE clause and map them to specific
collections, but the protocol is intentionally flexible.

Example: Model-based routing
-----------------------------

    from chromasql.analysis import extract_metadata_values
    from chromasql.multi_collection import CollectionRouter, execute_multi_collection

    class ModelBasedRouter(CollectionRouter):
        def __init__(self, query_config: Dict[str, Any]):
            self.query_config = query_config

        def route(self, query: Query) -> Optional[Sequence[str]]:
            # Extract model values from WHERE clause
            models = extract_metadata_values(query, field_path=("model",))
            if models:
                # Map models to collections using your config
                return get_collections_for_models(self.query_config, list(models))
            # Return None to query all collections
            return None

    router = ModelBasedRouter(config)
    result = await execute_multi_collection(
        query_str="SELECT * FROM demo WHERE metadata.model = 'Table';",
        router=router,
        async_client=my_async_client,
        embed_fn=my_embed_fn,
    )

Example: Custom discriminator routing
--------------------------------------

    class TenantBasedRouter(CollectionRouter):
        def route(self, query: Query) -> Optional[Sequence[str]]:
            # Extract tenant_id instead of model
            tenants = extract_metadata_values(query, field_path=("tenant_id",))
            if tenants:
                return [f"tenant_{t}_data" for t in tenants]
            return None  # Query all tenant collections
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Protocol, Sequence

from .ast import Query
from .errors import ChromaSQLExecutionError
from .executor import EmbedFunction, ExecutionResult
from .parser import parse
from .plan import QueryPlan
from .planner import build_plan

logger = logging.getLogger(__name__)


class CollectionRouter(Protocol):
    """Protocol for routing queries to specific collections.

    Implementations of this protocol decide which collections should be queried
    based on the parsed AST. Return ``None`` to query all available collections,
    or return a sequence of collection names to query a subset.
    """

    def route(self, query: Query) -> Optional[Sequence[str]]:
        """Determine which collections to query.

        Parameters
        ----------
        query:
            The parsed ChromaSQL query (AST).

        Returns
        -------
        Optional[Sequence[str]]
            Collection names to query, or ``None`` to query all collections.
        """
        ...


class AsyncCollectionProvider(Protocol):
    """Protocol for retrieving async ChromaDB collections.

    This abstraction allows the multi-collection executor to work with any
    async ChromaDB client (HTTP, Cloud, or custom implementations).
    """

    async def get_collection(self, name: str) -> Any:
        """Retrieve a collection by name.

        Parameters
        ----------
        name:
            Collection name.

        Returns
        -------
        Collection object with async ``query()`` and ``get()`` methods.
        """
        ...

    async def list_collection_names(self) -> Sequence[str]:
        """List all available collection names.

        Returns
        -------
        Sequence[str]
            All collection names available for querying.
        """
        ...


async def execute_multi_collection(
    query_str: str,
    router: CollectionRouter,
    collection_provider: AsyncCollectionProvider,
    *,
    embed_fn: Optional[EmbedFunction] = None,
    merge_strategy: str = "distance",
    n_results_per_collection: Optional[int] = None,
) -> ExecutionResult:
    """Execute a ChromaSQL query across multiple collections.

    This function orchestrates multi-collection query execution by:
    1. Parsing the query string into an AST
    2. Using the router to determine target collections
    3. Building a plan for each collection
    4. Executing plans in parallel using asyncio
    5. Merging results according to the merge strategy

    Parameters
    ----------
    query_str:
        ChromaSQL query string to execute.
    router:
        Collection router that decides which collections to query.
    collection_provider:
        Provider for retrieving async collections.
    embed_fn:
        Optional embedding function for TEXT queries.
    merge_strategy:
        Strategy for merging results from multiple collections.
        Currently only "distance" is supported (rank by similarity score).
    n_results_per_collection:
        Override the plan's n_results when querying each collection.
        Useful for gathering more candidates before final merge.

    Returns
    -------
    ExecutionResult
        Merged results with rows and raw response data.

    Raises
    ------
    ChromaSQLExecutionError
        If parsing, planning, or execution fails.
    """
    # Parse query
    try:
        query = parse(query_str)
    except Exception as exc:
        raise ChromaSQLExecutionError(f"Failed to parse query: {exc}") from exc

    # Route to collections
    target_collections = router.route(query)
    if target_collections is None:
        # Router says query all collections
        target_collections = await collection_provider.list_collection_names()
        logger.info(
            "Router returned None; querying all %d collections", len(target_collections)
        )
    else:
        target_collections = list(target_collections)
        logger.info(
            "Router selected %d collection(s): %s",
            len(target_collections),
            target_collections,
        )

    if not target_collections:
        raise ChromaSQLExecutionError("No collections available for query")

    # Build plan (validates query semantics)
    try:
        plan = build_plan(query)
    except Exception as exc:
        raise ChromaSQLExecutionError(f"Failed to build query plan: {exc}") from exc

    # Execute in parallel across all target collections
    tasks = [
        _execute_single_collection(
            plan=plan,
            collection_name=coll_name,
            collection_provider=collection_provider,
            embed_fn=embed_fn,
            n_results_override=n_results_per_collection,
        )
        for coll_name in target_collections
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and collect valid results
    valid_results: List[ExecutionResult] = []
    for i, result in enumerate(results):
        if isinstance(result, BaseException):
            logger.error(
                "Query to collection %s failed: %s",
                target_collections[i],
                result,
            )
        else:
            valid_results.append(result)

    if not valid_results:
        raise ChromaSQLExecutionError("All collection queries failed")

    logger.info(
        "Successfully executed query on %d/%d collection(s)",
        len(valid_results),
        len(target_collections),
    )

    # Merge results
    if merge_strategy == "distance":
        return _merge_by_distance(valid_results, plan)
    else:
        raise ChromaSQLExecutionError(f"Unsupported merge strategy: {merge_strategy}")


async def _execute_single_collection(
    plan: QueryPlan,
    collection_name: str,
    collection_provider: AsyncCollectionProvider,
    embed_fn: Optional[EmbedFunction],
    n_results_override: Optional[int],
) -> ExecutionResult:
    """Execute a plan against a single collection asynchronously.

    This is an async wrapper around the executor logic, adapted for
    async ChromaDB collections.

    Note: For multi-collection queries, we do NOT apply LIMIT/OFFSET here.
    Instead, we only normalize the raw response into rows and let the
    merge function handle ordering and pagination globally.
    """
    from .executor import _extract_vector_rows, _extract_filter_rows

    collection = await collection_provider.get_collection(collection_name)

    # Override n_results if requested (useful for gathering more candidates)
    if n_results_override is not None:
        from dataclasses import replace

        plan = replace(plan, n_results=n_results_override)

    # Execute the appropriate query type
    if plan.mode == "vector":
        raw = await _execute_vector_query_async(plan, collection, embed_fn)
    else:
        raw = await _execute_filter_query_async(plan, collection)

    # Extract rows without applying LIMIT/OFFSET (that's done in merge)
    # We only normalize the ChromaDB response into row dictionaries here
    if plan.mode == "vector":
        rows = _extract_vector_rows(plan, raw)
    else:
        rows = _extract_filter_rows(raw)

    return ExecutionResult(rows=rows, raw=raw)


async def _execute_vector_query_async(
    plan: QueryPlan,
    collection: Any,
    embed_fn: Optional[EmbedFunction],
) -> Dict[str, Any]:
    """Async version of vector query execution."""
    if plan.embedding_texts and embed_fn is None:
        raise ChromaSQLExecutionError("Embedding text requires an embed_fn")
    if plan.embedding_text and embed_fn is None:
        raise ChromaSQLExecutionError("Embedding text requires an embed_fn")

    query_embeddings: List[Sequence[float]] = []

    # Handle batch embeddings
    if plan.embedding_texts:
        for text, model in plan.embedding_texts:
            assert embed_fn is not None
            query_embeddings.append(list(embed_fn(text, model)))
    if plan.query_vector_batch:
        query_embeddings.extend([list(vector) for vector in plan.query_vector_batch])

    # Handle single embeddings
    if not query_embeddings:
        if plan.embedding_text:
            assert embed_fn is not None  # for type-checkers
            embedded = embed_fn(plan.embedding_text, plan.embedding_model)
            query_embeddings = [list(embedded)]
        elif plan.query_vector is not None:
            query_embeddings = [list(plan.query_vector)]
        else:
            raise ChromaSQLExecutionError(
                "Vector queries require embeddings or vectors"
            )
    elif plan.embedding_text and embed_fn is not None:
        query_embeddings.append(
            list(embed_fn(plan.embedding_text, plan.embedding_model))
        )
    elif plan.query_vector is not None:
        query_embeddings.append(list(plan.query_vector))

    include = list(plan.include) if plan.include else None

    try:
        result = await collection.query(
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


async def _execute_filter_query_async(
    plan: QueryPlan,
    collection: Any,
) -> Dict[str, Any]:
    """Async version of filter-only query execution."""
    include = list(plan.include) if plan.include else None

    limit = None if plan.order_by else plan.limit
    offset = None if plan.order_by else plan.offset

    try:
        result = await collection.get(
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


def _merge_by_distance(
    results: Sequence[ExecutionResult],
    plan: QueryPlan,
) -> ExecutionResult:
    """Merge multiple execution results by ranking on distance.

    For vector queries, this merges results across collections and re-ranks
    by distance. For filter queries, results are concatenated and then
    re-ordered according to the plan's ORDER BY clause.

    The final LIMIT/OFFSET is applied after merging, so each individual
    collection query may return more results than the final output.

    This function also applies score thresholds and projections globally.
    """
    if not results:
        return ExecutionResult(rows=[], raw={})

    # Collect all rows from all results
    all_rows: List[Dict[str, Any]] = []
    for result in results:
        all_rows.extend(result.rows)

    # Apply score threshold for vector queries
    if plan.mode == "vector" and plan.score_threshold is not None:
        all_rows = [
            row
            for row in all_rows
            if row["distance"] is None or row["distance"] <= plan.score_threshold
        ]

    # Apply ordering and pagination
    from .executor import _apply_order, _apply_limit_offset, _project_row

    ordered = _apply_order(all_rows, plan.order_by)
    sliced = _apply_limit_offset(ordered, plan.limit, plan.offset, plan.mode)

    # Apply projections to final results
    projected = [_project_row(plan, row) for row in sliced]

    # Build merged raw response (for debugging/inspection)
    merged_raw: Dict[str, Any] = {
        "merged_from_collections": len(results),
        "total_rows_before_merge": len(all_rows),
        "final_rows": len(projected),
    }

    return ExecutionResult(rows=projected, raw=merged_raw)


__all__ = [
    "CollectionRouter",
    "AsyncCollectionProvider",
    "execute_multi_collection",
]
