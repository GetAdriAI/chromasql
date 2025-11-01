# Getting Started

This guide walks through installing ChromaSQL, executing your first query, and
understanding the core workflow.

## Installation

```bash
pip install chromasql
```

If you are working from the monorepo, you can build and install a wheel with:

```bash
poetry run python -m build --wheel
pip install dist/chromasql-*.whl
```

## Basic Usage

```python
from chromasql import parse, build_plan, execute_plan

query = parse("""
    SELECT id, document
    FROM products
    USING EMBEDDING (TEXT 'mesh office chair')
    TOPK 5;
""")

plan = build_plan(query)
result = execute_plan(plan, collection=my_chroma_collection, embed_fn=my_embed_fn)

for row in result.rows:
    print(row["id"], row["document"])
```

### Required Components

* **Collection** – a ChromaDB collection handle (sync or async).
* **embed_fn** – callable that turns text into embeddings when `TEXT` clauses are
  used. Literal vectors do not need this.

## Explaining Plans

Use `plan_to_dict` to inspect how a query will execute without hitting the
database:

```python
from chromasql import plan_to_dict
plan_dict = plan_to_dict(plan)
print(plan_dict)
```

The explain output mirrors the arguments passed to `collection.query` or
`collection.get`.

## Running Tests

ChromaSQL ships with a comprehensive test suite. Run it from the repository
root:

```bash
poetry run pytest tests/chromasql -q
```

Add tests whenever you extend the language or touch planner/executor logic.
