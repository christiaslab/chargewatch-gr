"""Tests for the two adapter hooks: they fail open, block only on a positive finding, and never echo a value.

Each hook is run as a subprocess, the way the environment runs it, with
CLAUDE_PROJECT_DIR pointing at a temporary repository. Standard library only.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SESSION_START = REPOSITORY_ROOT / "scripts/hooks/session_start.py"
SECRETS_GUARD = REPOSITORY_ROOT / "scripts/hooks/pre_tool_secrets_guard.py"
# The fixtures below must themselves pass the write-time and commit-time guards, so the
# secret-like words are assembled at runtime instead of appearing as literals in this file.
WORD_TOKEN = "tok" + "en"
WORD_PASSWORD = "pass" + "word"
WORD_API_KEY = "API" + "_KEY"
MARKER = "synthetic-example-marker"
KEY_BLOCK_HEADER = "-----BEGIN RSA " + "PRIVATE" + " KEY-----"
# Secret-bearing file names for the read-side tests, assembled for the same reason.
NAME_ENV = "." + "env"
NAME_KEY_GLOB = "*." + "pem"
NAME_SSH_KEY = "id_" + "rsa"
NAME_CREDENTIALS = "credent" + "ials"

GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Test Author",
    "GIT_AUTHOR_EMAIL": "author@example.invalid",
    "GIT_COMMITTER_NAME": "Test Author",
    "GIT_COMMITTER_EMAIL": "author@example.invalid",
}


def run_hook(script: Path, project_dir: Path, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = {**GIT_ENV, "CLAUDE_PROJECT_DIR": str(project_dir)}
    return subprocess.run([sys.executable, str(script)], input=stdin, cwd=project_dir, env=env,
                          capture_output=True, text=True, timeout=30)


class HookFixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "scripts").mkdir()
        shutil.copy(REPOSITORY_ROOT / "scripts/pilot_core.py", self.root / "scripts/pilot_core.py")
        (self.root / "AGENTS.md").write_text(
            "| Latest session hand-off and open items | [docs/SESSION_HANDOFF_TEST.md](docs/SESSION_HANDOFF_TEST.md) |\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, env=GIT_ENV, check=True)
        subprocess.run(["git", "-c", "commit.gpgsign=false", "add", "-A"], cwd=self.root, env=GIT_ENV, check=True)
        subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "-q", "-m", "chore: bootstrap temporary repository"],
                       cwd=self.root, env=GIT_ENV, check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()


class SessionStartTest(HookFixture):
    def test_banner_reports_head_branch_and_handoff(self) -> None:
        result = run_hook(SESSION_START, self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("PAES session banner", result.stdout)
        self.assertIn("on main, working tree clean", result.stdout)
        self.assertIn("docs/SESSION_HANDOFF_TEST.md", result.stdout)
        self.assertIn("verification: not run at session start", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_banner_notes_uncommitted_changes(self) -> None:
        (self.root / "new.txt").write_text("x\n", encoding="utf-8")
        result = run_hook(SESSION_START, self.root)
        self.assertEqual(result.returncode, 0)
        self.assertIn("has uncommitted changes", result.stdout)

    def test_banner_fails_open_outside_a_repository(self) -> None:
        with tempfile.TemporaryDirectory() as plain:
            result = run_hook(SESSION_START, Path(plain))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)
        self.assertIn("session banner unavailable", result.stderr)


class SecretsGuardTest(HookFixture):
    def payload(self, tool: str, **tool_input: object) -> str:
        return json.dumps({"tool_name": tool, "tool_input": tool_input})

    def test_clean_write_passes(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Write", file_path="a.py", content="status = 'fine'\n"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_secret_like_write_is_blocked_without_echo(self) -> None:
        content = f'{WORD_TOKEN} = "{MARKER}"\n'
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Write", file_path="a.py", content=content))
        self.assertEqual(result.returncode, 2)
        self.assertIn("secret-like-assignment", result.stderr)
        self.assertNotIn(MARKER, result.stderr)
        self.assertNotIn(MARKER, result.stdout)

    def test_secret_like_edit_and_bash_are_blocked(self) -> None:
        edit = run_hook(SECRETS_GUARD, self.root, self.payload("Edit", file_path="a.py", old_string="x", new_string=f"{WORD_PASSWORD}: hunter-synthetic"))
        self.assertEqual(edit.returncode, 2)
        bash = run_hook(SECRETS_GUARD, self.root, self.payload("Bash", command=f"export {WORD_API_KEY}=synthetic-value && ./run"))
        self.assertEqual(bash.returncode, 2)
        self.assertNotIn("synthetic", bash.stderr)

    def test_private_key_block_is_blocked(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Write", file_path="k", content=KEY_BLOCK_HEADER + "\n"))
        self.assertEqual(result.returncode, 2)

    def test_other_tools_and_read_only_bash_pass(self) -> None:
        read = run_hook(SECRETS_GUARD, self.root, self.payload("Read", file_path="a.py"))
        self.assertEqual(read.returncode, 0)
        bash = run_hook(SECRETS_GUARD, self.root, self.payload("Bash", command="git status --short"))
        self.assertEqual(bash.returncode, 0)

    def test_malformed_payload_fails_open(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, "{not json")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)
        self.assertIn("secrets guard skipped", result.stderr)

    def test_missing_pilot_core_fails_open(self) -> None:
        (self.root / "scripts/pilot_core.py").unlink()
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Write", file_path="a", content=f'{WORD_TOKEN} = "x"'))
        self.assertEqual(result.returncode, 0)
        self.assertIn("secrets guard skipped", result.stderr)


class ReadSideGuardTest(HookFixture):
    """The read side: a Read, Grep or Glob that names a secret-bearing file is blocked by path component."""

    def payload(self, tool: str, **tool_input: object) -> str:
        return json.dumps({"tool_name": tool, "tool_input": tool_input})

    def assert_blocked_without_echo(self, result: subprocess.CompletedProcess[str], *values: str) -> None:
        self.assertEqual(result.returncode, 2)
        self.assertIn("secret-bearing-path", result.stderr)
        self.assertEqual(result.stdout, "")
        for value in values:
            self.assertNotIn(value, result.stderr)

    def test_read_of_env_file_is_blocked_without_echo(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Read", file_path=NAME_ENV))
        self.assert_blocked_without_echo(result, NAME_ENV)

    def test_read_of_placeholder_and_ordinary_files_passes(self) -> None:
        for name in (NAME_ENV + ".example", "README.md", "adapters/kit-templates/settings.json.template"):
            with self.subTest(name=name):
                result = run_hook(SECRETS_GUARD, self.root, self.payload("Read", file_path=name))
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stderr, "")

    def test_grep_path_naming_a_dotted_env_variant_is_blocked(self) -> None:
        path = "config/" + NAME_ENV + ".local"
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Grep", pattern="x", path=path))
        self.assert_blocked_without_echo(result, path)

    def test_grep_glob_reaching_key_files_is_blocked(self) -> None:
        glob = "**/" + NAME_KEY_GLOB
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Grep", pattern="x", glob=glob))
        self.assert_blocked_without_echo(result, glob)

    def test_glob_pattern_reaching_ssh_keys_is_blocked(self) -> None:
        pattern = "**/" + NAME_SSH_KEY + "*"
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Glob", pattern=pattern))
        self.assert_blocked_without_echo(result, pattern)

    def test_clean_glob_passes(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Glob", pattern="scripts/**/*.py", path="."))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_nested_credentials_component_is_blocked(self) -> None:
        path = "secrets/.aws/" + NAME_CREDENTIALS
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Read", file_path=path))
        self.assert_blocked_without_echo(result, path)

    def test_missing_or_non_string_field_fails_open(self) -> None:
        for payload in (self.payload("Read"), self.payload("Grep", pattern="x"), self.payload("Read", file_path=7)):
            with self.subTest(payload=payload):
                result = run_hook(SECRETS_GUARD, self.root, payload)
                self.assertEqual(result.returncode, 0)

    def test_brace_alternation_case_folding_and_other_credential_names_are_blocked(self) -> None:
        cases = {
            "brace": ("Glob", {"pattern": "**/*.{py," + NAME_KEY_GLOB[1:] + "}"}),
            "upper": ("Read", {"file_path": NAME_ENV.upper()}),
            "envrc": ("Read", {"file_path": NAME_ENV + "rc"}),
            "netrc": ("Read", {"file_path": "home/.net" + "rc"}),
            "credentials-json": ("Read", {"file_path": NAME_CREDENTIALS + ".json"}),
            "secrets-file": ("Read", {"file_path": "config/sec" + "rets.yaml"}),
            "glob-path": ("Glob", {"pattern": "*.py", "path": "deploy/" + NAME_ENV + ".production"}),
        }
        for label, (tool, tool_input) in cases.items():
            with self.subTest(label=label):
                result = run_hook(SECRETS_GUARD, self.root, self.payload(tool, **tool_input))
                self.assert_blocked_without_echo(result, *(v for v in tool_input.values() if isinstance(v, str)))

    def test_glob_patterns_are_matched_against_the_secret_names(self) -> None:
        # kit v10, finding 1 of the fifth chargewatch-gr trial: a wildcard is evaluated as a pattern
        # against the secret names, never deleted; placeholder copies stay readable.
        example = NAME_ENV + ".example"
        blocked_values = ("id_*", "*.p?m", example + "*", NAME_ENV + "*", NAME_KEY_GLOB, "sec" + "rets.*",
                          NAME_SSH_KEY, "server." + NAME_KEY_GLOB[2:], example + ".production",
                          "*." + "key", "**/id_*", NAME_CREDENTIALS + ".*")
        # generic searches: a pattern that also reaches an ordinary project file is not aimed at secrets
        allowed_values = (example, NAME_ENV + ".sample", NAME_ENV + ".template", NAME_ENV + ".dist",
                          "*.py", "src/*", "README*", "*.example", "config/*.example",
                          "*.json", "**/*.json", "*.yaml", "*.yml", "*.toml",
                          # Hidden-file, rc and short-prefix searches are generic: they reach ordinary files too.
                          ".*", "**/.*", ".??*", "*rc", "se*", "c*")
        for value in blocked_values:
            with self.subTest(blocked=value):
                result = run_hook(SECRETS_GUARD, self.root, self.payload("Glob", pattern=value))
                self.assert_blocked_without_echo(result, value)
        for value in allowed_values:
            with self.subTest(allowed=value):
                result = run_hook(SECRETS_GUARD, self.root, self.payload("Glob", pattern=value))
                self.assertEqual(result.returncode, 0, value)
                self.assertEqual(result.stderr, "")

    def test_grep_glob_pattern_and_read_path_share_the_pattern_semantics(self) -> None:
        grep = run_hook(SECRETS_GUARD, self.root, self.payload("Grep", pattern="x", glob="**/id_*"))
        self.assert_blocked_without_echo(grep, "**/id_*")
        placeholder = run_hook(SECRETS_GUARD, self.root, self.payload("Grep", pattern="x", glob="config/*.example"))
        self.assertEqual(placeholder.returncode, 0)

    def test_clean_read_does_not_need_pilot_core(self) -> None:
        (self.root / "scripts/pilot_core.py").unlink()
        result = run_hook(SECRETS_GUARD, self.root, self.payload("Read", file_path="README.md"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")

    def test_non_object_tool_input_fails_open_with_one_line(self) -> None:
        result = run_hook(SECRETS_GUARD, self.root, json.dumps({"tool_name": "Read", "tool_input": [NAME_ENV]}))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)
        self.assertIn("secrets guard skipped", result.stderr)
        self.assertNotIn(NAME_ENV, result.stderr)


if __name__ == "__main__":
    unittest.main()
