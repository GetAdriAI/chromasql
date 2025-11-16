# OR Predicate Routing: Edge Cases and Test Coverage

This document catalogs all edge cases for OR predicate routing in ChromaSQL's multi-collection system, ensuring comprehensive test coverage and documenting expected behavior.

## Overview

ChromaSQL uses **union routing** for OR predicates: when a query contains `OR` predicates with discriminator field filters, the system extracts values from **all branches** and queries the **union** of collections.

This prevents **under-routing** (missing results because a collection wasn't queried).

## Core Principle

```
WHERE metadata.model = 'A' OR metadata.model = 'B'
→ Extracts {'A', 'B'}
→ Routes to: union(collections_for_A, collections_for_B)
```

The router determines **which collections to query**, but each collection receives the **full WHERE clause**. Results are filtered by the complete predicate at query time.

---

## Edge Cases Tested

### 1. ✅ Simple OR with Same Field

**Query:**
```sql
WHERE metadata.model = 'Table' OR metadata.model = 'Field'
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field'}`
- Routes to: All collections containing 'Table' OR 'Field'

**Test:** `test_extract_metadata_values_with_or_single_field`

---

### 2. ✅ OR with Different Fields (Triggers Fallback)

**Query:**
```sql
WHERE metadata.model = 'Table' OR metadata.has_sem = FALSE
```

**Expected Behavior:**
- Extracts: `None` (fallback to all collections)
- Routes to: **ALL collections**
- Why: The second OR branch (`has_sem = FALSE`) could match records in ANY collection, so we must query all to avoid under-routing

**Test:** `test_extract_metadata_values_with_or_different_fields`

---

### 3. ✅ OR with IN Clause

**Query:**
```sql
WHERE metadata.model IN ('Table', 'Field') OR metadata.model = 'View'
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field', 'View'}`
- Routes to: Union of all three models' collections

**Test:** `test_extract_metadata_values_with_or_in_clause`

---

### 4. ✅ Nested OR Predicates

**Query:**
```sql
WHERE (metadata.model = 'Table' OR metadata.model = 'Field')
      OR metadata.model = 'View'
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field', 'View'}` (flattens nested OR)
- Routes to: Union of all three models' collections

**Test:** `test_extract_metadata_values_with_nested_or`

---

### 5. ✅ OR with Nested AND (User's Specific Case)

**Query:**
```sql
WHERE metadata.model = 'Table'
      OR (metadata.model = 'Field' AND metadata.fieldname = 'lang')
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field'}` (both models from OR branches)
- Routes to: Collections for 'Table' + Collections for 'Field'
- The `fieldname = 'lang'` filter is applied at query time in each collection

**Test:** `test_extract_or_with_nested_and`

**Why This Works:**
- The AND branch `(metadata.model = 'Field' AND metadata.fieldname = 'lang')` contains `model = 'Field'`
- Extraction traverses the entire predicate tree, collecting all discriminator values
- Collections for 'Field' receive the full WHERE clause and filter on `fieldname = 'lang'`

---

### 6. ✅ Multiple OR Branches with AND

**Query:**
```sql
WHERE (metadata.model = 'Table' AND metadata.system = 'S4')
      OR (metadata.model = 'Field' AND metadata.fieldname = 'lang')
      OR (metadata.model = 'View' AND metadata.active = TRUE)
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field', 'View'}`
- Routes to: Union of all three models' collections
- Each collection gets the full WHERE clause and applies its branch's filters

**Test:** `test_extract_complex_or_with_multiple_nested_ands`

---

### 7. ✅ Deeply Nested OR/AND Combinations

**Query:**
```sql
WHERE (
    (metadata.model = 'Table' AND metadata.system = 'ECC')
    OR (
        metadata.model = 'Field'
        AND (metadata.type = 'CHAR' OR metadata.type = 'NUMC')
    )
) OR metadata.model = 'View'
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field', 'View'}`
- Routes to: Union of all three models' collections
- Handles arbitrary nesting depth

**Test:** `test_extract_deeply_nested_or_and`

---

### 8. ✅ OR with No Discriminator Field

**Query:**
```sql
WHERE metadata.status = 'active' OR metadata.has_sem = TRUE
```

**Expected Behavior:**
- Extracts: `None` (no discriminator values found)
- Routes to: **All collections** (fallback mode)

**Test:** `test_extract_metadata_values_or_with_no_target_field`

---

### 9. ✅ OR with Only Some Branches Having Discriminator (Triggers Fallback)

**Query:**
```sql
WHERE (metadata.status = 'active' AND metadata.year > 2020)
      OR metadata.model = 'Table'
      OR (metadata.has_sem = TRUE AND metadata.env = 'prod')
```

**Expected Behavior:**
- Extracts: `None` (fallback to all collections)
- Routes to: **ALL collections**
- Why: Branches 1 and 3 lack the discriminator field and could match records in any collection

**Test:** `test_extract_or_with_only_one_branch_having_target_field`

---

### 10. ✅ OR Combining IN and AND Clauses

**Query:**
```sql
WHERE metadata.model IN ('Table', 'View')
      OR (metadata.model = 'Field' AND metadata.required = TRUE)
      OR (metadata.model = 'Function' AND metadata.status = 'active')
```

**Expected Behavior:**
- Extracts: `{'Table', 'View', 'Field', 'Function'}`
- Routes to: Union of all four models' collections

**Test:** `test_extract_or_with_in_and_nested_and`

---

### 11. ✅ Complex AND/OR Within AND Context

**Query:**
```sql
WHERE metadata.environment = 'prod'
      AND (metadata.model = 'Table' OR metadata.model = 'Field' OR metadata.model = 'View')
      AND metadata.year > 2020
```

**Expected Behavior:**
- Extracts: `{'Table', 'Field', 'View'}` (OR within AND context)
- Routes to: Union of all three models' collections
- Each collection applies the full predicate including `environment` and `year` filters

**Test:** `test_extract_with_complex_or_and_and`

---

### 12. ✅ OR with Unknown Model Value

**Query:**
```sql
WHERE metadata.model = 'Table' OR metadata.model = 'UnknownModel'
```

**Expected Behavior:**
- Extracts: `{'Table', 'UnknownModel'}`
- Routes to: Collections for 'Table' (logs warning about 'UnknownModel')
- Gracefully handles unknown discriminator values

**Test:** `test_router_or_with_unknown_model_partial_routing`

---

### 13. ✅ Deduplication of Overlapping Collections

**Query:**
```sql
WHERE metadata.model = 'Table' OR metadata.model = 'Field'
```

**Setup:**
- Table → [coll_1, shared_coll]
- Field → [coll_2, shared_coll]

**Expected Behavior:**
- Routes to: `[coll_1, coll_2, shared_coll]` (deduplicated)
- Ensures `shared_coll` is only queried once

**Test:** `test_router_deduplicates_collections_in_union`

---

## Anti-Patterns and Why They're Avoided

### ❌ Partial Routing for Mixed OR (PREVENTS UNDER-ROUTING)

Some systems might try to route to only the discriminator values found:
```sql
WHERE metadata.model = 'Table' OR metadata.has_sem = FALSE
→ Routes ONLY to 'Table' collections
→ PROBLEM: Misses records in other collections where has_sem = FALSE!
```

**Why ChromaSQL Uses Fallback Instead:**
When any OR branch lacks the discriminator field, we **fallback to all collections** to ensure no under-routing. This is conservative but correct.

### ✅ Correct Behavior: Conservative Fallback

ChromaSQL's approach:
```sql
WHERE metadata.model = 'Table' OR metadata.has_sem = FALSE
→ Routes to ALL collections (fallback)
→ RESULT: No under-routing, all matching records found
```

If you want efficient routing with mixed predicates, use AND:
```sql
WHERE metadata.model = 'Table' AND metadata.has_sem = FALSE
→ Routes to 'Table' collections only (efficient)
→ RESULT: Only Table records with has_sem = FALSE
```

---

## Implementation Details

### How Union Extraction Works

The `extract_metadata_values()` function in [chromasql/analysis.py](analysis.py) uses recursive traversal:

1. **BooleanPredicate (OR)**: Recursively collect values from all children
2. **BooleanPredicate (AND)**: Recursively collect values from all children (may be nested in OR)
3. **ComparisonPredicate (=)**: Extract single value if it matches discriminator field
4. **InPredicate**: Extract all values if it matches discriminator field
5. **Other fields**: Ignored (don't contribute to routing)

### Router Logic

The `MetadataFieldRouter` in [chromasql/adapters.py](adapters.py):

1. Calls `extract_metadata_values()` to get discriminator values
2. Maps each value to its collections via `query_config`
3. Takes **union** of all collection lists
4. Deduplicates the final list
5. Returns `None` if no values found (triggers fallback behavior)

---

## Test Coverage Summary

| Category | Tests | Status |
|----------|-------|--------|
| Basic OR extraction | 3 | ✅ Passing |
| Nested OR/AND combinations | 6 | ✅ Passing |
| Fallback scenarios | 2 | ✅ Passing |
| Router integration | 11 | ✅ Passing |
| **Total** | **22** | **✅ All Passing** |

---

## Usage Guidelines

### ✅ DO: Use OR for Union Queries

```sql
-- Good: Efficiently queries only Table and Field collections
SELECT * FROM sap_data
WHERE metadata.model = 'Table' OR metadata.model = 'Field'
```

### ✅ DO: Combine OR with AND for Complex Filters

```sql
-- Good: Routes to Table + Field, applies additional filters
SELECT * FROM sap_data
WHERE (metadata.model = 'Table' AND metadata.system = 'S4')
      OR (metadata.model = 'Field' AND metadata.required = TRUE)
```

### ✅ DO: Use IN When Appropriate

```sql
-- Good: Equivalent to OR, may be more readable
SELECT * FROM sap_data
WHERE metadata.model IN ('Table', 'Field', 'View')
```

### ⚠️ CAUTION: OR Without Discriminator

```sql
-- Caution: Queries ALL collections (fallback mode)
SELECT * FROM sap_data
WHERE metadata.status = 'active' OR metadata.has_sem = TRUE
```

### ⚠️ CAUTION: Mixed OR (Triggers Fallback)

```sql
-- Caution: Queries ALL collections (conservative fallback)
SELECT * FROM sap_data
WHERE metadata.model = 'Table' OR metadata.has_sem = FALSE
-- Result: Queries all 37 collections to avoid under-routing
```

**Why fallback?** The second OR branch could match records in any collection.

**To optimize, use AND instead:**
```sql
-- Better: Routes only to Table collections (efficient)
SELECT * FROM sap_data
WHERE metadata.model = 'Table' AND metadata.has_sem = FALSE
-- Result: Only queries Table collections
```

---

## Performance Implications

### Best Case: Single Discriminator Value
```sql
WHERE metadata.model = 'Table'
```
- Routes to: ~2-3 collections (out of 37)
- Fastest performance

### Good Case: Union of Few Values
```sql
WHERE metadata.model IN ('Table', 'Field')
```
- Routes to: ~4-6 collections (out of 37)
- Still very efficient

### Acceptable Case: Union of Many Values
```sql
WHERE metadata.model = 'A' OR metadata.model = 'B' OR ... (10 models)
```
- Routes to: ~20 collections (out of 37)
- Better than querying all 37

### Worst Case: Fallback to All
```sql
WHERE metadata.status = 'active'
```
- Routes to: All 37 collections
- Use AND with discriminator to improve:
  ```sql
  WHERE metadata.model = 'Table' AND metadata.status = 'active'
  ```

---

## Future Enhancements

Potential improvements (not currently implemented):

1. **Cost-Based Routing**: If union size exceeds threshold, fallback to all collections
2. **Statistics-Driven Routing**: Use collection size to decide routing strategy
3. **Partition Pruning**: Route based on partition keys in addition to discriminator
4. **Query Rewriting**: Optimize complex OR/AND combinations before routing

---

## References

- [chromasql/analysis.py](analysis.py) - Metadata value extraction
- [chromasql/adapters.py](adapters.py) - MetadataFieldRouter implementation
- [chromasql/EXAMPLES.md](EXAMPLES.md) - Multi-collection usage examples
- [tests/chromasql/test_or_routing.py](../tests/chromasql/test_or_routing.py) - Unit tests
- [tests/chromasql/test_or_routing_integration.py](../tests/chromasql/test_or_routing_integration.py) - Integration tests

---

**Last Updated:** 2025-01-01
**Test Coverage:** 22/22 tests passing
**Total Test Count:** 151 (chromasql + query_lib)

<div class="grid cards" markdown>

- [:material-github: **Need Help?**](https://github.com/GetAdriAI/chromasql/issues/new?title=Docs%20Issue&labels=chromasql-py){ target="_blank" }<br/>
Open a GitHub issue with the steps to reproduce and we’ll help you debug it.
</div>