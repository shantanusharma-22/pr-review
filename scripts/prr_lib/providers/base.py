"""Provider interface. Every adapter returns the same normalized bundle."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from ..http import Client, HttpError
from ..urls import PRRef

JIRA_KEY_RE = re.compile(r"\b([A-Z][A-Z0-9]{1,9}-\d{1,7})\b")
MAX_LINKED_ISSUES = 5
MAX_ISSUE_BODY = 6000


class PreflightError(Exception):
    """Raised when the very first API call fails (auth, permission, wrong URL, network)."""

    def __init__(self, provider: str, status: int, detail: str):
        self.provider, self.status, self.detail = provider, status, detail
        super().__init__(f"{provider} preflight failed (HTTP {status}): {detail}")


class Provider:
    name = "base"
    supports_post = True
    suggestion_style = "plain"   # github | gitlab | plain

    def __init__(self, ref: PRRef, api_url: Optional[str] = None, transport=None):
        self.ref = ref
        self.api_url = api_url
        self.transport = transport
        self.http: Client = None  # set by subclasses

    # ---- required -------------------------------------------------------
    def fetch(self) -> dict:
        raise NotImplementedError

    def read_file(self, path: str, sha: str) -> Optional[str]:
        raise NotImplementedError

    # ---- optional -------------------------------------------------------
    def load_patch(self, bundle: dict, f: dict) -> Optional[str]:
        return f.get("patch")

    def checks(self, bundle: dict) -> List[dict]:
        return []

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        raise NotImplementedError(f"Posting is not supported for {self.name}")

    # ---- helpers --------------------------------------------------------
    def preflight(self, fn):
        try:
            return fn()
        except HttpError as e:
            raise PreflightError(self.name, e.status, e.body[:300] or str(e)) from e


def new_bundle(ref: PRRef, **kw) -> dict:
    b = {
        "schema": 1,
        "ref": ref.to_dict(),
        "provider": ref.provider,
        "url": ref.url,
        "title": "",
        "body": "",
        "author": "",
        "state": "",
        "draft": False,
        "base": {"ref": "", "sha": ""},
        "head": {"ref": "", "sha": ""},
        "merge_base": "",
        "files": [],
        "comments": [],
        "commits": [],
        "linked_issues": [],
        "external_refs": [],
        "provider_data": {},
        "notes": [],
    }
    b.update(kw)
    return b


def issue_numbers(texts: List[str], host: str, owner: str, repo: str, symbol: str = "#") -> List[int]:
    """Same-repo issue refs: '#12', 'fixes #12', or full issue URLs for this repo."""
    nums: List[int] = []
    sym = re.escape(symbol)
    url_rx = re.compile(rf"https?://{re.escape(host)}/{re.escape(owner)}/{re.escape(repo)}/(?:-/)?issues/(\d+)")
    for text in texts:
        if not text:
            continue
        for m in re.finditer(rf"(?:^|[\s(\[]){sym}(\d+)\b", text):
            nums.append(int(m.group(1)))
        for m in url_rx.finditer(text):
            nums.append(int(m.group(1)))
    seen, out = set(), []
    for n in nums:
        if n not in seen:
            seen.add(n)
            out.append(n)
    return out[:MAX_LINKED_ISSUES]


def external_refs(texts: List[str]) -> List[str]:
    seen, out = set(), []
    for t in texts:
        for m in JIRA_KEY_RE.finditer(t or ""):
            k = m.group(1)
            if k not in seen and not k.startswith(("CVE-", "UTF-", "ISO-", "RFC-", "SHA-")):
                seen.add(k)
                out.append(k)
    return out[:10]


def comment(author: str, body: str, path: Optional[str] = None, line: Optional[int] = None,
            created: str = "", resolved: Optional[bool] = None) -> Dict:
    return {"author": author or "", "body": body or "", "path": (path or "").lstrip("/") or None,
            "line": line, "created_at": created or "", "resolved": resolved}


def issue(id_: str, title: str, body: str, url: str = "") -> Dict:
    return {"id": str(id_), "title": title or "", "body": (body or "")[:MAX_ISSUE_BODY], "url": url or ""}
