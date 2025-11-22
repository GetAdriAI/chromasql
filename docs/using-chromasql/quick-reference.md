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

Supports equality, inequality, numeric comparisons, `IN`/`NOT IN`, and `BETWEEN`.

**Note:** `LIKE` and `CONTAINS` are NOT supported on metadata (ChromaDB limitation).
Use `WHERE_DOCUMENT` for text/pattern matching.

**Note:** `BETWEEN` with mixed int/float types may behave unexpectedly due to ChromaDB type coercion. Use matching types (integer boundaries for integer metadata).

**Important:** Different filter types (metadata vs. document) can **only** be combined with `AND`, not `OR` (ChromaDB limitation). Within each type, use `OR` freely.

```sql
-- Valid: metadata AND document
WHERE metadata.category = 'outerwear'
  AND metadata.price BETWEEN 50 AND 150
  AND document CONTAINS 'waterproof'

-- Invalid: metadata OR document ❌
-- WHERE metadata.category = 'outerwear' OR document CONTAINS 'sale'
```

### Document (`WHERE_DOCUMENT`)

Applied after metadata filters. Supports text search operators: `CONTAINS`, `NOT CONTAINS`, `LIKE`, `NOT LIKE`, `REGEX`, `NOT REGEX`.

**These operators ONLY work with WHERE_DOCUMENT**, not with WHERE (metadata).

**Boolean expressions supported**: Use `AND`, `OR`, and parentheses for complex filters.

**Important:** Use `WHERE_DOCUMENT` **once** at the beginning, then combine predicates with boolean operators. Don't repeat `WHERE_DOCUMENT` for each condition.

```sql
-- Simple filter
WHERE_DOCUMENT LIKE '%gore-tex%'

-- OR: Match multiple terms (don't repeat WHERE_DOCUMENT!)
WHERE_DOCUMENT CONTAINS 'waterproof' OR CONTAINS 'breathable'

-- AND: Match all terms
WHERE_DOCUMENT CONTAINS 'outdoor' AND LIKE '%jacket%'

-- Complex: Nested with parentheses
WHERE_DOCUMENT (CONTAINS 'outdoor' AND LIKE '%jacket%') OR CONTAINS 'windproof'

-- Real-world: Multiple organization names
WHERE_DOCUMENT CONTAINS 'BofA' OR CONTAINS 'Bank of America' OR LIKE '%Wells Fargo%'

-- Exclude patterns
WHERE_DOCUMENT NOT LIKE '%test%'
WHERE_DOCUMENT NOT CONTAINS 'deprecated'

-- Regex patterns
WHERE_DOCUMENT REGEX '[a-z]+@[a-z]+\.com'  -- Email pattern
WHERE_DOCUMENT REGEX '(?i)python'  -- Case-insensitive matching
WHERE_DOCUMENT NOT REGEX '\d{3}-\d{2}-\d{4}'  -- Exclude SSN patterns
```

**Note:** Text operators are **case-sensitive**. `WHERE_DOCUMENT CONTAINS 'urgent'` will NOT match "Urgent" or "URGENT". To handle multiple cases, use OR: `CONTAINS 'urgent' OR CONTAINS 'Urgent'`, or use REGEX with `(?i)` flag: `REGEX '(?i)urgent'`.

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
