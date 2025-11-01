# Examples

The best way to explore ChromaSQL is through practical snippets. These examples
assume the demo `products` collection described in the tutorial.

## Vector Similarity Search

```python
from chromasql import parse, build_plan, execute_plan

query = parse("""
    SELECT id, distance, document
    FROM products
    USING EMBEDDING (TEXT 'lightweight waterproof jacket')
    TOPK 3;
""")

plan = build_plan(query)
result = execute_plan(plan, collection=my_collection, embed_fn=my_embed_fn)

for row in result.rows:
    print(row["id"], row["distance"])
```

## Filter-Only Retrieval

```python
query = parse("""
    SELECT id, metadata
    FROM products
    WHERE metadata.category = 'accessories'
    ORDER BY metadata.price ASC
    LIMIT 5;
""")

plan = build_plan(query)
result = execute_plan(plan, collection=my_collection)
```

## Explain Output

```python
from chromasql import plan_to_dict

plan = build_plan(parse("""
    SELECT id, distance
    FROM products
    USING EMBEDDING (VECTOR [0.1, 0.2, 0.3])
    LIMIT 5;
"""))

print(plan_to_dict(plan))
```

## Multi-Collection Query via Adapter

```python
from chromasql.adapters import AsyncMultiCollectionAdapter, MetadataFieldRouter
from chromasql.multi_collection import execute_multi_collection

router = MetadataFieldRouter(query_config=config, field_path=("model",))
adapter = AsyncMultiCollectionAdapter(existing_client)

result = await execute_multi_collection(
    query_str="""
        SELECT id, distance
        FROM demo
        WHERE metadata.model IN ('Table', 'Field')
        USING EMBEDDING (TEXT 'sap auth')
        TOPK 8;
    """,
    router=router,
    collection_provider=adapter,
    embed_fn=my_embed_fn,
)

print(result.rows)
```

Additional real-world scenarios are covered in `EXAMPLES.md` within the source
tree, along with unit tests under `tests/chromasql` that double as executable
documentation.
