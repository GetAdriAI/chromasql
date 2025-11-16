# ChromaSQL

ChromaSQL is a SQL-inspired domain specific language that maps cleanly to
ChromaDB’s vector and metadata query surfaces. It bundles everything you need to
parse user-facing queries, validate semantics, inspect execution plans, and run
them against a Chroma collection.

## Architecture

ChromaSQL follows a compiler-style pipeline:

1. **Grammar** – `chromasql/grammar.py` defines the surface language using Lark.
2. **Parser** – `chromasql/parser.py` turns the parse tree into typed AST nodes.
3. **Planner** – `chromasql/planner.py` converts AST nodes into validated plans.
4. **Executor** – `chromasql/executor.py` runs those plans against ChromaDB.
5. **Explain & Analysis** – helpers for tooling, routing, and introspection.

The planner and executor operate on frozen dataclasses (`chromasql/ast.py` and
`chromasql/plan.py`), making the system easy to test and reason about.

## Key Features

- Rich projection, filtering, ordering, pagination, and rerank clauses.
- Embedding support for inline text, literal vectors, and batches.
- Optional explain output for debugging query plans.
- Multi-collection routing primitives and adapters for [sharded deployments](reference/glossary/#sharded-deployment).
- 100% unit test coverage to keep language changes predictable.

## Next Steps

Pick the path that best suits your workflow. Happy querying! 

<div class="grid cards" markdown>

- [:material-school: **Using ChromaSQL**](using-chromasql/tutorial/setup.md)<br/>
  Learn the language through the narrative tutorial and clause reference.

- [:material-console: **Using ChromaSQL Python Package**](using-csql-py/index.md)<br/>
  Install the Python SDK, execute plans, and integrate multi-collection routing.

- [:material-robot: **Using ChromaSQL with LLMs**](chromasql-authoring-prompt.md)<br/>
  Drop this authoring prompt into your assistants so they emit valid queries.

- [:material-puzzle: **Building Extensions**](building-extensions.md)<br/>
  Extend the grammar, planner, executor, and packaging workflow safely.

</div>