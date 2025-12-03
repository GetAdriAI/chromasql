"""Utilities for explaining ChromaSQL plans.

``plan_to_dict`` is used by REPL tooling to show developers what is going to
hit ChromaDB *before* the network call happens.  We keep the representation
lossless so that it doubles as a debugging aid for the planner / executor.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .plan import PlanProjectionItem, QueryPlan


def plan_to_dict(plan: QueryPlan) -> Dict[str, Any]:
    """Convert a :class:`QueryPlan` into a JSON-serializable dictionary."""
    embedding: Dict[str, Any] | None = None
    if plan.embedding_texts or plan.query_vector_batch:
        items: List[Dict[str, Any]] = []
        if plan.embedding_texts:
            for text, model in plan.embedding_texts:
                items.append({"type": "text", "text": text, "model": model})
        if plan.query_vector_batch:
            for vector in plan.query_vector_batch:
                items.append({"type": "vector", "dimensions": len(vector)})
        embedding = {"type": "batch", "items": items}
    elif plan.embedding_text is not None:
        embedding = {
            "type": "text",
            "text": plan.embedding_text,
            "model": plan.embedding_model,
        }
    elif plan.query_vector is not None:
        embedding = {"type": "vector", "dimensions": len(plan.query_vector)}

    payload: Dict[str, Any] = {
        "collection": plan.collection,
        "mode": plan.mode,
        "explain": plan.explain,
        "projection": [
            _projection_item_to_dict(item) for item in _projection_columns(plan)
        ],
        "include": list(plan.include),
        "embedding": embedding,
        "where": plan.where,
        "where_document": plan.where_document,
        "ids": list(plan.ids) if plan.ids else None,
        "similarity": plan.similarity,
        "n_results": plan.n_results,
        "order_by": [
            {"field": item.field.dotted(), "direction": item.direction}
            for item in plan.order_by
        ],
        "limit": plan.limit,
        "offset": plan.offset,
        "score_threshold": plan.score_threshold,
    }
    if plan.rerank is not None:
        payload["rerank"] = {"strategy": "MMR", **plan.rerank}
    return payload


def _projection_columns(plan: QueryPlan) -> List[PlanProjectionItem]:
    if plan.select_all:
        return [
            PlanProjectionItem("id"),
            PlanProjectionItem("distance"),
            PlanProjectionItem("document"),
            PlanProjectionItem("metadata"),
        ]
    return list(plan.projection)


def _projection_item_to_dict(item: PlanProjectionItem) -> Dict[str, Any]:
    data: Dict[str, Any] = {"field": item.field}
    if item.alias:
        data["alias"] = item.alias
    return data
