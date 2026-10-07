"""Tests for the Dependabot sign-off exemption in commit_hygiene (docs/decisions.md #16).

The fixture is the full message of the real Dependabot commit c9d31710d482 from
pull request 13, the one that first failed kit-commit-history.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import commit_hygiene

FIXTURE = Path(__file__).parent / "fixtures" / "dependabot_commit_message.txt"
DEPENDABOT_NAME = "dependabot[bot]"
HUMAN = ("Test Author", "author@example.invalid")


def git(root: Path, *args: str, author: tuple[str, str] = HUMAN) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_AUTHOR_NAME": author[0],
        "GIT_AUTHOR_EMAIL": author[1],
        "GIT_COMMITTER_NAME": HUMAN[0],
        "GIT_COMMITTER_EMAIL": HUMAN[1],
    }
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root, env=env, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


class DependabotSignOffTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        git(self.root, "init", "-q", "-b", "main")
        git(self.root, "commit", "--allow-empty", "-q", "-m", "chore: bootstrap temporary repository")
        self.dependabot = (DEPENDABOT_NAME, commit_hygiene.DEPENDABOT_AUTHOR)
        self.real_message = FIXTURE.read_text(encoding="utf-8")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def commit(self, message: str, author: tuple[str, str]) -> str:
        git(self.root, "commit", "--allow-empty", "-q", "-m", message, author=author)
        return git(self.root, "rev-parse", "HEAD")

    def test_fixture_carries_the_sign_off(self) -> None:
        self.assertIn(commit_hygiene.DEPENDABOT_SIGN_OFF, self.real_message.splitlines())

    def test_real_dependabot_commit_passes(self) -> None:
        self.commit(self.real_message, self.dependabot)
        report = commit_hygiene.check_history(self.root)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["commits"], 2)

    def test_same_message_from_a_human_fails(self) -> None:
        sha = self.commit(self.real_message, HUMAN)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])

    def test_dependabot_with_another_sign_off_fails(self) -> None:
        sha = self.commit("chore(deps): bump x\n\nSigned-off-by: Someone <someone@example.invalid>", self.dependabot)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])

    def test_dependabot_with_co_author_fails(self) -> None:
        message = self.real_message + "\nCo-authored-by: Someone <someone@example.invalid>\n"
        sha = self.commit(message, self.dependabot)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "attribution-trailer"}])

    def test_dependabot_with_generated_signature_fails(self) -> None:
        sha = self.commit(self.real_message + "\nGenerated with Some Tool\n", self.dependabot)
        report = commit_hygiene.check_history(self.root)
        self.assertEqual(report["findings"], [{"commit": sha[:12], "rule": "generated-signature"}])

    def test_message_only_inspection_stays_strict(self) -> None:
        self.assertEqual(commit_hygiene.inspect_message(self.real_message), ["attribution-trailer"])


if __name__ == "__main__":
    unittest.main()
