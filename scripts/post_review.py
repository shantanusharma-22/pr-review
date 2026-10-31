#!/usr/bin/env python3
"""
post_review.py - Post an approved review to GitHub. The ONLY script that writes.

Usage:
    python scripts/post_review.py <decision.json> [--review-dir DIR] [--yes] [--dry-run]
                                                   [--event APPROVE|REQUEST_CHANGES|COMMENT]

Safety gates (all deterministic, all before any write):
  1. Re-validates decision.json (schema + policy). Invalid -> abort.
  2. Re-fetches the live PR. If head SHA != decision.pr.headSha -> abort (drift).
     Inline line numbers are only valid for the head that was reviewed.
  3. If the PR is closed/merged -> abort.
  4. Looks for a previous review from this agent (hidden marker) on the SAME head.
     If found -> abort as already-posted (idempotent) unless --force.
  5. Prints the exact payload and asks for a typed "yes" unless --yes.
  6. Creates a PENDING review with all inline comments in one call, then submits
     it with the event type. Two calls, one notification for the author.

--event lets the approving human override the verdict at post time (e.g. soften
REQUEST_CHANGES to COMMENT). The override is recorded in posted.json.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
MARKER_PREFIX = "<!-- pr-review-agent item="


def gh_json(args: list[str], stdin: str | None = None):
    r = subprocess.run(["gh", *args], input=stdin, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"error: gh {' '.join(args[:4])} failed:\n{r.stderr.strip()}")
    return json.loads(r.stdout or "null")


def validate(decision_path: Path) -> None:
    r = subprocess.run([sys.executable, str(HERE / "validate_findings.py"), str(decision_path)], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("error: decision failed validation; refusing to post.\n" + r.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("decision")
    ap.add_argument("--review-dir", help="dir containing REVIEW.public.md and inline.json (default: <decision dir>/review)")
    ap.add_argument("--event", choices=["APPROVE", "REQUEST_CHANGES", "COMMENT"], help="override verdict at post time")
    ap.add_argument("--yes", action="store_true", help="skip interactive confirmation (CI use only, after a human approved the preview)")
    ap.add_argument("--dry-run", action="store_true", help="run every gate, print payload, write nothing")
    ap.add_argument("--force", action="store_true", help="post even if this head was already reviewed by the agent")
    a = ap.parse_args()

    dpath = Path(a.decision).resolve()
    rdir = Path(a.review_dir) if a.review_dir else dpath.parent / "review"
    body_path, inline_path = rdir / "REVIEW.public.md", rdir / "inline.json"
    for p in (body_path, inline_path):
        if not p.exists():
            sys.exit(f"error: {p} missing. Run render_review.py first.")

    validate(dpath)
    d = json.loads(dpath.read_text())
    pr = d["pr"]
    owner, repo, num = pr["owner"], pr["repo"], pr["number"]
    event = a.event or d["verdict"]
    body = body_path.read_text()
    inline = json.loads(inline_path.read_text())

    # Gate 2/3: live state
    live = gh_json(["api", f"repos/{owner}/{repo}/pulls/{num}", "-X", "GET"])
    if live["state"] != "open":
        sys.exit(f"error: PR is {live['state']}; refusing to post.")
    if live["head"]["sha"] != pr["headSha"]:
        sys.exit(f"error: head drift. Reviewed {pr['headSha'][:12]} but PR is now at {live['head']['sha'][:12]}. "
                 "Re-run fetch_pr.py and re-review; inline line numbers may be stale.")

    # Gate 4: idempotency via marker
    prev = gh_json(["api", f"repos/{owner}/{repo}/pulls/{num}/reviews", "-X", "GET", "--paginate", "--slurp"])
    prev = [x for page in prev for x in page] if prev and isinstance(prev[0], list) else prev
    marker_head = f"{MARKER_PREFIX}{num} head={pr['headSha'][:12]}"
    dup = [r for r in prev if (r.get("body") or "").startswith(marker_head)]
    if dup and not a.force:
        sys.exit(f"error: this head was already reviewed by pr-review-agent (review id {dup[0]['id']}). Use --force to post anyway.")

    # Gate 5: show and confirm
    print("=" * 72)
    print(f"POST REVIEW -> https://github.com/{owner}/{repo}/pull/{num}  head {pr['headSha'][:12]}")
    print(f"event: {event}{'  (overrides verdict ' + d['verdict'] + ')' if event != d['verdict'] else ''}")
    print(f"inline comments: {len(inline)}")
    print("-" * 72)
    print(body)
    print("-" * 72)
    for c in inline:
        rng = f"{c['start_line']}-{c['line']}" if "start_line" in c else str(c["line"])
        print(f"[{c['path']}:{rng}] {c['body'].splitlines()[0]}")
    print("=" * 72)

    if a.dry_run:
        print("dry-run: all gates passed, nothing posted.")
        return
    if not a.yes:
        ans = input("Type 'yes' to post this review publicly: ").strip().lower()
        if ans != "yes":
            sys.exit("aborted: nothing posted.")

    # Gate 6: pending review -> submit
    payload = {"commit_id": pr["headSha"], "comments": inline}
    created = gh_json(["api", f"repos/{owner}/{repo}/pulls/{num}/reviews", "-X", "POST", "--input", "-"], stdin=json.dumps(payload))
    review_id = created["id"]
    if created.get("state") != "PENDING":
        print(f"warning: expected PENDING review, got {created.get('state')}", file=sys.stderr)

    submitted = gh_json(["api", f"repos/{owner}/{repo}/pulls/{num}/reviews/{review_id}/events", "-X", "POST", "--input", "-"],
                        stdin=json.dumps({"event": event, "body": body}))

    receipt = {
        "postedAt": datetime.now(timezone.utc).isoformat(),
        "reviewId": review_id, "url": submitted.get("html_url"),
        "event": event, "verdictInDecision": d["verdict"], "headSha": pr["headSha"],
        "inlineCount": len(inline),
    }
    (rdir / "posted.json").write_text(json.dumps(receipt, indent=2))
    print(f"ok: posted review {review_id} ({event}) -> {submitted.get('html_url')}")


if __name__ == "__main__":
    main()
