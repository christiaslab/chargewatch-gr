"""Mutation tests for the staged-content rules and the vendor-term matcher, in temporary git repositories.

Standard library only. Each repository is created fresh, the file under test is
staged, and the scan must report the rule without echoing the file's text.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import commit_rules

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=root, env=GIT_ENV, check=True, capture_output=True, text=True,
    )
    return result.stdout.strip()


class VendorTermMatcherTest(unittest.TestCase):
    def test_word_hits_are_reported_lowercase_and_sorted(self) -> None:
        self.assertEqual(commit_rules.vendor_hits("Reviewed with Claude Code and OpenAI tools"), ["claude", "openai"])

    def test_path_and_host_forms_are_not_hits(self) -> None:
        for text in (".claude/settings.json", "CLAUDE.local.md", "https://developers.openai.com/", "codex/README.md"):
            self.assertEqual(commit_rules.vendor_hits(text), [], text)

    def test_partial_words_are_not_hits(self) -> None:
        self.assertEqual(commit_rules.vendor_hits("llamas geminis copilots"), [])

    def test_custom_terms_replace_the_default_list(self) -> None:
        self.assertEqual(commit_rules.vendor_hits("Claude and Acme", ("acme",)), ["acme"])


class LocalFileRuleTest(unittest.TestCase):
    def test_local_instruction_files(self) -> None:
        for name in ("CLAUDE.local.md", "AGENTS.local.md", "notes/foo.local.md", ".claude/settings.local.json"):
            self.assertEqual(commit_rules.local_file_rule(name), "local-instruction-file-staged", name)

    def test_secret_files_except_the_example(self) -> None:
        self.assertEqual(commit_rules.local_file_rule(".env"), "local-secret-file-staged")
        self.assertEqual(commit_rules.local_file_rule("backend/.env.production"), "local-secret-file-staged")
        self.assertIsNone(commit_rules.local_file_rule(".env.example"))
        self.assertIsNone(commit_rules.local_file_rule("AGENTS.md"))


class StagedScanTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        git(self.root, "init", "-q", "-b", "main")
        (self.root / ".gitignore").write_text("secrets/\n", encoding="utf-8")
        (self.root / "README.md").write_text("# temporary\n", encoding="utf-8")
        git(self.root, "add", ".gitignore", "README.md")
        git(self.root, "commit", "-q", "-m", "chore: bootstrap temporary repository")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def stage(self, relative: str, text: str, force: bool = False) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        git(self.root, "add", *(["-f"] if force else []), relative)

    def test_clean_stage_passes_with_no_advisory(self) -> None:
        self.stage("docs/note.md", "A plain note.\n")
        report = commit_rules.scan_staged(self.root)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["findings"], [])
        self.assertEqual(report["advisories"], [])

    def test_staged_local_instruction_file_fails(self) -> None:
        self.stage("CLAUDE.local.md", "private session routine\n")
        report = commit_rules.scan_staged(self.root)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn({"path": "CLAUDE.local.md", "rule": "local-instruction-file-staged"}, report["findings"])
        self.assertNotIn("private session routine", str(report))

    def test_staged_ignored_path_fails(self) -> None:
        self.stage("secrets/key.txt", "not-a-real-value\n", force=True)
        report = commit_rules.scan_staged(self.root)
        self.assertEqual(report["result"], "FAIL")
        self.assertIn({"path": "secrets/key.txt", "rule": "gitignored-path-staged"}, report["findings"])
        self.assertNotIn("not-a-real-value", str(report))

    def test_vendor_name_is_an_advisory_not_a_failure(self) -> None:
        self.stage("docs/decision.md", "The adapter targets Claude Code as the development environment.\n")
        report = commit_rules.scan_staged(self.root)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["advisories"], [{"path": "docs/decision.md", "rule": "vendor-name-in-content", "term": "claude"}])
        self.assertNotIn("development environment", str(report))

    def test_explicit_paths_are_scanned_without_staging(self) -> None:
        (self.root / "AGENTS.local.md").write_text("local\n", encoding="utf-8")
        report = commit_rules.scan_staged(self.root, ["AGENTS.local.md"])
        self.assertEqual(report["result"], "FAIL")

    def test_cli_exit_codes(self) -> None:
        def run(argv: list[str]) -> tuple[int, str]:
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = commit_rules.main(argv)
            return code, out.getvalue()

        self.stage("docs/note.md", "fine\n")
        code, text = run(["--root", str(self.root)])
        self.assertEqual(code, 0)
        self.assertIn('"result": "PASS"', text)
        self.stage(".env", "SECRET=synthetic\n", force=True)
        code, text = run(["--root", str(self.root)])
        self.assertEqual(code, 1)
        self.assertNotIn("synthetic", text)
        with tempfile.TemporaryDirectory() as plain:
            self.assertEqual(run(["--root", plain])[0], 2)


if __name__ == "__main__":
    unittest.main()
