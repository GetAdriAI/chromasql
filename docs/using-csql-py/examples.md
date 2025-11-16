# Examples

The best way to explore ChromaSQL is through practical snippets. These examples
assume the demo `products` collection described in the [ChromaSQL's tutorial series](../using-chromasql/tutorial/setup.md). Before trying
them out, make sure you have:

- A `ChromaDB` collection handle (sync or async) assigned to `my_collection`.
- An embedding function `my_embed_fn` if you plan to execute text-based vector
  queries.
- The `chromasql` package installed and imported as shown below.

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

Batch queries follow the same pattern; each entry is evaluated independently:

```python
query = parse("""
    SELECT id, distance
    FROM products
    USING EMBEDDING BATCH (
        TEXT 'lightweight waterproof jacket',
        VECTOR [0.05, 0.02, -0.17]
    )
    TOPK 5;
""")
```

Change the embedding model per request with `MODEL 'text-embedding-3-large'`
inside the `USING EMBEDDING` clause when you need provider-specific encoders.

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

Filter-only queries run `collection.get` under the hood. You can still project
`embedding` explicitly, but `distance` is unavailable and cannot appear in
`ORDER BY`.

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

Typical output includes the execution mode, projection, filters, and embedding
payload:

```python
plan_dict = plan_to_dict(plan)
print(plan_dict["execution_mode"])  # "vector"
print(plan_dict["includes"])        # ["id", "distance"]
print(plan_dict["vector"]["value"]) # your literal vector
```

## Multi-Collection Query via Adapter

Jump to the
[multi-collection examples](multi-collection/EXAMPLES.md) for full async
walkthroughs that pair routers, adapters, and concurrency patterns.

Additional real-world scenarios are covered in
`tests/chromasql`, which double as executable documentation.

<div class="grid cards" markdown>

- [:material-github: **Need Help?**](https://github.com/GetAdriAI/chromasql/issues/new?title=Docs%20Issue&labels=chromasql-py){ target="_blank" }<br/>
Open a GitHub issue with the steps to reproduce and we’ll help you debug it.
</div>