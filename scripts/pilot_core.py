from __future__ import annotations

import hashlib
import html
import io
import json
import re
import csv
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Mapping, Sequence


OUTPUT_FILES = ("dashboard-data.json", "index.html")


def canonical_json(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("input must contain a non-empty rows list")
    return rows


def build_dashboard_model(rows: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Aggregate rows with a stable unique-key order."""
    totals: dict[str, Decimal] = defaultdict(Decimal)
    for row in rows:
        key = str(row["category"]).strip()
        if not key:
            raise ValueError("category cannot be empty")
        amount = Decimal(str(row["amount"]))
        if amount < 0:
            raise ValueError("amount cannot be negative")
        totals[key] += amount

    overall = sum(totals.values(), Decimal("0"))
    if overall == 0:
        raise ValueError("total amount must be greater than zero")

    result_rows: list[dict[str, object]] = []
    for key in sorted(totals, key=lambda item: (item.casefold(), item)):
        amount = totals[key]
        share = (amount / overall).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
        result_rows.append(
            {
                "category": key,
                "amount": int(amount) if amount == amount.to_integral() else float(amount),
                "share_of_total": float(share),
            }
        )

    return {
        "schema_version": 1,
        "metric": "amount",
        "total": int(overall) if overall == overall.to_integral() else float(overall),
        "rows": result_rows,
    }


def render_dashboard(model: Mapping[str, object]) -> str:
    rows = model["rows"]
    if not isinstance(rows, list):
        raise ValueError("model rows must be a list")

    table_rows: list[str] = []
    for row in rows:
        category = html.escape(str(row["category"]))
        amount = row["amount"]
        share = float(row["share_of_total"])
        table_rows.append(
            """          <tr>
            <th scope="row">{category}</th>
            <td>{amount}</td>
            <td>
              <span class="bar" style="--share: {percentage:.2f}%" aria-hidden="true"></span>
              <span>{percentage:.2f}%</span>
            </td>
          </tr>""".format(category=category, amount=amount, percentage=share * 100)
        )

    total = html.escape(str(model["total"]))
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Synthetic Operations Dashboard</title>
  <style>
    :root { color-scheme: light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f5f7fb; color: #16213b; }
    main { max-width: 880px; margin: 0 auto; padding: 3rem 1.5rem; }
    .eyebrow { color: #48617d; font-size: .78rem; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }
    h1 { font-size: clamp(2rem, 5vw, 3.5rem); margin: .4rem 0; }
    .summary { color: #53657a; max-width: 62ch; }
    .total { align-items: baseline; display: flex; gap: .65rem; margin-top: 1.5rem; }
    .total strong { font-size: 2rem; }
    .card { background: white; border: 1px solid #d9e1ec; border-radius: 16px; box-shadow: 0 12px 35px rgba(32, 55, 88, .08); margin-top: 2rem; overflow: hidden; }
    table { border-collapse: collapse; width: 100%; }
    caption { font-size: 1.15rem; font-weight: 700; padding: 1.25rem; text-align: left; }
    th, td { border-top: 1px solid #e6ebf2; padding: 1rem 1.25rem; text-align: left; }
    thead th { background: #eef3f8; color: #344960; font-size: .78rem; letter-spacing: .06em; text-transform: uppercase; }
    .bar { background: #2474e5; border-radius: 999px; display: inline-block; height: .65rem; margin-right: .65rem; max-width: 9rem; min-width: .25rem; width: var(--share); }
    .footnote { color: #617287; font-size: .82rem; margin-top: 1rem; }
  </style>
</head>
<body>
  <main>
    <p class="eyebrow">Synthetic pilot artifact</p>
    <h1>Operations overview</h1>
    <p class="summary">A deterministic view of synthetic amounts by category, including each category's share of total.</p>
    <p class="total"><span>Total amount</span><strong data-rendered-total>@@TOTAL@@</strong></p>
    <section class="card" aria-labelledby="breakdown-caption">
      <table>
        <caption id="breakdown-caption">Amount and share of total by category</caption>
        <thead>
          <tr><th scope="col">Category</th><th scope="col">Amount</th><th scope="col">Share of total</th></tr>
        </thead>
        <tbody>
@@ROWS@@
        </tbody>
      </table>
    </section>
    <p class="footnote">All values are fabricated for this local pilot.</p>
  </main>
</body>
</html>
""".replace("@@ROWS@@", "\n".join(table_rows)).replace("@@TOTAL@@", total)


def build_dashboard(input_path: Path, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    model = build_dashboard_model(load_rows(input_path))
    data_path = output_dir / "dashboard-data.json"
    html_path = output_dir / "index.html"
    data_path.write_text(canonical_json(model), encoding="utf-8")
    html_path.write_text(render_dashboard(model), encoding="utf-8")
    return {"data": data_path, "html": html_path}


def reconcile_intersection(
    left: Mapping[str, int | float], right: Mapping[str, int | float]
) -> dict[str, object]:
    keys = sorted(set(left).intersection(right))
    differences = [
        {"key": key, "left": left[key], "right": right[key]}
        for key in keys
        if Decimal(str(left[key])) != Decimal(str(right[key]))
    ]
    return {
        "result": "PASS" if not differences else "FAIL",
        "compared_keys": keys,
        "differences": differences,
        "left_only": sorted(set(left).difference(right)),
        "right_only": sorted(set(right).difference(left)),
    }


def validate_reference_set(
    internal: Mapping[str, int | float], references: Sequence[Mapping[str, int | float]]
) -> dict[str, object]:
    if not references:
        return {
            "check": "external-reference-reconciliation",
            "result": "WARN",
            "detail": "reference absent; internal checks remain eligible",
            "ratio": None,
        }

    signatures = [
        (len(reference), sum(Decimal(str(value)) for value in reference.values()))
        for reference in references
    ]
    duplicate_signature = len(signatures) != len(set(signatures))
    reference = references[0]
    common = sorted(set(internal).intersection(reference))
    internal_total = sum((Decimal(str(internal[key])) for key in common), Decimal("0"))
    reference_total = sum((Decimal(str(reference[key])) for key in common), Decimal("0"))
    ratio = None if internal_total == 0 else reference_total / internal_total

    if ratio != Decimal("1"):
        result = "FAIL"
        detail = f"intersection ratio={ratio}; keys={len(common)}"
    elif duplicate_signature:
        result = "WARN"
        detail = "duplicate reference signature; intersection ratio=1; keys=" + str(len(common))
    else:
        result = "PASS"
        detail = "intersection ratio=1; keys=" + str(len(common))
    return {
        "check": "external-reference-reconciliation",
        "result": result,
        "detail": detail,
        "ratio": float(ratio) if ratio is not None else None,
        "compared_keys": common,
        "duplicate_signature": duplicate_signature,
    }


SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:api[_-]?key|password|secret|token)\b\s*[:=]\s*[^\s]+"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)


def scan_text(text: str, banned_terms: Iterable[str] = ()) -> list[str]:
    findings: list[str] = []
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        findings.append("secret-like-assignment")
    lowered = text.casefold()
    if any(term.casefold() in lowered for term in banned_terms if term):
        findings.append("configured-private-identifier")
    return findings


def scan_paths(paths: Iterable[Path], banned_terms: Iterable[str] = ()) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append({"path": path.as_posix(), "rule": "unexpected-binary"})
            continue
        for rule in scan_text(text, banned_terms):
            findings.append({"path": path.as_posix(), "rule": rule})
    return findings


NEVER_COMMIT_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".parquet", ".xlsx", ".xls"}


def scan_staged_entries(
    entries: Mapping[str, str | bytes],
    allowlisted_curated: Iterable[str] = (),
    banned_terms: Iterable[str] = (),
) -> dict[str, list[dict[str, str]]]:
    """Scan only the supplied staged snapshot and report rules, never matched values."""
    allowlist = set(allowlisted_curated)
    findings: list[dict[str, str]] = []
    exemptions: list[dict[str, str]] = []
    for label, content in entries.items():
        if label in allowlist:
            exemptions.append({"path": label, "rule": "curated-path-content-review-deferred"})
            continue
        if Path(label).suffix.casefold() in NEVER_COMMIT_SUFFIXES:
            findings.append({"path": label, "rule": "never-commit-artifact-class"})
            continue
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                findings.append({"path": label, "rule": "unexpected-binary"})
                continue
        else:
            text = content
        for rule in scan_text(text, banned_terms):
            findings.append({"path": label, "rule": rule})
    return {"findings": findings, "exemptions": exemptions}


PERSON_LIKE_NOTE = re.compile(r"\b(?:ask|contact|notify)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b")


def steward_review_curated(
    entries: Mapping[str, str], curated_paths: Iterable[str], doctrine_enabled: bool = True
) -> list[dict[str, str]]:
    """Apply judgment to allowlisted curated text without returning matched content."""
    if not doctrine_enabled:
        return []
    findings: list[dict[str, str]] = []
    for path in curated_paths:
        text = entries.get(path)
        if text is None:
            continue
        reader = csv.DictReader(io.StringIO(text))
        for line_number, row in enumerate(reader, start=2):
            if any(PERSON_LIKE_NOTE.search(value or "") for value in row.values()):
                findings.append(
                    {
                        "path": f"{path}:{line_number}",
                        "rule": "incidental-personal-data-in-curated-text",
                        "verdict": "BLOCK",
                    }
                )
    return findings


class _StructureParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.text: list[str] = []
        self.lang = ""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        if tag == "html":
            self.lang = dict(attrs).get("lang") or ""

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.text.append(data.strip())


def validate_rendered_html(document: str) -> dict[str, bool]:
    parser = _StructureParser()
    parser.feed(document)
    joined = " ".join(parser.text).casefold()
    return {
        "declares_language": bool(parser.lang),
        "has_title": "title" in parser.tags,
        "has_main_landmark": "main" in parser.tags,
        "has_primary_heading": "h1" in parser.tags,
        "has_data_table": "table" in parser.tags,
        "has_table_caption": "caption" in parser.tags,
        "shows_amount": "amount" in joined,
        "shows_share_of_total": "share of total" in joined,
        "has_rendered_total": "total amount" in joined and "data-rendered-total" in document,
        "states_synthetic_status": "synthetic" in joined or "fabricated" in joined,
    }


def validate_rendered_total(document: str, expected_total: int | float) -> dict[str, object]:
    match = re.search(r"data-rendered-total[^>]*>\s*([^<]+)\s*<", document)
    if not match:
        return {"result": "FAIL", "stale_layer": "rendered-definition-layer", "detail": "total tile missing"}
    try:
        actual = Decimal(match.group(1).strip())
    except Exception:
        return {"result": "FAIL", "stale_layer": "rendered-definition-layer", "detail": "total tile is not numeric"}
    expected = Decimal(str(expected_total))
    return {
        "result": "PASS" if actual == expected else "FAIL",
        "stale_layer": None if actual == expected else "rendered-data-layer",
        "detail": "rendered total matches independent recomputation" if actual == expected else "rendered total differs from independent recomputation",
    }


def gate_effect(result: str, enforcement_context: str, human_waiver: bool = False) -> dict[str, object]:
    if result not in {"PASS", "FAIL"}:
        raise ValueError("result must be PASS or FAIL")
    if enforcement_context not in {"pipeline", "release"}:
        raise ValueError("enforcement_context must be pipeline or release")
    if human_waiver and not (result == "FAIL" and enforcement_context == "release"):
        raise ValueError("waivers apply only to failed release gates")

    if enforcement_context == "pipeline":
        effect = "record" if result == "PASS" else "record-without-rollback"
        may_progress = True
        recorded_result = result
    elif result == "PASS":
        effect = "allow"
        may_progress = True
        recorded_result = result
    elif human_waiver:
        effect = "allow-with-human-waiver"
        may_progress = True
        recorded_result = "WAIVED"
    else:
        effect = "block"
        may_progress = False
        recorded_result = result

    return {
        "result": recorded_result,
        "enforcement_context": enforcement_context,
        "gate_effect": effect,
        "writes_preserved": True,
        "may_progress": may_progress,
    }


def workflow_stages(artifact_kind: str) -> list[str]:
    stages = ["build", "commit-guard", "validation-suite", "verify-by-rebuild"]
    if artifact_kind == "rendered":
        stages.extend(["bi-author-review", "render-validation", "visual-evidence"])
    stages.extend(["data-steward-review", "human-release-gate"])
    return stages
