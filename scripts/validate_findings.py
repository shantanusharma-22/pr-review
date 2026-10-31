#!/usr/bin/env python3
"""
validate_findings.py - Validate a review decision JSON against the schema AND
the review policy. Fails loudly: a review that fails validation is never
rendered or posted.

Usage:
    python scripts/validate_findings.py <decision.json> [--files files.json] [--fix]

Policy gates (beyond JSON Schema):
  G1  verdict must be consistent with findings:
        any P0/P1 finding            -> REQUEST_CHANGES
        blocking security concern    -> REQUEST_CHANGES
        proofStatus == "missing" and proof required -> REQUEST_CHANGES
        productReview.worthIt == "no" -> REQUEST_CHANGES or COMMENT (never APPROVE)
        productReview.worthIt == "needs_maintainer" -> not APPROVE
  G2  finding ids unique; lineEnd >= lineStart
  G3  with --files: every finding/inline file must be in the PR's changed files
  G4  no duplicated inline comment (same file+line as a finding)
  G5  rating.overallTier may not exceed patchTier or proofTier by more than one step
  G6  summary/body text must not contain tool-plumbing words we never post

--fix rewrites the file with auto-corrections where safe (verdict downgrade,
empty-array defaults, side default). Everything else is reported as an error.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parent / "schema" / "review-decision.schema.json"
TIERS = ["F", "D", "C", "B", "A", "S"]
PLUMBING = re.compile(r"\b(as an ai|language model|i cannot|system prompt|tool call)\b", re.I)


def load(p: str | Path):
    with open(p) as f:
        return json.load(f)


def schema_errors(decision: dict) -> list[str]:
    try:
        import jsonschema  # type: ignore
    except ImportError:
        return ["(jsonschema not installed: `pip install jsonschema` to enable schema validation)"]
    v = jsonschema.Draft202012Validator(load(SCHEMA))
    return [f"schema: {'/'.join(str(x) for x in e.absolute_path) or '<root>'}: {e.message}" for e in v.iter_errors(decision)]


def policy_errors(d: dict, changed_files: set[str] | None, fix: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    fixes: list[str] = []

    for key in ("findings", "risks", "praise", "questions", "inlineComments"):
        if d.get(key) is None:
            d[key] = []
            fixes.append(f"defaulted {key} to []")

    findings = d.get("findings", [])
    sec = d.get("securityReview", {})
    test = d.get("testingReview", {})
    prod = d.get("productReview", {})
    verdict = d.get("verdict")

    # G1 verdict consistency
    must_request = False
    reasons = []
    if any(f.get("priority") in ("P0", "P1") for f in findings):
        must_request, reasons = True, reasons + ["P0/P1 finding present"]
    if any(c.get("blocking") for c in sec.get("concerns", [])):
        must_request, reasons = True, reasons + ["blocking security concern"]
    if test.get("proofStatus") == "missing":
        must_request, reasons = True, reasons + ["required proof missing"]
    if must_request and verdict != "REQUEST_CHANGES":
        if fix:
            d["verdict"] = "REQUEST_CHANGES"
            fixes.append(f"verdict {verdict} -> REQUEST_CHANGES ({'; '.join(reasons)})")
        else:
            errors.append(f"G1: verdict is {verdict} but policy requires REQUEST_CHANGES ({'; '.join(reasons)})")
    if prod.get("worthIt") in ("no", "needs_maintainer") and d.get("verdict") == "APPROVE":
        if fix:
            d["verdict"] = "COMMENT" if not must_request else "REQUEST_CHANGES"
            fixes.append(f"verdict APPROVE -> {d['verdict']} (productReview.worthIt={prod.get('worthIt')})")
        else:
            errors.append(f"G1: cannot APPROVE when productReview.worthIt={prod.get('worthIt')}")

    # G2 ids and ranges
    ids = [f.get("id") for f in findings]
    if len(ids) != len(set(ids)):
        errors.append("G2: duplicate finding ids")
    for f in findings:
        if f.get("lineEnd", 0) < f.get("lineStart", 0):
            if fix:
                f["lineEnd"] = f["lineStart"]
                fixes.append(f"{f.get('id')}: lineEnd < lineStart, set equal")
            else:
                errors.append(f"G2: {f.get('id')} lineEnd < lineStart")

    # G3 files exist in PR
    if changed_files is not None:
        for f in findings:
            if f.get("file") not in changed_files:
                errors.append(f"G3: {f.get('id')} references {f.get('file')!r} which is not in the PR diff")
        for c in d.get("inlineComments", []):
            if c.get("file") not in changed_files:
                errors.append(f"G3: inline comment references {c.get('file')!r} which is not in the PR diff")

    # G4 no duplicated inline
    anchors = {(f.get("file"), f.get("lineEnd")) for f in findings}
    for c in d.get("inlineComments", []):
        c.setdefault("side", "RIGHT")
        c.setdefault("startLine", None)
        if (c.get("file"), c.get("line")) in anchors:
            errors.append(f"G4: inline comment at {c.get('file')}:{c.get('line')} duplicates a finding anchor")

    # G5 tier sanity
    r = d.get("rating", {})
    try:
        o, p, pr_ = (TIERS.index(r["overallTier"]), TIERS.index(r["patchTier"]), TIERS.index(r["proofTier"]))
        if o > min(p, pr_) + 1:
            errors.append(f"G5: overallTier {r['overallTier']} is more than one step above patch/proof tiers")
        if findings and any(f["priority"] in ("P0", "P1") for f in findings) and r["overallTier"] in ("S", "A"):
            errors.append("G5: overallTier S/A with an open P0/P1 finding")
    except (KeyError, ValueError):
        pass  # schema reports NA / missing

    # G6 plumbing words
    for field in ("summary", "changeSummary"):
        if PLUMBING.search(d.get(field, "") or ""):
            errors.append(f"G6: {field} contains text that must never be posted")

    return errors, fixes


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decision")
    ap.add_argument("--files", help="files.json from fetch_pr.py to verify paths")
    ap.add_argument("--fix", action="store_true", help="apply safe auto-corrections in place")
    a = ap.parse_args()

    d = load(a.decision)
    changed = {f["filename"] for f in load(a.files)} if a.files else None

    errs = schema_errors(d)
    perrs, fixes = policy_errors(d, changed, a.fix)
    errs += perrs

    if fixes:
        Path(a.decision).write_text(json.dumps(d, indent=2))
        for fx in fixes:
            print(f"fixed: {fx}", file=sys.stderr)

    if errs:
        for e in errs:
            print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    n = len(d["findings"])
    p01 = sum(1 for f in d["findings"] if f["priority"] in ("P0", "P1"))
    print(f"ok: verdict={d['verdict']} findings={n} (P0/P1={p01}) tier={d['rating']['overallTier']}")


if __name__ == "__main__":
    main()
