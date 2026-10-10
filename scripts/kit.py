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
configures ruff, and the CI template pins its action by SHA. Kit v10 makes no
CI proposal when the target already has the workflow and lists it as skipped.
Kit v12: ``install --upgrade`` over an installed kit overwrites a copy only when
it still carries the digest the installed notice recorded for it, refuses a
modified copy or a path through a symbolic link by name and rewrites the
notice with the export's digests. Kit v13: an upgrade refuses a destination with a symbolic link at any component
below the target, wherever the link points; it appends a dated line to an `## Upgrades` section of the rewritten notice,
carrying the earlier lines forward; and the notice names the routine that retires a merged increment branch.
Kit v14: the specification gains two optional fields, ``sandbox`` (``on`` or ``off``, absent means off) and
``bot_authors``; with ``sandbox: on`` the rendered settings carry a sandbox block and the report proposes
``.worktrees/`` for the target's .gitignore. An upgrade marks a kit-written copy the target changed as ``modified``
only when the maintainer names it with ``--own <path>``; without it the copy is refused and still fails the digest check,
in the notice instead of recording a digest the file no longer has.
Kit v17 (Decision 0025): ``digests`` writes ``adapters/kit-digests.txt`` at the origin, the manifest's
``kit_version`` and one digest line per copy, read by the ``kit-copy-drift`` check of the repository verifier;
the record stays at the origin and is not a manifest entry.
Kit v18 (the three kit findings of the forty-sixth session): ``install`` refuses a source that resolves to the same tree
as the target, since ``--from`` defaults to the current directory; an upgrade records the export's digest for a
target-owned copy whose bytes equal the export's, so the kit check covers it from then on instead of leaving it
``skipped``; and the report warns when a kit test copy (``scripts/test_<name>.py``) tests a module the target owns
or changed, since ``verify_kit.py`` runs no test module.
Kit v19 (the two upgrade findings of the forty-ninth session): ``--project-name`` is optional; under ``--upgrade`` an
absent name is read from the target's ``adapters/project-spec.yaml``, and the installer refuses by name when neither the
flag nor the specification gives one, or when the flag is absent without ``--upgrade``. The default report of an upgrade
is ``adapters/KIT_UPGRADE_REPORT_<date>_V<version>.md``, dated today with the export's manifest version, so a second
upgrade on the same day at a newer version needs no ``--report``; the install default and the never-overwritten rule stay.
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
UPGRADE_REPORT = "adapters/KIT_UPGRADE_REPORT_{date}_V{version}.md"  # kit v19: the default report of an upgrade
DIGESTS = "adapters/kit-digests.txt"
SETTINGS = ".claude/settings.json"
PROPOSED_SETTINGS = ".claude/settings.proposed.json"
KIT_VERSIONS = ("1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19")
# An installer knows the manifest versions up to its own; a newer export is installed with the kit.py it ships (kit v11).
UPGRADE_NOTE = "a newer export is installed with the kit.py it ships, not with the installed one"
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
               "handoff_pointer", "integration", "guidance_files", "limits", "sandbox", "bot_authors")
SPEC_LIST_FIELDS = ("guidance_files", "limits", "bot_authors")
# Kit v14: fields a specification written before version fourteen lacks; absent, sandbox is off and the bot list empty.
SPEC_OPTIONAL_FIELDS = ("sandbox", "bot_authors")
SANDBOX_VALUES = ("on", "off")
# Kit v14 (trial 9, linetally): the session sandbox writes only inside the checkout, so a worktree lives at
# .worktrees/<slug>; gh fails TLS under the sandbox and is excluded; git push needs the forge's domain.
WORKTREES_IGNORE = ".worktrees/"
# kit v15 (review of kit v14): the exclusion matches the Bash call text only, exact without a trailing ` *`;
# api.github.com needs the wildcard.
SANDBOX_DOMAINS = {"github": ["github.com", "*.github.com"]}
PUSH_COMMAND = "python3 scripts/push_increment.py *"
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
# Kit v14: a copy the kit wrote and the target changed since; not digest-checked, kept until it is back at a kit digest.
MODIFIED = "modified"
MODIFIED_NOTE = "(written by the kit, changed by the target, not digest-checked)"
_MODIFIED_LINE = re.compile(r"^modified  (\S+)  ", re.MULTILINE)
# Kit v13: the upgrade record in the target's notice, one dated line per upgrade, inserted before the licence section.
UPGRADES_HEADING = "## Upgrades"
LICENCE_HEADING = "## Licence"
# Kit v13: the push script creates an increment branch in the target and no kit step removed it after the merge.
RETIREMENT = (
    "The push script, scripts/push_increment.py, creates an increment branch in this repository and opens its pull "
    "request; it never merges and never deletes. After the maintainer merges, and only once the forge shows the merge "
    "(`git ls-remote --heads origin` no longer lists the branch), retire it from the primary checkout, in order, as "
    "policies/worktree-flow.md rule 6 says: `git fetch --prune origin`, `git merge --ff-only origin/main`, "
    "`git worktree remove <worktree>` when a worktree holds the branch, then `git branch -D <branch>`."
)


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
        raise ValueError("kit manifest version is not one of " + ", ".join(KIT_VERSIONS) + "; " + UPGRADE_NOTE)
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


def sandbox_on(spec: dict[str, object] | None) -> bool:
    """kit v14: the specification turns the sandbox on only with `sandbox: on`; absent or anything else is off here."""
    return bool(spec) and spec.get("sandbox") == "on"


def sandbox_block(spec: dict[str, object] | None) -> dict[str, object]:
    """kit v15: the settings sandbox block; the push script's own command line is excluded beside gh, since the exclusion
    matches the text of the Bash call only; the allowed domains follow the review backend, none without a push script."""
    return {"enabled": True, "excludedCommands": ["gh *", PUSH_COMMAND],
            "network": {"allowedDomains": list(SANDBOX_DOMAINS.get(integration_backend(spec) or "", []))}}


def with_sandbox(settings_text: str, spec: dict[str, object] | None) -> str:
    """kit v14: the rendered settings with the sandbox block added after `permissions` when the specification turns it
    on; the text unchanged otherwise, so a target with the sandbox off or absent gets the same bytes as before."""
    if not sandbox_on(spec):
        return settings_text
    settings = json.loads(settings_text)
    result: dict[str, object] = {}
    for key, value in settings.items():
        result[key] = value
        if key == "permissions":
            result["sandbox"] = sandbox_block(spec)
    result.setdefault("sandbox", sandbox_block(spec))
    return json.dumps(result, indent=2) + "\n"


def worktrees_ignore_proposal(target: Path, spec: dict[str, object] | None) -> str | None:
    """kit v14: with the sandbox on, the worktree lives at .worktrees/<slug> inside the checkout, which git must ignore."""
    if not sandbox_on(spec):
        return None
    path = target / ".gitignore"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []
    except OSError:
        lines = []
    if any(line.strip() in (WORKTREES_IGNORE, "/" + WORKTREES_IGNORE, ".worktrees", "/.worktrees") for line in lines):
        return None
    return (f".gitignore: the specification turns the sandbox on, so a worktree lives at {WORKTREES_IGNORE}<slug> inside "
            f"the checkout (policies/worktree-flow.md rule 3); add the line `{WORKTREES_IGNORE}`")


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
        "Files below marked with a digest are byte-identical copies of the origin; templates are filled at install time and are not digest-checked; a line marked `skipped` names a file the target already had, which the installer left alone and does not digest-check; a line marked `modified` names a copy the kit wrote and the target changed since, which the maintainer took as the target's own with `install --upgrade --own <path>` and which is not digest-checked until it is back at a kit digest.",
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
    lines += ["", "## Retiring an increment branch", "", RETIREMENT, "", LICENCE_HEADING, "", MIT_TEXT]
    return "\n".join(lines) + "\n"


def manifest_version(root: Path) -> str:
    """The manifest's kit_version, validated by load_manifest."""
    load_manifest(root)
    return _VERSION.search((root / MANIFEST).read_text(encoding="utf-8")).group(1)


def digests_text(root: Path) -> str:
    """Kit v17 (Decision 0025 point 1): the manifest's kit_version on line one, then one digest line per copy entry,
    in the installed notice's line format, so parse_notice reads both."""
    lines = [f"kit_version: {manifest_version(root)}"]
    lines += [f"{sha256_file(root / entry.source)}  {entry.target}" for entry in load_manifest(root) if entry.role == "copy"]
    return "\n".join(lines) + "\n"


def write_digests(root: Path) -> dict[str, object]:
    """Decision 0025 point 2: the only writer of the digest record; point 4: refused outside the origin, so a target that
    runs the kit copy of this script gets no second derived file."""
    if not re.search(r"^origin: paes$", (root / MANIFEST).read_text(encoding="utf-8"), re.MULTILINE):
        raise ValueError(f"{DIGESTS} is written only at the origin")
    text = digests_text(root)
    (root / DIGESTS).write_text(text, encoding="utf-8")
    return {"result": "PASS", "written": DIGESTS, "kit_version": _VERSION.search(text).group(1),
            "copies": len(_DIGEST_LINE.findall(text))}


def copy_drift(root: Path) -> list[str]:
    """Decision 0025 point 3: the record's version against the manifest's, and every copy's digest in the working tree
    against the recorded one. Returns only paths and versions: the record's path when it is missing, a version line when the two
    versions differ, then each copy path whose digest differs or is missing on either side. Empty means no drift."""
    record = root / DIGESTS
    manifest = manifest_version(root)
    if not record.is_file():
        return [DIGESTS]
    text = record.read_text(encoding="utf-8")
    recorded_version = _VERSION.search(text)
    findings = []
    if recorded_version is None or recorded_version.group(1) != manifest:
        findings.append(f"kit_version {recorded_version.group(1) if recorded_version else 'none'} recorded, {manifest} in manifest")
    recorded = {path: digest for digest, path in _DIGEST_LINE.findall(text)}
    current = {entry.target: sha256_file(root / entry.source) for entry in load_manifest(root) if entry.role == "copy"}
    findings += sorted(path for path in set(recorded) | set(current) if recorded.get(path) != current.get(path))
    return findings


def parse_notice(text: str) -> dict[str, str]:
    """Path to recorded digest; kit v14: a `modified` line maps its path to MODIFIED instead of a digest."""
    recorded = {path: digest for digest, path in _DIGEST_LINE.findall(text)}
    recorded.update((path, MODIFIED) for path in _MODIFIED_LINE.findall(text))
    return recorded


def upgrade_lines(notice: str) -> list[str]:
    """kit v13: the dated lines of a notice's upgrade section, in order; none when it has no such section."""
    lines, inside = [], False
    for line in notice.splitlines():
        if line.startswith("## "):
            inside = line == UPGRADES_HEADING
        elif inside and line.startswith("- "):
            lines.append(line)
    return lines


def with_upgrade_record(notice: str, lines: list[str]) -> str:
    """kit v13: the notice with an upgrade section before the licence section. The lines start with `- `, so neither the
    digest parser nor verify_kit.py reads them as a digest or a `skipped` line."""
    section = "\n".join([UPGRADES_HEADING, "", *lines, "", ""])
    marker = "\n" + LICENCE_HEADING + "\n"
    if marker not in notice:
        return notice.rstrip("\n") + "\n\n" + section
    head, tail = notice.split(marker, 1)
    return head + "\n" + section + LICENCE_HEADING + "\n" + tail


def installed_notice(notice: str, skipped_targets: set[str], modified_targets: set[str] = frozenset()) -> str:
    """The notice written into a target: a digest only for files this install wrote; kit v14: a `modified` line for a
    kit-written copy the target changed, which an upgrade refused."""
    lines = []
    for line in notice.splitlines():
        match = _DIGEST_LINE.match(line)
        if match and match.group(2) in skipped_targets:
            lines.append(f"skipped  {match.group(2)}  (the target's own file, not written by the kit)")
        elif match and match.group(2) in modified_targets:
            lines.append(f"{MODIFIED}  {match.group(2)}  {MODIFIED_NOTE}")
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
    # kit v15 (review lane): a v14 target already carrying a sandbox block is told which list entries it lacks.
    if "sandbox" in kit_settings and isinstance(target_settings.get("sandbox"), dict):
        for path, wanted in sandbox_lists(kit_settings):
            present = sandbox_list(target_settings, path)
            if present is None:
                proposals.append(f"sandbox.{path} is not a list; compare it with the kit's by hand")
            else:
                proposals.extend(f"add `{item}` to sandbox.{path}" for item in wanted if item not in present)
    return proposals


def sandbox_lists(settings: dict) -> list[tuple[str, list[str]]]:
    """The two list paths of a sandbox block with their entries, empty when the block or a list is absent."""
    return [(path, sandbox_list(settings, path) or []) for path in ("excludedCommands", "network.allowedDomains")]


def sandbox_list(settings: dict, path: str) -> list[str] | None:
    """The list at a sandbox path; [] when absent, None when present but not a list, which is left to the maintainer."""
    value: object = settings.get("sandbox", {})
    for key in path.split("."):
        if not isinstance(value, dict):
            return None
        if key not in value:
            return []
        value = value[key]
    return list(value) if isinstance(value, list) else None


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
    if "sandbox" in kit_settings and isinstance(merged.get("sandbox"), dict):
        for path, wanted in sandbox_lists(kit_settings):
            present = sandbox_list(merged, path)
            missing = [] if present is None else [item for item in wanted if item not in present]
            if missing:
                node = merged["sandbox"]
                for key in path.split(".")[:-1]:
                    if not isinstance(node.get(key), dict):
                        node[key] = {}
                    node = node[key]
                node[path.split(".")[-1]] = present + missing
    return merged


def inside_target(destination: Path, target: Path) -> bool:
    """kit v12: a destination the upgrade may overwrite is no link, resolves inside the resolved target and, when it
    exists, is a regular file (review lane, fourth finding: a copy replaced by a directory would abort the run).
    kit v13, the review lane's fifth finding on v12: no component of the path below the target is a symbolic link, even
    one that resolves inside the target, so a linked directory never routes a write into a nested checkout."""
    try:
        parts = destination.relative_to(target).parts
    except ValueError:
        return False
    current = target
    for part in parts:
        current = current / part
        if current.is_symlink():
            return False
    if destination.exists() and not destination.is_file():
        return False
    try:
        return destination.resolve().is_relative_to(target.resolve())
    except (OSError, RuntimeError, ValueError):
        return False


def test_pairs(entries: list[Entry]) -> dict[str, list[str]]:
    """kit v18: each kit test copy `scripts/test_<name>.py` with the copies it tests, `scripts/<name>.py` or any copy under
    `scripts/<name>/`; a test with no such copy is left out."""
    copies = [entry.target for entry in entries if entry.role == "copy"]
    pairs: dict[str, list[str]] = {}
    for path in copies:
        match = re.fullmatch(r"scripts/test_([a-z0-9_]+)\.py", path)
        if match:
            name = match.group(1)
            modules = [other for other in copies if other == f"scripts/{name}.py" or other.startswith(f"scripts/{name}/")]
            if modules:
                pairs[path] = modules
    return pairs


def resolve_project_name(target: Path, project_name: str | None, upgrade: bool) -> str:
    """kit v19, finding 1 of the forty-ninth session: an absent name is read from the target's specification under
    --upgrade, where the installed specification already carries it; refused by name otherwise, before any write."""
    if project_name is not None:
        return project_name
    if not upgrade:
        raise ValueError("--project-name is required for an install; only an upgrade reads it from the target's specification")
    spec = read_spec(target)
    name = spec.get("project_name") if spec else None
    if not isinstance(name, str) or not name:
        raise ValueError(f"--project-name is absent and the target's {SPEC} gives no project_name")
    return name


def default_upgrade_report(source: Path, today: _dt.date | None = None) -> str:
    """kit v19, finding 2 of the forty-ninth session: the default upgrade report carries the date and the export's manifest
    version, so a second upgrade on the same day at a newer version needs no --report; a report is still never overwritten."""
    return UPGRADE_REPORT.format(date=(today or _dt.date.today()).isoformat(), version=manifest_version(source))


def install(source: Path, target: Path, project_name: str | None, report_path: Path | None, ci: bool = False,
            upgrade: bool = False, take_as_own: tuple[str, ...] = ()) -> dict[str, object]:
    project_name = resolve_project_name(target, project_name, upgrade)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}", project_name):
        raise ValueError("project name must be 1 to 64 characters of letters, digits, space, dot, underscore or hyphen")
    if source.resolve() == target.resolve():
        # kit v18, finding 3: --from defaults to the current directory, so a run from inside the target would upgrade it from itself
        raise ValueError(f"the source and the target are the same tree ({target}); pass --from the export or the PAES root")
    entries = load_manifest(source)
    installed: dict[str, str] = {}
    if upgrade:
        # kit v12: the installed notice's digest is the only evidence that a copy is still the kit's; refused before any write
        if not (target / NOTICE).is_file():
            raise FileNotFoundError("no installed kit notice in the target; run install without --upgrade")
        if not inside_target(target / NOTICE, target):
            # kit v12, review lane: the notice is rewritten on upgrade, so a link there would rewrite another install's
            raise FileNotFoundError(f"{NOTICE} is or lies under a symbolic link, or resolves outside the target; not followed")
        previous_notice = (target / NOTICE).read_text(encoding="utf-8")
        installed = parse_notice(previous_notice)
        previous_version = _VERSION.search((target / MANIFEST).read_text(encoding="utf-8")) if (target / MANIFEST).is_file() else None
    if report_path is not None:
        # kit v11, finding 3 of the sixth chargewatch-gr trial: the refusal comes before the first write; a report path
        # that names a file the install itself writes is refused here too, since it would be overwritten by the report
        if report_path.exists():
            raise FileExistsError(f"report exists and is not overwritten: {report_path}")
        outputs = {(target / entry.target).resolve() for entry in entries} | {(target / name).resolve() for name in ("CLAUDE.md", NOTICE, PROPOSED_SETTINGS)}
        if report_path.resolve() in outputs:
            raise ValueError(f"report path names a file the kit writes: {report_path}")
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
    own: set[str] = set()  # kit v12: copies the target already had, marked `skipped` in the notice
    changed: set[str] = set()  # kit v14: kit-written copies the target changed, marked `modified` in the notice
    owned: list[str] = []  # kit v14: paths this upgrade marked `modified` because the maintainer named them with --own
    backend = integration_backend(spec)
    ci_template = CI_TEMPLATES.get(backend) if backend else None
    for entry in entries:
        destination = target / entry.target
        if entry.role == "optional":
            if entry.source != ci_template:
                continue  # another backend's template, or one the target's integration path does not name
            if not ci and not destination.exists():  # kit v10: no proposal when the target already has the workflow
                proposals.append(f"{entry.target}: a CI workflow for the `{backend}` backend can be written from the kit; rerun the installer with --ci to write it")
                continue
        if upgrade and entry.role == "copy" and not inside_target(destination, target):
            # kit v12, review lane: a copy replaced by a symbolic link, or under a linked directory, is never followed, so an
            # upgrade of one target cannot write into another or into a nested checkout (kit v13); refused by name
            skipped.append((entry.target, "a symbolic link, a directory or outside the target; not overwritten"))
            if entry.target not in installed:
                own.add(entry.target)  # review lane, third finding: a target-owned link keeps its `skipped` line in the notice
            elif installed[entry.target] == MODIFIED:
                changed.add(entry.target)  # kit v14: a `modified` copy keeps its marker while it is refused
            proposals.append(f"{entry.target}: a symbolic link, a path through a linked directory, a directory or a path that resolves outside the target, not followed and not "
                             f"overwritten; replace it with {entry.source} from the export by hand if the kit's copy is wanted there")
            continue
        if upgrade and entry.role == "copy" and destination.exists() and entry.target in installed:
            # kit v12: overwrite only a copy still at the installed digest; a modified copy is refused by name
            current = sha256_file(destination)
            if current == sha256_file(source / entry.source):
                skipped.append((entry.target, "unchanged, already at the export's digest"))
                continue
            if current != installed[entry.target]:
                skipped.append((entry.target, "modified in the target; not overwritten"))
                if installed[entry.target] == MODIFIED or entry.target in take_as_own:
                    # kit v14: the marker is the maintainer's act (`--own`), kept by later upgrades until the bytes return
                    changed.add(entry.target)
                    if installed[entry.target] != MODIFIED:
                        owned.append(entry.target)
                    proposals.append(f"{entry.target}: modified in the target and taken as the target's own; the notice marks it "
                                     f"`{MODIFIED}`, not digest-checked until it is back at the export's bytes")
                else:
                    proposals.append(f"{entry.target}: modified in the target since the kit installed it and not overwritten; compare it "
                                     f"with {entry.source} in the export by hand; the notice now records the export's digest, so "
                                     f"{VERIFICATION_COMMAND} reports it as differing until it is reconciled, or rerun the upgrade "
                                     f"with --own {entry.target} to keep the change as the target's own")
                continue
        elif destination.exists():
            if upgrade and entry.role == "copy" and sha256_file(destination) == sha256_file(source / entry.source):
                # kit v18, finding 2: a target-owned copy back at the export's bytes is digest-checked from now on
                skipped.append((entry.target, "the target's own file, at the export's bytes; the notice now records its digest"))
                continue
            skipped.append((entry.target, "exists in the target; not overwritten"))
            if entry.role == "copy":
                own.add(entry.target)
            if entry.target == SETTINGS:
                try:
                    kit_settings = json.loads(with_sandbox(render((source / entry.source).read_text(encoding="utf-8"), fields), spec))
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
            text = render((source / entry.source).read_text(encoding="utf-8"), fields)
            destination.write_text(with_sandbox(text, spec) if entry.target == SETTINGS else text, encoding="utf-8")
        written.append((entry.target, sha256_file(destination)))
    if ci and ci_template is None:
        if backend is None:
            proposals.append(f"--ci: {SPEC} names no push-script backend yet; set `integration: {PUSH_SCRIPT}: <backend>` first, then rerun the installer with --ci")
        elif backend == "none":
            proposals.append("--ci: the `none` backend has no review tool and no CI template; the maintainer's own CI, if any, runs the verification command")
        else:
            proposals.append(f"--ci: no CI template exists for the `{backend}` backend; a template joins the kit once a target on that host has tried it (Decision 0017 point 4)")
    for test_path, module_paths in test_pairs(entries).items():
        # kit v18, finding 1: the kit check runs no test module, so a kit test over a target-owned or changed module is named here
        affected = [path for path in module_paths if path in own or path in changed]
        if affected and test_path not in own:
            proposals.append(f"{test_path}: the kit's test copy tests {', '.join(affected)}, which the target owns or changed; "
                             f"run `python3 -m unittest {test_path}` in the target, since {VERIFICATION_COMMAND} runs no test module")
    for path in take_as_own:
        if path not in owned:
            # kit v14: --own acts only on a kit-written copy the target changed, during an upgrade
            proposals.append(f"--own {path}: not a kit-written copy changed by the target in this upgrade; ignored")
    worktrees = worktrees_ignore_proposal(target, spec)
    if worktrees is not None:
        proposals.append(worktrees)
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
    if target_notice.exists() and not upgrade:
        skipped.append((NOTICE, "exists in the target; not overwritten"))
    else:
        # kit v12: on upgrade only the target's own copies stay `skipped`; a refused modified copy gets the export's digest
        target_notice.parent.mkdir(parents=True, exist_ok=True)
        marked = own if upgrade else {path for path, _ in skipped}
        text = installed_notice(notice, marked, changed)
        if upgrade:
            # kit v13: the upgrade leaves a record in the target beside its commit, the earlier lines carried forward
            refused = [path for path, reason in skipped if reason.startswith(("modified", "a symbolic link"))]
            old_commit = re.search(r"^origin_commit: (\S+)$", previous_notice, re.MULTILINE)
            new_version = _VERSION.search((source / MANIFEST).read_text(encoding="utf-8"))
            line = (f"- {_dt.date.today().isoformat()}: from origin commit {old_commit.group(1)[:12] if old_commit else 'unknown'}"
                    f" (kit version {previous_version.group(1) if previous_version else 'unknown'}) to {commit[:12]}"
                    f" (kit version {new_version.group(1)}); files written: {len(written)}; owned: {', '.join(owned) or 'none'};"
                    f" refused: {', '.join(refused) or 'none'}")
            text = with_upgrade_record(text, upgrade_lines(previous_notice) + [line])
        target_notice.write_text(text, encoding="utf-8")
        written.append((NOTICE, sha256_file(target_notice)))
    checklist = [
        f"review the merge proposals above, if any; a written {PROPOSED_SETTINGS} is the settings merge ready to adopt or discard",
        f"fill in {SPEC}: at least the maintainer, then the other roles, the verification command and the limits (copy the project's hard rules there, one line each); `{VERIFICATION_COMMAND}` fails while a placeholder remains",
        f"run `{VERIFICATION_COMMAND}` in the target and quote its result",
        "decide whether any git hook the target already had stays beside the kit's hooks",
        "commit under policies/contribution.md; the kit never commits, the maintainer does",
        f"choose the integration path in {SPEC}: `{PUSH_SCRIPT}: github`, `{PUSH_SCRIPT}: none` or `maintainer pushes`; scripts/push_increment.py runs only under the first two and never merges",
        f"then test the kit in a session opened in this checkout: look for the session banner, then paste: {FIRST_SESSION_PROMPT}",
        f"to upgrade later, run the kit.py of the newer export (`python3 <export>/scripts/kit.py install ...`): {UPGRADE_NOTE}",
        f"after each merged pull request, retire its branch as {NOTICE} says under `Retiring an increment branch`",
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
        "upgrade": upgrade,
    }
    if report_path is not None:
        if report_path.exists():  # unreachable after the check above; kept so that the report never overwrites anything
            raise FileExistsError(f"report exists and is not overwritten: {report_path}")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_markdown(report), encoding="utf-8")
        report["report"] = str(report_path)
    return report


def report_markdown(report: dict[str, object]) -> str:
    # kit v12: an upgrade overwrites the copies still at the installed digest, and the report says so
    done = ("Kit copies still at the installed notice's digest and the notice were overwritten; nothing was deleted."
            if report.get("upgrade") else "Nothing was overwritten or deleted.")
    lines = [
        f"# Kit install report for {report['project_name']}",
        "",
        f"Origin commit: `{report['origin_commit']}`. Target: `{report['target']}`. {done}",
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
    dig = sub.add_parser("digests", help=f"rewrite {DIGESTS} from the manifest and the copies in the working tree (kit v17, Decision 0025); the only writer; origin only")
    dig.add_argument("--root", type=Path, default=Path.cwd())
    ins = sub.add_parser("install", help="write the kit into a target, only where files are missing; with --upgrade, "
                         "also replace kit copies still at the installed notice's digest")
    ins.add_argument("--from", dest="source", type=Path, default=Path.cwd(), help="an export directory or the PAES root")
    ins.add_argument("--target", type=Path, required=True)
    ins.add_argument("--project-name", help=f"the target's name; required for an install, read from the target's {SPEC} when "
                     "absent under --upgrade (kit v19)")
    ins.add_argument("--report", type=Path, help=f"report file; default <target>/{DEFAULT_REPORT} for an install and "
                     f"<target>/{UPGRADE_REPORT} for an upgrade, dated today with the export's kit version (kit v19); never overwritten")
    ins.add_argument("--no-report", action="store_true")
    ins.add_argument("--ci", action="store_true", help="also write the CI workflow template of the specification's review backend, when one exists")
    ins.add_argument("--upgrade", action="store_true", help="over an installed kit: overwrite a copy only when it still carries the "
                     "installed notice's digest, refuse a modified one by name, rewrite the notice (kit v12) with a dated upgrade line (kit v13)")
    ins.add_argument("--own", action="append", default=[], metavar="TARGET_PATH",
                     help="with --upgrade, repeatable: take a kit-written copy the target changed as the target's own, so the notice marks "
                     "it `modified` and the kit check stops digest-checking it until it is back at the export's bytes (kit v14); without "
                     "it a modified copy is refused by name and keeps failing the digest check")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            result = export(args.root.resolve(), args.out.resolve())
        elif args.command == "digests":
            result = write_digests(args.root.resolve())
        else:
            target = args.target.resolve()
            source = args.source.resolve()
            if args.no_report:
                report_path = None
            elif args.report:
                report_path = args.report.resolve()
            else:
                report_path = target / (default_upgrade_report(source) if args.upgrade else DEFAULT_REPORT)
            result = install(source, target, args.project_name, report_path, ci=args.ci, upgrade=args.upgrade,
                             take_as_own=tuple(args.own))
    except (ValueError, FileNotFoundError, FileExistsError, OSError) as error:
        print(json.dumps({"result": "FAIL", "error": str(error)}, indent=2))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
