# ChromaSQL

ChromaSQL is a lightweight SQL-flavoured DSL that makes it easy to express
queries against ChromaDB collections. It wraps ChromaDB’s `collection.query`
and `collection.get` APIs with a familiar syntax and provides utilities for
parsing, semantic planning, execution, and multi-collection fan-out.

## Features

- Lark-based parser that converts SQL-like strings into typed AST nodes.
- Planner that translates the AST into validated `QueryPlan` objects ready for
  ChromaDB execution.
- Thin executor that orchestrates vector and filter queries, applies ordering
  and pagination, and normalises result rows.
- Optional multi-collection helpers and adapters for routing queries across
  sharded datasets.
- Analysis helpers for extracting metadata-driven routing hints.

For a clause-by-clause walkthrough, see `TUTORIAL.md`. Additional usage notes
and examples live in `EXAMPLES.md`, while edge cases for OR-based routing are
documented in `OR_ROUTING_EDGE_CASES.md`.

## Installation

```bash
pip install chromasql
```

## Quickstart

```python
from chromasql import parse, build_plan, execute_plan

query = parse(
    """
    SELECT id, document
    FROM products
    USING EMBEDDING (TEXT 'mesh office chair')
    TOPK 5;
    """
)

plan = build_plan(query)
result = execute_plan(plan, collection=my_chroma_collection, embed_fn=my_embed_fn)

for row in result.rows:
    print(row["id"], row["document"])
```

## Development

We publish `chromasql` from this monorepo. Use the helper scripts in
`scripts/` to build wheels, upload to PyPI, or synchronise the public mirror.
See `CONTRIBUTING.md` for architectural background and testing guidelines.
