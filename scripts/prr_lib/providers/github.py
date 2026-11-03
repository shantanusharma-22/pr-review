"""GitHub.com and GitHub Enterprise Server."""
from __future__ import annotations

import urllib.parse
from typing import List, Optional

from .. import auth
from ..diff import make_file
from ..http import Client, HttpError, next_link
from .base import Provider, comment, external_refs, issue, issue_numbers, new_bundle

STATUS = {"added": "added", "removed": "deleted", "renamed": "renamed", "copied": "added"}
EVENTS = {"approve": "APPROVE", "comment": "COMMENT", "request_changes": "REQUEST_CHANGES"}


class GitHub(Provider):
    name = "github"
    suggestion_style = "github"

    def __init__(self, ref, api_url=None, transport=None):
        super().__init__(ref, api_url, transport)
        base = api_url or ("https://api.github.com" if ref.host == "github.com"
                           else f"{ref.scheme}://{ref.host}/api/v3")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        headers.update(auth.github(ref.host.split(":")[0]))
        self.http = Client(base, headers, transport=transport)
        self.repo = f"/repos/{ref.owner}/{ref.repo}"

    def _pages(self, path: str, limit: int = 3000) -> list:
        out, url, params = [], path, {"per_page": 100}
        while url and len(out) < limit:
            r = self.http.get(url, params=params)
            out.extend(r.json() or [])
            url, params = next_link(r.headers.get("link")), None
        return out[:limit]

    def fetch(self) -> dict:
        n = self.ref.number
        pr = self.preflight(lambda: self.http.get(f"{self.repo}/pulls/{n}").json())
        files = [make_file(f["filename"], STATUS.get(f.get("status"), "modified"), f.get("patch"),
                           f.get("previous_filename"), f.get("additions"), f.get("deletions"),
                           binary=f.get("patch") is None and f.get("changes", 0) == 0)
                 for f in self._pages(f"{self.repo}/pulls/{n}/files")]
        comments = [comment(c.get("user", {}).get("login"), c.get("body"), c.get("path"),
                            c.get("line") or c.get("original_line"), c.get("created_at"))
                    for c in self._pages(f"{self.repo}/pulls/{n}/comments", 500)]
        comments += [comment(c.get("user", {}).get("login"), c.get("body"), created=c.get("created_at"))
                     for c in self._pages(f"{self.repo}/issues/{n}/comments", 300)]
        comments += [comment(r.get("user", {}).get("login"), r.get("body"), created=r.get("submitted_at"))
                     for r in self._pages(f"{self.repo}/pulls/{n}/reviews", 200) if r.get("body")]
        commits = [{"sha": c["sha"], "message": c.get("commit", {}).get("message", "")}
                   for c in self._pages(f"{self.repo}/pulls/{n}/commits", 250)]
        texts = [pr.get("title", ""), pr.get("body") or ""] + [c["message"] for c in commits]
        linked = []
        for num in issue_numbers(texts, self.ref.host, self.ref.owner, self.ref.repo):
            if num == n:
                continue
            r = self.http.try_get(f"{self.repo}/issues/{num}")
            if r and not r.json().get("pull_request"):
                j = r.json()
                linked.append(issue(num, j.get("title"), j.get("body"), j.get("html_url")))
        return new_bundle(
            self.ref, url=pr.get("html_url", self.ref.url), title=pr.get("title", ""), body=pr.get("body") or "",
            author=pr.get("user", {}).get("login", ""), state=pr.get("state", ""), draft=bool(pr.get("draft")),
            base={"ref": pr["base"]["ref"], "sha": pr["base"]["sha"]},
            head={"ref": pr["head"]["ref"], "sha": pr["head"]["sha"]},
            merge_base=self._merge_base(pr["base"]["sha"], pr["head"]["sha"]) or pr["base"]["sha"],
            files=files, comments=comments, commits=commits, linked_issues=linked,
            external_refs=external_refs(texts),
        )

    def _merge_base(self, base: str, head: str) -> Optional[str]:
        try:
            r = self.http.get(f"{self.repo}/compare/{base}...{head}", params={"per_page": 1})
            return (r.json() or {}).get("merge_base_commit", {}).get("sha")
        except HttpError:
            return None

    def read_file(self, path: str, sha: str) -> Optional[str]:
        r = self.http.try_get(f"{self.repo}/contents/{urllib.parse.quote(path)}", params={"ref": sha},
                              headers={"Accept": "application/vnd.github.raw"})
        return r.text() if r else None

    def checks(self, bundle: dict) -> List[dict]:
        sha = bundle["head"]["sha"]
        out = []
        r = self.http.try_get(f"{self.repo}/commits/{sha}/check-runs", params={"per_page": 100})
        for c in (r.json() or {}).get("check_runs", []) if r else []:
            out.append({"name": c.get("name"), "state": c.get("conclusion") or c.get("status"),
                        "url": c.get("html_url")})
        r = self.http.try_get(f"{self.repo}/commits/{sha}/status")
        for s in (r.json() or {}).get("statuses", []) if r else []:
            out.append({"name": s.get("context"), "state": s.get("state"), "url": s.get("target_url")})
        return out

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        comments = []
        for c in plan["inline"]:
            d = {"path": c["path"], "line": c["line"], "side": "RIGHT", "body": c["body"]}
            if c.get("start_line") and c["start_line"] < c["line"]:
                d.update(start_line=c["start_line"], start_side="RIGHT")
            comments.append(d)
        payload = {"commit_id": bundle["head"]["sha"], "body": plan["body"],
                   "event": EVENTS[plan["event"]], "comments": comments}
        try:
            r = self.http.post(f"{self.repo}/pulls/{self.ref.number}/reviews", payload)
        except HttpError as e:
            if e.status == 422 and "own pull request" in e.body and plan["event"] != "comment":
                payload["event"] = "COMMENT"
                r = self.http.post(f"{self.repo}/pulls/{self.ref.number}/reviews", payload)
            else:
                raise
        return [(r.json() or {}).get("html_url", "posted")]
