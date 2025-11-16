"""Abstract syntax tree (AST) definitions for the ChromaSQL language.

The parser is intentionally conservative: once a query string is parsed into
these lightweight, mostly-immutable dataclasses, every downstream stage
operates on *structured* data.  This separation keeps the rest of the system
agnostic to the quirks of SQL parsing and makes it cheap to write unit tests
that exercise planner/executor behaviour.

The dataclasses below intentionally mirror the logical clauses a user can write
in CSQL (projection, filtering, rerank hints, …).  Whenever the grammar grows,
start by adding / extending the relevant AST node before updating the parser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

__all__ = [
    "Field",
    "ProjectionItem",
    "Projection",
    "EmbeddingText",
    "EmbeddingVector",
    "EmbeddingBatch",
    "Embedding",
    "OrderItem",
    "Rerank",
    "Predicate",
    "ComparisonPredicate",
    "InPredicate",
    "BetweenPredicate",
    "LikePredicate",
    "ContainsPredicate",
    "BooleanPredicate",
    "Query",
]


@dataclass(frozen=True)
class Field:
    """Represents a selectable or filterable field."""

    root: str
    path: Tuple[str, ...] = ()

    @property
    def is_metadata(self) -> bool:
        return self.root == "metadata"

    def dotted(self) -> str:
        if not self.path:
            return self.root
        return ".".join((self.root, *self.path))


@dataclass(frozen=True)
class ProjectionItem:
    field: Field
    alias: Optional[str] = None


@dataclass(frozen=True)
class Projection:
    select_all: bool
    items: Tuple[ProjectionItem, ...] = ()

    def requested_fields(self) -> Tuple[Field, ...]:
        if self.select_all:
            return tuple(
                Field(name) for name in ("id", "distance", "document", "metadata")
            )
        return tuple(item.field for item in self.items)


@dataclass(frozen=True)
class EmbeddingText:
    text: str
    model: Optional[str] = None


@dataclass(frozen=True)
class EmbeddingVector:
    values: Tuple[float, ...]


EmbeddingValue = Union[EmbeddingText, EmbeddingVector]


@dataclass(frozen=True)
class EmbeddingBatch:
    items: Tuple[EmbeddingValue, ...]


Embedding = Union[EmbeddingValue, EmbeddingBatch]


@dataclass(frozen=True)
class OrderItem:
    field: Field
    direction: str  # "ASC" or "DESC"


@dataclass(frozen=True)
class Rerank:
    strategy: str
    params: Dict[str, float]


class Predicate:  # pragma: no cover - marker base class
    """Base class for all predicate expressions."""


@dataclass(frozen=True)
class ComparisonPredicate(Predicate):
    field: Field
    operator: str  # one of =, !=, <, <=, >, >=
    value: Union[str, int, float, bool, None]


@dataclass(frozen=True)
class InPredicate(Predicate):
    field: Field
    values: Tuple[Union[str, int, float, bool, None], ...]
    negated: bool = False


@dataclass(frozen=True)
class BetweenPredicate(Predicate):
    field: Field
    lower: Union[str, int, float]
    upper: Union[str, int, float]


@dataclass(frozen=True)
class LikePredicate(Predicate):
    field: Field
    pattern: str


@dataclass(frozen=True)
class ContainsPredicate(Predicate):
    field: Field
    value: Union[str, int, float, bool]


@dataclass(frozen=True)
class BooleanPredicate(Predicate):
    operator: str  # "AND" or "OR"
    predicates: Tuple[Predicate, ...]


@dataclass(frozen=True)
class Query:
    explain: bool
    collection: str
    alias: Optional[str]
    projection: Projection
    embedding: Optional[Embedding]
    where: Optional[Predicate]
    where_document: Optional[Predicate]
    similarity: str
    topk: Optional[int]
    order_by: Tuple[OrderItem, ...]
    limit: Optional[int]
    offset: Optional[int]
    score_threshold: Optional[float]
    rerank: Optional[Rerank]
