# ChromaSQL Query Clause Reference

ChromaSQL offers a compact set of clauses tailored to ChromaDB. This page is a
quick reference; for a narrative walkthrough see the [tutorial series](tutorial/setup.md).

## Query Skeleton

```sql
SELECT projection
FROM collection [AS alias]
[WHERE ...]
[WHERE_DOCUMENT ...]
[USING EMBEDDING (...)]
[SIMILARITY COSINE|L2|IP]
[TOPK n]
[ORDER BY ...]
[RERANK BY MMR(...)]
[LIMIT n]
[OFFSET n]
[WITH SCORE THRESHOLD x]
```

Clauses can appear in any order allowed by the grammar (see the [Grammar Specification](../reference/language-grammar.md) for details). `USING EMBEDDING` switches the query into vector mode;
omitting it produces a metadata-only `get`.

## Projection

- `SELECT *` returns `id`, `distance`, `document`, and `metadata`.
- `metadata.foo.bar` projects nested metadata.
- `SELECT metadata.price AS price_usd` applies aliases.

## Filtering

### Metadata (`WHERE`)

Supports equality, inequality, numeric comparisons, `IN`/`NOT IN`, `BETWEEN`,
`LIKE` (with `%value%` pattern), and `CONTAINS`.

```sql
WHERE metadata.category = 'outerwear'
  AND metadata.tags CONTAINS 'waterproof'
```

### Document (`WHERE_DOCUMENT`)

Applied after metadata filters. Supports `CONTAINS` and `%value%` `LIKE`
patterns.

```sql
WHERE_DOCUMENT LIKE '%gore-tex%'
```

## Embedding Clauses

```sql
USING EMBEDDING (TEXT 'query' [MODEL 'model'])
USING EMBEDDING (VECTOR [0.1, 0.2, 0.3])
USING EMBEDDING BATCH (
  TEXT 'first',
  VECTOR [0.4, 0.5, 0.6]
)
```

Batch queries return results for each item independently.

## Ordering & Pagination

- Vector queries default to `ORDER BY distance ASC`.
- Metadata fields and `id` are allowed in `ORDER BY`.
- Filter-only queries cannot sort by distance.

Pagination follows SQL semantics: `LIMIT` + `OFFSET` are applied after ordering.

## Score Thresholds

```sql
WITH SCORE THRESHOLD 0.25
```

Post-filter results by distance (lower is better). Useful when the top-k results
drift beyond an acceptable score.

## Rerank Hints

```sql
RERANK BY MMR(lambda = 0.4, candidates = 50)
```

## Explain

Prefix a query with `EXPLAIN` to inspect the plan:

```sql
EXPLAIN
SELECT id, distance
FROM products
USING EMBEDDING (TEXT 'chair')
TOPK 5;
```

The planner returns a `QueryPlan` with execution mode, includes, filters, and
other metadata, which you can serialize via `plan_to_dict`.
