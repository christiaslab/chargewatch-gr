"""Mutation tests for attribution hygiene, run against temporary git repositories."""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import commit_hygiene

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}

CLEAN_MESSAGES = (
    "chore: bootstrap temporary repository",
    "feat(plan): reject unknown fields\n\nClose the schema at every object level.\n\nVerification: 19 tests.",
    "Plain subject without a type prefix is not this check's concern",
)


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root, env=GIT_ENV, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


def commit(root: Path, message: str) -> str:
    git(root, "commit", "--allow-empty", "-q", "-m", message)
    return git(root, "rev-parse", "HEAD")


class CommitHygieneMutationTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        for message in CLEAN_MESSAGES:
            commit(self.root, message)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def assert_single_finding(self, sha: str, rule: str, offending_text: str) -> None:
        report = commit_hygiene.check_history(self.root)
        self.assertFalse(report["passed"])
        self.assertEqual(report["commits"], len(CLEAN_MESSAGES) + 1)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": rule}])
        self.assertNotIn(offending_text, str(report))

    def test_clean_history_passes(self) -> None:
        report = commit_hygiene.check_history(self.root)
        self.assertTrue(report["passed"])
        self.assertEqual(report["commits"], len(CLEAN_MESSAGES))
        self.assertEqual(report["findings"], [])

    def test_co_authored_by_trailer_fails(self) -> None:
        sha = commit(self.root, "fix: adjust tolerance\n\nCo-Authored-By: Someone <someone@example.invalid>")
        self.assert_single_finding(sha, "attribution-trailer", "someone@example.invalid")

    def test_signed_off_by_trailer_fails_case_insensitively(self) -> None:
        sha = commit(self.root, "fix: adjust tolerance\n\nsigned-off-by: Someone <someone@example.invalid>")
        self.assert_single_finding(sha, "attribution-trailer", "someone@example.invalid")

    def test_generated_with_signature_fails(self) -> None:
        sha = commit(self.root, "fix: adjust tolerance\n\n\U0001F916 Generated with Some Tool <https://example.invalid>")
        self.assert_single_finding(sha, "generated-signature", "example.invalid")

    def test_generated_by_line_fails(self) -> None:
        sha = commit(self.root, "fix: adjust tolerance\n\nGenerated-by: some-tool 1.0")
        self.assert_single_finding(sha, "generated-signature", "some-tool 1.0")

    def test_trailer_in_subject_line_fails(self) -> None:
        sha = commit(self.root, "Co-Authored-By: Someone <someone@example.invalid>")
        self.assert_single_finding(sha, "attribution-trailer", "someone@example.invalid")

    def test_merge_commit_with_trailer_fails(self) -> None:
        git(self.root, "checkout", "-q", "-b", "topic")
        commit(self.root, "feat: add topic work")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "merge", "-q", "--no-ff", "topic", "-m",
            "Merge branch topic\n\nCo-Authored-By: Someone <someone@example.invalid>")
        report = commit_hygiene.check_history(self.root)
        self.assertFalse(report["passed"])
        self.assertEqual([finding["rule"] for finding in report["findings"]], ["attribution-trailer"])

    def test_only_head_history_is_read(self) -> None:
        git(self.root, "checkout", "-q", "-b", "side")
        commit(self.root, "fix: side work\n\nCo-Authored-By: Someone <someone@example.invalid>")
        git(self.root, "checkout", "-q", "main")
        (self.root / "note.txt").write_text("draft\n", encoding="utf-8")
        git(self.root, "add", "note.txt")
        git(self.root, "stash", "push", "-q", "-m", "wip draft")
        report = commit_hygiene.check_history(self.root)
        self.assertTrue(report["passed"])
        self.assertEqual(report["commits"], len(CLEAN_MESSAGES))

    def test_empty_repository_has_no_findings(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            git(Path(empty), "init", "-q", "-b", "main")
            self.assertEqual(commit_hygiene.check_history(Path(empty)), {"passed": True, "commits": 0, "findings": []})


class InspectMessageTest(unittest.TestCase):
    def test_multiple_issues_are_reported_once_each_and_sorted(self) -> None:
        message = "fix: thing\n\nGenerated with tool\nCo-Authored-By: a\nCo-authored-by: b\n"
        self.assertEqual(commit_hygiene.inspect_message(message), ["attribution-trailer", "generated-signature"])

    def test_prose_mentioning_generation_mid_line_is_not_flagged(self) -> None:
        message = "docs: explain the build\n\nThe dashboard is generated by the build script from frozen data."
        self.assertEqual(commit_hygiene.inspect_message(message), [])


if __name__ == "__main__":
    unittest.main()
