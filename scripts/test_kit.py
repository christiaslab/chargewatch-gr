"""Tests for the portable kit's export and install (scripts/kit.py), against the real manifest.

Export writes every entry and a notice with digests; install writes only what
is missing, fills templates, never overwrites, proposes merges for an existing
settings file and writes the merge beside it as settings.proposed.json, marks
skipped files in the target's notice instead of digesting them (kit v2),
writes the project specification only when absent and renders the kit's
AGENTS.md from it (kit v4, Decision 0014), and writes a report it will not
overwrite. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
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


class KitExportInstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.out = base / "export"
        self.target = base / "target"
        self.target.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.target, env=GIT_ENV, check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_manifest_loads_and_sources_exist(self) -> None:
        entries = kit.load_manifest(REPOSITORY_ROOT)
        self.assertGreaterEqual(len(entries), 10)
        for entry in entries:
            self.assertTrue((REPOSITORY_ROOT / entry.source).is_file(), entry.source)

    def test_export_writes_every_entry_and_a_notice_with_digests(self) -> None:
        result = kit.export(REPOSITORY_ROOT, self.out)
        self.assertEqual(result["result"], "PASS")
        entries = kit.load_manifest(REPOSITORY_ROOT)
        for entry in entries:
            self.assertEqual(kit.sha256_file(self.out / entry.source), kit.sha256_file(REPOSITORY_ROOT / entry.source))
        notice = (self.out / kit.NOTICE).read_text(encoding="utf-8")
        recorded = kit.parse_notice(notice)
        copies = [entry for entry in entries if entry.role == "copy"]
        self.assertEqual(len(recorded), len(copies))
        for entry in copies:
            self.assertEqual(recorded[entry.target], kit.sha256_file(REPOSITORY_ROOT / entry.source))
        self.assertNotIn("licence: AGPL-3.0-only", notice)

    def test_exported_notice_carries_the_mit_grant_and_its_text(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        notice = (self.out / kit.NOTICE).read_text(encoding="utf-8")
        self.assertIn("licence: MIT", notice)
        self.assertIn("granted under the MIT licence", notice)
        self.assertIn("Copyright (c) 2026 Panagiotis Christias", notice)
        self.assertIn("## Licence\n\nMIT License\n", notice)
        self.assertIn("Permission is hereby granted, free of charge, to any person obtaining a copy", notice)
        self.assertIn("The above copyright notice and this permission notice shall be included in all", notice)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND', notice)
        self.assertIn("AGPL-3.0-only", notice)
        self.assertIn(f"origin_commit: {kit.origin_commit(REPOSITORY_ROOT)}", notice)
        copies = [entry.target for entry in kit.load_manifest(REPOSITORY_ROOT) if entry.role == "copy"]
        recorded = kit.parse_notice(notice)
        self.assertEqual(sorted(recorded), sorted(copies))
        self.assertEqual(kit.parse_notice(kit.MIT_TEXT + "\n" + kit.LICENCE_SCOPE), {})

    def test_installed_notice_keeps_the_mit_section(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        kit.install(self.out, self.target, "Temp Project", None)
        notice = (self.target / kit.NOTICE).read_text(encoding="utf-8")
        self.assertIn("licence: MIT", notice)
        self.assertIn("Copyright (c) 2026 Panagiotis Christias", notice)
        self.assertIn(kit.MIT_TEXT, notice)
        # The licence body is pinned by digest, as licence-declared pins LICENSE: a silent edit fails here.
        self.assertEqual(hashlib.sha256(kit.MIT_TEXT.encode("utf-8")).hexdigest(), "cc11c9c1aa955e4b54fa3c887bc5caf89fb55aa281968003306c5887ef8d7627")

    def test_install_into_empty_target_writes_all_and_fills_templates(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        report = kit.install(self.out, self.target, "Temp Project", self.target / kit.DEFAULT_REPORT)
        self.assertEqual(report["result"], "PASS")
        self.assertEqual(report["skipped"], [])
        agents = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("Working guidance for Temp Project", agents)
        self.assertIn(kit.VERIFICATION_COMMAND, agents)
        self.assertNotIn("{{", agents)
        wrapper = (self.target / ".claude/skills/verify-kit/SKILL.md").read_text(encoding="utf-8")
        self.assertIn("in Temp Project", wrapper)
        self.assertEqual((self.target / "CLAUDE.md").read_text(encoding="utf-8"), "@AGENTS.md\n")
        self.assertTrue((self.target / kit.NOTICE).is_file())
        self.assertTrue((self.target / kit.DEFAULT_REPORT).is_file())
        self.assertIn("Nothing was overwritten or deleted", (self.target / kit.DEFAULT_REPORT).read_text(encoding="utf-8"))

    def test_install_never_overwrites_and_refuses_an_existing_report(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        first = kit.install(self.out, self.target, "Temp Project", self.target / kit.DEFAULT_REPORT)
        digests = {item["path"]: item["sha256"] for item in first["written"]}
        marker = self.target / "policies/contribution.md"
        marker.write_text("owner edit\n", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            kit.install(self.out, self.target, "Temp Project", self.target / kit.DEFAULT_REPORT)
        second = kit.install(self.out, self.target, "Temp Project", None)
        self.assertEqual(second["written"], [])
        self.assertEqual(marker.read_text(encoding="utf-8"), "owner edit\n")
        for path, digest in digests.items():
            if path != "policies/contribution.md":
                self.assertEqual(kit.sha256_file(self.target / path), digest, path)

    def test_existing_settings_are_kept_and_a_merge_is_proposed(self) -> None:
        (self.target / ".claude").mkdir()
        (self.target / ".claude/settings.json").write_text('{"attribution": {"commit": ""}}\n', encoding="utf-8")
        (self.target / "AGENTS.md").write_text("# Existing guidance\n", encoding="utf-8")
        (self.target / "CLAUDE.md").write_text("# Project context\n", encoding="utf-8")
        report = kit.install(REPOSITORY_ROOT, self.target, "running-project", None)
        skipped = {item["path"] for item in report["skipped"]}
        self.assertIn(".claude/settings.json", skipped)
        self.assertIn("AGENTS.md", skipped)
        self.assertEqual((self.target / ".claude/settings.json").read_text(encoding="utf-8"), '{"attribution": {"commit": ""}}\n')
        proposals = "\n".join(report["proposals"])
        # kit v4: a count and a pointer, not one line per entry, once the proposed file is written
        self.assertNotIn("Bash(git push:*)", proposals)
        self.assertIn("5 deny entries", proposals)
        self.assertIn("21 allow entries", proposals)
        # kit v5: the no-bypass value is named on its own line and not counted among the additions
        self.assertIn("30 additions the target lacks", proposals)
        self.assertIn("and the no-bypass value, named below", proposals)
        self.assertIn(kit.FIRST_SESSION_PROMPT, "\n".join(report["checklist"]))
        self.assertIn("disableBypassPermissionsMode", proposals)
        self.assertIn("## Verification", proposals)
        self.assertIn("CLAUDE.md: exists", proposals)
        self.assertIn(kit.PROPOSED_SETTINGS, proposals)
        proposed = json.loads((self.target / kit.PROPOSED_SETTINGS).read_text(encoding="utf-8"))
        self.assertEqual(proposed["attribution"], {"commit": ""})
        self.assertIn("Bash(git push:*)", proposed["permissions"]["deny"])
        self.assertEqual(proposed["permissions"]["disableBypassPermissionsMode"], "disable")
        self.assertIn("SessionStart", proposed["hooks"])
        self.assertIn(kit.PROPOSED_SETTINGS, {item["path"] for item in report["written"]})

    def test_a_boolean_no_bypass_value_in_the_target_is_proposed_for_replacement(self) -> None:
        # Kit versions one and two wrote `true`; the settings schema accepts only the string "disable" and
        # skips the whole file otherwise, so an existing `true` must be named and replaced, not accepted.
        (self.target / ".claude").mkdir()
        (self.target / ".claude/settings.json").write_text(
            '{"permissions": {"deny": ["Bash(git push:*)"], "disableBypassPermissionsMode": true}}\n', encoding="utf-8")
        report = kit.install(REPOSITORY_ROOT, self.target, "kit-v2-target", None)
        proposal = [item for item in report["proposals"] if "disableBypassPermissionsMode" in item]
        self.assertEqual(len(proposal), 1, report["proposals"])
        self.assertIn("replace permissions.disableBypassPermissionsMode: true", proposal[0])
        self.assertIn('"disable"', proposal[0])
        proposed = json.loads((self.target / kit.PROPOSED_SETTINGS).read_text(encoding="utf-8"))
        self.assertEqual(proposed["permissions"]["disableBypassPermissionsMode"], "disable")
        self.assertNotIn("to true", "\n".join(report["proposals"]))

    def test_an_existing_proposed_file_keeps_the_full_proposal_list(self) -> None:
        (self.target / ".claude").mkdir()
        (self.target / ".claude/settings.json").write_text('{"attribution": {"commit": ""}}\n', encoding="utf-8")
        (self.target / kit.PROPOSED_SETTINGS).write_text("{}\n", encoding="utf-8")
        report = kit.install(REPOSITORY_ROOT, self.target, "running-project", None)
        proposals = "\n".join(report["proposals"])
        self.assertIn("Bash(git push:*)", proposals)
        self.assertIn("already exists and was left alone", proposals)
        self.assertEqual((self.target / kit.PROPOSED_SETTINGS).read_text(encoding="utf-8"), "{}\n")

    def test_install_writes_the_spec_skeleton_and_renders_agents_from_defaults(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        report = kit.install(self.out, self.target, "Temp Project", None)
        self.assertIn(kit.SPEC, {item["path"] for item in report["written"]})
        spec = kit.parse_spec((self.target / kit.SPEC).read_text(encoding="utf-8"))
        self.assertEqual(tuple(spec), kit.SPEC_FIELDS)
        self.assertEqual(spec["spec_version"], kit.SPEC_VERSION)
        self.assertEqual(spec["project_name"], "Temp Project")
        self.assertEqual(spec["maintainer"], kit.SPEC_PLACEHOLDER)
        self.assertEqual(spec["verification_command"], kit.VERIFICATION_COMMAND)
        self.assertEqual(spec["handoff_pointer"], kit.NO_HANDOFF)
        self.assertEqual(spec["guidance_files"], [])
        self.assertEqual(spec["limits"], [])
        agents = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("[adapters/project-spec.yaml](adapters/project-spec.yaml)", agents)
        self.assertIn("| Latest session hand-off and open items | (none yet) |", agents)
        self.assertIn(kit.SPEC, "\n".join(report["checklist"]))

    def test_install_renders_agents_from_an_existing_spec_and_never_overwrites_it(self) -> None:
        (self.target / "adapters").mkdir()
        (self.target / "CLAUDE.md").write_text("# Project context\n", encoding="utf-8")
        own = ("spec_version: 1\nproject_name: Own\nmaintainer: Alex\nreviewer: same as maintainer\nrelease_authority: none\n"
               "verification_command: make verify\nhandoff_pointer: docs/HANDOFF.md\nintegration: maintainer pushes\n"
               "guidance_files:\n  - CLAUDE.md\nlimits:\n  - never touch data/\n")
        (self.target / kit.SPEC).write_text(own, encoding="utf-8")
        report = kit.install(REPOSITORY_ROOT, self.target, "Own", None)
        self.assertIn(kit.SPEC, {item["path"] for item in report["skipped"]})
        self.assertEqual((self.target / kit.SPEC).read_text(encoding="utf-8"), own)
        agents = (self.target / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("```sh\nmake verify\n```", agents)
        self.assertIn("| Latest session hand-off and open items | [docs/HANDOFF.md](docs/HANDOFF.md) |", agents)
        self.assertNotIn(kit.VERIFICATION_COMMAND + "\n```", agents)

    def test_parse_spec_reads_scalars_lists_and_comments_and_rejects_bad_lines(self) -> None:
        spec = kit.parse_spec("# comment\na: 1\nb:\n  - x\n  - y\n\nc:\n")
        self.assertEqual(spec, {"a": "1", "b": ["x", "y"], "c": []})
        with self.assertRaises(ValueError):
            kit.parse_spec("a: 1\na: 2\n")
        with self.assertRaises(ValueError):
            kit.parse_spec("a: 1\n  - stray\n")
        with self.assertRaises(ValueError):
            kit.parse_spec("not a field\n")

    def test_settings_template_allows_only_kit_scripts_and_a_matching_target_gets_no_proposal(self) -> None:
        template = json.loads((REPOSITORY_ROOT / "adapters/kit-templates/settings.json.template").read_text(encoding="utf-8"))
        shipped = {entry.target for entry in kit.load_manifest(REPOSITORY_ROOT)}
        for item in template["permissions"]["allow"]:
            if item.startswith("Bash(python3 scripts/"):
                self.assertIn(item[len("Bash(python3 "):-len(":*)")], shipped, item)
        (self.target / ".claude").mkdir()
        (self.target / ".claude/settings.json").write_text(json.dumps(template), encoding="utf-8")
        report = kit.install(REPOSITORY_ROOT, self.target, "matching", None)
        self.assertFalse((self.target / kit.PROPOSED_SETTINGS).exists())
        self.assertEqual([item for item in report["proposals"] if "settings" in item], [])

    def test_merge_settings_keeps_target_values_and_adds_the_kit(self) -> None:
        kit_settings = {"attribution": {"commit": "none"}, "permissions": {"allow": ["Bash(ls:*)"], "deny": ["Bash(git push:*)"],
                        "disableBypassPermissionsMode": "disable"}, "hooks": {"SessionStart": [{"hooks": []}]}}
        target_settings = {"attribution": {"commit": "x"}, "permissions": {"allow": ["Bash(make:*)", "Bash(ls:*)"]},
                           "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo"}]}]}}
        merged = kit.merge_settings(kit_settings, target_settings)
        self.assertEqual(merged["attribution"], {"commit": "x"})
        self.assertEqual(merged["permissions"]["allow"], ["Bash(make:*)", "Bash(ls:*)"])
        self.assertEqual(merged["permissions"]["deny"], ["Bash(git push:*)"])
        self.assertEqual(merged["permissions"]["disableBypassPermissionsMode"], "disable")
        self.assertEqual(merged["hooks"], target_settings["hooks"])
        self.assertEqual(target_settings["permissions"], {"allow": ["Bash(make:*)", "Bash(ls:*)"]})

    def test_notice_in_a_running_target_marks_skipped_files_instead_of_digesting_them(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        (self.target / "policies").mkdir()
        (self.target / "policies/contribution.md").write_text("# own policy\n", encoding="utf-8")
        report = kit.install(self.out, self.target, "running", None)
        notice = (self.target / kit.NOTICE).read_text(encoding="utf-8")
        self.assertNotIn("policies/contribution.md", kit.parse_notice(notice))
        self.assertIn("skipped  policies/contribution.md", notice)
        self.assertIn("policies/worktree-flow.md", kit.parse_notice(notice))
        self.assertNotIn("policies/contribution.md", {item["path"] for item in report["written"]})
        self.assertNotIn("{{", (self.target / ".claude/settings.json").read_text(encoding="utf-8"))
        self.assertNotIn("the owner", (self.target / kit.NOTICE).read_text(encoding="utf-8"))
        for relative in ("AGENTS.md", "policies/worktree-flow.md", "policies/conform-review.md", ".claude/skills/commit-guard/SKILL.md"):
            self.assertNotIn("the owner'", (self.target / relative).read_text(encoding="utf-8"), relative)

    def test_optional_ci_template_is_exported_and_written_only_with_ci_for_a_github_backend(self) -> None:
        kit.export(REPOSITORY_ROOT, self.out)
        optional = [entry for entry in kit.load_manifest(REPOSITORY_ROOT) if entry.role == "optional"]
        self.assertEqual([entry.target for entry in optional], [".github/workflows/verify.yml"])
        self.assertTrue((self.out / optional[0].source).is_file())
        self.assertIn("optional  .github/workflows/verify.yml", (self.out / kit.NOTICE).read_text(encoding="utf-8"))
        # the default specification says `maintainer pushes`: --ci writes nothing and says what to set first
        report = kit.install(self.out, self.target, "plain", None, ci=True)
        self.assertFalse((self.target / ".github/workflows/verify.yml").exists())
        self.assertTrue(any("names no push-script backend yet" in item for item in report["proposals"]), report["proposals"])
        # a target whose specification names the github backend: proposed without --ci, written with it
        spec = self.target / kit.SPEC
        spec.write_text(spec.read_text(encoding="utf-8").replace("integration: maintainer pushes", "integration: push script: github"), encoding="utf-8")
        report = kit.install(self.out, self.target, "plain", None)
        self.assertFalse((self.target / ".github/workflows/verify.yml").exists())
        self.assertTrue(any("rerun the installer with --ci" in item for item in report["proposals"]), report["proposals"])
        report = kit.install(self.out, self.target, "plain", None, ci=True)
        workflow = (self.target / ".github/workflows/verify.yml").read_text(encoding="utf-8")
        self.assertIn("run: |\n          python3 scripts/verify_kit.py\n", workflow)
        self.assertIn("for plain", workflow)
        self.assertNotIn("{{", workflow)
        self.assertIn(".github/workflows/verify.yml", {item["path"] for item in report["written"]})
        report = kit.install(self.out, self.target, "plain", None, ci=True)
        self.assertIn(".github/workflows/verify.yml", {item["path"] for item in report["skipped"]})
        none_target = Path(self._tmp.name) / "none"
        none_target.mkdir()
        kit.install(self.out, none_target, "quiet", None)
        spec = none_target / kit.SPEC
        spec.write_text(spec.read_text(encoding="utf-8").replace("integration: maintainer pushes", "integration: push script: none"), encoding="utf-8")
        report = kit.install(self.out, none_target, "quiet", None, ci=True)
        self.assertFalse((none_target / ".github").exists())
        self.assertTrue(any("`none` backend has no review tool" in item for item in report["proposals"]), report["proposals"])
        self.assertEqual(kit.integration_backend({"integration": "push script: none"}), "none")
        self.assertIsNone(kit.integration_backend({"integration": "push script"}))
        self.assertIsNone(kit.integration_backend(None))

    def test_bad_project_name_and_bad_manifest_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            kit.install(REPOSITORY_ROOT, self.target, "../escape", None)
        bad = Path(self._tmp.name) / "bad"
        (bad / "adapters").mkdir(parents=True)
        (bad / kit.MANIFEST).write_text("kit_version: 1\nentries:\n  - role: copy\n    source: ../secret\n    target: x\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            kit.load_manifest(bad)

    def test_cli_export_and_install(self) -> None:
        run = subprocess.run([os.sys.executable, "scripts/kit.py", "export", "--out", str(self.out)],
                             cwd=REPOSITORY_ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        run = subprocess.run([os.sys.executable, str(self.out / "scripts/kit.py"), "install", "--from", str(self.out),
                              "--target", str(self.target), "--project-name", "cli-target", "--no-report"],
                             cwd=self.out, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual(json.loads(run.stdout)["result"], "PASS")


if __name__ == "__main__":
    unittest.main()
