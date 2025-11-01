# flake8: noqa

"""Lark grammar definition for the ChromaSQL language."""

CSQL_GRAMMAR = r"""
?start: query

?query: explain? select_stmt ";"? -> query

?explain: "EXPLAIN"i -> explain

select_stmt: "SELECT"i projection "FROM"i collection collection_alias? embedding_clause? where_clause? where_document_clause? similarity_clause? topk_clause? order_clause? rerank_clause? limit_clause? offset_clause? threshold_clause?

collection: IDENT

collection_alias: "AS"i IDENT -> collection_alias
projection_alias: "AS"i IDENT -> projection_alias

projection: "*" -> projection_all
          | projection_item ("," projection_item)* -> projection_list

projection_item: projection_field projection_alias? -> projection_item_with_alias

?projection_field: "id"i -> field_id
                 | "document"i -> field_document
                 | "embedding"i -> field_embedding
                 | "metadata"i -> field_metadata_root
                 | metadata_path -> projection_metadata_path
                 | "distance"i -> field_distance

embedding_clause: "USING"i "EMBEDDING"i (embedding_batch | "(" embedding_source ")") -> embedding_clause

embedding_batch: "BATCH"i "(" embedding_batch_item ("," embedding_batch_item)* ")" -> embedding_batch
embedding_batch_item: text_embedding -> embedding_batch_text
                    | vector_embedding -> embedding_batch_vector

embedding_source: text_embedding
                | vector_embedding

text_embedding: "TEXT"i string_literal model_override? -> embedding_text
model_override: "MODEL"i string_literal -> model_override

vector_embedding: "VECTOR"i "[" vector_list? "]" -> embedding_vector
vector_list: number_literal ("," number_literal)* -> vector_list

where_clause: "WHERE"i predicate -> where_clause
where_document_clause: "WHERE_DOCUMENT"i document_predicate -> where_document_clause
document_predicate: "CONTAINS"i value -> document_contains
                   | "LIKE"i string_literal -> document_like

similarity_clause: "SIMILARITY"i similarity_value -> similarity_clause
similarity_value: "COSINE"i -> similarity_cosine
                | "L2"i -> similarity_l2
                | "IP"i -> similarity_ip

topk_clause: "TOPK"i INT -> topk_clause

order_clause: "ORDER"i "BY"i order_item ("," order_item)* -> order_clause
order_item: order_field order_direction? -> order_item

?order_field: "distance"i -> field_distance
            | "id"i -> field_id
            | metadata_path -> metadata_order_field

order_direction: "ASC"i -> asc
               | "DESC"i -> desc

rerank_clause: "RERANK"i "BY"i rerank_strategy -> rerank_clause
rerank_strategy: "MMR"i rerank_params? -> rerank_mmr
rerank_params: "(" rerank_param ("," rerank_param)* ")" -> rerank_params
rerank_param: IDENT "=" number_literal -> rerank_param

limit_clause: "LIMIT"i INT -> limit_clause
offset_clause: "OFFSET"i INT -> offset_clause
threshold_clause: "WITH"i "SCORE"i "THRESHOLD"i number_literal -> threshold_clause

?predicate: or_expr
?or_expr: and_expr ("OR"i and_expr)* -> or_expr
?and_expr: atom ("AND"i atom)* -> and_expr

?atom: "(" predicate ")" -> grouped_predicate
     | comparison

?comparison: filter_field comp_op value -> comparison
           | filter_field "IN"i "(" value_list ")" -> in_list
           | filter_field "NOT"i "IN"i "(" value_list ")" -> not_in_list
           | filter_field "BETWEEN"i value "AND"i value -> between
           | filter_field "LIKE"i string_literal -> like
           | filter_field "CONTAINS"i value -> contains

COMP_OP: "=" | "!=" | "<" | "<=" | ">" | ">="
comp_op: COMP_OP

?filter_field: "id"i -> field_id
             | "document"i -> field_document
             | metadata_path -> metadata_filter_field

metadata_path: "metadata"i "." IDENT ("." IDENT)* -> metadata_path

value_list: value ("," value)* -> value_list

?value: string_literal -> string_value
      | number_literal -> number_value
      | "TRUE"i -> true_value
      | "FALSE"i -> false_value
      | "NULL"i -> null_value

string_literal: STRING
number_literal: SIGNED_NUMBER

IDENT: /[A-Za-z_][A-Za-z0-9_]*/
INT: SIGNED_INT
STRING: /"([^"\\]|\\.)*"|'([^'\\]|\\.)*'/

%import common.SIGNED_INT
%import common.SIGNED_NUMBER
%import common.WS
%ignore WS
"""
