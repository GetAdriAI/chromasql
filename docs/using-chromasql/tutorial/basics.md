# Build Your First Query

## Start with the Smallest Query

```sql
SELECT *
FROM products;
```

* Returns the default set of columns (`id`, `distance`, `document`, `metadata`).
* Works on a **single collection**.  There is no `JOIN` support – run multiple
  queries and merge results in Python if you need cross-collection logic.

!!! warning "Myth"
    `SELECT *` fetches everything, *including embeddings*.  In reality embeddings are excluded. 
    
    If you need vectors, you must explicitly include the `embedding` column in the query.

## Choose Your Projection

```sql
SELECT id, document, metadata.category
FROM products;
```

* `metadata.category` drills into nested metadata.

!!! note "Schema context"
    `metadata.category` and `metadata.price` are metadata keys on the sample `products` collection described above.

* Use `AS` to rename columns:
  
```sql
SELECT metadata.price AS price_usd FROM products;
```

!!! tip
    `metadata.foo` pulls from your metadata JSON, not the document.

    Fields stored directly on the document (via `document`) are separate.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>