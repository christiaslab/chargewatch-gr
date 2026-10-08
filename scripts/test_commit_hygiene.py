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


def commit(root: Path, message: str, author_email: str | None = None) -> str:
    env = GIT_ENV if author_email is None else {**GIT_ENV, "GIT_AUTHOR_EMAIL": author_email}
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "commit", "--allow-empty", "-q", "-m", message],
        cwd=root, env=env, check=True, capture_output=True, text=True,
    )
    return git(root, "rev-parse", "HEAD")


BOT_EMAIL = "49699333+dependabot[bot]@users.noreply.github.com"
BOT_SIGNED_OFF = "chore(deps): bump a dependency\n\nSigned-off-by: dependabot[bot] <support@example.invalid>"
MINIMAL_SPEC = (
    "# temporary specification\n"
    "spec_version: 1\n"
    "verification_command: python3 scripts/verify_repository.py\n"
    "bot_authors:\n"
    f"  - {BOT_EMAIL}\n"
)


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


class BotAuthorsHistoryTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        commit(self.root, CLEAN_MESSAGES[0])
        (self.root / "adapters").mkdir()
        (self.root / "adapters" / "project-spec.yaml").write_text(MINIMAL_SPEC, encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_signed_off_by_from_listed_bot_passes(self) -> None:
        commit(self.root, BOT_SIGNED_OFF, author_email=BOT_EMAIL)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report, {"passed": True, "commits": 2, "findings": []})

    def test_same_message_from_human_fails(self) -> None:
        sha = commit(self.root, BOT_SIGNED_OFF)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])
        self.assertNotIn("support@example.invalid", str(report))

    def test_bot_with_co_authored_by_fails(self) -> None:
        sha = commit(self.root, BOT_SIGNED_OFF + "\nCo-Authored-By: Someone <someone@example.invalid>", author_email=BOT_EMAIL)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])

    def test_bot_with_generated_signature_fails(self) -> None:
        sha = commit(self.root, BOT_SIGNED_OFF + "\nGenerated by some-tool 1.0", author_email=BOT_EMAIL)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "generated-signature"}])

    def test_missing_spec_means_no_bots(self) -> None:
        (self.root / "adapters" / "project-spec.yaml").unlink()
        sha = commit(self.root, BOT_SIGNED_OFF, author_email=BOT_EMAIL)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])

    def test_unparsable_spec_means_no_bots(self) -> None:
        (self.root / "adapters" / "project-spec.yaml").write_text("  - orphan item\n", encoding="utf-8")
        commit(self.root, BOT_SIGNED_OFF, author_email=BOT_EMAIL)
        self.assertFalse(commit_hygiene.check_history(self.root)["passed"])

    def test_spec_without_key_means_no_bots(self) -> None:
        (self.root / "adapters" / "project-spec.yaml").write_text("spec_version: 1\n", encoding="utf-8")
        commit(self.root, BOT_SIGNED_OFF, author_email=BOT_EMAIL)
        self.assertFalse(commit_hygiene.check_history(self.root)["passed"])


class InspectMessageTest(unittest.TestCase):
    def test_without_author_stays_strict(self) -> None:
        self.assertEqual(commit_hygiene.inspect_message(BOT_SIGNED_OFF), ["attribution-trailer"])
        self.assertEqual(commit_hygiene.inspect_message(BOT_SIGNED_OFF, bot_authors=(BOT_EMAIL,)), ["attribution-trailer"])

    def test_listed_bot_skips_only_signed_off_by(self) -> None:
        self.assertEqual(commit_hygiene.inspect_message(BOT_SIGNED_OFF, BOT_EMAIL, (BOT_EMAIL,)), [])
        message = BOT_SIGNED_OFF + "\nCo-authored-by: b\nGenerated with tool"
        self.assertEqual(commit_hygiene.inspect_message(message, BOT_EMAIL, (BOT_EMAIL,)),
                         ["attribution-trailer", "generated-signature"])

    def test_unlisted_author_stays_strict(self) -> None:
        self.assertEqual(commit_hygiene.inspect_message(BOT_SIGNED_OFF, "author@example.invalid", (BOT_EMAIL,)),
                         ["attribution-trailer"])

    def test_multiple_issues_are_reported_once_each_and_sorted(self) -> None:
        message = "fix: thing\n\nGenerated with tool\nCo-Authored-By: a\nCo-authored-by: b\n"
        self.assertEqual(commit_hygiene.inspect_message(message), ["attribution-trailer", "generated-signature"])

    def test_prose_mentioning_generation_mid_line_is_not_flagged(self) -> None:
        message = "docs: explain the build\n\nThe dashboard is generated by the build script from frozen data."
        self.assertEqual(commit_hygiene.inspect_message(message), [])


if __name__ == "__main__":
    unittest.main()
