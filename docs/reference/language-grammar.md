# ChromaSQL Grammar Specification

ChromaSQL’s grammar is defined in `chromasql/grammar.py` using Lark. This page
summarizes the top-level productions; consult the source file for the authoritative
definition.

## Start Rule

```
?start: query

?query: explain? select_stmt ";"?
```

`EXPLAIN` is optional. Semicolons are allowed but not required.

## Projection

```
projection: "*" | projection_item ("," projection_item)*
projection_item: projection_field projection_alias?
projection_field:
    | "id"
    | "document"
    | "embedding"
    | "metadata"
    | metadata_path
    | "distance"
```

## From Clause

```
select_stmt: "SELECT" projection "FROM" collection collection_alias? ...
collection: IDENT
collection_alias: "AS" IDENT
```

## Embedding Clause

```
embedding_clause: "USING" "EMBEDDING" (embedding_batch | "(" embedding_source ")")
embedding_source:
    | text_embedding
    | vector_embedding
text_embedding: "TEXT" string_literal model_override?
vector_embedding: "VECTOR" "[" vector_list? "]"
embedding_batch: "BATCH" "(" embedding_batch_item ("," embedding_batch_item)* ")"
```

## Where Clauses

```
where_clause: "WHERE" predicate
where_document_clause: "WHERE_DOCUMENT" document_predicate_expr

predicate:
    or_expr

document_predicate_expr:
    document_or_expr
document_or_expr:
    document_and_expr ("OR" document_and_expr)*
document_and_expr:
    document_atom ("AND" document_atom)*
document_atom:
    | "(" document_predicate_expr ")"
    | "CONTAINS" value
    | "LIKE" string_literal
    | "document" "CONTAINS" value
    | "document" "LIKE" string_literal
```

Metadata predicates support:

- Comparisons (`=`, `!=`, `<`, `<=`, `>`, `>=`)
- `IN` / `NOT IN`
- `BETWEEN`

**Note:** `LIKE` and `CONTAINS` are only supported for document predicates (via `WHERE_DOCUMENT`), not for metadata filters. This is a ChromaDB limitation.

Both `WHERE` and `WHERE_DOCUMENT` support boolean expressions with `AND` / `OR` and parentheses for grouping.

## Similarity & TopK

```
similarity_clause: "SIMILARITY" ("COSINE" | "L2" | "IP")
topk_clause: "TOPK" INT
```

## Ordering & Pagination

```
order_clause: "ORDER" "BY" order_item ("," order_item)*
order_item: order_field order_direction?
order_field: "distance" | "id" | metadata_path

limit_clause: "LIMIT" INT
offset_clause: "OFFSET" INT
```

## Score Threshold & Rerank

```
threshold_clause: "WITH" "SCORE" "THRESHOLD" number_literal
rerank_clause: "RERANK" "BY" rerank_strategy
rerank_strategy: "MMR" rerank_params?
rerank_params: "(" rerank_param ("," rerank_param)* ")"
rerank_param: IDENT "=" number_literal
```

## Values & Literals

```
string_literal: STRING
number_literal: SIGNED_NUMBER
IDENT: /[A-Za-z_][A-Za-z0-9_]*/
```

The grammar intentionally omits mutations (INSERT/UPDATE/DELETE) and joins,
keeping the DSL squarely focused on read-only retrieval surfaces.

Refer to the tutorial and query language reference for examples that exercise
each production.
