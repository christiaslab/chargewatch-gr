#!/usr/bin/env python3
"""Validate a task brief against contracts/task-contract.yaml.

A brief is a JSON object that bounds one unit of work: goal, owned paths, what is
out of scope, the commands that prove completion, and how the result is handed
back. The schema is closed: every field is required or listed as optional, and
any other key is an error. Identifiers are slugs, texts are length-bounded, and
owned paths must be relative, inside the repository and outside the protected
evidence paths. Standard library only.

Usage: python3 scripts/task_contract.py BRIEF.json
Exit 0 when valid, 1 when invalid (errors on stdout), 2 on a usage error.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
REQUIRED = ("schema_version", "task_id", "goal", "owned_paths", "out_of_scope", "done_means", "hand_back")
OPTIONAL = ("plan_id", "node_id", "note")

ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MAX_ID_LENGTH = 64
MAX_GOAL_LENGTH = 500
MAX_PATH_LENGTH = 256
MAX_OWNED_PATHS = 64
MAX_OUT_OF_SCOPE = 64
MAX_OUT_OF_SCOPE_LENGTH = 200
MAX_DONE_MEANS = 32
MAX_COMMAND_LENGTH = 500
MAX_HAND_BACK_LENGTH = 500
MAX_NOTE_LENGTH = 1000

# A brief may not own these paths; changing them is a decision or a new record.
PROTECTED_PATHS = (
    "reference/",
    "runs/baseline-2026-08-15-001.yaml",
    "runs/exp-001-in-process-orchestration.json",
    "runs/exp-002-matched-orchestration-confirmation.json",
    "examples/synthetic-dashboard/output/",
    "docs/experiments/",
)


def _id_errors(value: Any, where: str) -> list[str]:
    if not isinstance(value, str) or not value:
        return [f"{where} must be a non-empty string"]
    errors: list[str] = []
    if len(value) > MAX_ID_LENGTH:
        errors.append(f"{where} exceeds {MAX_ID_LENGTH} characters ({len(value)})")
    if not ID_PATTERN.fullmatch(value):
        errors.append(f"{where} must match {ID_PATTERN.pattern}: {value!r}")
    return errors


def _text_errors(value: Any, where: str, limit: int) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        return [f"{where} must be a non-empty string"]
    if len(value) > limit:
        return [f"{where} exceeds {limit} characters ({len(value)})"]
    return []


def _list_errors(value: Any, where: str, minimum: int, maximum: int) -> list[str]:
    if not isinstance(value, list):
        return [f"{where} must be a list"]
    if len(value) < minimum:
        return [f"{where} must have at least {minimum} entr{'y' if minimum == 1 else 'ies'}"]
    if len(value) > maximum:
        return [f"{where} exceeds {maximum} entries ({len(value)})"]
    return []


def _path_errors(value: Any, where: str) -> list[str]:
    if not isinstance(value, str) or not value:
        return [f"{where} must be a non-empty string"]
    errors: list[str] = []
    if len(value) > MAX_PATH_LENGTH:
        errors.append(f"{where} exceeds {MAX_PATH_LENGTH} characters ({len(value)})")
    if value.startswith("/") or value.startswith("\\") or re.match(r"^[A-Za-z]:", value):
        errors.append(f"{where} must be relative to the repository root: {value!r}")
    parts = value.replace("\\", "/").split("/")
    if ".." in parts:
        errors.append(f"{where} must not contain a '..' segment: {value!r}")
    if any(part == "" for part in parts[:-1]) or value.startswith("./"):
        errors.append(f"{where} must be a normalized path: {value!r}")
    for protected in PROTECTED_PATHS:
        if protected.endswith("/"):
            if value == protected.rstrip("/") or value.startswith(protected):
                errors.append(f"{where} is inside the protected path {protected}: {value!r}")
        elif value == protected:
            errors.append(f"{where} is a protected path: {value!r}")
    return errors


def validate_brief(brief: Any) -> list[str]:
    """Return a list of schema errors; empty means valid."""
    if not isinstance(brief, dict):
        return ["brief must be an object"]
    errors: list[str] = [f"brief missing field: {key}" for key in REQUIRED if key not in brief]
    if errors:
        return errors
    extra = sorted(set(brief) - set(REQUIRED) - set(OPTIONAL))
    if extra:
        errors.append(f"brief: unknown field(s) {extra}")
    if brief["schema_version"] != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version: {brief['schema_version']!r}")
    errors.extend(_id_errors(brief["task_id"], "task_id"))
    errors.extend(_text_errors(brief["goal"], "goal", MAX_GOAL_LENGTH))

    errors.extend(_list_errors(brief["owned_paths"], "owned_paths", 1, MAX_OWNED_PATHS))
    if isinstance(brief["owned_paths"], list):
        seen: set[str] = set()
        for index, path in enumerate(brief["owned_paths"]):
            where = f"owned_paths[{index}]"
            errors.extend(_path_errors(path, where))
            if isinstance(path, str):
                if path in seen:
                    errors.append(f"{where} duplicates an earlier entry: {path!r}")
                seen.add(path)

    errors.extend(_list_errors(brief["out_of_scope"], "out_of_scope", 0, MAX_OUT_OF_SCOPE))
    if isinstance(brief["out_of_scope"], list):
        for index, item in enumerate(brief["out_of_scope"]):
            errors.extend(_text_errors(item, f"out_of_scope[{index}]", MAX_OUT_OF_SCOPE_LENGTH))

    errors.extend(_list_errors(brief["done_means"], "done_means", 1, MAX_DONE_MEANS))
    if isinstance(brief["done_means"], list):
        for index, command in enumerate(brief["done_means"]):
            errors.extend(_text_errors(command, f"done_means[{index}]", MAX_COMMAND_LENGTH))

    errors.extend(_text_errors(brief["hand_back"], "hand_back", MAX_HAND_BACK_LENGTH))
    for key in ("plan_id", "node_id"):
        if key in brief:
            errors.extend(_id_errors(brief[key], key))
    if "note" in brief:
        errors.extend(_text_errors(brief["note"], "note", MAX_NOTE_LENGTH))
    return errors


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate key in brief: {key!r}")
        result[key] = value
    return result


def load_brief(path: Path) -> dict[str, Any]:
    """Load and validate a brief; raise ValueError with every error joined by newlines."""
    try:
        brief = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as error:
        raise ValueError(f"brief is not valid JSON: {error}") from error
    errors = validate_brief(brief)
    if errors:
        raise ValueError("\n".join(errors))
    return brief


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: task_contract.py BRIEF.json", file=sys.stderr)
        return 2
    path = Path(argv[1])
    if not path.is_file():
        print(f"usage: brief not found: {path}", file=sys.stderr)
        return 2
    try:
        brief = load_brief(path)
    except ValueError as error:
        print(f"INVALID {path}\n{error}")
        return 1
    print(f"VALID {path}: task {brief['task_id']}, {len(brief['owned_paths'])} owned path(s), {len(brief['done_means'])} done-means command(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
