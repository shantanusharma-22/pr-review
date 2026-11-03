"""findings.json -> validated review plan -> provider post / markdown."""
from __future__ import annotations

import json
from typing import Dict, List, Tuple

from .bundle import MARKER
from .diff import new_side_lines

AXES = ("correctness", "standards", "spec")
SEVERITIES = ("blocker", "major", "minor", "nit", "question")
DECISIONS = ("approve", "comment", "request_changes")
EVIDENCE = ("patch", "snippet", "inferred")
SEV_RANK = {s: i for i, s in enumerate(SEVERITIES)}
MAX_NITS = 5


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(review: dict, bundle: dict) -> Tuple[List[str], List[str]]:
    """Return (errors, warnings). Errors block posting."""
    errors: List[str] = []
    warns: List[str] = []
    if review.get("decision") not in DECISIONS:
        errors.append(f"decision must be one of {DECISIONS}")
    if not (review.get("summary") or "").strip():
        errors.append("summary is required")
    findings = review.get("findings") or []
    if not isinstance(findings, list):
        return errors + ["findings must be a list"], warns
    paths = {f["path"] for f in bundle["files"]} | {f.get("old_path") for f in bundle["files"] if f.get("old_path")}
    for i, f in enumerate(findings):
        tag = f"findings[{i}] '{(f.get('title') or '')[:40]}'"
        if f.get("axis") not in AXES:
            errors.append(f"{tag}: axis must be one of {AXES}")
        if f.get("severity") not in SEVERITIES:
            errors.append(f"{tag}: severity must be one of {SEVERITIES}")
        if not (f.get("title") or "").strip():
            errors.append(f"{tag}: title is required")
        if f.get("evidence", "patch") not in EVIDENCE:
            errors.append(f"{tag}: evidence must be one of {EVIDENCE}")
        if f.get("path") and f["path"] not in paths:
            warns.append(f"{tag}: path not in this PR's diff; it will go in the summary, not inline")
        if f.get("severity") == "blocker" and f.get("evidence") == "inferred":
            warns.append(f"{tag}: blocker based only on inference — confirm with a snippet or downgrade")
        if f.get("axis") == "standards" and f.get("severity") in ("blocker", "major") and not f.get("rule"):
            warns.append(f"{tag}: hard standards finding without a cited rule (file + rule); "
                         "smell-baseline findings should be minor/nit")
    sev = [f.get("severity") for f in findings]
    if review.get("decision") == "approve" and "blocker" in sev:
        errors.append("cannot approve with open blocker findings")
    if review.get("decision") == "approve" and "major" in sev:
        warns.append("approving with major findings — make sure that is intended")
    if review.get("decision") == "request_changes" and not ({"blocker", "major"} & set(sev)):
        warns.append("request_changes without a blocker/major finding — prefer 'comment'")
    if sev.count("nit") > MAX_NITS:
        warns.append(f"{sev.count('nit')} nits; keep at most {MAX_NITS} (drop the least useful)")
    return errors, warns


def _suggestion(style: str, text: str, span: int) -> str:
    text = text.rstrip("\n")
    if style == "github":
        return f"```suggestion\n{text}\n```"
    if style == "gitlab":
        return f"```suggestion:-{max(0, span)}+0\n{text}\n```"
    return f"Suggested change:\n```\n{text}\n```"


def _dup(f: dict, comments: List[dict]) -> bool:
    title = (f.get("title") or "").lower()[:40]
    for c in comments:
        if c.get("path") == f.get("path") and c.get("line") and f.get("line") \
                and abs(int(c["line"]) - int(f["line"])) <= 2 and title and title in (c.get("body") or "").lower():
            return True
    return False


def plan(review: dict, bundle: dict, style: str, allow_approve: bool = True) -> Dict:
    """Split findings into anchored inline comments and summary-only items; build the review body."""
    by_path = {f["path"]: f for f in bundle["files"]}
    inline, summary_only, dropped = [], [], []
    findings = sorted(review.get("findings") or [], key=lambda f: (SEV_RANK.get(f.get("severity"), 9),
                                                                   AXES.index(f["axis"]) if f.get("axis") in AXES else 9))
    for f in findings:
        if _dup(f, bundle.get("comments", [])):
            dropped.append(f)
            continue
        fe = by_path.get(f.get("path") or "")
        lines = new_side_lines(fe.get("patch")) if fe else {}
        line = f.get("line")
        start = f.get("start_line")
        anchored = bool(fe and isinstance(line, int) and line in lines)
        if anchored and start and not (isinstance(start, int) and start <= line
                                       and all(n in lines for n in range(start, line + 1))):
            start = None
        if not anchored:
            summary_only.append(f)
            continue
        body = f"**[{f['severity']} · {f['axis']}]** {f['title']}"
        if f.get("body"):
            body += f"\n\n{f['body']}"
        if f.get("rule"):
            body += f"\n\n_Rule: {f['rule']}_"
        if f.get("suggestion") is not None:
            body += "\n\n" + _suggestion(style, f["suggestion"], (line - start) if start else 0)
        inline.append({"path": f["path"], "line": line, "start_line": start, "old_line": lines.get(line),
                       "old_path": fe.get("old_path"), "body": body, "finding": f})
    event = review.get("decision", "comment")
    notes = []
    if event == "approve" and not allow_approve:
        event = "comment"
        notes.append("approval disabled (--no-approve); posting as comment")
    body = render_body(review, bundle, inline, summary_only)
    return {"event": event, "body": body, "inline": inline, "summary_only": summary_only,
            "dropped_duplicates": dropped, "notes": notes}


def _item(f: dict, inline: bool) -> str:
    loc = f" `{f['path']}{':' + str(f['line']) if f.get('line') else ''}`" if f.get("path") else ""
    text = f"- **[{f['severity']}]**{loc} {f['title']}"
    if inline:
        return text + " _(inline)_"
    if f.get("body"):
        text += f" — {f['body']}"
    if f.get("rule"):
        text += f" _(rule: {f['rule']})_"
    return text


def render_body(review: dict, bundle: dict, inline: List[dict], summary_only: List[dict]) -> str:
    label = {"approve": "Approve", "comment": "Comment", "request_changes": "Request changes"}
    out = ["## Review summary", "", review.get("summary", "").strip(), "",
           f"**Decision:** {label.get(review.get('decision'), 'Comment')}"
           + (f" — {review['decision_reason']}" if review.get("decision_reason") else "")]
    if review.get("discrepancies"):
        out += ["", "### PR description vs. code"] + [f"- {d}" for d in review["discrepancies"]]
    inline_ids = {id(c["finding"]) for c in inline}
    allf = [c["finding"] for c in inline] + summary_only
    for axis, title in (("correctness", "Correctness & risk"), ("standards", "Standards"), ("spec", "Spec")):
        items = sorted([f for f in allf if f.get("axis") == axis], key=lambda f: SEV_RANK.get(f["severity"], 9))
        if axis == "spec" and review.get("spec_status") == "no_spec":
            out += ["", f"### {title}", "- Skipped: no spec or linked issue was available."]
            continue
        if items:
            out += ["", f"### {title}"] + [_item(f, id(f) in inline_ids) for f in items]
    for key, title in (("tests", "Tests & docs"), ("risk", "Risk & scope")):
        if (review.get(key) or "").strip():
            out += ["", f"### {title}", review[key].strip()]
    if review.get("unverified"):
        out += ["", "### Not verified"] + [f"- {u}" for u in review["unverified"]]
    out += ["", f"{MARKER} head={bundle['head']['sha'][:12]} -->"]
    return "\n".join(out).strip() + "\n"


def describe(p: dict) -> str:
    lines = [f"event: {p['event']}", f"inline comments: {len(p['inline'])}",
             f"summary-only findings: {len(p['summary_only'])}"]
    if p["dropped_duplicates"]:
        lines.append(f"skipped as already raised by others: {len(p['dropped_duplicates'])}")
    lines += [f"note: {n}" for n in p["notes"]]
    for c in p["inline"]:
        rng = f"{c['start_line']}-{c['line']}" if c.get("start_line") else str(c["line"])
        lines.append(f"  inline {c['path']}:{rng} [{c['finding']['severity']}] {c['finding']['title']}")
    for f in p["summary_only"]:
        where = f" ({f['path']}:{f.get('line')})" if f.get("path") else ""
        lines.append(f"  summary [{f['severity']}] {f['title']}{where}")
    return "\n".join(lines)
