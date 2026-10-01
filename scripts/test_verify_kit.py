"""Mutation tests for the kit verifier (scripts/verify_kit.py) on an installed kit in a temporary repository.

Standard library only. The verifier runs as a subprocess so that the target's
own scripts/ modules are the ones imported.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import kit

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}


def fill_maintainer(root: Path, name: str = "Test Maintainer") -> None:
    """What a maintainer does after install; the verifier refuses the placeholder (Decision 0014)."""
    path = root / kit.SPEC
    path.write_text(path.read_text(encoding="utf-8").replace(f"maintainer: {kit.SPEC_PLACEHOLDER}", f"maintainer: {name}", 1), encoding="utf-8")


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, env=GIT_ENV, check=True, capture_output=True)


class VerifyKitMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.target = base / "target"
        self.target.mkdir()
        git(self.target, "init", "-q", "-b", "main")
        kit.install(REPOSITORY_ROOT, self.target, "verify-target", None)
        fill_maintainer(self.target)
        git(self.target, "add", "-A")
        git(self.target, "commit", "-q", "-m", "chore: install the portable kit")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def verify(self) -> dict:
        run = subprocess.run([sys.executable, "scripts/verify_kit.py"], cwd=self.target, env=GIT_ENV,
                             capture_output=True, text=True)
        return json.loads(run.stdout)

    def failing(self, report: dict) -> dict[str, str]:
        return {item["check"]: item["detail"] for item in report["checks"] if not item["passed"]}

    def test_installed_kit_passes(self) -> None:
        report = self.verify()
        self.assertEqual(report["result"], "PASS", report)
        self.assertEqual(len(report["checks"]), 8)
        skills = next(item for item in report["checks"] if item["check"] == "kit-skills")
        self.assertIn("3 skills", skills["detail"])

    def test_spec_placeholder_missing_file_drift_and_unknown_field_fail(self) -> None:
        path = self.target / kit.SPEC
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("maintainer: Test Maintainer", f"maintainer: {kit.SPEC_PLACEHOLDER}"), encoding="utf-8")
        failing = self.failing(self.verify())
        self.assertEqual(list(failing), ["kit-project-spec"])
        self.assertIn("placeholder", failing["kit-project-spec"])
        path.unlink()
        failing = self.failing(self.verify())
        self.assertIn(f"{kit.SPEC} is missing", failing["kit-project-spec"])
        path.write_text(original.replace("verification_command: python3 scripts/verify_kit.py", "verification_command: make verify"), encoding="utf-8")
        failing = self.failing(self.verify())
        self.assertIn("AGENTS.md runs", failing["kit-project-spec"])
        path.write_text(original + "stack: python\n", encoding="utf-8")
        failing = self.failing(self.verify())
        self.assertIn("unknown fields: stack", failing["kit-project-spec"])
        path.write_text(original, encoding="utf-8")
        self.assertEqual(self.verify()["result"], "PASS")

    def test_skill_with_missing_doctrine_script_or_allow_entry_fails(self) -> None:
        path = self.target / ".claude/skills/publish-increment/SKILL.md"
        original = path.read_text(encoding="utf-8")
        path.write_text(original.replace("- Doctrine: `policies/worktree-flow.md`", "- Doctrine: `skills/publish.md`"), encoding="utf-8")
        failing = self.failing(self.verify())
        self.assertEqual(list(failing), ["kit-skills"])
        self.assertIn("Doctrine points at skills/publish.md", failing["kit-skills"])
        path.write_text(original.replace("- Script: `scripts/push_increment.py`", "- Script: `scripts/publish.py`"), encoding="utf-8")
        self.assertIn("Script points at scripts/publish.py", self.failing(self.verify())["kit-skills"])
        path.write_text(original.replace("python3 scripts/push_increment.py\n```", "python3 scripts/push_increment.py\ngit push origin HEAD\n```"), encoding="utf-8")
        self.assertIn("no allow entry", self.failing(self.verify())["kit-skills"])
        path.write_text(original.replace("It must print", "It prints"), encoding="utf-8")
        self.assertIn("what it must print", self.failing(self.verify())["kit-skills"])
        path.write_text(original.replace("name: publish-increment", "name: publish"), encoding="utf-8")
        self.assertIn("front matter name", self.failing(self.verify())["kit-skills"])
        path.write_text(original, encoding="utf-8")
        self.assertEqual(self.verify()["result"], "PASS")

    def test_missing_deny_entry_fails(self) -> None:
        path = self.target / ".claude/settings.json"
        settings = json.loads(path.read_text(encoding="utf-8"))
        settings["permissions"]["deny"].remove("Bash(git push:*)")
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        self.assertIn("kit-settings", self.failing(self.verify()))

    def test_schema_rejected_no_bypass_value_fails(self) -> None:
        # A boolean true parses as JSON but the settings schema rejects it and skips the whole file; the
        # verifier must not report PASS over a file the development environment never loads (kit v3).
        path = self.target / ".claude/settings.json"
        for key, value in (("disableBypassPermissionsMode", True), ("disableAutoMode", True)):
            settings = json.loads(path.read_text(encoding="utf-8"))
            settings["permissions"][key] = value
            path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            failing = self.failing(self.verify())
            self.assertIn("kit-settings", failing)
            self.assertIn(f"permissions.{key} is true", failing["kit-settings"])
            self.assertIn('"disable"', failing["kit-settings"])
        settings = json.loads(path.read_text(encoding="utf-8"))
        settings["permissions"]["disableAutoMode"] = "disable"
        settings["permissions"]["disableBypassPermissionsMode"] = "disable"
        path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        self.assertEqual(self.verify()["result"], "PASS")

    def test_dangling_hook_fails(self) -> None:
        (self.target / "scripts/hooks/session_start.py").unlink()
        self.assertIn("kit-hooks-wired", self.failing(self.verify()))

    def test_attribution_trailer_in_history_fails(self) -> None:
        trailer = "Co-Authored" + "-By: Someone <someone@example.invalid>"
        git(self.target, "commit", "--allow-empty", "-q", "-m", f"chore: trailer\n\n{trailer}")
        self.assertIn("kit-commit-history", self.failing(self.verify()))

    def test_drifted_kit_file_fails(self) -> None:
        path = self.target / "policies/contribution.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nlocal edit\n", encoding="utf-8")
        failing = self.failing(self.verify())
        self.assertIn("kit-notice-digests", failing)
        self.assertIn("policies/contribution.md differs", failing["kit-notice-digests"])

    def test_running_target_with_its_own_policy_passes_the_digest_check(self) -> None:
        base = Path(self._tmp.name).resolve()
        running = base / "running"
        (running / "policies").mkdir(parents=True)
        (running / "policies/contribution.md").write_text("# own policy\n", encoding="utf-8")
        git(running, "init", "-q", "-b", "main")
        kit.install(REPOSITORY_ROOT, running, "running-target", None)
        fill_maintainer(running)
        git(running, "add", "-A")
        git(running, "commit", "-q", "-m", "chore: install the portable kit")
        run = subprocess.run([sys.executable, "scripts/verify_kit.py"], cwd=running, env=GIT_ENV, capture_output=True, text=True)
        report = json.loads(run.stdout)
        self.assertEqual(report["result"], "PASS", report)
        digests = next(item for item in report["checks"] if item["check"] == "kit-notice-digests")
        self.assertIn("1 target-owned files not digest-checked", digests["detail"])

    def test_invalid_task_brief_fails_and_a_valid_one_passes(self) -> None:
        tasks = self.target / "tasks"
        tasks.mkdir()
        (tasks / "bad.json").write_text('{"schema_version": 1}\n', encoding="utf-8")
        self.assertIn("kit-task-briefs", self.failing(self.verify()))
        (tasks / "bad.json").unlink()
        (tasks / "good.json").write_text(json.dumps({
            "schema_version": 1, "task_id": "trial", "goal": "Try the kit.", "owned_paths": ["docs/trial.md"],
            "out_of_scope": [], "done_means": ["python3 scripts/verify_kit.py"], "hand_back": "A note in docs/trial.md.",
        }), encoding="utf-8")
        self.assertEqual(self.verify()["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
