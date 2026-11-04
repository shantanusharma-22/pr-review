#!/usr/bin/env python3
"""pr-review CLI — provider-neutral data collection and posting for the pr-review skill.

  prr.py collect <PR URL | owner/repo#N | N> [--provider P] [--api-url URL]
  prr.py collect --local [--base REF] [--head REF|WORKTREE] [--fetch-ref REF]
  prr.py patch    -w WS PATH [PATH ...]
  prr.py snippet  -w WS PATH[:START-END] [...] [--at head|base]
  prr.py checks   -w WS
  prr.py validate -w WS FINDINGS.json
  prr.py render   -w WS FINDINGS.json
  prr.py post     -w WS FINDINGS.json [--confirm] [--no-approve]

Exit codes: 0 ok · 2 usage · 3 preflight/auth/network · 4 findings invalid.
Python 3.9+ standard library only. Tokens come from env vars (see references/providers.md).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prr_lib import VERSION, auth, bundle as bmod, findings as fmod  # noqa: E402
from prr_lib.diff import annotate_patch, count_changes, risk_score  # noqa: E402
from prr_lib.http import HttpError  # noqa: E402
from prr_lib.providers import PreflightError, get_provider  # noqa: E402
from prr_lib.urls import PRRef, parse_target  # noqa: E402

MAX_PRINT_LINES = 1500


def _error_block(provider: str, cmd: str, detail: str) -> None:
    sys.stderr.write(
        "### Error\n\n"
        f"Cannot review: the {provider} preflight failed.\n\n"
        f"- Failing step: `{cmd}`\n- Error: {detail}\n"
        f"- Required action: {auth.HINTS.get(provider, 'check the URL, network access and credentials.')}"
        f"{auth.TRUST_HINT if provider in ('github', 'gitlab', 'gitea') else ''}\n")


def _provider_from_bundle(b: dict, args=None):
    ref = PRRef.from_dict(b["ref"])
    kw = {"cwd": b.get("provider_data", {}).get("cwd")} if ref.provider == "local" else {}
    return get_provider(ref, api_url=b.get("api_url"), **kw)


def cmd_collect(a) -> int:
    if a.local:
        ref = PRRef("local", repo=os.path.basename(os.getcwd()), number=0)
        prov = get_provider(ref, base=a.base, head=a.head or "HEAD", fetch_ref=a.fetch_ref)
    else:
        if not a.target:
            print("collect needs a PR/MR URL, owner/repo#N, a number, or --local", file=sys.stderr)
            return 2
        ref = parse_target(a.target, a.provider, a.host)
        prov = get_provider(ref, api_url=a.api_url)
    try:
        b = prov.fetch()
    except PreflightError as e:
        detail = e.detail if e.provider == "local" or not e.status else f"HTTP {e.status}: {e.detail}"
        _error_block(e.provider, "collect", detail)
        return 3
    except HttpError as e:
        _error_block(ref.provider, "collect", str(e)[:300])
        return 3
    b["api_url"] = a.api_url
    if ref.provider == "local":
        b["provider_data"]["cwd"] = os.getcwd()
    if a.spec:
        for i, path in enumerate(a.spec):
            with open(path, encoding="utf-8") as fh:
                b["linked_issues"].insert(i, {"id": f"spec{i + 1}", "title": os.path.basename(path),
                                              "body": fh.read()[:20000], "url": path})
    if not a.no_standards:
        bmod.discover_standards(prov, b)
    ws = bmod.workspace_for(ref.slug or "local", a.workspace)
    bmod.save(ws, b)
    digest = bmod.render_digest(b, ws, a.max_files, a.max_lines)
    with open(os.path.join(ws, "digest.md"), "w", encoding="utf-8") as fh:
        fh.write(digest)
    print(digest)
    return 0


def _ensure_patch(prov, b: dict, f: dict) -> None:
    if f.get("patch_deferred"):
        f["patch"] = prov.load_patch(b, f)
        f["patch_deferred"] = False
        f["additions"], f["deletions"] = count_changes(f["patch"])
        f["risk"], f["risk_reasons"] = risk_score(f)


def cmd_patch(a) -> int:
    b = bmod.load(a.workspace)
    by = {f["path"]: f for f in b["files"]}
    prov = None
    printed = 0
    for p in a.paths:
        f = by.get(p)
        if not f:
            print(f"## {p}\n  [not in this diff]")
            continue
        if f.get("patch_deferred"):
            prov = prov or _provider_from_bundle(b)
            _ensure_patch(prov, b, f)
        text = annotate_patch(f.get("patch"))
        n = text.count("\n") + 1
        if printed + n > MAX_PRINT_LINES:
            print(f"## {p}\n  [skipped: output budget of {MAX_PRINT_LINES} lines reached; request fewer files]")
            continue
        printed += n
        print(f"## {p}  ({f['status']}, +{f['additions']}/-{f['deletions']})\n{text}\n")
    if prov:
        bmod.save(a.workspace, b)
    return 0


def cmd_snippet(a) -> int:
    b = bmod.load(a.workspace)
    prov = _provider_from_bundle(b)
    if a.at == "base":
        sha = b.get("merge_base") or b["base"]["sha"]
    else:
        sha = "WORKTREE" if b.get("provider_data", {}).get("worktree") else b["head"]["sha"]
    cache = os.path.join(a.workspace, "files")
    os.makedirs(cache, exist_ok=True)
    for spec in a.specs:
        m = re.fullmatch(r"(.+?)(?::(\d+)-(\d+))?", spec)
        path, lo, hi = m.group(1), m.group(2), m.group(3)
        # Key by commit so a re-review of a newer head never reads stale content; the worktree changes
        # under us, so it is never cached.
        cpath = os.path.join(cache, f"{a.at}-{sha[:12]}__" + re.sub(r"[^A-Za-z0-9._-]+", "__", path))
        use_cache = sha != "WORKTREE"
        if use_cache and os.path.exists(cpath):
            with open(cpath, encoding="utf-8") as fh:
                text = fh.read()
        else:
            try:
                text = prov.read_file(path, sha)
            except HttpError as e:
                _error_block(b["provider"], f"snippet {spec}", str(e)[:300])
                return 3
            if text is None:
                print(f"## {path}\n  [not found at {a.at} {sha[:12]}]")
                continue
            if use_cache:
                with open(cpath, "w", encoding="utf-8") as fh:
                    fh.write(text)
        lines = text.splitlines()
        start = max(1, int(lo)) if lo else 1
        end = min(len(lines), int(hi)) if hi else min(len(lines), 300)
        print(f"## {path}:{start}-{end} (of {len(lines)}) @ {a.at}")
        for i in range(start, end + 1):
            print(f"{i:>6}  {lines[i - 1]}")
        if not hi and len(lines) > 300:
            print("  [truncated at 300 lines; request a range]")
    return 0


def cmd_checks(a) -> int:
    b = bmod.load(a.workspace)
    prov = _provider_from_bundle(b)
    try:
        rows = prov.checks(b)
    except HttpError as e:
        print(f"checks unavailable: {str(e)[:200]}")
        return 0
    if not rows:
        print("no CI checks reported")
    for r in rows:
        print(f"- {r.get('state')}: {r.get('name')} {r.get('url') or ''}".rstrip())
    return 0


def _prepare(a):
    b = bmod.load(a.workspace)
    review = fmod.load(a.findings)
    errors, warns = fmod.validate(review, b)
    return b, review, errors, warns


def _report(errors, warns) -> None:
    for e in errors:
        print(f"ERROR: {e}")
    for w in warns:
        print(f"warning: {w}")


def cmd_validate(a) -> int:
    b, review, errors, warns = _prepare(a)
    _report(errors, warns)
    if errors:
        return 4
    prov = _provider_from_bundle(b)
    _load_needed_patches(prov, b, review)
    print(fmod.describe(fmod.plan(review, b, prov.suggestion_style)))
    return 0


def _load_needed_patches(prov, b, review) -> None:
    by = {f["path"]: f for f in b["files"]}
    for f in review.get("findings") or []:
        fe = by.get(f.get("path") or "")
        if fe and fe.get("patch_deferred"):
            _ensure_patch(prov, b, fe)


def cmd_render(a) -> int:
    b, review, errors, warns = _prepare(a)
    _report(errors, warns)
    if errors:
        return 4
    prov = _provider_from_bundle(b)
    _load_needed_patches(prov, b, review)
    p = fmod.plan(review, b, "plain")
    body = p["body"]
    if p["inline"]:
        body += "\n### Inline comments\n" + "\n".join(
            f"\n**{c['path']}:{c['line']}**\n\n{c['body']}" for c in p["inline"])
    out = os.path.join(a.workspace, "review.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(body)
    print(body)
    print(f"\n[saved to {out}]")
    return 0


def cmd_post(a) -> int:
    b, review, errors, warns = _prepare(a)
    _report(errors, warns)
    if errors:
        return 4
    prov = _provider_from_bundle(b)
    if not prov.supports_post:
        print(f"Posting is not supported for {b['provider']}; use `render` and paste the result.")
        return 2
    _load_needed_patches(prov, b, review)
    allow = not (a.no_approve or os.environ.get("PR_REVIEW_NO_APPROVE") == "1")
    p = fmod.plan(review, b, prov.suggestion_style, allow_approve=allow)
    print(fmod.describe(p))
    with open(os.path.join(a.workspace, "post-preview.md"), "w", encoding="utf-8") as fh:
        fh.write(p["body"])
    if not a.confirm:
        print("\nDRY RUN — nothing was posted. Show this plan to the user; rerun with --confirm only after "
              "they explicitly approve.")
        return 0
    try:
        urls = prov.post_review(b, p)
    except HttpError as e:
        _error_block(b["provider"], "post", str(e)[:400])
        return 3
    print("POSTED: " + ", ".join(u for u in urls if u))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="prr.py", description=__doc__.split("\n")[0])
    ap.add_argument("--version", action="version", version=f"pr-review {VERSION}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("collect", help="fetch PR data into a workspace and print the digest")
    c.add_argument("target", nargs="?")
    c.add_argument("--provider", choices=["github", "gitlab", "bitbucket", "azure", "gitea"])
    c.add_argument("--host", help="host for owner/repo#N short form (e.g. GitHub Enterprise)")
    c.add_argument("--api-url", help="override API base URL (self-hosted, proxies)")
    c.add_argument("--local", action="store_true", help="review local git refs instead of a hosted PR")
    c.add_argument("--base", help="local: base ref (default: origin/HEAD, main, master)")
    c.add_argument("--head", help="local: head ref (default HEAD; WORKTREE = include uncommitted changes)")
    c.add_argument("--fetch-ref", help="local: fetch this ref first, e.g. refs/pull/123/head")
    c.add_argument("--spec", action="append", help="path to a spec/issue file (repeatable)")
    c.add_argument("-w", "--workspace")
    c.add_argument("--max-files", type=int, default=int(os.environ.get("PR_REVIEW_MAX_FILES", 25)))
    c.add_argument("--max-lines", type=int, default=int(os.environ.get("PR_REVIEW_MAX_LINES", 1000)))
    c.add_argument("--no-standards", action="store_true")
    c.set_defaults(fn=cmd_collect)

    for name, fn, hlp in (("patch", cmd_patch, "print annotated patches for paths"),
                          ("snippet", cmd_snippet, "print file lines at head or base"),
                          ("checks", cmd_checks, "list CI status for the head commit")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("-w", "--workspace", required=True)
        if name == "patch":
            s.add_argument("paths", nargs="+")
        if name == "snippet":
            s.add_argument("specs", nargs="+")
            s.add_argument("--at", choices=["head", "base"], default="head")
        s.set_defaults(fn=fn)

    for name, fn, hlp in (("validate", cmd_validate, "check findings.json and preview anchoring"),
                          ("render", cmd_render, "render the review as markdown (no network)"),
                          ("post", cmd_post, "post the review (dry run unless --confirm)")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("-w", "--workspace", required=True)
        s.add_argument("findings")
        if name == "post":
            s.add_argument("--confirm", action="store_true", help="actually post (after explicit user approval)")
            s.add_argument("--no-approve", action="store_true", help="never approve; downgrade to comment")
        s.set_defaults(fn=fn)

    a = ap.parse_args(argv)
    try:
        return a.fn(a)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
