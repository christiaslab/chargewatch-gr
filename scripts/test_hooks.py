"""Tests for the adapter hooks: they fail open, only the secrets guard blocks and only on a positive finding, and none
echoes a value; the event feed (Decision 0019) copies nothing but its whitelist.

Each hook is run as a subprocess, the way the environment runs it, with
CLAUDE_PROJECT_DIR pointing at a temporary repository. Standard library only.
"""
from __future__ import annotations

import importlib.util
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
# Decision 0019: the event feed is PAES-only (point 7); its tests run where the script is and skip in a kit target.
EVENT_FEED = REPOSITORY_ROOT / "scripts/hooks/event_feed.py"
# Decision 0024: the context guard is PAES-only; its tests run where the script is and skip in a kit target.
CONTEXT_GUARD = REPOSITORY_ROOT / "scripts/hooks/context_guard.py"
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

    def test_negated_class_samples_a_character_the_class_does_not_exclude(self) -> None:
        # kit v11, finding 1 of the sixth chargewatch-gr trial: a fixed x made [!x] sample to the one name the
        # pattern cannot match, so the placeholder was allowed and the harmless suffix was blocked.
        example = NAME_ENV + ".example"
        # Review lane, kit v11: a single letter sample spelled the placeholder, .env.s[!xyz]mple reaching only .env.sample.
        blocked_values = (NAME_ENV + ".e[!x]ample", NAME_ENV + ".[!a]ocal", "id_[!x]sa", "*.pe[!x]", "*.[!x]em",
                          NAME_ENV + ".s[!xyz]mple", NAME_ENV + ".e[!0-9_-]ample", NAME_ENV + ".[!x][!y]ample",
                          NAME_ENV + ".e[!s]ample")
        allowed_values = ("*.pf[!x]", "*.p[!f]x", example, "src/[!_]*.py", "*.[!p]em", "*.[!e]xample", "config/[!.]*.example")
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


LEAK = "leak" + "-planted-value"  # lower case: a URL host is folded by the parser
FEED_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PostToolUseFailure",
               "SubagentStart", "SubagentStop", "Stop", "SessionEnd")
RECORD_KEYS = ["version", "timestamp", "event", "session", "agent", "agent_type", "prompt_id", "tool", "tool_use_id", "meta"]
# Decision 0019 point 1: the only free text a record carries, each clipped to 120 characters.
FREE_TEXT_KEYS = {"label", "description", "error"}
# The structural fields the whitelist of point 1 copies in name or pattern shape: a relative glob pattern, a subagent
# type, a skill name, a model name, a URL host, and a path only when it is inside the repository. The leak test plants
# the constant in every one of them, plants paths outside the repository, which never arrive, and asserts that the
# constant arrives through exactly the fields named here and the three free-text fields (hand-off of session 16, M3).
COPIED_STRUCTURAL_KEYS = {"pattern", "subagent_type", "skill", "model", "host"}
FEED_TOOLS = ("Agent", "Skill", "Read", "Glob", "Grep", "Bash", "WebFetch", "Edit", "Write", "WebSearch")


def tool_input_for(tool: str, text: str) -> dict:
    """Every input field of every tool the whitelist knows, each carrying the same text; a path field carries it as
    a path outside the repository, the case point 5 forbids."""
    outside = str(Path(tempfile.gettempdir()).resolve() / ("outside-" + text))
    inputs = {
        "Agent": {"subagent_type": text, "description": text, "prompt": text, "model": text, "run_in_background": True},
        "Skill": {"skill": text, "args": text},
        "Read": {"file_path": outside, "offset": 1},
        "Glob": {"pattern": "**/" + text + "*.py", "path": outside},
        "Grep": {"pattern": text, "path": outside, "glob": text},
        "Bash": {"command": text, "description": text, "run_in_background": False},
        "WebFetch": {"url": "https://" + text + ".invalid/" + text + "?q=" + text, "prompt": text},
        "Edit": {"file_path": outside, "old_string": text, "new_string": text},
        "Write": {"file_path": outside, "content": text},
        "WebSearch": {"query": text},
    }
    return inputs[tool]


class EventFeedFixture(HookFixture):
    """The feed directory is redirected by CLAUDE_PROJECT_DIR: every record lands under the temporary root."""

    def setUp(self) -> None:
        super().setUp()
        agents = self.root / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "explorer.md").write_text("---\nname: explorer\nmodel: model-pinned-in-agent-file\ntools: Read\n---\n", encoding="utf-8")
        (agents / "unpinned.md").write_text("---\nname: unpinned\ntools: Read\n---\n", encoding="utf-8")

    def feed_files(self) -> list[Path]:
        return sorted((self.root / "logs" / "events").glob("*.jsonl")) if (self.root / "logs" / "events").is_dir() else []

    def records(self) -> list[dict]:
        return [json.loads(line) for path in self.feed_files() for line in path.read_text(encoding="utf-8").splitlines()]

    def run_feed(self, payload: object) -> subprocess.CompletedProcess[str]:
        return run_hook(EVENT_FEED, self.root, payload if isinstance(payload, str) else json.dumps(payload))

    def payload(self, event: str, text: str, tool: str = "Bash", **extra: object) -> dict:
        body: dict = {"hook_event_name": event, "session_id": "session-1", "transcript_path": text, "cwd": text,
                      "permission_mode": "default", "prompt_id": "prompt-1"}
        if event in ("PreToolUse", "PostToolUse", "PostToolUseFailure"):
            body.update(tool_name=tool, tool_input=tool_input_for(tool, text), tool_use_id="toolu-1")
        if event == "PostToolUse":
            body["tool_response"] = {"stdout": text, "content": text}
        if event == "PostToolUseFailure":
            body["error"] = text + "\nsecond line " + text
        if event == "UserPromptSubmit":
            body["prompt"] = text
        if event == "SessionStart":
            body.update(source=text, model=text, session_title=text)
        if event in ("SubagentStart", "SubagentStop"):
            body.update(agent_id="agent-1", agent_type=text, agent_transcript_path=text)
        if event in ("SubagentStop", "Stop"):
            body.update(last_assistant_message=text, stop_hook_active=False)
        if event == "SessionEnd":
            body["reason"] = text
        body["unexpected_field"] = text
        body.update(extra)
        return body


@unittest.skipUnless(EVENT_FEED.is_file(), "the event feed hook is PAES-only (Decision 0019 point 7)")
class EventFeedLeakTest(EventFeedFixture):
    """Decision 0019 point 5: LEAK planted in every field of every payload kind reaches a record only through the
    three clipped free-text fields, and never from a prompt, a command, a content, a result, a pattern or a path
    outside the repository."""

    def test_leak_reaches_a_record_only_through_the_named_fields(self) -> None:
        payloads = [self.payload(event, LEAK) for event in FEED_EVENTS if event not in ("PreToolUse", "PostToolUse", "PostToolUseFailure")]
        payloads += [self.payload(event, LEAK, tool) for event in ("PreToolUse", "PostToolUse", "PostToolUseFailure") for tool in FEED_TOOLS]
        for body in payloads:  # the identifier fields carry the constant in a shape no identifier has
            body.update(session_id=LEAK + " session", agent_id=LEAK + " agent", prompt_id=LEAK + " prompt", tool_use_id=LEAK + " use")
            if "agent_type" in body:
                body["agent_type"] = LEAK + " type"
        for body in payloads:
            result = self.run_feed(body)
            self.assertEqual((result.returncode, result.stdout), (0, ""), body["hook_event_name"])
            self.assertEqual(result.stderr, "", body["hook_event_name"])
        records = self.records()
        self.assertEqual(len(records), len(payloads))
        arrived_through: set[str] = set()
        for entry in records:
            for key, value in entry.items():
                if key == "meta":
                    continue
                self.assertNotIn(LEAK, json.dumps(value), f"{entry['event']}: top-level key {key} carries the planted value")
            for key, value in entry["meta"].items():
                if LEAK in json.dumps(value):
                    self.assertIn(key, FREE_TEXT_KEYS | COPIED_STRUCTURAL_KEYS, f"{entry['event']} {entry['tool']}: meta key {key} carries the planted value")
                    if key in FREE_TEXT_KEYS:
                        self.assertLessEqual(len(value), 120)
                        self.assertNotIn("\n", value)
                    else:
                        self.assertNotIn(" ", value)
                    arrived_through.add(key)
        # The constant must arrive through each named field, so the test proves them copied on purpose and no other.
        self.assertEqual(arrived_through, FREE_TEXT_KEYS | COPIED_STRUCTURAL_KEYS)
        self.assertEqual(len(self.records()), len(payloads))

    def test_whitelist_is_closed_per_tool(self) -> None:
        expected = {
            "Agent": {"subagent_type", "model", "background", "label", "prompt_sha256", "prompt_bytes"},
            "Skill": {"skill"}, "Read": {"path", "outside_repository"}, "Glob": {"pattern"},
            "Grep": {"path", "outside_repository"}, "Bash": {"description", "background"}, "WebFetch": {"host"},
            "Edit": set(), "Write": set(), "WebSearch": set(),
        }
        expected["Glob"] = {"pattern", "outside_repository"}
        for tool in FEED_TOOLS:
            self.run_feed(self.payload("PreToolUse", "plain", tool))
        by_tool = {entry["tool"]: entry["meta"] for entry in self.records()}
        for tool, keys in expected.items():
            with self.subTest(tool=tool):
                self.assertEqual(set(by_tool[tool]), keys)
        self.assertEqual(by_tool["Grep"], {"path": None, "outside_repository": True})
        self.assertEqual(by_tool["Agent"]["subagent_type"], "plain")
        self.assertEqual(by_tool["Agent"]["model"], "plain")  # the call's override wins (point 3)
        self.assertEqual(by_tool["WebFetch"]["host"], "plain.invalid")
        self.assertEqual(by_tool["Glob"]["pattern"], "**/plain*.py")
        self.assertEqual(by_tool["Skill"]["skill"], "plain")

    def test_prompt_and_path_outside_the_repository_never_arrive(self) -> None:
        outside = str(Path(tempfile.gettempdir()).resolve() / ("outside-" + LEAK))
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": outside}))
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "../" + LEAK}))
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "scripts/pilot_core.py"}))
        self.run_feed(self.payload("PreToolUse", "x", "Grep", tool_input={"pattern": LEAK, "path": str(self.root / "scripts")}))
        self.run_feed(self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "explorer", "prompt": LEAK, "description": "d"}))
        self.run_feed(self.payload("UserPromptSubmit", LEAK))
        self.run_feed(self.payload("PreToolUse", "x", "Glob", tool_input={"pattern": outside + "/**"}))
        self.run_feed(self.payload("PreToolUse", "x", "Glob", tool_input={"pattern": "../" + LEAK + "/*.py"}))
        self.run_feed(self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "x" * 65, "model": "has space " + LEAK, "prompt": "p"}))
        text = "\n".join(path.read_text(encoding="utf-8") for path in self.feed_files())
        self.assertNotIn(LEAK, text)
        records = self.records()
        self.assertEqual([(r["meta"].get("path"), r["meta"].get("outside_repository")) for r in records[:4]],
                         [(None, True), (None, True), ("scripts/pilot_core.py", False), ("scripts", False)])
        self.assertEqual(records[4]["meta"]["prompt_bytes"], len(LEAK.encode("utf-8")))
        self.assertEqual(len(records[4]["meta"]["prompt_sha256"]), 64)
        self.assertEqual(records[5]["meta"], {"prompt_chars": len(LEAK)})
        self.assertEqual([(r["meta"]["pattern"], r["meta"]["outside_repository"]) for r in records[6:8]], [(None, True), (None, True)])
        self.assertEqual((records[8]["meta"]["subagent_type"], records[8]["meta"]["model"]), (None, "inherited"))

    def feed_text(self) -> str:
        return "\n".join(path.read_text(encoding="utf-8") for path in self.feed_files())

    def test_relative_path_from_a_cwd_inside_the_repository_is_root_relative(self) -> None:
        inside = self.root / "sub" / "dir"
        inside.mkdir(parents=True)
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "file.py"}, cwd=str(inside)))
        self.run_feed(self.payload("PreToolUse", "x", "Grep", tool_input={"pattern": "p", "path": "."}, cwd=str(inside)))
        link_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(link_tmp.cleanup)
        link = Path(link_tmp.name) / "link"
        link.symlink_to(inside, target_is_directory=True)
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "via_link.py"}, cwd=str(link)))
        self.assertEqual([(r["meta"]["path"], r["meta"]["outside_repository"]) for r in self.records()],
                         [("sub/dir/file.py", False), ("sub/dir", False), ("sub/dir/via_link.py", False)])

    def test_relative_path_from_a_cwd_outside_the_repository_never_arrives(self) -> None:
        outside_tmp = tempfile.TemporaryDirectory()
        self.addCleanup(outside_tmp.cleanup)
        outside = Path(outside_tmp.name).resolve() / ("outside-" + LEAK)
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "file-" + LEAK + ".py"}, cwd=str(outside)))
        self.run_feed(self.payload("PreToolUse", "x", "Grep", tool_input={"pattern": "p", "path": LEAK}, cwd=str(outside)))
        self.assertNotIn(LEAK, self.feed_text())
        self.assertEqual([(r["meta"]["path"], r["meta"]["outside_repository"]) for r in self.records()],
                         [(None, True), (None, True)])

    def test_relative_path_climbing_from_a_subdirectory_stays_inside_until_it_leaves_the_tree(self) -> None:
        sub = self.root / "sub"
        sub.mkdir()
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "../file.py"}, cwd=str(sub)))
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": "../../" + LEAK}, cwd=str(sub)))
        self.run_feed(self.payload("PreToolUse", "x", "Read", tool_input={"file_path": LEAK}, cwd=str(sub) + "\u0000" + LEAK))
        self.assertNotIn(LEAK, self.feed_text())
        self.assertEqual([(r["meta"]["path"], r["meta"]["outside_repository"]) for r in self.records()],
                         [("file.py", False), (None, True), (None, True)])

    def test_relative_glob_pattern_is_clipped_before_the_planted_tail(self) -> None:
        spec = importlib.util.spec_from_file_location("event_feed", EVENT_FEED)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        pattern = "src/" + "a" * module.CLIP + "/" + LEAK + "/*.py"
        self.assertNotIn(LEAK, pattern[:module.CLIP])
        self.run_feed(self.payload("PreToolUse", "x", "Glob", tool_input={"pattern": pattern}))
        self.assertNotIn(LEAK, self.feed_text())
        meta = self.records()[0]["meta"]
        self.assertEqual(len(meta["pattern"]), module.CLIP)
        self.assertEqual((meta["pattern"], meta["outside_repository"]), (pattern[:module.CLIP], False))

    def test_identifiers_without_token_shape_are_dropped(self) -> None:
        self.run_feed(self.payload("Stop", "x", session_id="has space " + LEAK, agent_id="x" * 81, prompt_id=7))
        entry = self.records()[0]
        self.assertEqual((entry["session"], entry["agent"], entry["prompt_id"]), (None, None, None))
        self.assertNotIn(LEAK, json.dumps(entry))


@unittest.skipUnless(EVENT_FEED.is_file(), "the event feed hook is PAES-only (Decision 0019 point 7)")
class EventFeedHermeticTest(EventFeedFixture):
    """Decision 0019 point 5: every admitted event against a redirected feed directory; one record per payload,
    the fixed key order, exit 0, empty standard output, a non-null model on every dispatch record."""

    def test_one_record_per_payload_in_fixed_key_order(self) -> None:
        payloads = [self.payload(event, "plain", "Agent") for event in FEED_EVENTS]
        for body in payloads:
            result = self.run_feed(body)
            self.assertEqual(result.returncode, 0, body["hook_event_name"])
            self.assertEqual(result.stdout, "", body["hook_event_name"])
            self.assertEqual(result.stderr, "", body["hook_event_name"])
        self.assertEqual(len(self.feed_files()), 1)
        self.assertRegex(self.feed_files()[0].name, r"^\d{4}-\d{2}-\d{2}\.jsonl$")
        records = self.records()
        self.assertEqual([r["event"] for r in records], list(FEED_EVENTS))
        for entry in records:
            self.assertEqual(list(entry), RECORD_KEYS)
            self.assertEqual(entry["version"], 1)
            self.assertRegex(entry["timestamp"], r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
            self.assertEqual(entry["session"], "session-1")
            self.assertEqual(entry["prompt_id"], "prompt-1")
        self.assertEqual(records[0]["meta"], {"model": "plain"})  # SessionStart: the session model the payload names
        self.run_feed(self.payload("SessionStart", "x", model="not a name"))
        self.assertEqual(self.records()[-1]["meta"], {})
        self.assertEqual(records[1]["meta"], {"prompt_chars": 5})
        self.assertEqual(records[4]["meta"]["error"], "plain")
        self.assertEqual(records[5]["agent"], "agent-1")
        self.assertEqual(records[7]["meta"], {})
        self.assertEqual(records[8]["meta"], {})

    def test_model_is_never_null_on_a_dispatch_record(self) -> None:
        cases = {
            "override": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "explorer", "model": "model-from-call-override", "prompt": "p"}), "model-from-call-override"),
            "agent-file-pin": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "explorer", "prompt": "p"}), "model-pinned-in-agent-file"),
            "session-model": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "unpinned", "prompt": "p"}, model="model-named-by-session"), "model-named-by-session"),
            "inherited": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "unpinned", "prompt": "p"}), "inherited"),
            "unknown-type": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "../explorer", "prompt": "p"}), "inherited"),
            "empty-override": (self.payload("PreToolUse", "x", "Agent", tool_input={"subagent_type": "explorer", "model": "", "prompt": "p"}), "model-pinned-in-agent-file"),
            "subagent-start": (self.payload("SubagentStart", "x", agent_type="explorer"), "model-pinned-in-agent-file"),
            "subagent-stop-unpinned": (self.payload("SubagentStop", "x", agent_type="unpinned"), "inherited"),
            "subagent-stop-no-type": (self.payload("SubagentStop", "x", agent_type=None), "inherited"),
            "post-tool-use": (self.payload("PostToolUse", "x", "Agent", tool_input={"subagent_type": "explorer", "prompt": "p"}), "model-pinned-in-agent-file"),
            "failure": (self.payload("PostToolUseFailure", "x", "Agent", tool_input={"subagent_type": "explorer", "prompt": "p"}), "model-pinned-in-agent-file"),
            "override-wins": (self.payload("PostToolUse", "x", "Agent"), "x"),
        }
        for label, (body, _) in cases.items():
            self.assertEqual(self.run_feed(body).returncode, 0, label)
        records = self.records()
        self.assertEqual(len(records), len(cases))
        for (label, (_, expected)), entry in zip(cases.items(), records):
            with self.subTest(label=label):
                self.assertIsInstance(entry["meta"].get("model"), str)
                self.assertTrue(entry["meta"]["model"])
                self.assertEqual(entry["meta"]["model"], expected)

    def test_unparsed_payload_produces_one_record_without_content(self) -> None:
        for raw in ("{not json", json.dumps([LEAK]), json.dumps("x"), ""):
            result = self.run_feed(raw)
            self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""), raw)
        unknown = self.run_feed({"hook_event_name": "Notification", "session_id": "s", "message": LEAK})
        self.assertEqual(unknown.returncode, 0)
        records = self.records()
        self.assertEqual(len(records), 5)
        for entry in records:
            self.assertEqual(list(entry), RECORD_KEYS)
            self.assertEqual(entry["meta"], {"unparsed": True})
            self.assertNotIn(LEAK, json.dumps(entry))
        self.assertEqual(records[4]["session"], "s")

    def test_hook_fails_open_when_the_feed_cannot_be_written(self) -> None:
        (self.root / "logs").write_text("a file where the directory should be\n", encoding="utf-8")
        result = self.run_feed(self.payload("Stop", "x"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertEqual(len(result.stderr.strip().splitlines()), 1)
        self.assertIn("event feed skipped", result.stderr)

    def test_records_append_across_runs_and_the_feed_is_ignored_by_git(self) -> None:
        for _ in range(3):
            self.run_feed(self.payload("Stop", "x"))
        self.assertEqual(len(self.records()), 3)
        ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("logs/", ignore)


@unittest.skipUnless(CONTEXT_GUARD.is_file(), "the context guard is PAES-only (Decision 0024)")
class ContextGuardTest(HookFixture):
    DENIED = ("Agent", "Task", "Edit", "Write", "MultiEdit", "NotebookEdit")

    def transcript(self, *usages: dict, extra: str = "") -> Path:
        path = self.root / "transcript.jsonl"
        lines = [json.dumps({"type": "user", "message": {"content": "hello"}})]
        for usage in usages:
            lines.append(json.dumps({"type": "assistant", "message": {"usage": usage}}))
            lines.append(json.dumps({"type": "user", "message": {"content": "tool result"}}))
        path.write_text("\n".join(lines) + "\n" + extra, encoding="utf-8")
        return path

    def window(self, total: int) -> Path:
        return self.transcript({"input_tokens": 10, "cache_read_input_tokens": total - 1010, "cache_creation_input_tokens": 1000})

    def guard(self, transcript: Path | None, tool: str, tool_input: dict | None = None) -> subprocess.CompletedProcess[str]:
        payload = {"hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input or {}}
        if transcript is not None:
            payload["transcript_path"] = str(transcript)
        return run_hook(CONTEXT_GUARD, self.root, json.dumps(payload))

    def decision(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stderr, "")
        output = json.loads(result.stdout)["hookSpecificOutput"]
        self.assertEqual(output["hookEventName"], "PreToolUse")
        return output

    @staticmethod
    def input_for(tool: str, target: str) -> dict:
        return {"notebook_path": target} if tool == "NotebookEdit" else {"file_path": target, "content": "x"}

    def test_sum_is_taken_from_the_last_assistant_usage_and_below_warn_prints_nothing(self) -> None:
        early = {"input_tokens": 120_000, "cache_read_input_tokens": 50_000, "cache_creation_input_tokens": 1}
        last = {"input_tokens": 3, "cache_read_input_tokens": 90_000, "cache_creation_input_tokens": 19_000, "output_tokens": 999_999}
        result = self.guard(self.transcript(early, last), "Write", {"file_path": "README.md"})
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        last["cache_creation_input_tokens"] = 20_000  # 110,003: now above the warning, and the figure is the last sum
        output = self.decision(self.guard(self.transcript(early, last), "Read", {"file_path": "README.md"}))
        self.assertIn("110,003 tokens", output["additionalContext"])

    def test_top_level_usage_is_accepted(self) -> None:
        path = self.root / "transcript.jsonl"
        path.write_text(json.dumps({"type": "assistant", "usage": {"input_tokens": 120_000}}) + "\n", encoding="utf-8")
        self.assertIn("120,000 tokens", self.decision(self.guard(path, "Bash"))["additionalContext"])

    def test_above_warn_returns_additional_context_with_the_figure(self) -> None:
        for tool in self.DENIED + ("Bash", "Read"):
            with self.subTest(tool=tool):
                output = self.decision(self.guard(self.window(120_500), tool, self.input_for(tool, "src/app.py")))
                self.assertNotIn("permissionDecision", output)
                self.assertIn("context guard: 120,500 tokens in the window, above 110,000", output["additionalContext"])
                self.assertIn("Decision 0024", output["additionalContext"])

    def test_above_hard_denies_write_and_spawn_tools_only(self) -> None:
        transcript = self.window(160_000)
        for tool in self.DENIED:
            with self.subTest(tool=tool):
                output = self.decision(self.guard(transcript, tool, self.input_for(tool, "src/app.py")))
                self.assertEqual(output["permissionDecision"], "deny")
                self.assertIn("160,000 tokens in the window, above 150,000", output["permissionDecisionReason"])
                self.assertIn("python3 scripts/push_increment.py", output["permissionDecisionReason"])
        for tool, tool_input in (("Bash", {"command": "python3 scripts/verify_repository.py"}), ("Read", {"file_path": "src/app.py"})):
            with self.subTest(tool=tool):
                output = self.decision(self.guard(transcript, tool, tool_input))
                self.assertNotIn("permissionDecision", output)
                self.assertIn("160,000 tokens", output["additionalContext"])

    def test_above_hard_the_handoff_agents_md_and_a_brief_stay_writable_and_agent_does_not(self) -> None:
        transcript = self.window(200_000)
        for relative in ("docs/SESSION_HANDOFF_2026-10-07_X.md", "AGENTS.md", "tasks/x.json"):
            for target in (relative, str(self.root / relative)):
                for tool in ("Write", "Edit", "MultiEdit"):
                    with self.subTest(target=target, tool=tool):
                        output = self.decision(self.guard(transcript, tool, {"file_path": target}))
                        self.assertNotIn("permissionDecision", output)
                        self.assertIn("200,000 tokens", output["additionalContext"])
        for target in ("docs/SESSION_HANDOFF_X.txt", "docs/old/SESSION_HANDOFF_X.md", "tasks/sub/x.json", "sub/AGENTS.md",
                       "../AGENTS.md", "/elsewhere/AGENTS.md", "tasks/x.json.bak"):
            with self.subTest(target=target):
                self.assertEqual(self.decision(self.guard(transcript, "Write", {"file_path": target}))["permissionDecision"], "deny")
        agent = self.decision(self.guard(transcript, "Agent", {"file_path": "AGENTS.md", "prompt": "x"}))
        self.assertEqual(agent["permissionDecision"], "deny")

    def test_a_symbolic_link_named_like_an_exempt_file_is_judged_by_its_target(self) -> None:
        transcript = self.window(160_000)
        (self.root / "tasks").mkdir()
        (self.root / "docs").mkdir()
        (self.root / "scripts/x.py").write_text("x = 1\n", encoding="utf-8")
        outside = Path(self._tmp.name + "-outside.md")
        self.addCleanup(lambda: outside.unlink(missing_ok=True))
        outside.write_text("outside\n", encoding="utf-8")
        (self.root / "tasks/brief.json").symlink_to(self.root / "scripts/x.py")
        (self.root / "docs/SESSION_HANDOFF_link.md").symlink_to(outside)
        for target in ("tasks/brief.json", str(self.root / "tasks/brief.json"),
                       "docs/SESSION_HANDOFF_link.md", str(self.root / "docs/SESSION_HANDOFF_link.md")):
            with self.subTest(target=target):
                self.assertEqual(self.decision(self.guard(transcript, "Write", {"file_path": target}))["permissionDecision"], "deny")
        (self.root / "tasks/real.json").write_text("{}\n", encoding="utf-8")
        for target in ("tasks/real.json", "docs/SESSION_HANDOFF_new.md"):
            with self.subTest(target=target):
                self.assertNotIn("permissionDecision", self.decision(self.guard(transcript, "Edit", {"file_path": target})))

    def assert_fails_open(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        lines = result.stderr.splitlines()
        self.assertEqual(len(lines), 1, result.stderr)
        self.assertTrue(lines[0].startswith("context guard:"))
        self.assertNotIn(MARKER, result.stderr)

    def test_fails_open_with_one_stderr_line(self) -> None:
        cases = {
            "missing transcript_path": self.guard(None, "Write", {"file_path": MARKER}),
            "nonexistent file": self.guard(self.root / "absent.jsonl", "Write", {"file_path": MARKER}),
        }
        cases["malformed line"] = self.guard(self.transcript({"input_tokens": 200_000}, extra=MARKER + " {not json\n"),
                                             "Write", {"file_path": MARKER})
        no_usage = self.root / "no-usage.jsonl"
        no_usage.write_text(json.dumps({"type": "assistant", "message": {"content": MARKER}}) + "\n", encoding="utf-8")
        cases["no usage"] = self.guard(no_usage, "Write", {"file_path": MARKER})
        cases["malformed stdin"] = run_hook(CONTEXT_GUARD, self.root, "{" + MARKER)
        cases["stdin not an object"] = run_hook(CONTEXT_GUARD, self.root, json.dumps([MARKER]))
        for name, result in cases.items():
            with self.subTest(case=name):
                self.assert_fails_open(result)


if __name__ == "__main__":
    unittest.main()
