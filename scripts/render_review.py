#!/usr/bin/env python3
"""
render_review.py - Turn a validated decision JSON into the files a human
approves before anything is posted.

Usage:
    python scripts/render_review.py <decision.json> [--out DIR]

Writes to DIR (default: alongside decision.json, in ./review/):
    REVIEW.internal.md   full detail incl. confidence scores, tiers, rationale (never posted)
    REVIEW.public.md     the review body that will be posted (marker-backed, no emojis, no scores)
    inline.json          the exact `comments[]` payload for the GitHub pending-review API
    PREVIEW.md           everything in one page: what will be posted, where, and the event type

The public body carries a hidden HTML marker so a re-review can find and
edit the previous comment in place instead of stacking new ones.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MARKER = "<!-- pr-review-agent item={num} head={sha} v=1 -->"
PRIORITY_LABEL = {"P0": "Blocker", "P1": "Blocker", "P2": "Important", "P3": "Minor"}
EVENT_SENTENCE = {
    "APPROVE": "Approving. The remaining notes are non-blocking.",
    "REQUEST_CHANGES": "Requesting changes. The blockers below need to be addressed before merge.",
    "COMMENT": "Leaving comments only; no verdict on merge readiness.",
}


def fence_suggestion(code: str) -> str:
    # Use 4 backticks if the suggestion itself contains triple backticks (markdown/docs PRs).
    fence = "````" if "```" in code else "```"
    return f"{fence}suggestion\n{code.rstrip()}\n{fence}"


def finding_inline_body(f: dict, public: bool = True) -> str:
    parts = [f"**{PRIORITY_LABEL[f['priority']]} ({f['priority']}, {f['category']}): {f['title']}**", "", f["body"].strip()]
    if f.get("suggestion"):
        parts += ["", fence_suggestion(f["suggestion"])]
    if not public:
        parts += ["", f"_confidence {f['confidenceScore']:.2f} - {f['file']}:{f['lineStart']}-{f['lineEnd']}_"]
    return "\n".join(parts)


def render_public(d: dict) -> str:
    pr, fs = d["pr"], d["findings"]
    blockers = [f for f in fs if f["priority"] in ("P0", "P1")]
    important = [f for f in fs if f["priority"] == "P2"]
    minor = [f for f in fs if f["priority"] == "P3"]
    sec, test, rat = d["securityReview"], d["testingReview"], d["rating"]

    out = [MARKER.format(num=pr["number"], sha=pr["headSha"][:12]), "", "## Review", "", d["summary"].strip(), "", EVENT_SENTENCE[d["verdict"]], ""]
    out += ["**What this PR does:** " + d["changeSummary"].strip(), ""]

    if d["productReview"]["worthIt"] != "yes":
        out += ["### Product direction", "", f"Worth merging: **{d['productReview']['worthIt'].replace('_', ' ')}**. {d['productReview']['rationale'].strip()}", ""]

    def section(title: str, items: list[dict]) -> None:
        if not items:
            return
        out.append(f"### {title}")
        out.append("")
        for f in items:
            out.append(f"- **{f['title']}** (`{f['file']}:{f['lineStart']}`) - {f['body'].strip().splitlines()[0]}")
        out.append("")

    section("Blockers", blockers)
    section("Important", important)
    section("Minor", minor)

    if sec["status"] == "needs_attention":
        out += ["### Security", "", sec["summary"].strip(), ""]
        for c in sec["concerns"]:
            loc = f" (`{c['file']}:{c['line']}`)" if c.get("file") else ""
            out.append(f"- {'**Blocking:** ' if c['blocking'] else ''}{c['kind'].replace('_', ' ')}{loc} - {c['detail']}")
        out.append("")

    if test["proofStatus"] in ("insufficient", "missing") or test["missingE2e"] or test["lowValueTests"]:
        out += ["### Testing and proof", ""]
        out.append(f"- Evidence that the changed behaviour runs: **{test['proofPath'].replace('_', ' ')}** ({test['proofStatus']}).")
        if test["missingE2e"]:
            out.append(f"- Not yet shown: {test['missingE2e'].strip()}")
        for t in test["lowValueTests"]:
            out.append(f"- Consider removing: {t}")
        out.append("")

    if d["risks"]:
        out += ["### Before merge", ""] + [f"- {r}" for r in d["risks"]] + [""]
    if d["questions"]:
        out += ["### Questions", ""] + [f"- {q}" for q in d["questions"]] + [""]
    if d["praise"]:
        out += ["### What works well", ""] + [f"- {p}" for p in d["praise"]] + [""]

    out += ["---", f"Rating: proof **{rat['proofTier']}** / patch **{rat['patchTier']}** / overall **{rat['overallTier']}**. {rat['rationale'].strip()}", "",
            f"_Reviewed head `{pr['headSha'][:12]}`. Inline comments are attached to the exact lines. "
            "If this review was produced with AI assistance, a human approved it before posting._"]
    return "\n".join(out).rstrip() + "\n"


def render_internal(d: dict) -> str:
    pr = d["pr"]
    out = [f"# INTERNAL review: {pr['owner']}/{pr['repo']}#{pr['number']} @ {pr['headSha'][:12]}", "",
           f"- Verdict: {d['verdict']}  Confidence: {d['confidence']}",
           f"- Author: {pr['author']} ({pr['authorAssociation']})  {pr['headRef']} -> {pr['baseRef']}",
           f"- Product: worthIt={d['productReview']['worthIt']}  problem: {d['productReview']['userProblem']}",
           f"- Rating: proof {d['rating']['proofTier']} / patch {d['rating']['patchTier']} / overall {d['rating']['overallTier']}",
           f"- Security: {d['securityReview']['status']}  Proof: {d['testingReview']['proofPath']} / {d['testingReview']['proofStatus']}",
           "", "## Summary", "", d["summary"], "", "## Findings", ""]
    for f in d["findings"]:
        out += [f"### {f['id']} [{f['priority']}] {f['title']}", "", finding_inline_body(f, public=False), ""]
    if d["securityReview"]["concerns"]:
        out += ["## Security concerns", ""] + [json.dumps(c) for c in d["securityReview"]["concerns"]] + [""]
    if d["risks"]:
        out += ["## Risks", ""] + [f"- {r}" for r in d["risks"]] + [""]
    if d["inlineComments"]:
        out += ["## Extra inline comments", ""] + [f"- {c['file']}:{c['line']} - {c['body']}" for c in d["inlineComments"]] + [""]
    return "\n".join(out)


def render_inline_payload(d: dict) -> list[dict]:
    payload = []
    for f in d["findings"]:
        c = {"path": f["file"], "line": f["lineEnd"], "side": "RIGHT", "body": finding_inline_body(f)}
        if f["lineEnd"] > f["lineStart"]:
            c["start_line"], c["start_side"] = f["lineStart"], "RIGHT"
        payload.append(c)
    for ic in d["inlineComments"]:
        c = {"path": ic["file"], "line": ic["line"], "side": ic.get("side", "RIGHT"), "body": ic["body"]}
        if ic.get("startLine"):
            c["start_line"], c["start_side"] = ic["startLine"], ic.get("side", "RIGHT")
        payload.append(c)
    return payload


def render_preview(d: dict, public: str, inline: list[dict]) -> str:
    pr = d["pr"]
    out = [f"# PREVIEW - nothing has been posted", "",
           f"Target: https://github.com/{pr['owner']}/{pr['repo']}/pull/{pr['number']}  (head `{pr['headSha'][:12]}`)",
           f"Event type: **{d['verdict']}**", f"Inline comments: **{len(inline)}**", "",
           "Approve by running:  `python scripts/post_review.py <decision.json>`", "",
           "---", "## Review body (will be posted as the review summary)", "", public, "",
           "---", f"## Inline comments ({len(inline)})", ""]
    for i, c in enumerate(inline, 1):
        rng = f"{c['start_line']}-{c['line']}" if "start_line" in c else str(c["line"])
        out += [f"### {i}. `{c['path']}` line {rng} ({c['side']})", "", c["body"], ""]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decision")
    ap.add_argument("--out")
    a = ap.parse_args()

    d = json.loads(Path(a.decision).read_text())
    out = Path(a.out) if a.out else Path(a.decision).resolve().parent / "review"
    out.mkdir(parents=True, exist_ok=True)

    public = render_public(d)
    inline = render_inline_payload(d)
    (out / "REVIEW.public.md").write_text(public)
    (out / "REVIEW.internal.md").write_text(render_internal(d))
    (out / "inline.json").write_text(json.dumps(inline, indent=2))
    (out / "PREVIEW.md").write_text(render_preview(d, public, inline))
    print(f"ok: wrote {out}/PREVIEW.md  (verdict={d['verdict']}, inline={len(inline)})")


if __name__ == "__main__":
    main()
