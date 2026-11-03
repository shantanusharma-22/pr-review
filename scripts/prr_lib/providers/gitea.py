"""Gitea, Forgejo and Codeberg (API v1)."""
from __future__ import annotations

import urllib.parse
from typing import List, Optional

from .. import auth
from ..diff import split_unified_diff
from ..http import Client
from .base import Provider, comment, external_refs, issue, issue_numbers, new_bundle

EVENTS = {"approve": "APPROVED", "comment": "COMMENT", "request_changes": "REQUEST_CHANGES"}


class Gitea(Provider):
    name = "gitea"
    suggestion_style = "plain"

    def __init__(self, ref, api_url=None, transport=None):
        super().__init__(ref, api_url, transport)
        self.http = Client(api_url or f"{ref.scheme}://{ref.host}/api/v1",
                           auth.gitea(ref.host), transport=transport)
        self.repo = f"/repos/{ref.owner}/{ref.repo}"
        self.pr = f"{self.repo}/pulls/{ref.number}"

    def _pages(self, path: str, limit: int = 1000) -> list:
        out, page = [], 1
        while len(out) < limit:
            data = self.http.get(path, params={"page": page, "limit": 50}).json() or []
            out.extend(data)
            if len(data) < 50:
                break
            page += 1
        return out[:limit]

    def fetch(self) -> dict:
        pr = self.preflight(lambda: self.http.get(self.pr).json())
        files = split_unified_diff(self.http.get(f"{self.pr}.diff", headers={"Accept": "text/plain"}).text())
        comments = [comment((c.get("user") or {}).get("login"), c.get("body"), created=c.get("created_at"))
                    for c in self._pages(f"{self.repo}/issues/{self.ref.number}/comments", 300)]
        for rv in self._pages(f"{self.pr}/reviews", 50):
            if rv.get("body"):
                comments.append(comment((rv.get("user") or {}).get("login"), rv["body"],
                                        created=rv.get("submitted_at")))
            if rv.get("comments_count"):
                for c in self.http.get(f"{self.pr}/reviews/{rv['id']}/comments").json() or []:
                    comments.append(comment((c.get("user") or {}).get("login"), c.get("body"), c.get("path"),
                                            c.get("position") or c.get("original_position"), c.get("created_at"),
                                            bool(c.get("resolver"))))
        commits = [{"sha": c.get("sha"), "message": (c.get("commit") or {}).get("message", "")}
                   for c in self._pages(f"{self.pr}/commits", 250)]
        texts = [pr.get("title", ""), pr.get("body") or ""] + [c["message"] for c in commits]
        linked = []
        for num in issue_numbers(texts, self.ref.host, self.ref.owner, self.ref.repo):
            if num == self.ref.number:
                continue
            r = self.http.try_get(f"{self.repo}/issues/{num}")
            if r and not (r.json() or {}).get("pull_request"):
                j = r.json()
                linked.append(issue(num, j.get("title"), j.get("body"), j.get("html_url")))
        base, head = pr.get("base") or {}, pr.get("head") or {}
        return new_bundle(
            self.ref, url=pr.get("html_url", self.ref.url), title=pr.get("title", ""), body=pr.get("body") or "",
            author=(pr.get("user") or {}).get("login", ""), state=pr.get("state", ""),
            draft=bool(pr.get("draft")) or pr.get("title", "").upper().startswith(("WIP", "[WIP]", "DRAFT")),
            base={"ref": base.get("ref", ""), "sha": base.get("sha", "")},
            head={"ref": head.get("ref", ""), "sha": head.get("sha", "")},
            merge_base=pr.get("merge_base") or base.get("sha", ""), files=files, comments=comments,
            commits=commits, linked_issues=linked, external_refs=external_refs(texts),
        )

    def read_file(self, path: str, sha: str) -> Optional[str]:
        r = self.http.try_get(f"{self.repo}/raw/{urllib.parse.quote(path)}", params={"ref": sha})
        return r.text() if r else None

    def checks(self, bundle: dict) -> List[dict]:
        r = self.http.try_get(f"{self.repo}/commits/{bundle['head']['sha']}/status")
        return [{"name": s.get("context"), "state": s.get("status"), "url": s.get("target_url")}
                for s in ((r.json() or {}).get("statuses") or [] if r else [])]

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        payload = {"body": plan["body"], "event": EVENTS[plan["event"]], "commit_id": bundle["head"]["sha"],
                   "comments": [{"path": c["path"], "body": c["body"], "new_position": c["line"]}
                                for c in plan["inline"]]}
        r = self.http.post(f"{self.pr}/reviews", payload)
        return [(r.json() or {}).get("html_url") or bundle.get("url", "")]
