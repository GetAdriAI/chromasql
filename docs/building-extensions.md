# Building Extensions

ChromaSQL is intentionally modular so you can evolve the language and runtime
without rewriting the whole stack. This page highlights the recommended
workflow, which mirrors the guidelines in `CONTRIBUTING.md`.

## 1. Extend the AST

Start with `chromasql/ast.py`. Add new dataclasses or fields that represent the
construct you want to support. The AST layer is lightweight and frozen, keeping
downstream reasoning simple.

```python
@dataclass(frozen=True)
class ScoreBoost:
    field: Field
    weight: float
```

## 2. Update Grammar & Parser

- Modify `chromasql/grammar.py` with the new syntax.
- Implement transformer hooks in `chromasql/parser.py` that map tokens to your
  AST nodes.
- Add parser guardrail tests in `tests/chromasql/test_internal_errors.py`.

## 3. Planner Changes

In `chromasql/planner.py`, translate the AST into plan data structures, enforce
semantic rules, and populate `QueryPlan` fields. For complicated predicates or
options, create helper functions with focused unit tests.

## 4. Executor Updates

Only required if the planner emits new fields the executor needs to honor
(e.g., additional include sets or result post-processing). The executor has
well-covered helpers in `tests/chromasql/test_executor.py`.

## 5. Tests & Docs

- Snapshot tests in `tests/chromasql/test_planner.py` should cover new grammar.
- Extend executor, analysis, or multi-collection tests as needed.
- Update tutorial / docs (`TUTORIAL.md`, `docs/query-language.md`, etc.) so the
  feature is discoverable.

## 6. Packaging & Release

ChromaSQL ships with the same tooling as other packages in the repo:

```bash
cd chromasql
./scripts/publish_pypi.sh
./scripts/sync_public_repo.sh --tag
```

Remember to bump the version in `pyproject.toml` and keep coverage high before
publishing.
