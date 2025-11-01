"""Custom exceptions for the ChromaSQL package."""

from __future__ import annotations


class ChromaSQLError(Exception):
    """Base error for all ChromaSQL failures."""


class ChromaSQLParseError(ChromaSQLError):
    """Raised when the query string cannot be parsed."""


class ChromaSQLPlanningError(ChromaSQLError):
    """Raised when the parsed query cannot be translated into a plan."""


class ChromaSQLExecutionError(ChromaSQLError):
    """Raised when executing a plan against ChromaDB fails."""
