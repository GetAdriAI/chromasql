"""Analysis helpers for ChromaSQL queries.

These helpers inspect the parsed AST to derive additional routing hints.  They
are intentionally kept separate from the planner/executor so that callers can
build custom dispatch strategies (for example, fan-out to specific collections
based on metadata filters) without re-implementing predicate traversal.
"""

from __future__ import annotations

from typing import Optional, Sequence, Set, Tuple

from ._ast_nodes import (
    BooleanPredicate,
    ComparisonPredicate,
    Field,
    InPredicate,
    Predicate,
    Query,
)


def extract_metadata_values(
    query: Query,
    *,
    field_path: Sequence[str],
) -> Optional[Set[str]]:
    """Return the set of equality values for ``metadata.<path>`` in ``WHERE``.

    This function extracts values from equality (``=``) and membership (``IN``)
    predicates for a specific metadata field. It performs **union extraction**
    across OR predicates, ensuring that all possible values are captured.

    Union Routing Behavior
    -----------------------
    For OR predicates, this function collects values from ALL branches:

    - ``WHERE metadata.model = 'Table' OR metadata.model = 'Field'``
      → Returns ``{'Table', 'Field'}`` (queries union of collections)

    - ``WHERE metadata.model IN ('A', 'B') OR metadata.model = 'C'``
      → Returns ``{'A', 'B', 'C'}`` (union of all values)

    - ``WHERE metadata.model = 'Table' OR metadata.other_field = 'X'``
      → Returns ``{'Table'}`` (only extracts target field)

    This ensures **no under-routing**: when using OR predicates, all relevant
    collections will be queried to guarantee complete results.

    Parameters
    ----------
    query:
        Parsed query (output of :func:`chromasql.parser.parse`).
    field_path:
        Metadata path relative to ``metadata`` – e.g. ``("model",)`` for
        ``metadata.model`` or ``("foo", "bar")`` for ``metadata.foo.bar``.

    Returns
    -------
    set[str] | None
        The set of values referenced via ``=`` or ``IN`` for that path.  Returns
        ``None`` when the query does not constrain the path.

    Examples
    --------
    >>> from chromasql import parse
    >>> query = parse("SELECT * FROM demo WHERE metadata.model = 'Table';")
    >>> extract_metadata_values(query, field_path=("model",))
    {'Table'}

    >>> query = parse("SELECT * FROM demo WHERE metadata.model IN ('A', 'B');")
    >>> extract_metadata_values(query, field_path=("model",))
    {'A', 'B'}

    >>> # Union routing with OR
    >>> query = parse("SELECT * FROM demo WHERE metadata.model = 'A' OR metadata.model = 'B';")
    >>> extract_metadata_values(query, field_path=("model",))
    {'A', 'B'}
    """

    if not query.where:
        return None

    values = _collect_metadata_values(query.where, tuple(field_path))
    return values or None


def _collect_metadata_values(predicate: Predicate, path: Tuple[str, ...]) -> Set[str]:
    """Collect metadata values from a predicate tree.

    Returns empty set if we should query all collections (to prevent under-routing).

    For OR predicates: If ANY branch lacks the target field, we return empty set
    (signaling "query all collections") to avoid under-routing.

    For AND predicates: We collect values from all branches (intersection semantics).
    """
    values: Set[str] = set()

    if isinstance(predicate, BooleanPredicate):
        if predicate.operator == "OR":
            # OR: Check if ANY branch lacks the discriminator field
            # If so, we must query all collections to avoid under-routing
            branch_values_list = []
            for child in predicate.predicates:
                branch_values = _collect_metadata_values(child, path)
                branch_values_list.append(branch_values)

            # If any OR branch has no discriminator values, it could match
            # records in ANY collection, so we must query all collections
            if any(len(branch_vals) == 0 for branch_vals in branch_values_list):
                return set()  # Signal: query all collections

            # Otherwise, take union of all branch values
            for branch_vals in branch_values_list:
                values.update(branch_vals)
            return values
        else:  # AND
            # AND: Collect from all branches (they all must be satisfied)
            for child in predicate.predicates:
                values.update(_collect_metadata_values(child, path))
            return values

    if isinstance(predicate, ComparisonPredicate):
        if (
            predicate.operator == "="
            and _matches_field(predicate.field, path)
            and isinstance(predicate.value, str)
        ):
            values.add(predicate.value)
        return values

    if isinstance(predicate, InPredicate):
        if not predicate.negated and _matches_field(predicate.field, path):
            for value in predicate.values:
                if isinstance(value, str):
                    values.add(value)
        return values

    # If we reach here, this predicate doesn't reference the target field
    return values


def _matches_field(field: Field, path: Tuple[str, ...]) -> bool:
    return field.root == "metadata" and field.path == path


__all__ = ["extract_metadata_values"]
