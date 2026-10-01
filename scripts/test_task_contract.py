"""Mutation tests for the task-contract loader, run against in-memory briefs and temporary files.

Each test changes one fact of a valid brief and expects validation to fail with
the field named; the clean brief passes and round-trips through ``load_brief``.
Standard library only.
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import tempfile
import unittest
from pathlib import Path

from scripts import task_contract

VALID_BRIEF = {
    "schema_version": 1,
    "task_id": "increment-2-task-contract",
    "goal": "Add the task-contract loader and its tests so the workflow input has a contract file.",
    "owned_paths": [
        "contracts/task-contract.yaml",
        "scripts/task_contract.py",
        "scripts/test_task_contract.py",
    ],
    "out_of_scope": ["any file under .claude/ or adapters/", "any change to pilot-manifest.yaml"],
    "done_means": [
        "python3 -m unittest scripts/test_task_contract.py",
        "python3 scripts/verify_repository.py",
    ],
    "hand_back": "A session hand-off under docs/ that quotes the verification result and lists every file written.",
    "plan_id": "synthetic-dashboard",
    "node_id": "build",
    "note": "Example brief used by the tests.",
}


class TaskContractMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.brief = copy.deepcopy(VALID_BRIEF)

    def assert_fails(self, fragment: str) -> None:
        errors = task_contract.validate_brief(self.brief)
        self.assertTrue(errors, "expected a validation error")
        self.assertTrue(any(fragment in error for error in errors), f"{fragment!r} not in {errors}")

    def test_clean_brief_passes(self) -> None:
        self.assertEqual(task_contract.validate_brief(self.brief), [])

    def test_optional_fields_may_be_absent(self) -> None:
        for key in task_contract.OPTIONAL:
            del self.brief[key]
        self.assertEqual(task_contract.validate_brief(self.brief), [])

    def test_missing_required_field_fails(self) -> None:
        del self.brief["done_means"]
        self.assert_fails("missing field: done_means")

    def test_unknown_field_fails(self) -> None:
        self.brief["model"] = "anything"
        self.assert_fails("unknown field(s) ['model']")

    def test_wrong_schema_version_fails(self) -> None:
        self.brief["schema_version"] = 2
        self.assert_fails("unsupported schema_version")

    def test_task_id_must_be_a_slug(self) -> None:
        self.brief["task_id"] = "Increment 2"
        self.assert_fails("task_id must match")

    def test_task_id_at_bound_passes_and_one_over_fails(self) -> None:
        self.brief["task_id"] = "a" * task_contract.MAX_ID_LENGTH
        self.assertEqual(task_contract.validate_brief(self.brief), [])
        self.brief["task_id"] = "a" * (task_contract.MAX_ID_LENGTH + 1)
        self.assert_fails("task_id exceeds")

    def test_goal_length_bound(self) -> None:
        self.brief["goal"] = "g" * (task_contract.MAX_GOAL_LENGTH + 1)
        self.assert_fails("goal exceeds")

    def test_owned_paths_must_not_be_empty(self) -> None:
        self.brief["owned_paths"] = []
        self.assert_fails("owned_paths must have at least 1 entry")

    def test_absolute_owned_path_fails(self) -> None:
        self.brief["owned_paths"] = ["/etc/passwd"]
        self.assert_fails("must be relative")

    def test_parent_segment_in_owned_path_fails(self) -> None:
        self.brief["owned_paths"] = ["scripts/../reference/x.md"]
        self.assert_fails("must not contain a '..' segment")

    def test_protected_owned_path_fails(self) -> None:
        self.brief["owned_paths"] = ["reference/handoff-v1/README.md"]
        self.assert_fails("inside the protected path reference/")
        self.brief["owned_paths"] = ["runs/baseline-2026-08-15-001.yaml"]
        self.assert_fails("is a protected path")

    def test_duplicate_owned_path_fails(self) -> None:
        self.brief["owned_paths"] = ["scripts/a.py", "scripts/a.py"]
        self.assert_fails("duplicates an earlier entry")

    def test_too_many_owned_paths_fails(self) -> None:
        self.brief["owned_paths"] = [f"scripts/f{index}.py" for index in range(task_contract.MAX_OWNED_PATHS + 1)]
        self.assert_fails("owned_paths exceeds")

    def test_done_means_must_not_be_empty(self) -> None:
        self.brief["done_means"] = []
        self.assert_fails("done_means must have at least 1 entry")

    def test_blank_command_fails(self) -> None:
        self.brief["done_means"] = ["   "]
        self.assert_fails("done_means[0] must be a non-empty string")

    def test_out_of_scope_may_be_empty_but_entries_are_bounded(self) -> None:
        self.brief["out_of_scope"] = []
        self.assertEqual(task_contract.validate_brief(self.brief), [])
        self.brief["out_of_scope"] = ["x" * (task_contract.MAX_OUT_OF_SCOPE_LENGTH + 1)]
        self.assert_fails("out_of_scope[0] exceeds")

    def test_note_length_bound(self) -> None:
        self.brief["note"] = "n" * (task_contract.MAX_NOTE_LENGTH + 1)
        self.assert_fails("note exceeds")

    def test_non_object_brief_fails(self) -> None:
        self.assertEqual(task_contract.validate_brief(["not", "an", "object"]), ["brief must be an object"])

    def test_load_brief_round_trip_and_duplicate_key_rejection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text(json.dumps(self.brief), encoding="utf-8")
            self.assertEqual(task_contract.load_brief(path), self.brief)
            text = json.dumps(self.brief)
            duplicated = text[:-1] + ', "goal": "second goal"}'
            path.write_text(duplicated, encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                task_contract.load_brief(path)
            self.assertIn("duplicate key", str(raised.exception))

    def test_load_brief_reports_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "brief.json"
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(ValueError) as raised:
                task_contract.load_brief(path)
            self.assertIn("not valid JSON", str(raised.exception))

    def test_cli_exit_codes(self) -> None:
        def run(argv: list[str]) -> tuple[int, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = task_contract.main(argv)
            return code, out.getvalue()

        with tempfile.TemporaryDirectory() as tmp:
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps(self.brief), encoding="utf-8")
            code, text = run(["task_contract.py", str(good)])
            self.assertEqual(code, 0)
            self.assertTrue(text.startswith("VALID"))
            bad = Path(tmp) / "bad.json"
            self.brief["owned_paths"] = []
            bad.write_text(json.dumps(self.brief), encoding="utf-8")
            code, text = run(["task_contract.py", str(bad)])
            self.assertEqual(code, 1)
            self.assertTrue(text.startswith("INVALID"))
            self.assertEqual(run(["task_contract.py"])[0], 2)
            self.assertEqual(run(["task_contract.py", str(Path(tmp) / "missing.json")])[0], 2)


if __name__ == "__main__":
    unittest.main()
