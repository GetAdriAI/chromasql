# Run Filter-Only Retrieval using `get`

```sql
SELECT id, metadata
FROM products
WHERE metadata.category = 'accessories'
ORDER BY metadata.price ASC
LIMIT 50;
```
* Without a `USING EMBEDDING` clause the planner automatically switches to the
  filter-only path (`collection.get`).
* `distance` cannot be selected or ordered in this mode.

!!! note "Schema context"
    This example filters by `metadata.category` and orders by `metadata.price`,
    both standard keys in the demo schema.

!!! tip "Cheaper metadata lookups"
    Filter-only queries never touch the embedding store, so they’re usually
    cheaper.  If you only need metadata lookups, prefer this mode.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>