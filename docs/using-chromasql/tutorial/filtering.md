# Filter ChromaSQL Results

## Filter on Metadata with `WHERE`

```sql
SELECT id, metadata
FROM products
WHERE metadata.category = 'outerwear'
  AND metadata.price BETWEEN 50 AND 150;
```
!!! note "Schema context"
    `metadata.price` is a numeric key on our demo schema.

!!! warning "CONTAINS not supported on metadata"
    The example previously showed `metadata.tags CONTAINS 'waterproof'` but this is NOT supported due to ChromaDB limitations. Use `WHERE_DOCUMENT CONTAINS 'waterproof'` to search document text instead, or use `metadata.tags IN ('waterproof', 'breathable')` for exact list matching.

### Supported operators inside `WHERE`

| Operator | Meaning                               |
|----------|----------------------------------------|
| `=`/`!=` | equality / inequality                  |
| `<`, `<=`, `>`, `>=` | numeric comparisons        |
| `IN`, `NOT IN` | membership tests on lists        |
| `BETWEEN` | inclusive numeric range               |

!!! warning "LIKE and CONTAINS not supported on metadata"
    `LIKE` and `CONTAINS` operators only work with `WHERE_DOCUMENT` for filtering document text, not with `WHERE` for metadata fields. This is a ChromaDB limitation. Use exact matches (`=`, `IN`) or numeric comparisons for metadata filtering.

!!! note "Numeric type coercion with BETWEEN"
    ChromaDB may coerce types when comparing integer metadata with float boundaries. For example, `BETWEEN 1500.5 AND 3500.5` on integer metadata might behave unexpectedly. For reliable results, use integer boundaries (`BETWEEN 1500 AND 3500`) when your metadata values are integers.

!!! warning "Cannot OR different filter types"
    ChromaDB limitation: You can only combine **metadata and document filters with AND**, not OR.

    **✅ Valid:**
    ```sql
    WHERE metadata.category = 'finance' AND document CONTAINS 'payment'
    WHERE (metadata.status = 'urgent' OR metadata.amount > 5000) AND document CONTAINS 'invoice'
    ```

    **❌ Invalid:**
    ```sql
    WHERE metadata.category = 'finance' OR document CONTAINS 'payment'
    ```

    Within each filter type (all metadata or all document), you can use OR freely.

## Filter the Document Body with `WHERE_DOCUMENT`

```sql
SELECT id, document
FROM products
WHERE metadata.category = 'outerwear'
WHERE_DOCUMENT CONTAINS 'gore-tex';
```

* `WHERE_DOCUMENT` is evaluated after metadata filters.
* Text operators (`CONTAINS`, `NOT CONTAINS`, `LIKE`, `NOT LIKE`, `REGEX`, `NOT REGEX`) **only work with WHERE_DOCUMENT**, not with WHERE (metadata filters).
* **Boolean expressions are supported**: Use `AND`, `OR`, and parentheses to create complex document filters.

!!! danger "Common Mistake: Don't Repeat WHERE_DOCUMENT"
    **❌ INCORRECT** - This will cause a parse error:
    ```sql
    WHERE_DOCUMENT CONTAINS 'vendor' OR WHERE_DOCUMENT CONTAINS 'payee'
    ```

    **✅ CORRECT** - Use `WHERE_DOCUMENT` once, then combine with boolean operators:
    ```sql
    WHERE_DOCUMENT CONTAINS 'vendor' OR CONTAINS 'payee'
    ```

    Think of `WHERE_DOCUMENT` as introducing a boolean expression, not as part of each condition.

### Examples with Boolean Expressions

```sql
-- Match documents containing either 'waterproof' OR 'breathable'
SELECT id FROM products
WHERE_DOCUMENT CONTAINS 'waterproof' OR CONTAINS 'breathable';

-- Match documents containing both 'gore-tex' AND 'jacket'
SELECT id FROM products
WHERE_DOCUMENT CONTAINS 'gore-tex' AND LIKE '%jacket%';

-- Complex nested conditions with parentheses
SELECT id FROM products
WHERE_DOCUMENT (CONTAINS 'waterproof' OR CONTAINS 'windproof')
              AND LIKE '%outdoor%';

-- Real-world example: Find bank-related documents
SELECT document, metadata.object_name FROM transactions
WHERE_DOCUMENT CONTAINS 'BofA' OR CONTAINS 'Bank of America' OR LIKE '%Wells Fargo%';

-- Exclude documents with specific text
SELECT id FROM products
WHERE_DOCUMENT NOT CONTAINS 'deprecated';

-- Exclude multi-word phrases
SELECT id FROM products
WHERE_DOCUMENT NOT LIKE '%do not use%';

-- Match email patterns with REGEX
SELECT id FROM contacts
WHERE_DOCUMENT REGEX '[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}';

-- Case-insensitive matching with REGEX
SELECT id FROM products
WHERE_DOCUMENT REGEX '(?i)python';  -- Matches PYTHON, python, Python, etc.

-- Exclude documents matching patterns
SELECT id FROM documents
WHERE_DOCUMENT NOT REGEX '\d{3}-\d{2}-\d{4}';  -- Exclude SSN patterns
```

!!! warning "Case-sensitive matching"
    Text operators (`CONTAINS`, `LIKE`, `REGEX`) are **case-sensitive** by default. For example:

    - `WHERE_DOCUMENT CONTAINS 'BofA'` will NOT match "bofa" or "BOFA"
    - `WHERE_DOCUMENT LIKE '%urgent%'` will NOT match "Urgent" or "URGENT"

    **Workarounds:**

    - **Use OR for multiple cases**: `WHERE_DOCUMENT CONTAINS 'BofA' OR CONTAINS 'bofa' OR CONTAINS 'BOFA'`
    - **Use REGEX with (?i) flag**: `WHERE_DOCUMENT REGEX '(?i)bofa'` (matches BofA, bofa, BOFA, etc.)

!!! note "Pattern syntax"
    - `LIKE` only supports the `%text%` shape (exactly two `%` wildcards at start and end, no `_` wildcard or mid-string `%`). Example: `WHERE_DOCUMENT LIKE '%gore-tex%'`
    - For complex patterns, use `REGEX`: `WHERE_DOCUMENT REGEX '.*gore.*tex.*'`

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