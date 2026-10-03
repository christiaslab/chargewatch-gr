#!/usr/bin/env python3
"""The portable kit: export from PAES, install into a target. Decision 0012.

``export --out DIR`` copies every manifest entry to DIR at its source path and
writes DIR/adapters/KIT_NOTICE.md with the origin commit, a digest per copy
and the MIT grant with its full text (kit v7, Decision 0018).
``install --target DIR --project-name NAME [--from SRC] [--report FILE]`` writes
into DIR only the files that do not exist there, fills templates, never
overwrites, never deletes, never merges; for an existing settings file it writes
``.claude/settings.proposed.json`` beside it (the merge, for the maintainer to
review) and records the proposal; for an existing CLAUDE.md or AGENTS.md it
records a proposal. The notice written into DIR lists a digest only for the
files this install wrote; skipped entries are marked as the target's own. It
runs no git command that changes state and makes no network call. The
project specification ``adapters/project-spec.yaml`` (Decision 0014, kit v4)
is written only when absent and, when present, supplies the verification
command and hand-off pointer that the kit's AGENTS.md renders. An
``optional`` manifest entry (kit v6, Decision 0017 point 7) is exported with
the kit and written into a target only with ``install --ci``, when the
specification's ``integration`` names a review backend that has a template.
Kit v8 proposes a ruff exclude for the kit's Python copies when the target
configures ruff, and the CI template pins its action by SHA.
Standard library only.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

MANIFEST = "adapters/kit-manifest.yaml"
NOTICE = "adapters/KIT_NOTICE.md"
DEFAULT_REPORT = "adapters/KIT_INSTALL_REPORT.md"
SETTINGS = ".claude/settings.json"
PROPOSED_SETTINGS = ".claude/settings.proposed.json"
KIT_VERSIONS = ("1", "2", "3", "4", "5", "6", "7", "8", "9")
# Where a target configures ruff, in the order the installer looks (kit v8, finding 1 of the fourth chargewatch-gr trial).
RUFF_CONFIGS = ("pyproject.toml", "ruff.toml", ".ruff.toml")
# The no-bypass field is restricted by the settings schema to this one string (kit v3, 2026-09-28).
# A boolean true, which versions one and two wrote, has the whole settings file rejected and skipped,
# so the deny list and the hooks are silently inactive while the file still parses as JSON.
NO_BYPASS_KEY = "disableBypassPermissionsMode"
NO_BYPASS_VALUE = "disable"
VERIFICATION_COMMAND = "python3 scripts/verify_kit.py"
# Decision 0014 (kit v4): the per-project specification, a closed field set of version 1, parsed as flat YAML.
SPEC = "adapters/project-spec.yaml"
SPEC_VERSION = "1"
SPEC_FIELDS = ("spec_version", "project_name", "maintainer", "reviewer", "release_authority", "verification_command",
               "handoff_pointer", "integration", "guidance_files", "limits")
SPEC_LIST_FIELDS = ("guidance_files", "limits")
SPEC_PLACEHOLDER = "(fill in)"
NO_HANDOFF = "none"
# What a maintainer pastes into the first session after install (kit v5, finding 5 of the third chargewatch-gr trial).
FIRST_SESSION_PROMPT = ("Read AGENTS.md and adapters/project-spec.yaml. Name the one bounded task you would take next in this project, "
                        "with its owned paths, and stop before writing. Then run the verify-kit skill and quote the result. "
                        "Then try git push --dry-run and curl https://example.com, and report what happened. Do not commit.")
_SPEC_KEY = re.compile(r"^([a-z_]+):(.*)$")
_SPEC_ITEM = re.compile(r"^  - (.+)$")
LICENCE = "MIT (the exported kit, Decision 0018; full text in the section below)"
COPYRIGHT = "Copyright (c) 2026 Panagiotis Christias"
LICENCE_SCOPE = (
    "The exported kit is granted under the MIT licence; inside the origin repository the same files are "
    "AGPL-3.0-only, and the MIT grant attaches to exactly the files the manifest lists at the origin commit, "
    "byte-identical copies and rendered templates alike."
)
MIT_TEXT = f"""MIT License

{COPYRIGHT}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE."""
_ENTRY = re.compile(r"^  - role: (copy|template|optional)\n    source: (\S+)\n    target: (\S+)$", re.MULTILINE)
# Kit v6 (Decision 0017 point 7): the optional CI template per review backend, written only with `install --ci`.
CI_TEMPLATES = {"github": "adapters/kit-templates/ci/github-verify.yml.template"}
PUSH_SCRIPT = "push script"
_VERSION = re.compile(r"^kit_version: (\d+)$", re.MULTILINE)
_DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$", re.MULTILINE)


class Entry:
    __slots__ = ("role", "source", "target")

    def __init__(self, role: str, source: str, target: str) -> None:
        self.role, self.source, self.target = role, source, target


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(root: Path) -> list[Entry]:
    text = (root / MANIFEST).read_text(encoding="utf-8")
    version = _VERSION.search(text)
    if not version or version.group(1) not in KIT_VERSIONS:
        raise ValueError("kit manifest version is not one of " + ", ".join(KIT_VERSIONS))
    entries = [Entry(role, source, target) for role, source, target in _ENTRY.findall(text)]
    if not entries:
        raise ValueError("kit manifest lists no entries")
    for entry in entries:
        for value in (entry.source, entry.target):
            if value.startswith("/") or ".." in Path(value).parts:
                raise ValueError(f"kit manifest path is not repository-relative: {value}")
    if len({entry.target for entry in entries}) != len(entries):
        raise ValueError("kit manifest has duplicate targets")
    return entries


def origin_commit(root: Path) -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return "unknown"


def render(text: str, fields: dict[str, str]) -> str:
    for name, value in fields.items():
        text = text.replace("{{" + name + "}}", value)
    left = re.findall(r"\{\{[a-z_]+\}\}", text)
    if left:
        raise ValueError("unfilled template fields: " + ", ".join(sorted(set(left))))
    return text


def parse_spec(text: str) -> dict[str, object]:
    """The flat YAML subset of the project specification: `key: value` scalars and `  - item` lists."""
    spec: dict[str, object] = {}
    current: str | None = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = _SPEC_ITEM.match(line)
        if item:
            if current is None or not isinstance(spec[current], list):
                raise ValueError(f"line {number}: list item outside a list field")
            spec[current].append(item.group(1).strip())
            continue
        key = _SPEC_KEY.match(line)
        if not key:
            raise ValueError(f"line {number}: not a `key: value` line or a `  - item` line")
        name, value = key.group(1), key.group(2).strip()
        if name in spec:
            raise ValueError(f"line {number}: duplicate field {name}")
        spec[name] = value if value else []
        current = name if not value else None
    return spec


def integration_backend(spec: dict[str, object] | None) -> str | None:
    """The backend the specification's `integration` field names (`push script: <name>`), else None."""
    value = spec.get("integration") if spec else None
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text[len(PUSH_SCRIPT) + 1:].strip() or None if text.startswith(PUSH_SCRIPT + ":") else None


def read_spec(target: Path) -> dict[str, object] | None:
    """The target's specification when it exists and parses; None otherwise."""
    path = target / SPEC
    if not path.is_file():
        return None
    try:
        return parse_spec(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def proposal_summary(items: list[str]) -> str:
    """One line for the report when the merge is already written as a file (finding 1 of the second trial).
    The no-bypass value is a replacement or a setting, not an addition, and is named on its own line (kit v5)."""
    additions = [item for item in items if NO_BYPASS_KEY not in item]
    counts = {
        "top-level keys": sum(item.startswith("add top-level key") for item in additions),
        "allow entries": sum(item.endswith("permissions.allow") for item in additions),
        "deny entries": sum(item.endswith("permissions.deny") for item in additions),
        "hook events": sum(item.endswith("hook entry") for item in additions),
    }
    parts = [f"{count} {name}" for name, count in counts.items() if count]
    summary = f"{len(additions)} additions the target lacks" + (": " + ", ".join(parts) if parts else "")
    return summary + ("; and the no-bypass value, named below" if len(additions) != len(items) else "")


def ruff_exclude_proposal(target: Path, entries: list[Entry]) -> str | None:
    """One proposal line when the target configures ruff and does not yet exclude the kit's Python copies (kit v8).
    The copies are digest-checked, so they cannot be reformatted to the target's width or rule set."""
    patterns: list[str] = []
    for entry in entries:
        if entry.role == "copy" and entry.target.endswith(".py"):
            parent = entry.target.rsplit("/", 1)[0] if "/" in entry.target else ""
            pattern = f"{parent}/*.py" if parent else "*.py"
            if pattern not in patterns:
                patterns.append(pattern)
    patterns.sort()  # sorted, not manifest order, so the line is stable when entries move: scripts/*.py first
    if not patterns:
        return None
    for name in RUFF_CONFIGS:
        path = target / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        if name == "pyproject.toml" and not any(line.startswith("[tool.ruff") for line in text.splitlines()):
            continue
        if all(pattern in text for pattern in patterns):
            return None
        where = "under [tool.ruff]" if name == "pyproject.toml" else "at the top level"
        line = "extend-exclude = [" + ", ".join(f'"{pattern}"' for pattern in patterns) + "]"
        return (f"{name}: configures ruff; the kit's Python copies are digest-checked and are not reformatted to the "
                f"target's width, so add {where} the line {line}, or lint them separately")
    return None


def notice_text(root: Path, entries: list[Entry], commit: str) -> str:
    lines = [
        "# PAES kit notice",
        "",
        "origin: paes",
        f"origin_commit: {commit}",
        f"exported: {_dt.date.today().isoformat()}",
        f"licence: {LICENCE}",
        f"copyright: {COPYRIGHT}",
        "",
        LICENCE_SCOPE,
        "",
        "Files below marked with a digest are byte-identical copies of the origin; templates are filled at install time and are not digest-checked; a line marked `skipped` names a file the target already had, which the installer left alone and does not digest-check.",
        "",
        "## Digests",
        "",
    ]
    for entry in entries:
        if entry.role == "copy":
            lines.append(f"{sha256_file(root / entry.source)}  {entry.target}")
        elif entry.role == "optional":
            lines.append(f"optional  {entry.target}  (written only when the installer is asked)")
        else:
            lines.append(f"template  {entry.target}")
    lines += ["", "## Licence", "", MIT_TEXT]
    return "\n".join(lines) + "\n"


def parse_notice(text: str) -> dict[str, str]:
    return {path: digest for digest, path in _DIGEST_LINE.findall(text)}


def installed_notice(notice: str, skipped_targets: set[str]) -> str:
    """The notice written into a target: a digest only for files this install wrote."""
    lines = []
    for line in notice.splitlines():
        match = _DIGEST_LINE.match(line)
        if match and match.group(2) in skipped_targets:
            lines.append(f"skipped  {match.group(2)}  (the target's own file, not written by the kit)")
        else:
            lines.append(line)
    return "\n".join(lines) + "\n"


def export(root: Path, out: Path) -> dict[str, object]:
    entries = load_manifest(root)
    missing = [entry.source for entry in entries if not (root / entry.source).is_file()]
    if missing:
        raise FileNotFoundError("kit sources missing: " + ", ".join(missing))
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for entry in entries:
        destination = out / entry.source
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / entry.source, destination)
        written.append(entry.source)
    commit = origin_commit(root)
    (out / NOTICE).parent.mkdir(parents=True, exist_ok=True)
    (out / NOTICE).write_text(notice_text(root, entries, commit), encoding="utf-8")
    written.append(NOTICE)
    return {"result": "PASS", "origin_commit": commit, "out": str(out), "files": written}


def settings_proposal(kit_settings: dict, target_settings: dict) -> list[str]:
    proposals: list[str] = []
    for key in kit_settings:
        if key not in target_settings:
            proposals.append(f"add top-level key `{key}`")
    kit_permissions = kit_settings.get("permissions", {})
    target_permissions = target_settings.get("permissions", {}) if isinstance(target_settings.get("permissions"), dict) else {}
    for list_name in ("allow", "deny"):
        wanted = kit_permissions.get(list_name, [])
        present = set(target_permissions.get(list_name, []))
        for item in wanted:
            if item not in present:
                proposals.append(f"add `{item}` to permissions.{list_name}")
    if kit_permissions.get(NO_BYPASS_KEY) == NO_BYPASS_VALUE and target_permissions.get(NO_BYPASS_KEY) != NO_BYPASS_VALUE:
        if NO_BYPASS_KEY in target_permissions:
            proposals.append(f'replace permissions.{NO_BYPASS_KEY}: {json.dumps(target_permissions[NO_BYPASS_KEY])} with the string "{NO_BYPASS_VALUE}"; '
                             "the settings schema accepts only that string, and a rejected value has the whole file skipped")
        else:
            proposals.append(f'set permissions.{NO_BYPASS_KEY} to the string "{NO_BYPASS_VALUE}"')
    for event in kit_settings.get("hooks", {}):
        if event not in target_settings.get("hooks", {}):
            proposals.append(f"add the `{event}` hook entry")
    return proposals


def merge_settings(kit_settings: dict, target_settings: dict) -> dict:
    """The target's settings with the kit's added: target values win, lists gain the kit's entries in order."""
    merged = json.loads(json.dumps(target_settings))
    for key, value in kit_settings.items():
        if key not in merged:
            merged[key] = value
    if not isinstance(merged.get("permissions"), dict):
        merged["permissions"] = {}
    kit_permissions = kit_settings.get("permissions", {})
    for list_name in ("allow", "deny"):
        present = list(merged["permissions"].get(list_name, []))
        for item in kit_permissions.get(list_name, []):
            if item not in present:
                present.append(item)
        if present or list_name in kit_permissions:
            merged["permissions"][list_name] = present
    if kit_permissions.get(NO_BYPASS_KEY) == NO_BYPASS_VALUE:
        merged["permissions"][NO_BYPASS_KEY] = NO_BYPASS_VALUE
    if kit_settings.get("hooks"):
        if not isinstance(merged.get("hooks"), dict):
            merged["hooks"] = {}
        for event, entries in kit_settings["hooks"].items():
            if event not in merged["hooks"]:
                merged["hooks"][event] = entries
    return merged


def install(source: Path, target: Path, project_name: str, report_path: Path | None, ci: bool = False) -> dict[str, object]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", project_name):
        raise ValueError("project name must be 1 to 64 characters of letters, digits, space, dot, underscore or hyphen")
    entries = load_manifest(source)
    notice_path = source / NOTICE
    notice = notice_path.read_text(encoding="utf-8") if notice_path.is_file() else notice_text(source, entries, origin_commit(source))
    commit = re.search(r"^origin_commit: (\S+)$", notice, re.MULTILINE).group(1)
    proposals: list[str] = []
    spec = read_spec(target)
    verification = spec.get("verification_command") if spec else None
    handoff = spec.get("handoff_pointer") if spec else None
    verification = verification if isinstance(verification, str) and verification else VERIFICATION_COMMAND
    handoff = handoff if isinstance(handoff, str) and handoff else NO_HANDOFF
    guidance = [name for name in ("CLAUDE.md", "AGENTS.md") if (target / name).is_file()]
    fields = {
        "project_name": project_name,
        "origin_commit": commit[:12],
        "verification_command": verification,
        "handoff_pointer": handoff,
        "handoff_row": "(none yet)" if handoff == NO_HANDOFF else f"[{handoff}]({handoff})",
        "guidance_files": "\n".join(f"  - {name}" for name in guidance),
    }
    if (target / SPEC).is_file() and spec is None:
        proposals.append(f"{SPEC}: exists but could not be parsed as the flat YAML the kit reads; the defaults were rendered instead")
    written: list[tuple[str, str]] = []
    skipped: list[tuple[str, str]] = []
    backend = integration_backend(spec)
    ci_template = CI_TEMPLATES.get(backend) if backend else None
    for entry in entries:
        destination = target / entry.target
        if entry.role == "optional":
            if entry.source != ci_template:
                continue  # another backend's template, or one the target's integration path does not name
            if not ci:
                proposals.append(f"{entry.target}: a CI workflow for the `{backend}` backend can be written from the kit; rerun the installer with --ci to write it")
                continue
        if destination.exists():
            skipped.append((entry.target, "exists in the target; not overwritten"))
            if entry.target == SETTINGS:
                try:
                    kit_settings = json.loads(render((source / entry.source).read_text(encoding="utf-8"), fields))
                    target_settings = json.loads(destination.read_text(encoding="utf-8"))
                    items = settings_proposal(kit_settings, target_settings)
                except (json.JSONDecodeError, OSError, ValueError):
                    proposals.append(f"{entry.target}: could not be read as JSON; compare by hand")
                else:
                    if items:
                        proposed = target / PROPOSED_SETTINGS
                        if proposed.exists():
                            # kit v4: the full list only when no proposed file could be written this time
                            skipped.append((PROPOSED_SETTINGS, "exists in the target; not overwritten"))
                            proposals.extend(f"{entry.target}: {item}" for item in items)
                            proposals.append(f"{PROPOSED_SETTINGS}: already exists and was left alone; compare it with the list above")
                        else:
                            proposed.write_text(json.dumps(merge_settings(kit_settings, target_settings), indent=2) + "\n", encoding="utf-8")
                            written.append((PROPOSED_SETTINGS, sha256_file(proposed)))
                            # kit v4: a count and a pointer instead of one line per entry; the no-bypass value stays named
                            proposals.append(f"{entry.target}: {proposal_summary(items)}; the merge is written as {PROPOSED_SETTINGS}")
                            proposals.extend(f"{entry.target}: {item}" for item in items if NO_BYPASS_KEY in item)
                            proposals.append(f"{PROPOSED_SETTINGS}: the target's settings with the kit's added, written beside the original for review; adopt it by replacing {SETTINGS}, then delete it")
            elif entry.target == "AGENTS.md":
                text = destination.read_text(encoding="utf-8", errors="replace")
                if "## Verification" not in text:
                    proposals.append(f"AGENTS.md: add a `## Verification` section whose first fenced command is `{verification}`")
                if SPEC not in text:
                    proposals.append(f"AGENTS.md: add a read-first row `Project specification` pointing to {SPEC}")
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if entry.role == "copy":
            shutil.copyfile(source / entry.source, destination)
        else:
            destination.write_text(render((source / entry.source).read_text(encoding="utf-8"), fields), encoding="utf-8")
        written.append((entry.target, sha256_file(destination)))
    if ci and ci_template is None:
        if backend is None:
            proposals.append(f"--ci: {SPEC} names no push-script backend yet; set `integration: {PUSH_SCRIPT}: <backend>` first, then rerun the installer with --ci")
        elif backend == "none":
            proposals.append("--ci: the `none` backend has no review tool and no CI template; the maintainer's own CI, if any, runs the verification command")
        else:
            proposals.append(f"--ci: no CI template exists for the `{backend}` backend; a template joins the kit once a target on that host has tried it (Decision 0017 point 4)")
    ruff = ruff_exclude_proposal(target, entries)
    if ruff is not None:
        proposals.append(ruff)
    claude_md = target / "CLAUDE.md"
    if claude_md.exists():
        if "@AGENTS.md" not in claude_md.read_text(encoding="utf-8", errors="replace"):
            proposals.append("CLAUDE.md: exists; add the line `@AGENTS.md` so the working guidance is read, or keep it separate on purpose")
    else:
        claude_md.write_text("@AGENTS.md\n", encoding="utf-8")
        written.append(("CLAUDE.md", sha256_file(claude_md)))
    target_notice = target / NOTICE
    if target_notice.exists():
        skipped.append((NOTICE, "exists in the target; not overwritten"))
    else:
        target_notice.parent.mkdir(parents=True, exist_ok=True)
        target_notice.write_text(installed_notice(notice, {path for path, _ in skipped}), encoding="utf-8")
        written.append((NOTICE, sha256_file(target_notice)))
    checklist = [
        f"review the merge proposals above, if any; a written {PROPOSED_SETTINGS} is the settings merge ready to adopt or discard",
        f"fill in {SPEC}: at least the maintainer, then the other roles, the verification command and the limits (copy the project's hard rules there, one line each); `{VERIFICATION_COMMAND}` fails while a placeholder remains",
        f"run `{VERIFICATION_COMMAND}` in the target and quote its result",
        "decide whether any git hook the target already had stays beside the kit's hooks",
        "commit under policies/contribution.md; the kit never commits, the maintainer does",
        f"choose the integration path in {SPEC}: `{PUSH_SCRIPT}: github`, `{PUSH_SCRIPT}: none` or `maintainer pushes`; scripts/push_increment.py runs only under the first two and never merges",
        f"then test the kit in a session opened in this checkout: look for the session banner, then paste: {FIRST_SESSION_PROMPT}",
    ]
    report = {
        "result": "PASS",
        "project_name": project_name,
        "origin_commit": commit,
        "target": str(target),
        "written": [{"path": path, "sha256": digest} for path, digest in written],
        "skipped": [{"path": path, "reason": reason} for path, reason in skipped],
        "proposals": proposals,
        "checklist": checklist,
    }
    if report_path is not None:
        if report_path.exists():
            raise FileExistsError(f"report exists and is not overwritten: {report_path}")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown(report), encoding="utf-8")
        report["report"] = str(report_path)
    return report


def report_markdown(report: dict[str, object]) -> str:
    lines = [
        f"# Kit install report for {report['project_name']}",
        "",
        f"Origin commit: `{report['origin_commit']}`. Target: `{report['target']}`. Nothing was overwritten or deleted.",
        "",
        "## Written",
        "",
        "| Path | SHA-256 |",
        "| --- | --- |",
    ]
    lines += [f"| `{item['path']}` | `{item['sha256']}` |" for item in report["written"]] or ["| (none) | |"]
    lines += ["", "## Skipped", ""]
    lines += [f"- `{item['path']}`: {item['reason']}" for item in report["skipped"]] or ["- (none)"]
    lines += ["", "## Merge proposals, for the maintainer", ""]
    lines += [f"- {item}" for item in report["proposals"]] or ["- (none)"]
    lines += ["", "## Checklist", ""]
    lines += [f"{index}. {item}" for index, item in enumerate(report["checklist"], 1)]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export or install the PAES portable kit.")
    sub = parser.add_subparsers(dest="command", required=True)
    exp = sub.add_parser("export", help="copy the kit to a directory with a notice and digests")
    exp.add_argument("--root", type=Path, default=Path.cwd())
    exp.add_argument("--out", type=Path, required=True)
    ins = sub.add_parser("install", help="write the kit into a target, only where files are missing")
    ins.add_argument("--from", dest="source", type=Path, default=Path.cwd(), help="an export directory or the PAES root")
    ins.add_argument("--target", type=Path, required=True)
    ins.add_argument("--project-name", required=True)
    ins.add_argument("--report", type=Path, help=f"report file; default <target>/{DEFAULT_REPORT}; never overwritten")
    ins.add_argument("--no-report", action="store_true")
    ins.add_argument("--ci", action="store_true", help="also write the CI workflow template of the specification's review backend, when one exists")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export(args.root.resolve(), args.out.resolve())
        else:
            target = args.target.resolve()
            report_path = None if args.no_report else (args.report.resolve() if args.report else target / DEFAULT_REPORT)
            result = install(args.source.resolve(), target, args.project_name, report_path, ci=args.ci)
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as error:
        print(json.dumps({"result": "FAIL", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
