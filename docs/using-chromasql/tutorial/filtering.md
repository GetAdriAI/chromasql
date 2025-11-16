# Filter ChromaSQL Results

## Filter on Metadata with `WHERE`

```sql
SELECT id, metadata
FROM products
WHERE metadata.category = 'outerwear'
  AND metadata.tags CONTAINS 'waterproof'
  AND metadata.price BETWEEN 50 AND 150;
```
!!! note "Schema context"
    `metadata.tags` is a list-valued key on our demo schema; `metadata.price`
    is a numeric key.

### Supported operators inside `WHERE`

| Operator | Meaning                               |
|----------|----------------------------------------|
| `=`/`!=` | equality / inequality                  |
| `<`, `<=`, `>`, `>=` | numeric comparisons        |
| `IN`, `NOT IN` | membership tests on lists        |
| `BETWEEN` | inclusive numeric range               |
| `LIKE` | `%pattern%` wildcard (only leading/trailing `%` supported)
| `CONTAINS` | substring or list membership (depending on metadata type) |

!!! warning "Limit"
    `LIKE` only supports the `%text%` shape for now (no `_` wildcard or
    mid-string `%`).

## Filter the Document Body with `WHERE_DOCUMENT`

```sql
SELECT id, document
FROM products
WHERE metadata.category = 'outerwear'
WHERE_DOCUMENT CONTAINS 'gore-tex';
```

* `WHERE_DOCUMENT` is evaluated after metadata filters.
* `CONTAINS` and `%LIKE%` are supported just like metadata filters.

!!! note "Schema context"
    Document predicates operate on the `document` column, which stores the
    natural language product description in our example collection.

!!! warning "Watch out"
    `WHERE` and `WHERE_DOCUMENT` are independent.  Specify both if you need both
    metadata and document filtering.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>