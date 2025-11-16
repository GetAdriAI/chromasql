# Inspect Plans with `EXPLAIN`

```sql
EXPLAIN
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'mesh office chair')
TOPK 5;
```
* Returns the plan dictionary (collection name, include fields, where payload,
  rerank hints, etc.) without hitting ChromaDB.
* Useful for debugging or to understand how clauses are mapped before execution.

!!! tip "Dry-run complex queries"
    Use `EXPLAIN` while iterating on new clauses so you can inspect the planned
    payloads without burning ChromaDB capacity.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>