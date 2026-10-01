"""The ingestion write path reaches nothing but GCS.

CLAUDE.md hard rule and docs/specs/m1-logger.md section 4: the logger fetches bytes and stores
bytes; no Neon, no DuckLake, no validation before the write. Contracts live downstream of raw.
These tests make that rule fail loudly the moment a lake or warehouse driver enters the package.
"""

import ast
import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
SRC = ROOT / "src" / "chargewatch"

ALLOWED_RUNTIME = {"fastapi", "uvicorn", "httpx", "google-cloud-storage", "pydantic-settings"}
ALLOWED_DEV = {"pytest", "ruff"}
FORBIDDEN_WORDS = ("neon", "duckdb", "psycopg", "polars", "ducklake", "sqlmesh")
FORBIDDEN_MODULES = {
    "asyncpg",
    "duckdb",
    "ducklake",
    "polars",
    "psycopg",
    "psycopg2",
    "sqlalchemy",
    "sqlmesh",
}


def _name(requirement: str) -> str:
    return re.split(r"[<>=!~\[; ]", requirement, maxsplit=1)[0].strip().lower()


def _pyproject() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module.split(".")[0])
    return found


def test_runtime_dependencies_are_exactly_the_five_allowed():
    declared = {_name(dep) for dep in _pyproject()["project"]["dependencies"]}
    assert declared == ALLOWED_RUNTIME


def test_dev_dependencies_are_exactly_pytest_and_ruff():
    declared = {_name(dep) for dep in _pyproject()["dependency-groups"]["dev"]}
    assert declared == ALLOWED_DEV


def test_pyproject_names_no_lake_or_warehouse_driver():
    text = PYPROJECT.read_text(encoding="utf-8").lower()
    present = [word for word in FORBIDDEN_WORDS if word in text]
    assert present == []


def test_no_module_under_src_imports_a_lake_or_warehouse_driver():
    modules = sorted(SRC.rglob("*.py"))
    assert modules, "no modules found under src/chargewatch"
    offenders = {
        str(path.relative_to(ROOT)): sorted(_top_level_imports(path) & FORBIDDEN_MODULES)
        for path in modules
    }
    offenders = {path: names for path, names in offenders.items() if names}
    assert offenders == {}
