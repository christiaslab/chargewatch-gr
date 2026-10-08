#!/usr/bin/env python3
"""Generic verifier for a checkout that carries the PAES portable kit. Decision 0012 point 4.

Checks only what holds in any target: the permission deny list and no-bypass
setting, hook wiring, the project specification and its verification command
(Decision 0014), the shape of every skill (Decision 0017 point 5), the
commit-history rule over HEAD, the staged-content rules
over the index, task briefs under tasks/, and the kit digests recorded in
adapters/KIT_NOTICE.md. Prints one JSON document; exit 0 on PASS, 1 on FAIL.
Standard library only; imports the kit's own modules from scripts/.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

SETTINGS = ".claude/settings.json"
NOTICE = "adapters/KIT_NOTICE.md"
REQUIRED_DENY = ("Bash(git push:*)", "Bash(git remote:*)", "Bash(rm -rf:*)", "Bash(curl:*)", "Bash(wget:*)")
WILDCARD_ALLOW = {"*", "Bash", "Bash(*)", "Bash(*:*)", "Bash(:*)"}
NO_BYPASS_KEY = "disableBypassPermissionsMode"
# Permission fields the settings schema restricts to one string (kit v3, 2026-09-28). Any other value,
# the boolean true included, has the whole settings file rejected and skipped: the deny list and the
# hooks are then silently inactive while the file still parses as JSON, so presence alone proves nothing.
RESTRICTED_VALUES = {NO_BYPASS_KEY: "disable", "disableAutoMode": "disable"}
HOOK_COMMAND = re.compile(r'^python3 "\$CLAUDE_PROJECT_DIR"/(scripts/hooks/[a-z0-9_]+\.py)$')
_DIGEST_LINE = re.compile(r"^([0-9a-f]{64})  (\S+)$", re.MULTILINE)
_SKIPPED_LINE = re.compile(r"^skipped  (\S+)  ", re.MULTILINE)
# Kit v14: a copy the kit wrote and the target changed since; like a `skipped` line, not digest-checked.
_MODIFIED_LINE = re.compile(r"^modified  (\S+)  ", re.MULTILINE)
# The first fenced command under "## Verification" in AGENTS.md, as the session banner reads it.
_AGENTS_VERIFICATION = re.compile(r"^## Verification\n.*?```[a-z]*\n([^\n]+)\n", re.MULTILINE | re.DOTALL)
# Kit v6 (Decision 0017 point 5): the one shape of a skill. Front matter with name and a description that names
# its triggers; a Doctrine pointer to a file the checkout has; a Script pointer to a script the checkout has; a
# "How to run" block whose every command has an allow entry in the settings; a line saying what it must print.
SKILLS_DIR = ".claude/skills"
_FRONT_MATTER = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
_POINTER = re.compile(r"^- (Doctrine|Script): `([^`]+)`$", re.MULTILINE)
_HOW_TO_RUN = re.compile(r"^## How to run\n\n```[a-z]*\n(.*?)\n```", re.MULTILINE | re.DOTALL)
_MUST_PRINT = re.compile(r"must print", re.IGNORECASE)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_settings(root: Path) -> tuple[bool, str]:
    path = root / SETTINGS
    if not path.is_file():
        return False, f"{SETTINGS} is missing"
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, f"{SETTINGS} is not valid JSON"
    permissions = settings.get("permissions") if isinstance(settings, dict) else None
    if not isinstance(permissions, dict):
        return False, "no permissions block"
    problems = []
    deny = set(permissions.get("deny", []))
    missing = [item for item in REQUIRED_DENY if item not in deny]
    if missing:
        problems.append("deny list lacks " + ", ".join(missing))
    wild = [item for item in permissions.get("allow", []) if item in WILDCARD_ALLOW]
    if wild:
        problems.append("wildcard allow entries: " + ", ".join(wild))
    if NO_BYPASS_KEY not in permissions:
        problems.append(f'bypass mode is not disabled: permissions.{NO_BYPASS_KEY} is absent, expected the string "{RESTRICTED_VALUES[NO_BYPASS_KEY]}"')
    for key, wanted in RESTRICTED_VALUES.items():
        if key in permissions and permissions[key] != wanted:
            problems.append(f'permissions.{key} is {json.dumps(permissions[key])}, not the string "{wanted}"; '
                            "the settings schema rejects it and the whole file is skipped")
    return (not problems), ("; ".join(problems) if problems else "deny list present, no wildcard allow, bypass disabled with a schema-valid value")


def check_hooks(root: Path) -> tuple[bool, str]:
    path = root / SETTINGS
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, f"{SETTINGS} unreadable"
    hooks = settings.get("hooks", {}) if isinstance(settings, dict) else {}
    if not isinstance(hooks, dict):
        return False, "hooks block is not an object"
    wired: list[str] = []
    problems: list[str] = []
    for event, entries in hooks.items():
        for entry in entries if isinstance(entries, list) else []:
            for hook in entry.get("hooks", []) if isinstance(entry, dict) else []:
                command = hook.get("command", "") if isinstance(hook, dict) else ""
                match = HOOK_COMMAND.match(command)
                if not match:
                    problems.append(f"{event}: command is not a project hook script run through CLAUDE_PROJECT_DIR")
                    continue
                if not (root / match.group(1)).is_file():
                    problems.append(f"{event}: {match.group(1)} is missing")
                else:
                    wired.append(match.group(1))
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(wired)} hook commands wired to existing scripts" if wired else "no hooks configured"


def check_project_spec(root: Path) -> tuple[bool, str]:
    """Decision 0014 point 4: the specification exists, carries exactly the closed field set, holds no
    placeholder where a value is required, and agrees with AGENTS.md on the verification command."""
    import kit  # from scripts/
    path = root / kit.SPEC
    if not path.is_file():
        return False, f"{kit.SPEC} is missing; kit version four declares the project's roles and verification command there (Decision 0014)"
    try:
        spec = kit.parse_spec(path.read_text(encoding="utf-8"))
    except ValueError as error:
        return False, f"{kit.SPEC}: {error}"
    problems = []
    missing = [field for field in kit.SPEC_FIELDS if field not in spec and field not in kit.SPEC_OPTIONAL_FIELDS]
    unknown = [field for field in spec if field not in kit.SPEC_FIELDS]
    if missing:
        problems.append("missing fields: " + ", ".join(missing))
    if unknown:
        problems.append("unknown fields: " + ", ".join(unknown))
    if spec.get("spec_version") != kit.SPEC_VERSION:
        problems.append(f"spec_version is {spec.get('spec_version')!r}, expected {kit.SPEC_VERSION}")
    for field in kit.SPEC_FIELDS:
        if field not in spec:
            continue
        value = spec[field]
        if field in kit.SPEC_LIST_FIELDS:
            if not isinstance(value, list):
                problems.append(f"{field} must be a list")
        elif not isinstance(value, str) or not value:
            problems.append(f"{field} must be one non-empty value")
        elif field == "sandbox" and value not in kit.SANDBOX_VALUES:
            problems.append(f"sandbox is {value!r}, expected on or off")
    for field in ("maintainer", "verification_command"):
        if isinstance(spec.get(field), str) and kit.SPEC_PLACEHOLDER in spec[field]:
            problems.append(f"{field} still holds the placeholder {kit.SPEC_PLACEHOLDER}")
    agents = root / "AGENTS.md"
    command = spec.get("verification_command")
    if isinstance(command, str) and command and kit.SPEC_PLACEHOLDER not in command:
        if not agents.is_file():
            problems.append("AGENTS.md is missing, so the verification command is not published to sessions")
        else:
            match = _AGENTS_VERIFICATION.search(agents.read_text(encoding="utf-8", errors="replace"))
            if not match:
                problems.append("AGENTS.md has no fenced command under ## Verification")
            elif match.group(1).strip() != command:
                problems.append(f"AGENTS.md runs {match.group(1).strip()!r} but the specification says {command!r}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{kit.SPEC} declares {spec['project_name']} with maintainer {spec['maintainer']}; AGENTS.md agrees on the verification command"


def allow_prefixes(settings: dict) -> list[str]:
    """The commands the settings allow, as prefixes: `Bash(python3 scripts/x.py:*)` allows `python3 scripts/x.py ...`."""
    permissions = settings.get("permissions") if isinstance(settings, dict) else None
    entries = permissions.get("allow", []) if isinstance(permissions, dict) else []
    prefixes = []
    for item in entries:
        if isinstance(item, str) and item.startswith("Bash(") and item.endswith(":*)"):
            prefixes.append(item[len("Bash("):-len(":*)")])
    return prefixes


def command_allowed(command: str, prefixes: list[str]) -> bool:
    return any(command == prefix or command.startswith(prefix + " ") for prefix in prefixes)


def skill_problems(root: Path, relative: str, text: str, prefixes: list[str]) -> list[str]:
    problems = []
    front = _FRONT_MATTER.match(text)
    name = Path(relative).parent.name
    if not front:
        problems.append("no front matter")
    else:
        if not re.search(rf"^name: {re.escape(name)}$", front.group(1), re.MULTILINE):
            problems.append(f"front matter name is not {name!r}")
        if not re.search(r"^description: .*Triggers", front.group(1), re.MULTILINE):
            problems.append("description names no triggers")
    pointers = dict(_POINTER.findall(text))
    for kind in ("Doctrine", "Script"):
        target = pointers.get(kind)
        if not target:
            problems.append(f"no {kind} pointer")
        elif target.startswith("/") or ".." in Path(target).parts or not (root / target).is_file():
            problems.append(f"{kind} points at {target}, which this checkout does not have")
    block = _HOW_TO_RUN.search(text)
    if not block:
        problems.append("no `## How to run` block with a fenced command")
    else:
        for command in (line.strip() for line in block.group(1).splitlines() if line.strip()):
            if not command_allowed(command, prefixes):
                problems.append(f"command has no allow entry in {SETTINGS}: {command}")
    if not _MUST_PRINT.search(text):
        problems.append("no line saying what it must print")
    return problems


def check_skills(root: Path) -> tuple[bool, str]:
    """Decision 0017 point 5: every skill under .claude/skills/ has the one shape, and each pointer resolves here."""
    skills = sorted((root / SKILLS_DIR).glob("*/SKILL.md"))
    if not skills:
        return False, f"no skill under {SKILLS_DIR}; the kit ships three"
    try:
        settings = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False, f"{SETTINGS} unreadable, so no command can be matched to an allow entry"
    prefixes = allow_prefixes(settings)
    problems = []
    for path in skills:
        relative = path.relative_to(root).as_posix()
        for problem in skill_problems(root, relative, path.read_text(encoding="utf-8", errors="replace"), prefixes):
            problems.append(f"{relative}: {problem}")
    if problems:
        return False, "; ".join(problems)
    return True, f"{len(skills)} skills have the one shape; every doctrine, script and command resolves in this checkout"


def check_commit_history(root: Path) -> tuple[bool, str]:
    import commit_hygiene  # from scripts/
    try:
        report = commit_hygiene.check_history(root)
    except RuntimeError as error:
        return False, str(error)
    if report["passed"]:
        return True, f"{report['commits']} commits clean"
    return False, "; ".join(f"{item['commit']}: {item['rule']}" for item in report["findings"])


def check_staged_content(root: Path) -> tuple[bool, str]:
    import commit_rules  # from scripts/
    try:
        report = commit_rules.scan_staged(root)
    except Exception as error:  # a scan failure is a failure, never a pass
        return False, f"{type(error).__name__}: {error}"
    if report["result"] == "PASS":
        return True, f"{report['artifact_count']} staged paths, no findings, {len(report['advisories'])} advisories"
    return False, "; ".join(f"{item['path']}: {item['rule']}" for item in report["findings"])


def check_task_briefs(root: Path) -> tuple[bool, str]:
    import task_contract  # from scripts/
    tasks = root / "tasks"
    if not tasks.is_dir():
        return True, "no tasks/ directory"
    problems = []
    briefs = sorted(tasks.glob("*.json"))
    for brief in briefs:
        try:
            errors = task_contract.validate_brief(task_contract.load_brief(brief))
        except Exception as error:
            errors = [f"{type(error).__name__}: {error}"]
        if errors:
            problems.append(f"{brief.name}: {errors[0]}")
    return (not problems), ("; ".join(problems) if problems else f"{len(briefs)} briefs valid")


def check_notice_digests(root: Path) -> tuple[bool, str]:
    notice = root / NOTICE
    if not notice.is_file():
        return True, "no kit notice; this checkout is the origin or was not installed from an export"
    text = notice.read_text(encoding="utf-8")
    recorded = _DIGEST_LINE.findall(text)
    skipped = _SKIPPED_LINE.findall(text)
    modified = _MODIFIED_LINE.findall(text)
    if not recorded and not skipped and not modified:
        return False, "kit notice lists no digests"
    problems = []
    for digest, relative in recorded:
        path = root / relative
        if not path.is_file():
            problems.append(f"{relative} missing")
        elif sha256_file(path) != digest:
            problems.append(f"{relative} differs from the exported version")
    summary = (f"{len(recorded)} kit files match the notice" + (f"; {len(skipped)} target-owned files not digest-checked" if skipped else "")
               + (f"; {len(modified)} kit files modified by the target, not digest-checked" if modified else ""))
    return (not problems), ("; ".join(problems) if problems else summary)


CHECKS = (
    ("kit-settings", check_settings),
    ("kit-hooks-wired", check_hooks),
    ("kit-project-spec", check_project_spec),
    ("kit-skills", check_skills),
    ("kit-commit-history", check_commit_history),
    ("kit-staged-content", check_staged_content),
    ("kit-task-briefs", check_task_briefs),
    ("kit-notice-digests", check_notice_digests),
)


def verify(root: Path) -> dict[str, object]:
    sys.path.insert(0, str(root / "scripts"))
    checks = []
    for name, function in CHECKS:
        try:
            passed, detail = function(root)
        except Exception as error:  # an unexpected error fails the check, never hides it
            passed, detail = False, f"{type(error).__name__}: {error}"
        checks.append({"check": name, "passed": passed, "detail": detail})
    return {"result": "PASS" if all(item["passed"] for item in checks) else "FAIL", "checks": checks}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify a checkout that carries the PAES portable kit.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    report = verify(args.root.resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
