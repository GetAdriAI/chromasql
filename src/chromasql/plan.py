"""Planning data structures for ChromaSQL queries.

The planner stores its output in these frozen dataclasses before handing the
plan to the executor.  They intentionally mirror the parameters accepted by
``collection.query`` and ``collection.get``.  Keeping them centralised makes it
easy to inspect / serialise plans (e.g. ``EXPLAIN`` output).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ._ast_nodes import OrderItem


@dataclass(frozen=True)
class PlanProjectionItem:
    """Projection column and optional alias in the execution plan."""

    field: str
    alias: Optional[str] = None


@dataclass(frozen=True)
class QueryPlan:
    """Immutable representation of the work required to answer a query."""

    explain: bool
    mode: str  # "vector" or "filter"
    collection: str
    projection: Tuple[PlanProjectionItem, ...]
    select_all: bool
    include: Tuple[str, ...]
    embedding_text: Optional[str]
    embedding_model: Optional[str]
    query_vector: Optional[Tuple[float, ...]]
    embedding_texts: Optional[Tuple[Tuple[str, Optional[str]], ...]]
    query_vector_batch: Optional[Tuple[Tuple[float, ...], ...]]
    where: Optional[Dict[str, object]]
    where_document: Optional[Dict[str, object]]
    ids: Optional[Tuple[str, ...]]
    n_results: int
    similarity: str
    order_by: Tuple[OrderItem, ...]
    limit: Optional[int]
    offset: Optional[int]
    score_threshold: Optional[float]
    rerank: Optional[Dict[str, float]]
