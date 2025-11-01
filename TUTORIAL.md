# ChromaSQL Tutorial

Welcome! This guide shows you **every clause** the ChromaSQL DSL currently
supports, why you might use it, and a few common pitfalls to avoid.  Follow it
sequentially – the later sections build on the earlier ones.

## Demo Collection Schema

To keep the examples concrete we will query an imaginary `products` collection.
ChromaSQL operates on collections, so think of this as one table whose rows were
previously ingested into ChromaDB.

**Core columns (ChromaSQL defaults)**
- `id`: Stable identifier for each row. Present in every collection.
- `document`: The natural-language payload that was embedded (plain text).
- `embedding`: The stored vector. Only returned when explicitly requested.
- `metadata`: JSON object with user-defined attributes (keys vary by dataset).

These four columns exist regardless of the domain you model—you will see them in
every example and in real queries, even if you never project or filter by all of
them.

**Sample metadata keys for this tutorial (domain-specific)**
- `metadata.category` (string): Product category (e.g. `outerwear`).
- `metadata.tags` (list of strings): Lightweight tags, such as `["waterproof"]`.
- `metadata.price` (number): Price in USD.
- `metadata.gender` (string): Target audience (`men`, `women`, `unisex`).
- `metadata.brand` (string): Brand name.
- `metadata.model` (string): Internal classifier used in routing examples later on.

> **Use-case specific metadata.** When an example introduces an additional key
> (for example `metadata.system` in the reranking section or
> `metadata.fieldname` in routing examples) it represents a hypothetical field
> that exists in this sample schema for illustration. Adjust the field names to
> match the metadata that lives in your own collections.

> **Heads-up:** ChromaSQL is read-only.  It helps you query ChromaDB collections
> but does not create, mutate, or delete data.  For ingest / management you still
> use the Python SDK or REST API.

---

## 1. Getting started: the tiniest query

```sql
SELECT *
FROM products;
```

* Returns the default set of columns (`id`, `distance`, `document`, `metadata`).
* Works on a **single collection**.  There is no `JOIN` support – run multiple
  queries and merge results in Python if you need cross-collection logic.

> **Myth:** `SELECT *` fetches everything, *including embeddings*.  In reality
> embeddings are excluded – include the `embedding` column explicitly if you
> need vectors.


## 2. Choosing your projection

```sql
SELECT id, document, metadata.category
FROM products;
```

* `metadata.category` drills into nested metadata.
* Use `AS` to rename columns:
  ```sql
  SELECT metadata.price AS price_usd FROM products;
  ```

> **Schema context:** `metadata.category` and `metadata.price` are metadata keys
> on the sample `products` collection described above.

> **Tip:** `metadata.foo` pulls from your metadata JSON, not the document.
> Fields stored directly on the document (via `document`) are separate.


## 3. Filtering with `WHERE`

```sql
SELECT id, metadata
FROM products
WHERE metadata.category = 'outerwear'
  AND metadata.tags CONTAINS 'waterproof'
  AND metadata.price BETWEEN 50 AND 150;
```

Supported operators inside `WHERE`:
| Operator | Meaning                               |
|----------|----------------------------------------|
| `=`/`!=` | equality / inequality                  |
| `<`, `<=`, `>`, `>=` | numeric comparisons        |
| `IN`, `NOT IN` | membership tests on lists        |
| `BETWEEN` | inclusive numeric range               |
| `LIKE` | `%pattern%` wildcard (only leading/trailing `%` supported)
| `CONTAINS` | substring or list membership (depending on metadata type) |

> **Schema context:** `metadata.tags` is a list-valued key on our demo schema;
> `metadata.price` is a numeric key.

> **Limit:** `LIKE` only supports the `%text%` shape for now (no `_` wildcard or
> mid-string `%`).


## 4. Filtering the document body: `WHERE_DOCUMENT`

```sql
SELECT id, document
FROM products
WHERE metadata.category = 'outerwear'
WHERE_DOCUMENT CONTAINS 'gore-tex';
```

* `WHERE_DOCUMENT` is evaluated after metadata filters.
* `CONTAINS` and `%LIKE%` are supported just like metadata filters.

> **Schema context:** Document predicates operate on the `document` column,
> which stores the natural language product description in our example
> collection.

> **Watch out:** `WHERE` and `WHERE_DOCUMENT` are independent.  Specify both if
> you need both metadata and document filtering.


## 5. Running vector similarity (`USING EMBEDDING`)

### 5.1 Provide text to embed on the fly
```sql
SELECT id, distance, document
FROM products
USING EMBEDDING (TEXT 'lightweight waterproof jacket')
TOPK 5;
```
* `TOPK` defaults to 10.  Only valid with vector queries.
* Provide a custom model per query with `MODEL 'text-embedding-3-large'`.

### 5.2 Provide the vector yourself
```sql
SELECT id, distance
FROM products
USING EMBEDDING (VECTOR [0.12, -0.33, ...])
TOPK 10;
```
* Handy in tests or when you already cached embeddings on the client side.

### 5.3 Batched queries
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
* If you supply `TEXT` entries, make sure the executor is passed an embed
  function – otherwise you will get `ChromaSQLExecutionError`.

> **Reminder:** `TOPK` applies **per batch item**, not across the entire batch.


## 6. Similarity metric

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'soft shell jacket')
SIMILARITY L2;
```
* `COSINE` is the default; accepted values: `COSINE`, `L2`, `IP`.
* The clause is a **hint**.  Ensure your Chroma collection was created with the
  corresponding metric for consistent results.


## 7. Ordering and pagination

```sql
SELECT id, distance, metadata.price
FROM products
USING EMBEDDING (TEXT 'down jacket')
ORDER BY distance ASC, metadata.price DESC
LIMIT 20 OFFSET 10;
```
* Vector queries automatically default to `ORDER BY distance ASC`.
* Filter-only queries cannot order by `distance`.

> **Clarification:** `LIMIT/OFFSET` act after retrieval.  The executor asks for
> enough rows to respect `TOPK` then trims locally.


## 8. Score thresholds

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'rain poncho')
WITH SCORE THRESHOLD 0.15;
```
* Discards results whose distance is greater than the threshold after the
  Chroma response is received.


## 9. Reranking hints

```sql
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'graphite pencil')
RERANK BY MMR(lambda = 0.4, candidates = 50)
TOPK 10;
```
* MMR (Maximal Marginal Relevance) is a popular diversification strategy.  The
  plan records the lambda / candidate values so your executor can plug in an
  external reranker after the initial fetch.
* Parameters are purely a hint – ChromaSQL does not run the reranker for you.

> **Watch out:** Rerank clauses only annotate the plan.  You still need to run
> the reranker after fetching results.


## 10. Batch + Rerank + Filters (full example)

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

> **Schema context:** `metadata.gender` and `metadata.brand` are additional
> metadata keys in our imagined `products` schema. Adjust these names to match
> your own domain.


## 11. Filter-only retrieval (`get`)

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

> **Schema context:** This example filters by `metadata.category` and orders by
> `metadata.price`, both standard keys in the demo schema.

> **Tip:** Filter-only queries never touch the embedding store, so they’re
> usually cheaper.  If you only need metadata lookups, prefer this mode.


## 12. EXPLAIN

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


## 13. What ChromaSQL does not do (yet)

* **Joins / multi-collection SQL.**  Execute separate queries if you need to
  merge results from multiple collections.
* **Aggregations / GROUP BY.**  Fetch the rows and aggregate in Python.
* **Streaming or async execution.**  The executor currently collects results
  eagerly.  Wrap it yourself if you need incremental delivery.
* **Custom arithmetic in ORDER BY.**  Only `distance`, `id`, and metadata paths
  are supported today.  Blend scores (e.g. `0.8 * SIM_SCORE + …`) in your own
  post-processing if you need that behaviour.

---

## 14. Troubleshooting & misconceptions recap

| Symptom | Likely cause |
|---------|--------------|
| `ChromaSQLParseError: Unexpected token` | Typo in your query, or clause order incorrect (e.g. `WHERE_DOCUMENT` before `WHERE`). |
| `ChromaSQLPlanningError: TOPK can only be used with EMBEDDING queries` | You forgot the `USING EMBEDDING` clause. |
| Distances missing in results | You ran a filter-only query or dropped `distance` from the projection. |
| Batch query returns unexpected duplicates | Remember that `TOPK` applies per batch item; dedupe in post-processing if needed. |
| Rerank hint seemingly ignored | The executor returns the hint in the plan; you still need to implement the MMR reranker. |

If you bump into behaviour that feels surprising or want to propose a language
extension, check out `CONTRIBUTING.md` for instructions on how to get involved.

Happy querying!
