# Combine Batching, Reranking, and Filters

## Add Rerank Hints to a Query

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'graphite pencil')
RERANK BY MMR(lambda = 0.4, candidates = 50)
TOPK 10;
```
* MMR (Maximal Marginal Relevance) is a popular diversification strategy.
* The `RERANK` clause adds lambda and candidate values to the query plan metadata.


## Full Example with Batching, Filters, and Reranking

```sql
SELECT id, distance, metadata.brand
FROM products
USING EMBEDDING BATCH (
  TEXT 'trail running shoe',
  TEXT 'lightweight hiking shoe'
)
WHERE metadata.gender IN ('men', 'unisex')
WHERE_DOCUMENT LIKE '%gore-tex%'
SIMILARITY COSINE
TOPK 15
RERANK BY MMR(lambda = 0.3, candidates = 60)
ORDER BY distance ASC
LIMIT 10;
```
This combines all supported clauses:

* Batch execution with two textual queries.
* Metadata + document filters.
* Similarity change, top-k, rerank hint, and pagination.
* Projection includes a nested metadata field.

!!! note "Schema context"
    `metadata.gender` and `metadata.brand` are additional metadata keys in the
    sample `products` schema.  Adjust the names to match your own domain.

!!! warning "Clause order matters"
    Keep the clauses in the order shown above.  Placing `WHERE_DOCUMENT` before
    `WHERE`, or rerank hints before `TOPK`, will raise parser errors.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>