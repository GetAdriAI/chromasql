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
- Multi-collection routing primitives and adapters for sharded deployments.
- 100% unit test coverage to keep language changes predictable.

Use the navigation on the left to dive into the tutorial, query language
reference, multi-collection support, and advanced extension points.
