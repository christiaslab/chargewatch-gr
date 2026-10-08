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
import importlib.util
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
  "pr list") if [ -f "$FAKE_GH_LOG.listfail" ]; then echo "HTTP 403 graphql refused" >&2; exit 1; fi
    case "$*" in *"--state open"*) open=1 ;; *) open=0 ;; esac
    if [ -f "$FAKE_GH_LOG.merged" ] && [ "$open" = 0 ]; then echo "https://example.invalid/pull/0"; fi
    if [ -f "$FAKE_GH_LOG.exists" ]; then echo "https://example.invalid/pull/1"; fi; exit 0 ;;
  "pr create") if [ -f "$FAKE_GH_LOG.fail" ]; then echo "HTTP 403 graphql refused" >&2; exit 1; else echo "https://example.invalid/pull/2"; exit 0; fi ;;
  "api "*) case "$*" in *"--method GET"*)
      if [ -f "$FAKE_GH_LOG.getfail" ]; then echo "HTTP 403 refused" >&2; exit 1; fi
      if [ -f "$FAKE_GH_LOG.exists" ]; then echo '[{"html_url": "https://example.invalid/pull/1"}]'; else echo '[]'; fi; exit 0 ;; esac
    cat > "$FAKE_GH_LOG.stdin"
    if [ -f "$FAKE_GH_LOG.apifail" ]; then echo "HTTP 422 rest refused" >&2; exit 1; fi
    echo '{"number": 3, "html_url": "https://example.invalid/pull/3"}'; exit 0 ;;
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
        lookup = [call for call in self.gh_calls() if call.startswith("pr list")]
        self.assertTrue(lookup)
        self.assertIn("--head feat/thing --state open", lookup[0])
        self.assertEqual(git(self.work, "status", "--porcelain"), "", "a run must leave the tree clean, bytecode included")

    def test_a_merged_pull_request_with_the_same_branch_name_is_not_reused(self) -> None:
        # The fake lists the merged pull/0 for any lookup that does not restrict itself to open reviews.
        (self.log.parent / "gh.log.merged").write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertTrue(report["created"])
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/2")
        self.assertEqual(len([call for call in self.gh_calls() if call.startswith("pr create")]), 1)
        self.assertFalse(any(call.startswith("pr view") for call in self.gh_calls()))

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

    def use_github_shaped_origin(self) -> None:
        """The configured URL names a GitHub repository; an insteadOf rewrite sends fetch and push to the bare one on disk."""
        github = "git@github.com:acme/widget.git"
        git(self.work, "remote", "set-url", "origin", github)
        git(self.work, "config", f"url.{self.origin}.insteadOf", github)

    def test_failed_create_falls_back_to_rest(self) -> None:
        self.use_github_shaped_origin()
        (self.log.parent / "gh.log.fail").write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertEqual(report["route"], "rest")
        self.assertTrue(report["created"])
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/3")
        self.assertIn("feat/thing", git(self.work, "ls-remote", "--heads", "origin"))
        api = [call for call in self.gh_calls() if call.startswith("api ")]
        self.assertEqual(api, ["api --method POST repos/acme/widget/pulls --input -"])
        sent = json.loads((self.log.parent / "gh.log.stdin").read_text(encoding="utf-8"))
        self.assertEqual((sent["head"], sent["base"], sent["title"]), ("feat/thing", "main", "feat(thing): add a note"))
        self.assertIn("Commits:", sent["body"])
        self.assertEqual(len([call for call in self.gh_calls() if call.startswith("pr list")]), 1, "no lookup after a REST create")

    def test_both_routes_failing_names_both_failures(self) -> None:
        self.use_github_shaped_origin()
        for flag in ("gh.log.fail", "gh.log.apifail"):
            (self.log.parent / flag).write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertEqual(report["pushed_to"], "origin")
        self.assertNotIn("route", report)
        self.assertIn("pr create failed: HTTP 403 graphql refused", report["refused"][0])
        self.assertIn("api (REST) failed: HTTP 422 rest refused", report["refused"][0])
        self.assertIn("the branch is pushed", report["refused"][0])

    def test_a_path_origin_skips_the_rest_fallback_with_a_clear_error(self) -> None:
        (self.log.parent / "gh.log.fail").write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "FAIL")
        self.assertIn("REST fallback was skipped: origin names no GitHub owner and repository", report["refused"][0])
        self.assertNotIn(str(self.origin), report["refused"][0], "the origin URL may carry a credential")
        self.assertFalse(any(call.startswith("api ") for call in self.gh_calls()))

    def test_blocked_list_finds_the_existing_pull_request_through_rest(self) -> None:
        self.use_github_shaped_origin()
        for flag in ("gh.log.listfail", "gh.log.exists"):
            (self.log.parent / flag).write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertFalse(report["created"])
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/1")
        self.assertNotIn("route", report)
        self.assertIn("api --method GET repos/acme/widget/pulls?head=acme:feat/thing&state=open", self.gh_calls())
        self.assertFalse(any(call.startswith("pr create") or "POST" in call for call in self.gh_calls()))

    def test_fully_blocked_lookups_then_rest_creates(self) -> None:
        self.use_github_shaped_origin()
        for flag in ("gh.log.listfail", "gh.log.getfail", "gh.log.fail"):
            (self.log.parent / flag).write_text("", encoding="utf-8")
        report = self.run_script()
        self.assertEqual(report["result"], "PASS", report)
        self.assertTrue(report["created"])
        self.assertEqual(report["route"], "rest")
        self.assertEqual(report["pull_request"], "https://example.invalid/pull/3")
        self.assertEqual(len([call for call in self.gh_calls() if "--method GET" in call]), 1)
        self.assertEqual(len([call for call in self.gh_calls() if "--method POST" in call]), 1)

    def test_normal_path_reports_route_cli(self) -> None:
        report = self.run_script()
        self.assertEqual(report["route"], "cli")
        self.assertFalse(any(call.startswith("api ") for call in self.gh_calls()))

    def test_github_url_parser_over_ssh_https_and_path_forms(self) -> None:
        spec = importlib.util.spec_from_file_location("push_increment_under_test", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        sys.dont_write_bytecode, before = True, sys.dont_write_bytecode
        try:
            spec.loader.exec_module(module)
        finally:
            sys.dont_write_bytecode = before
        parse = module.github_repository
        self.assertEqual(parse("git@github.com:christiaslab/paes.git"), ("christiaslab", "paes"))
        self.assertEqual(parse("https://github.com/christiaslab/paes.git"), ("christiaslab", "paes"))
        self.assertEqual(parse("https://github.com/christiaslab/paes"), ("christiaslab", "paes"))
        self.assertEqual(parse("https://github.com/owner/repo.name/"), ("owner", "repo.name"))
        self.assertIsNone(parse(str(self.origin)))
        self.assertIsNone(parse("/srv/git/paes.git"))
        self.assertIsNone(parse("https://gitlab.com/owner/repo.git"))

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
