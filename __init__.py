"""Public entry points for the ChromaSQL package."""

from __future__ import annotations

from .errors import (
    ChromaSQLError,
    ChromaSQLExecutionError,
    ChromaSQLParseError,
    ChromaSQLPlanningError,
)
from .parser import parse
from .planner import build_plan
from .plan import QueryPlan, PlanProjectionItem
from .executor import execute_plan, ExecutionResult
from .explain import plan_to_dict
from .analysis import extract_metadata_values

# Multi-collection support (optional, requires async ChromaDB client)
try:
    from .multi_collection import (  # noqa: F401
        CollectionRouter,
        AsyncCollectionProvider,
        execute_multi_collection,
    )
    from .adapters import (  # noqa: F401
        AsyncMultiCollectionAdapter,
        MetadataFieldRouter,
        SimpleAsyncClientAdapter,
    )

    _MULTI_COLLECTION_AVAILABLE = True
except ImportError:  # pragma: no cover
    _MULTI_COLLECTION_AVAILABLE = False

__all__ = [
    # Core API
    "parse",
    "build_plan",
    "plan_to_dict",
    "execute_plan",
    "ExecutionResult",
    "QueryPlan",
    "PlanProjectionItem",
    # Errors
    "ChromaSQLError",
    "ChromaSQLParseError",
    "ChromaSQLPlanningError",
    "ChromaSQLExecutionError",
    # Analysis helpers
    "extract_metadata_values",
]

# Add multi-collection exports if available
if _MULTI_COLLECTION_AVAILABLE:
    __all__.extend(
        [
            "CollectionRouter",
            "AsyncCollectionProvider",
            "execute_multi_collection",
            "AsyncMultiCollectionAdapter",
            "MetadataFieldRouter",
            "SimpleAsyncClientAdapter",
        ]
    )
