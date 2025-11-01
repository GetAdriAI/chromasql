# Contributing to ChromaSQL

Thanks for taking the time to improve the ChromaSQL package! This document
explains the concepts that underpin the codebase and sketches the workflow for
adding new language features or execution behaviour. Most contributors will be
writing Python, but the package is first and foremost a domain specific
language (DSL), so the background below focuses on how the pieces fit together.

## Architectural overview

The repository follows a classic compiler pipeline:

1. **Grammar (`chromasql/grammar.py`)**
   * Defines the SQL surface syntax using a Lark grammar.
   * Only contains syntax – there are no semantics baked into the grammar.

2. **Parser (`chromasql/parser.py`)**
   * Uses the grammar + Lark to produce an abstract syntax tree (AST).
   * `_ChromaSQLTransformer` converts the parsed tokens into dataclasses defined
     in `chromasql/ast.py`.
   * Validates *syntactic* concerns (e.g. disallowing malformed projections),
     but leaves semantic validation for the planner.

3. **AST (`chromasql/ast.py`)**
   * Lightweight dataclasses describing the logical query (projection, where
     clauses, rerank hints, embedding definitions, etc.).
   * Extend these first when you introduce a new piece of syntax.

4. **Planner (`chromasql/planner.py`)**
   * Performs semantic checks (e.g. `TOPK` only valid with embeddings, which
     fields can appear in `ORDER BY`, how to translate metadata predicates to
     Chroma’s JSON filters).
   * Produces a frozen `QueryPlan` (`chromasql/plan.py`) that mirrors ChromaDB’s
     `collection.query` / `collection.get` parameters.

5. **Executor (`chromasql/executor.py`)**
   * Turns the plan into actual ChromaDB calls, handles embedding batches and
     filter-only mode, and normalises results according to the projection /
     ordering /
     pagination requested.
   * Returned value is an `ExecutionResult` (rows + the raw response) so REPLs
     can easily display data while still giving access to the original payload.

6. **Explain (`chromasql/explain.py`)**
   * Serialises a `QueryPlan` into a JSON-friendly dictionary.  Used by CLI
     tooling and tests to inspect what will be sent to ChromaDB.

7. **Analysis (`chromasql/analysis.py`)**
   * Helper functions for extracting information from parsed queries.
   * Enables custom routing strategies based on query filters.
   * Used by multi-collection infrastructure for intelligent query dispatch.

8. **Multi-Collection Support (`chromasql/multi_collection.py` & `chromasql/adapters.py`)**
   * Generic abstractions for executing queries across multiple collections.
   * Protocol-based design allows custom routing strategies.
   * Adapters bridge ChromaSQL with existing async ChromaDB clients.

### Tests

The `tests/chromasql/` package hosts several test suites:

* `test_planner.py` — snapshot-style tests that exercise grammar → planner →
  plan conversions for representative queries.
* `test_executor.py` — uses in-memory Chroma collections to validate the
  runtime code paths.
* `test_internal_errors.py` — drills into edge cases (parser validation,
  planner semantics, executor failure modes).  If you change a helper, search
  this file first: chances are the guardrail already exists.
* `test_analysis.py` — validates metadata extraction for routing strategies.
* `test_multi_collection.py` — tests multi-collection query execution, routing,
  and result merging.

Every change should be covered with unit tests.  The CI directive is:

```bash
poetry run coverage run -m pytest tests/chromasql -q
poetry run coverage report -m
```

The current suite must stay at ~100% coverage to the extent possible.  When
adding new code, also add tests that exercise both the success path and the
expected error conditions.

## Workflow for extending the language

When implementing a new SQL feature (for example, a `WITH SCORE THRESHOLD`
clause):

1. **Update the AST (`chromasql/ast.py`).** Add/extend dataclasses so the rest of
   the pipeline has a typed hook.
2. **Update the grammar + parser.** Modify `chromasql/grammar.py`, add
   transformer hooks in `chromasql/parser.py`, and write parser tests if the
   transformation logic is non-trivial.
3. **Adjust the planner.** Translate the new AST fields into plan fields and
   enforce any semantic rules.  New helper functions usually live here as well.
4. **Update the executor (if necessary).** Extend `_run_vector_query` or
   `_run_filter_query` whenever the plan requires different Chroma parameters or
   post-processing.
5. **Expand the tests.** Add planner snapshot coverage, executor behaviour, and
   internal guardrail tests.  Strike a balance: high-level behaviour goes in
   `test_planner.py`, corner cases into `test_internal_errors.py`.
6. **Document the change.** Update this file, docstrings, and/or REPL help so
   downstream users understand the feature.

## Code style & conventions

* **Docstrings:** Follow the style used in the package—describe the intent and
  the reasoning behind non-trivial steps.  Because contributors might be new to
  DSLs, it’s helpful to say *why* a helper exists, not merely *what* it does.
* **Type hints:** Everything is type hinted.  Use `Optional[...]` instead of
  `| None` for compatibility with older tooling.
* **Immutability:** The AST and Plan dataclasses are frozen on purpose to make
  bugs easier to chase.  If you need to “modify” a plan, create a new instance.
* **Error translation:** Raise `ChromaSQLParseError`, `ChromaSQLPlanningError`,
  or `ChromaSQLExecutionError` so callers see consistent exception types.
* **Tests first:** Prefer writing / updating tests before changing production
  code.  It is easier to reason about grammar/planner changes when a failing
  test tells you exactly which behaviour regressed.

## Building multi-collection routing strategies

ChromaSQL provides generic abstractions for executing queries across multiple
collections (partitions). This pattern is common when dealing with large-scale
data sharded across collections by metadata discriminators like model type,
tenant ID, region, or time period.

### Architecture

The multi-collection system uses two core protocols:

1. **`CollectionRouter`** — decides which collections to query based on the
   parsed AST. Return `None` to query all collections, or a sequence of
   collection names for targeted routing.

2. **`AsyncCollectionProvider`** — abstracts collection retrieval from any
   async ChromaDB client. This lets you integrate with HTTP, Cloud, or custom
   clients.

### Example: Metadata-based routing

The most common pattern is routing based on metadata filters in the `WHERE`
clause. ChromaSQL provides a generic `MetadataFieldRouter` adapter:

```python
from pathlib import Path
from chromasql.adapters import AsyncMultiCollectionAdapter, MetadataFieldRouter
from chromasql.multi_collection import execute_multi_collection
from indexer.vectorize_lib.query_client import AsyncMultiCollectionQueryClient
from indexer.vectorize_lib.query_config import load_query_config

# Load your query config (maps discriminator values to collections)
config = load_query_config(Path("query_config.json"))

# Initialize your existing multi-collection client
client = AsyncMultiCollectionQueryClient(
    config_path=Path("query_config.json"),
    client_type="cloud",
    cloud_api_key=api_key,
)
await client.connect()

# Wrap with ChromaSQL adapters
adapter = AsyncMultiCollectionAdapter(client)
router = MetadataFieldRouter(
    query_config=config,
    field_path=("model",),  # Your discriminator field
    fallback_to_all=True,   # Query all collections if not filtered
)

# Execute ChromaSQL query with intelligent routing
result = await execute_multi_collection(
    query_str="""
        SELECT id, distance, document
        FROM demo
        WHERE metadata.model IN ('Table', 'Field')
        USING EMBEDDING (TEXT 'SAP table structures')
        TOPK 10;
    """,
    router=router,
    collection_provider=adapter,
    embed_fn=my_embed_function,
)

await client.close()
```

The router extracts `{'Table', 'Field'}` from the WHERE clause, maps them to
the relevant collections via your `query_config.json`, and fans out the query
in parallel. Results are merged and ranked by distance.

### Custom routers

For specialized logic, implement the `CollectionRouter` protocol:

```python
from chromasql.multi_collection import CollectionRouter
from chromasql.analysis import extract_metadata_values

class TenantBasedRouter(CollectionRouter):
    def __init__(self, tenant_mapping: dict):
        self.tenant_mapping = tenant_mapping

    def route(self, query) -> Optional[Sequence[str]]:
        tenant_ids = extract_metadata_values(query, field_path=("tenant_id",))
        if tenant_ids:
            collections = [
                self.tenant_mapping[tid]
                for tid in tenant_ids
                if tid in self.tenant_mapping
            ]
            return collections if collections else None
        return None  # Query all collections
```

### Testing multi-collection code

When adding custom routers or adapters:

1. Write unit tests for the router's `route()` logic using parsed queries
2. Mock `AsyncCollectionProvider` for integration tests
3. Test fallback behavior when discriminator is absent
4. Verify partial failure handling (some collections fail)
5. Ensure result merging respects LIMIT/OFFSET/ORDER BY

See `tests/chromasql/test_multi_collection.py` for examples.

## Local development tips

* Run `poetry install` once to create the virtualenv.
* Use `poetry run pytest -q` during tight feedback loops, then enable coverage
  before pushing.
* Most helper functions are pure; feel free to unit test them directly instead
  of going through full parser/plan/executor stacks for every scenario.

Happy hacking!  If you run into questions or need a design review for a DSL
extension, open an issue or reach out in the discussion channel so we can align
before code goes in.
