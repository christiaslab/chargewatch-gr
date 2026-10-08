#!/usr/bin/env python3
"""Push the current increment branch to origin and open its review. Decisions 0013 and 0017.

The adapter keeps denying a raw ``git push``; this script is the one allowed way
to publish an increment, and it refuses everything the rules refuse: ``main``
or any branch not shaped ``type/slug``, a dirty tree, a second remote, a
checkout whose verification does not PASS, and any force option (none exists
here). It never merges: ``gh pr merge`` is not called and not allowed.

Kit version six (Decision 0017 point 2) splits it in two. The core is
provider-neutral: the refusals, the verification gate, ``git fetch``, ``git
push --set-upstream``, the attribution-stripped body and the one JSON report.
The step "open the review" runs behind a backend named by the ``integration``
field of ``adapters/project-spec.yaml``:

    push script: github   gh pr list --state open, gh pr create; when pr create fails,
                          gh api POST repos/<owner>/<repo>/pulls (REST) once
    push script: none     push only; the maintainer opens the review by hand
    maintainer pushes     the script refuses to run

The REST fallback serves hosts where GitHub's GraphQL endpoint is blocked and
REST is not (owner ruling 2026-10-07); owner and repository come from the
configured ``origin`` URL, never from ``gh repo view``, which is GraphQL. The
report's ``route`` says which path created the review: ``cli`` or ``rest``.

The backend set is closed and trial-driven (point 4): ``azure-devops`` and
others join it only once a target on that host has tried them. The core makes
no HTTP call and reads no token; authentication belongs to the provider's CLI
and the environment. The verification command is the specification's and
the provider's CLI is found on PATH by name: no option overrides either, so
the allow entry a target carries cannot be turned into a bypass of the gate.
Kit version eighteen: ``--draft`` (default off) opens the review as a draft, so a host that asks code owners
(``CODEOWNERS``) to review every ready pull request asks none until the maintainer marks it ready; the
report says ``"draft": true`` or ``false``, the flag as given, also when an existing open review is reused.
Standard library only; runs ``git`` and the provider's CLI as subprocesses.
Prints one JSON document; exit 0 when the branch is on ``origin`` and the
review step of its backend is done, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# The script imports modules from the checkout it publishes; bytecode written there would dirty the tree.
sys.dont_write_bytecode = True

BRANCH = re.compile(r"^(feat|fix|docs|chore)/[a-z0-9][a-z0-9-]{0,63}$")
PROTECTED = ("main",)
REMOTE = "origin"
PUSH_SCRIPT = "push script"
MAINTAINER_PUSHES = "maintainer pushes"


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def refusals(root: Path, branch: str) -> list[str]:
    problems = []
    if branch in PROTECTED or not BRANCH.match(branch):
        problems.append(f"branch {branch!r} is not an increment branch of the form type/slug")
    if git(root, "status", "--porcelain"):
        problems.append("working tree is not clean")
    remotes = git(root, "remote").split()
    if remotes != [REMOTE]:
        problems.append(f"remotes are {remotes}, expected exactly [{REMOTE!r}]")
    return problems


def integration_backend(spec: dict[str, object]) -> tuple[str | None, str | None]:
    """The backend named by the specification's `integration` field, or why the script may not run.
    The field is parsed once, by kit.integration_backend; this function only rules on the result."""
    import kit  # from scripts/
    value = spec.get("integration")
    if not isinstance(value, str) or not value.strip():
        return None, "the specification has no integration field"
    text = " ".join(value.split())
    if text == MAINTAINER_PUSHES:
        return None, f"integration is '{MAINTAINER_PUSHES}': the maintainer pushes, the script does not run here"
    if text == PUSH_SCRIPT:
        return None, f"integration '{PUSH_SCRIPT}' names no backend; write '{PUSH_SCRIPT}: github' or '{PUSH_SCRIPT}: none'"
    name = kit.integration_backend(spec)
    if name is None:
        return None, f"integration {value!r} is in the project's own words; the script runs only under '{PUSH_SCRIPT}: <backend>'"
    if name not in BACKENDS:
        return None, f"backend {name!r} is not in the set {sorted(BACKENDS)}; a backend joins it only after a target has tried it (Decision 0017 point 4)"
    return name, None


def read_specification(root: Path) -> tuple[dict[str, object] | None, str | None]:
    try:
        import kit  # from scripts/
    except ImportError:
        return None, "scripts/kit.py is missing; the kit ships it beside this script"
    path = root / kit.SPEC
    if not path.is_file():
        return None, f"{kit.SPEC} is missing; the script reads its integration path and verification command there (Decision 0014)"
    try:
        return kit.parse_spec(path.read_text(encoding="utf-8")), None
    except (OSError, ValueError) as error:
        return None, f"{kit.SPEC}: {error}"


def verification_passes(root: Path, command: str) -> tuple[bool, str]:
    run = subprocess.run(command, shell=True, cwd=root, capture_output=True, text=True)
    try:
        result = json.loads(run.stdout)["result"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return False, f"verification printed no result (exit {run.returncode})"
    return result == "PASS", f"verification {result}"


def clean_body(text: str) -> str:
    """Drop attribution lines; policies/contribution.md forbids them in review descriptions too.
    Runs in the core, before any backend, so no backend can send one."""
    import commit_hygiene  # from scripts/
    return "\n".join(line for line in text.splitlines() if not commit_hygiene.inspect_message(line)) + "\n"


def title_problem(title: str) -> str | None:
    import commit_hygiene  # from scripts/
    return "the title carries an attribution line, which policies/contribution.md forbids" if commit_hygiene.inspect_message(title) else None


def default_body(root: Path, branch: str, verify_command: str, verification: str) -> str:
    subjects = git(root, "log", "--format=- %s", f"{REMOTE}/main..HEAD")
    return f"Increment branch `{branch}`.\n\nCommits:\n{subjects}\n\nLocal `{verify_command}`: {verification}.\n"


# Backends. Each takes the root, the branch, the title, the cleaned body and the CLI executable, and returns
# (url, created, error, route): the review's URL when one exists, whether this call created it, an error text
# when the provider's CLI refused, and the path that created it. A backend runs the provider's CLI and a read of the
# configured origin URL, and nothing else; no error or report text carries that URL, which may hold a credential.

GITHUB_URL = re.compile(r"^(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^@/]+@)?github\.com/)"
                        r"(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?/?$")


def github_repository(url: str) -> tuple[str, str] | None:
    """Owner and repository from a GitHub remote URL, SSH or HTTPS form; None for any other URL, a local path included."""
    match = GITHUB_URL.match(url.strip())
    return (match["owner"], match["repo"]) if match else None


def origin_repository(root: Path) -> tuple[str, str] | None:
    """Owner and repository of the configured origin URL. The configured URL is read, not ``git remote get-url``,
    which expands ``insteadOf`` rewrites into a URL that may no longer name the repository."""
    configured = subprocess.run(["git", "config", "--get", f"remote.{REMOTE}.url"], cwd=root, capture_output=True, text=True).stdout.strip()
    return github_repository(configured)


def rest_open_review(root: Path, branch: str, cli: str) -> str | None:
    """The open pull request for this branch through REST, for hosts where ``gh pr list`` (GraphQL) is blocked."""
    repository = origin_repository(root)
    if repository is None:
        return None
    owner, repo = repository
    found = subprocess.run([cli, "api", "--method", "GET", f"repos/{owner}/{repo}/pulls?head={owner}:{branch}&state=open"],
                           cwd=root, capture_output=True, text=True)
    if found.returncode != 0:
        return None
    try:
        url = json.loads(found.stdout)[0]["html_url"]
    except (json.JSONDecodeError, IndexError, KeyError, TypeError):
        return None
    return url if isinstance(url, str) and url else None


def rest_create(root: Path, branch: str, title: str, body: str, cli: str, draft: bool = False) -> tuple[str | None, str | None]:
    """Open the pull request through REST with ``gh api``; returns (url, error)."""
    repository = origin_repository(root)
    if repository is None:
        return None, f"the REST fallback was skipped: {REMOTE} names no GitHub owner and repository"
    owner, repo = repository
    payload = json.dumps({"title": title, "head": branch, "base": "main", "body": body, "draft": draft})
    run = subprocess.run([cli, "api", "--method", "POST", f"repos/{owner}/{repo}/pulls", "--input", "-"],
                         cwd=root, input=payload, capture_output=True, text=True)
    if run.returncode != 0:
        return None, f"{Path(cli).name} api (REST) failed: {(run.stderr.strip() or run.stdout.strip())[:200]}"
    try:
        url = json.loads(run.stdout)["html_url"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None, f"{Path(cli).name} api (REST) replied without html_url: {run.stdout.strip()[:200]}"
    return (url, None) if isinstance(url, str) and url else (None, f"{Path(cli).name} api (REST) replied with an empty html_url")

def open_review(root: Path, branch: str, cli: str) -> str | None:
    """The URL of the OPEN pull request whose head is this branch, or None. A merged or closed one that once
    used the same branch name does not count (``gh pr view <branch>`` would return it, so it is not used).
    When ``gh pr list`` fails (GraphQL blocked), the lookup is tried once through REST."""
    found = subprocess.run([cli, "pr", "list", "--head", branch, "--state", "open", "--json", "url", "--jq", ".[0].url // empty"],
                           cwd=root, capture_output=True, text=True)
    if found.returncode != 0:
        return rest_open_review(root, branch, cli)
    return found.stdout.strip().splitlines()[0] if found.stdout.strip() else None


def github_backend(root: Path, branch: str, title: str, body: str, cli: str, draft: bool = False) -> tuple[str | None, bool, str | None, str | None]:
    existing = open_review(root, branch, cli)
    if existing:
        return existing, False, None, None
    run = subprocess.run([cli, "pr", "create", "--base", "main", "--head", branch, "--title", title, "--body", body]
                         + (["--draft"] if draft else []), cwd=root, capture_output=True, text=True)
    if run.returncode != 0:
        cli_error = f"{Path(cli).name} pr create failed: {run.stderr.strip()[:200]}"
        url, rest_error = rest_create(root, branch, title, body, cli, draft)
        if url is None:
            return None, False, f"{cli_error}; {rest_error}; the branch is pushed, open the review by hand", None
        return url, True, None, "rest"
    url = run.stdout.strip().splitlines()[-1] if run.stdout.strip() else None
    if url is None:
        url = open_review(root, branch, cli)
    if url is None:
        return None, True, f"{Path(cli).name} pr create printed no URL and pr list found no open one; the branch is pushed, check the review by hand", None
    return url, True, None, "cli"


def none_backend(root: Path, branch: str, title: str, body: str, cli: str, draft: bool = False) -> tuple[str | None, bool, str | None, str | None]:
    return None, False, None, None


BACKENDS = {"github": github_backend, "none": none_backend}
# The provider's CLI, found on PATH by name; a backend without one runs no program.
BACKEND_CLI = {"github": "gh", "none": None}


def publish(root: Path, title: str | None, body_file: Path | None, draft: bool = False) -> dict[str, object]:
    sys.path.insert(0, str(root / "scripts"))
    branch = git(root, "rev-parse", "--abbrev-ref", "HEAD")
    problems = refusals(root, branch)
    if problems:
        return {"result": "FAIL", "branch": branch, "refused": problems}
    spec, error = read_specification(root)
    if error:
        return {"result": "FAIL", "branch": branch, "refused": [error]}
    backend, error = integration_backend(spec)
    if error:
        return {"result": "FAIL", "branch": branch, "refused": [error]}
    import kit  # from scripts/
    command = spec.get("verification_command")
    verify_command = command if isinstance(command, str) and command and kit.SPEC_PLACEHOLDER not in command else None
    if not verify_command:
        return {"result": "FAIL", "branch": branch, "refused": ["the specification names no verification command"]}
    cli = BACKEND_CLI[backend]
    if cli is not None and shutil.which(cli) is None:
        return {"result": "FAIL", "branch": branch, "refused": [f"the {backend!r} backend needs {cli!r} on PATH and it is absent; nothing was pushed"]}
    title = title or git(root, "log", "-1", "--format=%s")
    problem = title_problem(title)
    if problem:
        return {"result": "FAIL", "branch": branch, "refused": [problem]}
    passed, verification = verification_passes(root, verify_command)
    if not passed:
        return {"result": "FAIL", "branch": branch, "refused": [verification]}
    git(root, "fetch", REMOTE)
    git(root, "push", "--set-upstream", REMOTE, branch)
    body = clean_body(body_file.read_text(encoding="utf-8") if body_file else default_body(root, branch, verify_command, verification))
    url, created, error, route = BACKENDS[backend](root, branch, title, body, cli or "", draft)
    if error:
        return {"result": "FAIL", "branch": branch, "pushed_to": REMOTE, "backend": backend, "refused": [error]}
    report: dict[str, object] = {"result": "PASS", "branch": branch, "pushed_to": REMOTE, "backend": backend,
                                 "pull_request": url, "created": created, "draft": draft, "verification": verification,
                                 "merge": "left to the maintainer"}
    if route:
        report["route"] = route
    if backend == "none":
        report["review"] = f"the maintainer opens the review of branch {branch!r} by hand; no review tool is configured"
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Push the increment branch and open its review through the specification's backend; never merge.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--title", help="review title; default: the last commit subject")
    parser.add_argument("--body-file", type=Path, help="review body; default: the commit subjects and the verification result")
    parser.add_argument("--draft", action="store_true", help="open the review as a draft, so code owners are not requested yet (kit v18)")
    args = parser.parse_args(argv)
    try:
        report = publish(args.root.resolve(), args.title, args.body_file, args.draft)
    except (subprocess.CalledProcessError, OSError) as error:
        detail = getattr(error, "stderr", "") or str(error)
        report = {"result": "FAIL", "refused": [f"{type(error).__name__}: {str(detail).strip()[:200]}"]}
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
