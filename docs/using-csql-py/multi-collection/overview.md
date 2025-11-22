# Multi-Collection

Large deployments often [shard data](reference/glossary/#sharded-deployment) across multiple ChromaDB collections. The
multi-collection module provides adapters and routing helpers that let you fan
out a single ChromaSQL query across those shards.

## Core Concepts

| Component | Description |
|-----------|-------------|
| `CollectionRouter` | Decides which collections should be queried based on the parsed AST. |
| `AsyncCollectionProvider` | Async interface for fetching collection handles. |
| `execute_multi_collection` | Orchestrates parse → plan → execute across collections and merges results. |

## Metadata-Based Routing

Use the built-in `MetadataFieldRouter` to route by discriminator values stored
in metadata:

```python
from chromasql.adapters import MetadataFieldRouter
from chromasql.multi_collection import execute_multi_collection
from idxr.query_lib.async_multi_collection_adapter import AsyncMultiCollectionAdapter

router = MetadataFieldRouter(
    query_config=config,
    field_path=("model",),
    fallback_to_all=True,
)
adapter = AsyncMultiCollectionAdapter(async_client)

result = await execute_multi_collection(
    query_str="SELECT id FROM demo WHERE metadata.model IN ('Table', 'Field');",
    router=router,
    collection_provider=adapter,
    embed_fn=my_embed_fn,
)
```

The router reads the parsed query, extracts `metadata.model` values, maps them
to collection names using the query config, and executes the plan in parallel.

## Custom Routers

Implement the `CollectionRouter` protocol for bespoke routing logic:

```python
from chromasql.multi_collection import CollectionRouter
from chromasql.analysis import extract_metadata_values

class TenantRouter(CollectionRouter):
    def __init__(self, mapping):
        self.mapping = mapping

    def route(self, query):
        tenant_ids = extract_metadata_values(query, field_path=("tenant_id",))
        if not tenant_ids:
            return None  # query all collections
        return [self.mapping[tenant] for tenant in tenant_ids if tenant in self.mapping]
```

## Merging Strategy

`execute_multi_collection` collects rows from all collections, applies score
thresholds, sorts by distance (or metadata order), respects LIMIT/OFFSET, and
projects the requested columns.

The merged `ExecutionResult` contains:

- `rows`: projected rows after global ordering/pagination.
- `raw`: summary payload with counts and metadata, useful for diagnostics.

## Error Handling

- Failed collections are logged and skipped; results from successful collections
  are still returned.
- When `fallback_to_all` is disabled and no discriminator is present, the router
  raises an error to avoid unexpected fan-out.

Refer to `tests/chromasql/test_multi_collection.py` and
`tests/chromasql/test_or_routing_integration.py` for exhaustive behavior.

<div class="grid cards" markdown>

- [:material-github: **Need Help?**](https://github.com/GetAdriAI/chromasql/issues/new?title=Docs%20Issue&labels=chromasql-py){ target="_blank" }<br/>
Open a GitHub issue with the steps to reproduce and we’ll help you debug it.
</div>