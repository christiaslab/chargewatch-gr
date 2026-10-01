"""Tests for scripts/push_increment.py (Decisions 0013 and 0017) against a temporary origin and a fake CLI.

The fake CLI records its arguments and prints a review URL; the origin is a
bare repository on disk; the backend comes from a project specification written
into the fixture. No network, no real provider. Standard library only.
"""
from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY_ROOT / "scripts/push_increment.py"
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}
PASS_VERIFY = f'{sys.executable} -c "print(\'{{\\"result\\": \\"PASS\\"}}\')"'
FAIL_VERIFY = f'{sys.executable} -c "print(\'{{\\"result\\": \\"FAIL\\"}}\')"'
FAKE_GH = """#!/bin/sh
printf '%s\\n' "$*" >> "$FAKE_GH_LOG"
case "$1 $2" in
  "pr view") if [ -f "$FAKE_GH_LOG.exists" ]; then echo "https://example.invalid/pull/1"; exit 0; else exit 1; fi ;;
  "pr create") if [ -f "$FAKE_GH_LOG.fail" ]; then echo "refused" >&2; exit 1; else echo "https://example.invalid/pull/2"; exit 0; fi ;;
  *) echo "unexpected gh call" >&2; exit 1 ;;
esac
"""


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=root, env=GIT_ENV, check=True,
                          capture_output=True, text=True).stdout.strip()


class PushIncrementTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.origin = base / "origin.git"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.origin)], env=GIT_ENV, check=True)
        self.work = base / "work"
        self.work.mkdir()
        (self.work / "scripts").mkdir()
        for name in ("commit_hygiene.py", "kit.py"):
            (self.work / "scripts" / name).write_bytes((REPOSITORY_ROOT / "scripts" / name).read_bytes())
        self.write_spec("push script: github")
        git(self.work, "init", "-q", "-b", "main")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "chore: seed")
        git(self.work, "remote", "add", "origin", str(self.origin))
        git(self.work, "push", "-q", "-u", "origin", "main")
        git(self.work, "switch", "-q", "-c", "feat/thing")
        (self.work / "note.md").write_text("increment\n", encoding="utf-8")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "feat(thing): add a note")
        self.bin = base / "bin"
        self.bin.mkdir()
        self.gh = self.bin / "gh"
        self.gh.write_text(FAKE_GH, encoding="utf-8")
        self.gh.chmod(self.gh.stat().st_mode | stat.S_IXUSR)
        self.log = base / "gh.log"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write_spec(self, integration: str, verification: str = PASS_VERIFY) -> None:
        """The specification is the only source of the verification command and the backend (no option overrides them)."""
        (self.work / "adapters").mkdir(exist_ok=True)
        (self.work / "adapters/project-spec.yaml").write_text(
            "spec_version: 1\nproject_name: work\nmaintainer: Test Maintainer\nreviewer: same as maintainer\n"
            "release_authority: same as maintainer\n" + f"verification_command: {verification}\n"
            f"handoff_pointer: none\nintegration: {integration}\nguidance_files:\nlimits:\n", encoding="utf-8")

    def run_script(self, *extra: str, with_cli: bool = True) -> dict:
        """The fake gh is found on PATH by name, as the real one is; without it the github backend must refuse early."""
        if with_cli:
            path = str(self.bin) + os.pathsep + os.environ.get("PATH", "")
        else:  # a PATH with git alone, so that no real gh on this machine is found
            nogh = self.bin.parent / "nogh"
            nogh.mkdir(exist_ok=True)
            (nogh / "git").exists() or os.symlink(shutil.which("git"), nogh / "git")
            path = str(nogh)
        env = {**GIT_ENV, "FAKE_GH_LOG": str(self.log), "PATH": path}
        env.pop("PYTHONDONTWRITEBYTECODE", None)  # the script itself must keep the tree clean
        run = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.work), *extra], env=env, capture_output=True, text=True)
        report = json.loads(run.stdout)
        self.assertEqual(run.returncode, 0 if report["result"] == "PASS" else 1, run.stdout + run.stderr)
        return report

    def gh_calls(self) -> list[str]:
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []

    def test_pushes_the_branch_and_opens_a_pull_request(self) -> None:
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertTrue(report["created"])
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/2")
        self.assertEqual(report["backend"], "github")
        self.assertIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))
        create = [call for call in self.gh_calls() if call.startswith("pr create")]
        self.assertEqual(len(create), 1)
        self.assertIn("--base main --head feat/thing", create[0])
        self.assertIn("feat(thing): add a note", create[0])
        self.assertFalse(any("merge" in call for call in self.gh_calls()))
        self.assertEqual(git(self.work, "status", "--porcelain"), "", "a run must leave the tree clean, bytecode included")

    def test_second_run_reuses_the_existing_pull_request(self) -> None:
        self.run_script()
        (self.log.parent / "gh.log.exists").write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertFalse(report["created"])
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/1")
        self.assertEqual(len([call for call in self.gh_calls() if call.startswith("pr create")]), 1)

    def test_refuses_main(self) -> None:
        git(self.work, "switch", "-q", "main")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("not an increment branch", report["refused"][0])
        self.assertEqual(self.gh_calls(), [])

    def test_refuses_a_badly_named_branch(self) -> None:
        git(self.work, "switch", "-q", "-c", "Feature_Thing")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertNotIn("Feature_Thing", git(self.work, "ls-remote", "--heads", "origin"))

    def test_refuses_a_dirty_tree(self) -> None:
        (self.work / "note.md").write_text("edited\n", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("not clean", report["refused"][0])
        self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))

    def test_refuses_a_second_remote(self) -> None:
        git(self.work, "remote", "add", "mirror", str(self.origin))
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("remotes are", report["refused"][0])

    def test_refuses_when_verification_fails(self) -> None:
        self.write_spec("push script: github", verification=FAIL_VERIFY)
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "chore: failing verification command")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("verification FAIL", report["refused"][0])
        self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))
        self.assertEqual(self.gh_calls(), [])

    def test_body_drops_attribution_lines(self) -> None:
        body = self.log.parent / "body.md"
        trailer = "Co-Authored" + "-By: Someone <someone@example.invalid>"
        body.write_text(f"Summary line.\n\n{trailer}\n", encoding="utf-8")
        self.run_script("--body-file", str(body), "--title", "feat: titled")
        create = [call for call in self.gh_calls() if call.startswith("pr create")][0]
        self.assertIn("Summary line.", create)
        self.assertNotIn("Co-Authored", create)
        self.assertIn("--title feat: titled", create)

    def test_none_backend_pushes_and_leaves_the_review_to_the_maintainer(self) -> None:
        self.write_spec("push script: none")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "chore: integration none")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertEqual(report["backend"], "none")
        self.assertIsNone(report["pull_request"])
        self.assertIn("feat/thing", report["review"])
        self.assertIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))
        self.assertEqual(self.gh_calls(), [])

    def test_maintainer_pushes_bare_push_script_own_words_and_untried_backend_are_refused(self) -> None:
        for integration, fragment in (("maintainer pushes", "the maintainer pushes"),
                                      ("push script", "names no backend"),
                                      ("the release engineer merges on Friday", "own words"),
                                      ("push script: azure-devops", "not in the set")):
            self.write_spec(integration)
            git(self.work, "add", "-A")
            git(self.work, "commit", "-q", "-m", f"chore: integration {integration.split(':')[0].split()[0]}")
            report = self.run_script()
            self.assertEqual(report["result"], "FAIL", integration)
            self.assertIn(fragment, report["refused"][0], integration)
            self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"), integration)
        self.assertEqual(self.gh_calls(), [])

    def test_missing_specification_is_refused_before_any_push(self) -> None:
        (self.work / "adapters/project-spec.yaml").unlink()
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "chore: no specification")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("project-spec.yaml is missing", report["refused"][0])
        self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))

    def test_placeholder_verification_command_is_refused_and_no_option_overrides_it(self) -> None:
        self.write_spec("push script: github", verification="(fill in)")
        git(self.work, "add", "-A")
        git(self.work, "commit", "-q", "-m", "chore: placeholder verification command")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("no verification command", report["refused"][0])
        run = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.work), "--verify-command", PASS_VERIFY],
                             env=GIT_ENV, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, "an option that overrides the verification gate must not exist")
        run = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.work), "--cli", str(self.gh)],
                             env=GIT_ENV, capture_output=True, text=True)
        self.assertEqual(run.returncode, 2, "an option that names the review program must not exist")
        self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))

    def test_missing_cli_is_refused_before_any_push(self) -> None:
        report = self.run_script(with_cli=False)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("'gh' on PATH", report["refused"][0])
        self.assertNotIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))

    def test_failed_create_reports_the_push_and_a_title_with_attribution_is_refused(self) -> None:
        (self.log.parent / "gh.log.fail").write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["pushed_to"], "origin")
        self.assertIn("pr create failed", report["refused"][0])
        (self.log.parent / "gh.log.fail").unlink()
        trailer = "Co-Authored" + "-By: Someone <someone@example.invalid>"
        report = self.run_script("--title", trailer)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("attribution", report["refused"][0])
        self.assertEqual(len([call for call in self.gh_calls() if call.startswith("pr create")]), 1)

    def test_core_makes_no_network_call_and_reads_no_token(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("urllib", "http.client", "requests", "TOKEN", "socket", "os.environ", "getenv", "--verify-command", "--cli"):
            self.assertNotIn(forbidden, text, forbidden)

    def test_script_never_forces(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("--force", text)
        self.assertNotIn("-f ", text)
        self.assertNotIn("pr merge", text.replace("``gh pr merge`` is not called and not allowed", ""))
        self.assertNotIn("merge --", text)


if __name__ == "__main__":
    unittest.main()
