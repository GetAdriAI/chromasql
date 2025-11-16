# Run Vector Searches

## Embed Text on the Fly
```sql
SELECT id, distance, document
FROM products
USING EMBEDDING (TEXT 'lightweight waterproof jacket')
TOPK 5;
```
* `TOPK` defaults to 10.  Only valid with vector queries.
* Provide a custom model per query with `MODEL 'text-embedding-3-large'`.

!!! tip "Swap embedding models per query"
    Override the default embedding model with the `MODEL` clause when you need
    provider-specific encoders for an individual request.

## Use a Precomputed Vector

```sql
SELECT id, distance
FROM products
USING EMBEDDING (VECTOR [0.12, -0.33, ...])
TOPK 10;
```
* Handy in tests or when you already cached embeddings on the client side.

!!! note "Great for benchmarks"
    Providing your own vector keeps queries deterministic, which is useful when
    you want reproducible tests or to compare executor behaviour.

## Batch Multiple Queries

```sql
SELECT id, distance
FROM products
USING EMBEDDING BATCH (
  TEXT 'lightweight waterproof jacket',
  VECTOR [0.05, 0.02, ...]
)
TOPK 5;
```
* Each item in the batch is queried individually and post-processed with the
  same projection / filters.

!!! warning "Embed function required"
    If you supply `TEXT` entries, pass an embed function to the executor.  If you skip
    it, you will see `ChromaSQLExecutionError`.

!!! note "TOPK applies per batch item"
    `TOPK` limits results per batch entry.  Deduplicate in post-processing if
    you need a global top-k.

## Choose a Similarity Metric

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'soft shell jacket')
SIMILARITY L2;
```
* `COSINE` is the default; accepted values: `COSINE`, `L2`, `IP`.
* The clause is a **hint**.  Ensure your Chroma collection was created with the
  corresponding metric for consistent results.

!!! warning "Match your collection metric"
    Chroma stores vectors with a fixed distance metric.  If you hint `L2` but
    the collection was created with cosine, your results will be inconsistent.

## Order and Paginate Results

```sql
SELECT id, distance, metadata.price
FROM products
USING EMBEDDING (TEXT 'down jacket')
ORDER BY distance ASC, metadata.price DESC
LIMIT 20 OFFSET 10;
```
* Vector queries automatically default to `ORDER BY distance ASC`.
* Filter-only queries cannot order by `distance`.

!!! note
    `LIMIT` and `OFFSET` act after retrieval.  The executor asks for enough rows
    to respect `TOPK` and then trims locally.


## Apply Score Thresholds

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'rain poncho')
WITH SCORE THRESHOLD 0.15;
```
* Discards results whose distance is greater than the threshold after the
  ChromaSQL response is received.

!!! tip "Tune thresholds against real data"
    Distance values vary with the embedding model and metric.  Calibrate the
    threshold using real query logs so you do not accidentally hide relevant
    matches.

<div class="grid cards" markdown>

- [:material-lifebuoy: **Need Help?**](troubleshooting.md)<br/>
  Check the troubleshooting guide for fixes to the most common ChromaSQL hiccups.

</div>