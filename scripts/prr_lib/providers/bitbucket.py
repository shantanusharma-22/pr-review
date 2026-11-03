"""Bitbucket Cloud (API 2.0). Bitbucket Data Center: use local mode (see references/providers.md)."""
from __future__ import annotations

import urllib.parse
from typing import List, Optional

from .. import auth
from ..diff import split_unified_diff
from ..http import Client
from .base import Provider, comment, external_refs, new_bundle


class Bitbucket(Provider):
    name = "bitbucket"
    suggestion_style = "plain"

    def __init__(self, ref, api_url=None, transport=None):
        super().__init__(ref, api_url, transport)
        self.http = Client(api_url or "https://api.bitbucket.org/2.0", auth.bitbucket(), transport=transport)
        self.repo = f"/repositories/{ref.owner}/{ref.repo}"
        self.pr = f"{self.repo}/pullrequests/{ref.number}"

    def _pages(self, path: str, limit: int = 2000) -> list:
        out, url, params = [], path, {"pagelen": 50}
        while url and len(out) < limit:
            j = self.http.get(url, params=params).json() or {}
            out.extend(j.get("values", []))
            url, params = j.get("next"), None
        return out[:limit]

    def fetch(self) -> dict:
        pr = self.preflight(lambda: self.http.get(self.pr).json())
        diff_text = self.http.get(f"{self.pr}/diff", headers={"Accept": "text/plain"}).text()
        files = split_unified_diff(diff_text)
        comments = []
        for c in self._pages(f"{self.pr}/comments", 1000):
            if c.get("deleted"):
                continue
            inline = c.get("inline") or {}
            comments.append(comment((c.get("user") or {}).get("display_name"), (c.get("content") or {}).get("raw"),
                                    inline.get("path"), inline.get("to"), c.get("created_on"),
                                    bool(c.get("resolution"))))
        commits = [{"sha": c.get("hash"), "message": c.get("message", "")}
                   for c in self._pages(f"{self.pr}/commits", 250)]
        texts = [pr.get("title", ""), pr.get("description") or ""] + [c["message"] for c in commits]
        src, dst = pr.get("source") or {}, pr.get("destination") or {}
        return new_bundle(
            self.ref, url=((pr.get("links") or {}).get("html") or {}).get("href", self.ref.url),
            title=pr.get("title", ""), body=pr.get("description") or "",
            author=(pr.get("author") or {}).get("display_name", ""), state=pr.get("state", ""),
            draft=bool(pr.get("draft")),
            base={"ref": (dst.get("branch") or {}).get("name", ""), "sha": (dst.get("commit") or {}).get("hash", "")},
            head={"ref": (src.get("branch") or {}).get("name", ""), "sha": (src.get("commit") or {}).get("hash", "")},
            merge_base=(dst.get("commit") or {}).get("hash", ""),
            files=files, comments=comments, commits=commits, external_refs=external_refs(texts),
        )

    def read_file(self, path: str, sha: str) -> Optional[str]:
        r = self.http.try_get(f"{self.repo}/src/{sha}/{urllib.parse.quote(path)}")
        return r.text() if r else None

    def checks(self, bundle: dict) -> List[dict]:
        sha = bundle["head"]["sha"]
        return [{"name": s.get("name") or s.get("key"), "state": s.get("state"), "url": s.get("url")}
                for s in self._pages(f"{self.repo}/commit/{sha}/statuses", 100)]

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        for c in plan["inline"]:
            self.http.post(f"{self.pr}/comments", {"content": {"raw": c["body"]},
                                                   "inline": {"path": c["path"], "to": c["line"]}})
        r = self.http.post(f"{self.pr}/comments", {"content": {"raw": plan["body"]}})
        if plan["event"] == "approve":
            self.http.post(f"{self.pr}/approve")
        elif plan["event"] == "request_changes":
            self.http.post(f"{self.pr}/request-changes")
        return [(((r.json() or {}).get("links") or {}).get("html") or {}).get("href", bundle.get("url", ""))]
