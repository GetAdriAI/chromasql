"""Parser for the ChromaSQL language built on top of Lark.

The parser converts a SQL-like query string into the strongly typed AST defined
in :mod:`chromasql.ast`.  The grammar lives in :mod:`chromasql.grammar` and is
purposefully small so that we can reason about every construct end-to-end:
parsing → planning → execution.  Whenever you tweak the grammar remember to
1) update the AST (if needed), 2) regenerate the Transformer hooks here, and
3) add regression tests in ``tests/chromasql``.

A noteworthy design decision: the parser *never* performs semantic validation
(e.g. checking ORDER BY fields against query mode).  Those rules belong in the
planner.  The parser is only responsible for syntactic / structural hygiene.
"""

from __future__ import annotations

import ast
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union, cast

from lark import Lark, Token, Transformer
from lark.exceptions import VisitError

from ._ast_nodes import (
    BooleanPredicate,
    ComparisonPredicate,
    ContainsPredicate,
    Embedding,
    EmbeddingBatch,
    EmbeddingText,
    EmbeddingValue,
    EmbeddingVector,
    Field,
    InPredicate,
    BetweenPredicate,
    LikePredicate,
    RegexPredicate,
    OrderItem,
    Predicate,
    Projection,
    ProjectionItem,
    Query,
    Rerank,
)
from .errors import ChromaSQLParseError
from .grammar import CSQL_GRAMMAR


def _coerce_number(text: str) -> Union[int, float]:
    if any(sep in text for sep in (".", "e", "E")):
        return float(text)
    return int(text)


def _strip_quotes(token: Token) -> str:
    try:
        return ast.literal_eval(token.value)
    except (SyntaxError, ValueError) as exc:  # pragma: no cover - defensive
        raise ChromaSQLParseError(f"Invalid string literal: {token.value}") from exc


def _combine_boolean(operator: str, predicates: Iterable[Predicate]) -> Predicate:
    items: List[Predicate] = []
    for predicate in predicates:
        if isinstance(predicate, BooleanPredicate) and predicate.operator == operator:
            items.extend(predicate.predicates)
        else:
            items.append(predicate)
    if not items:
        raise ChromaSQLParseError(f"Empty {operator} expression")
    if len(items) == 1:
        return items[0]
    return BooleanPredicate(operator=operator, predicates=tuple(items))


class _ChromaSQLTransformer(Transformer):
    """Convert the raw Lark parse tree into the AST defined in :mod:`chromasql.ast`.

    Lark gives us a concrete syntax tree (every token is preserved).  By wiring
    each grammar production to a small method we can translate the tree into the
    exact dataclasses used by downstream components.  Keeping this logic in one
    place makes it straightforward to extend the language while preserving the
    planner / executor contract.
    """

    def query(self, items: List[Any]) -> Query:
        explain = False
        statement: Optional[Dict[str, Any]] = None

        for item in items:
            if isinstance(item, tuple) and item[0] == "explain":
                explain = True
            elif isinstance(item, dict):
                statement = item

        if statement is None:
            raise ChromaSQLParseError("Missing SELECT statement")

        return Query(
            explain=explain,
            collection=statement["collection"],
            alias=statement.get("collection_alias"),
            projection=statement["projection"],
            embedding=statement.get("embedding"),
            where=statement.get("where"),
            where_document=statement.get("where_document"),
            similarity=statement.get("similarity", "COSINE"),
            topk=statement.get("topk"),
            order_by=statement.get("order_by", ()),
            limit=statement.get("limit"),
            offset=statement.get("offset"),
            score_threshold=statement.get("score_threshold"),
            rerank=statement.get("rerank"),
        )

    def explain(self, _: List[Any]) -> Tuple[str, bool]:
        return ("explain", True)

    def select_stmt(self, items: List[Any]) -> Dict[str, Any]:
        if not items:
            raise ChromaSQLParseError("Expected SELECT statement")

        projection = items[0]
        if not isinstance(projection, Projection):
            raise ChromaSQLParseError("Malformed projection in SELECT")

        output: Dict[str, Any] = {"projection": projection}

        for item in items[1:]:
            if not isinstance(item, tuple):
                raise ChromaSQLParseError("Unexpected element in SELECT statement")
            key, value = item
            output[key] = value

        # Apply defaults
        output.setdefault("similarity", "COSINE")
        output.setdefault("order_by", ())
        output.setdefault("where_document", None)
        output.setdefault("rerank", None)

        # Ensure mandatory clauses exist
        if "collection" not in output:
            raise ChromaSQLParseError("Missing collection name in FROM clause")

        return output

    def collection(self, items: List[Token]) -> Tuple[str, str]:
        [token] = items
        return ("collection", str(token))

    def collection_alias(self, items: List[Token]) -> Tuple[str, str]:
        [token] = items
        return ("collection_alias", str(token))

    def projection_alias(self, items: List[Token]) -> str:
        [token] = items
        return str(token)

    def projection_all(self, _: List[Any]) -> Projection:
        return Projection(select_all=True)

    def projection_list(self, items: List[ProjectionItem]) -> Projection:
        return Projection(select_all=False, items=tuple(items))

    def projection_item_with_alias(
        self, items: List[Union[Field, str]]
    ) -> ProjectionItem:
        if not items:
            raise ChromaSQLParseError("Invalid projection item")
        field = items[0]
        if not isinstance(field, Field):
            raise ChromaSQLParseError("Projection item is missing a field")
        alias: Optional[str] = None
        if len(items) > 1:
            alias_val = items[1]
            if isinstance(alias_val, str):
                alias = alias_val
        return ProjectionItem(field=field, alias=alias)

    # Field helpers -----------------------------------------------------

    def field_id(self, _: List[Any]) -> Field:
        return Field("id")

    def field_document(self, _: List[Any]) -> Field:
        return Field("document")

    def field_embedding(self, _: List[Any]) -> Field:
        return Field("embedding")

    def field_metadata_root(self, _: List[Any]) -> Field:
        return Field("metadata")

    def field_distance(self, _: List[Any]) -> Field:
        return Field("distance")

    def metadata_path(self, items: List[Token]) -> Field:
        path = tuple(str(token) for token in items)
        if not path:
            raise ChromaSQLParseError("Metadata path must include a field name")
        return Field("metadata", path)

    def projection_metadata_path(self, items: List[Field]) -> Field:
        [field] = items
        return field

    def metadata_order_field(self, items: List[Field]) -> Tuple[str, Field]:
        [field] = items
        return ("order_field", field)

    def metadata_filter_field(self, items: List[Field]) -> Field:
        [field] = items
        return field

    # Embedding clauses -------------------------------------------------

    def embedding_clause(self, items: List[Embedding]) -> Tuple[str, Embedding]:
        [embedding] = items
        return ("embedding", embedding)

    def embedding_batch(self, items: List[Embedding]) -> EmbeddingBatch:
        # The grammar ensures items are EmbeddingValue, not EmbeddingBatch
        return EmbeddingBatch(items=tuple(cast(List[EmbeddingValue], items)))

    def embedding_batch_text(self, items: List[Embedding]) -> Embedding:
        [embedding] = items
        return embedding

    def embedding_batch_vector(self, items: List[Embedding]) -> Embedding:
        [embedding] = items
        return embedding

    def embedding_source(self, items: List[Embedding]) -> Embedding:
        [embedding] = items
        return embedding

    def embedding_text(self, items: List[Union[str, Tuple[str, str]]]) -> EmbeddingText:
        if not items:
            raise ChromaSQLParseError("TEXT clause requires a literal")
        text = items[0]
        if not isinstance(text, str):
            raise ChromaSQLParseError("Invalid TEXT literal")

        model: Optional[str] = None
        if len(items) > 1:
            # Grammar ensures items[1] is a tuple from model_override
            model_tuple = cast(Tuple[str, str], items[1])
            _, model = model_tuple

        return EmbeddingText(text=text, model=model)

    def model_override(self, items: List[str]) -> Tuple[str, str]:
        [model] = items
        return ("model", model)

    def embedding_vector(
        self, items: List[Optional[Tuple[float, ...]]]
    ) -> EmbeddingVector:
        vector = items[0] if items else ()
        if vector is None:
            vector = ()
        if not vector:
            raise ChromaSQLParseError("VECTOR clause requires at least one number")
        return EmbeddingVector(values=tuple(vector))

    def vector_list(self, items: List[Union[int, float]]) -> Tuple[float, ...]:
        return tuple(float(value) for value in items)

    # Where clause ------------------------------------------------------

    def where_clause(self, items: List[Predicate]) -> Tuple[str, Predicate]:
        [predicate] = items
        return ("where", predicate)

    def where_document_clause(self, items: List[Predicate]) -> Tuple[str, Predicate]:
        [predicate] = items
        return ("where_document", predicate)

    def document_contains(self, items: List[Any]) -> ContainsPredicate:
        [value] = items
        return ContainsPredicate(field=Field("document"), value=value)

    def document_like(self, items: List[Any]) -> LikePredicate:
        [pattern] = items
        return LikePredicate(field=Field("document"), pattern=pattern)

    def contains_explicit_field(self, items: List[Any]) -> ContainsPredicate:
        [value] = items
        return ContainsPredicate(field=Field("document"), value=value)

    def like_explicit_field(self, items: List[Any]) -> LikePredicate:
        [pattern] = items
        return LikePredicate(field=Field("document"), pattern=pattern)

    def document_not_contains(self, items: List[Any]) -> ContainsPredicate:
        [value] = items
        return ContainsPredicate(field=Field("document"), value=value, negated=True)

    def document_not_like(self, items: List[Any]) -> LikePredicate:
        [pattern] = items
        return LikePredicate(field=Field("document"), pattern=pattern, negated=True)

    def document_regex(self, items: List[Any]) -> RegexPredicate:
        [pattern] = items
        return RegexPredicate(field=Field("document"), pattern=pattern)

    def document_not_regex(self, items: List[Any]) -> RegexPredicate:
        [pattern] = items
        return RegexPredicate(field=Field("document"), pattern=pattern, negated=True)

    def not_contains_explicit_field(self, items: List[Any]) -> ContainsPredicate:
        [value] = items
        return ContainsPredicate(field=Field("document"), value=value, negated=True)

    def not_like_explicit_field(self, items: List[Any]) -> LikePredicate:
        [pattern] = items
        return LikePredicate(field=Field("document"), pattern=pattern, negated=True)

    def regex_explicit_field(self, items: List[Any]) -> RegexPredicate:
        [pattern] = items
        return RegexPredicate(field=Field("document"), pattern=pattern)

    def not_regex_explicit_field(self, items: List[Any]) -> RegexPredicate:
        [pattern] = items
        return RegexPredicate(field=Field("document"), pattern=pattern, negated=True)

    def or_expr(self, items: List[Predicate]) -> Predicate:
        return _combine_boolean("OR", items)

    def and_expr(self, items: List[Predicate]) -> Predicate:
        return _combine_boolean("AND", items)

    def grouped_predicate(self, items: List[Predicate]) -> Predicate:
        [predicate] = items
        return predicate

    def comparison(self, items: List[Any]) -> ComparisonPredicate:
        if len(items) != 3:
            raise ChromaSQLParseError("Malformed comparison expression")
        field, operator, value = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("Comparison left side must be a field")
        return ComparisonPredicate(field=field, operator=str(operator), value=value)

    def in_list(self, items: List[Any]) -> InPredicate:
        field = items[0]
        values = items[-1]
        if not isinstance(field, Field):
            raise ChromaSQLParseError("IN clause left side must be a field")
        return InPredicate(field=field, values=tuple(values), negated=False)

    def not_in_list(self, items: List[Any]) -> InPredicate:
        field = items[0]
        values = items[-1]
        if not isinstance(field, Field):
            raise ChromaSQLParseError("NOT IN clause left side must be a field")
        return InPredicate(field=field, values=tuple(values), negated=True)

    def between(self, items: List[Any]) -> BetweenPredicate:
        field, lower, upper = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("BETWEEN clause left side must be a field")
        return BetweenPredicate(field=field, lower=lower, upper=upper)

    def like(self, items: List[Any]) -> LikePredicate:
        field, pattern = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("LIKE clause left side must be a field")
        if not isinstance(pattern, str):
            raise ChromaSQLParseError("LIKE clause requires a string literal")
        return LikePredicate(field=field, pattern=pattern)

    def contains(self, items: List[Any]) -> ContainsPredicate:
        field, value = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("CONTAINS clause left side must be a field")
        return ContainsPredicate(field=field, value=value)

    def not_like(self, items: List[Any]) -> LikePredicate:
        field, pattern = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("NOT LIKE clause left side must be a field")
        if not isinstance(pattern, str):
            raise ChromaSQLParseError("NOT LIKE clause requires a string literal")
        return LikePredicate(field=field, pattern=pattern, negated=True)

    def not_contains(self, items: List[Any]) -> ContainsPredicate:
        field, value = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("NOT CONTAINS clause left side must be a field")
        return ContainsPredicate(field=field, value=value, negated=True)

    def regex(self, items: List[Any]) -> RegexPredicate:
        field, pattern = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("REGEX clause left side must be a field")
        if not isinstance(pattern, str):
            raise ChromaSQLParseError("REGEX clause requires a string literal")
        return RegexPredicate(field=field, pattern=pattern)

    def not_regex(self, items: List[Any]) -> RegexPredicate:
        field, pattern = items
        if not isinstance(field, Field):
            raise ChromaSQLParseError("NOT REGEX clause left side must be a field")
        if not isinstance(pattern, str):
            raise ChromaSQLParseError("NOT REGEX clause requires a string literal")
        return RegexPredicate(field=field, pattern=pattern, negated=True)

    def comp_op(self, items: List[Token]) -> str:
        [token] = items
        return str(token)

    def value_list(self, items: List[Any]) -> Tuple[Any, ...]:
        return tuple(items)

    # Values ------------------------------------------------------------

    def string_literal(self, items: List[Token]) -> str:
        [token] = items
        return _strip_quotes(token)

    def string_value(self, items: List[str]) -> str:
        [value] = items
        return value

    def number_literal(self, items: List[Token]) -> Union[int, float]:
        [token] = items
        return _coerce_number(token.value)

    def number_value(self, items: List[Union[int, float]]) -> Union[int, float]:
        [value] = items
        return value

    def true_value(self, _: List[Any]) -> bool:
        return True

    def false_value(self, _: List[Any]) -> bool:
        return False

    def null_value(self, _: List[Any]) -> None:
        return None

    # Order by ----------------------------------------------------------

    def order_clause(self, items: List[OrderItem]) -> Tuple[str, Tuple[OrderItem, ...]]:
        return ("order_by", tuple(items))

    def order_item(self, items: List[Any]) -> OrderItem:
        field = items[0]
        direction = "ASC"
        if len(items) > 1:
            direction = items[1]
        if isinstance(field, tuple) and field[0] == "order_field":
            field = field[1]
        if not isinstance(field, Field):
            raise ChromaSQLParseError("ORDER BY expression must reference a field")
        return OrderItem(field=field, direction=direction)

    def asc(self, _: List[Any]) -> str:
        return "ASC"

    def desc(self, _: List[Any]) -> str:
        return "DESC"

    # Remaining clause helpers -----------------------------------------

    def similarity_clause(self, items: List[str]) -> Tuple[str, str]:
        [similarity] = items
        return ("similarity", similarity)

    def similarity_cosine(self, _: List[Any]) -> str:
        return "COSINE"

    def similarity_l2(self, _: List[Any]) -> str:
        return "L2"

    def similarity_ip(self, _: List[Any]) -> str:
        return "IP"

    def topk_clause(self, items: List[Token]) -> Tuple[str, int]:
        [token] = items
        return ("topk", int(token))

    def limit_clause(self, items: List[Token]) -> Tuple[str, int]:
        [token] = items
        return ("limit", int(token))

    def offset_clause(self, items: List[Token]) -> Tuple[str, int]:
        [token] = items
        return ("offset", int(token))

    def threshold_clause(self, items: List[Union[int, float]]) -> Tuple[str, float]:
        [value] = items
        return ("score_threshold", float(value))

    def rerank_clause(self, items: List[Rerank]) -> Tuple[str, Rerank]:
        [rerank] = items
        return ("rerank", rerank)

    def rerank_mmr(self, items: List[Dict[str, float]]) -> Rerank:
        params = items[0] if items else {}
        return Rerank(strategy="MMR", params=params)

    def rerank_params(self, items: List[Tuple[str, float]]) -> Dict[str, float]:
        return {key: value for key, value in items}

    def rerank_param(self, items: List[Any]) -> Tuple[str, float]:
        key_token, value = items
        return (str(key_token), float(value))


_LARK_PARSER = Lark(
    CSQL_GRAMMAR,
    start="query",
    parser="lalr",
    maybe_placeholders=False,
)


def parse(query: str) -> Query:
    """Parse a CSQL query string into a :class:`chromasql.ast.Query`.

    Parameters
    ----------
    query:
        The raw ChromaSQL string to parse.

    Returns
    -------
    chromasql.ast.Query
        The structured representation of the query.  The planner *always* works
        with this object rather than the original string.

    Raises
    ------
    ChromaSQLParseError
        If the query contains a syntax error or a Transformer hook raises one.
    """
    try:
        tree = _LARK_PARSER.parse(query)
    except Exception as exc:
        raise ChromaSQLParseError(str(exc)) from exc
    transformer = _ChromaSQLTransformer()
    try:
        return transformer.transform(tree)
    except VisitError as exc:
        original = getattr(exc, "orig_exc", None)
        if isinstance(original, ChromaSQLParseError):
            raise original
        if original is not None:
            raise ChromaSQLParseError(str(original)) from original
        raise ChromaSQLParseError(str(exc)) from exc
