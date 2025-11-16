#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKG_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_DIR="$(cd "${PKG_DIR}/.." && pwd)"

REMOTE="${PUBLISH_REMOTE:-origin}"

for tool in python twine; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "Missing required tool: ${tool}" >&2
    exit 1
  fi
done

VERSION="$(python - <<'PY'
import pathlib, tomllib
data = tomllib.loads(pathlib.Path("pyproject.toml").read_text())
print(data["project"]["version"])
PY
)"

TAG="v${VERSION}"

rm -rf "${PKG_DIR}/dist" "${PKG_DIR}/build" "${PKG_DIR}"/*.egg-info

python -m build "${PKG_DIR}"
twine check "${PKG_DIR}/dist"/*
twine upload "${PKG_DIR}/dist"/*

if git -C "${REPO_DIR}" rev-parse "${TAG}" >/dev/null 2>&1; then
  echo "Tag ${TAG} already exists; skipping tag creation."
else
  git -C "${REPO_DIR}" tag -a "${TAG}" -m "chromasql ${VERSION}"
  git -C "${REPO_DIR}" push "${REMOTE}" "${TAG}"
fi

echo "Published chromasql ${VERSION} to PyPI."
