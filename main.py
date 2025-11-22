"""Custom macros for MkDocs builds."""

from __future__ import annotations

from pathlib import Path

DOCS_ROOT = Path(__file__).parent


def define_env(env) -> None:  # pragma: no cover - executed by mkdocs
    """Register custom macros for documentation templates."""

    @env.macro
    def read_file(relative_path: str) -> str:
        """Return the contents of a docs-relative file for inlining."""
        file_path = DOCS_ROOT / relative_path
        return file_path.read_text(encoding="utf-8")
