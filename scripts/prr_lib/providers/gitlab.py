"""GitLab.com and self-managed GitLab (API v4)."""
from __future__ import annotations

import urllib.parse
from typing import List, Optional

from .. import auth
from ..diff import make_file
from ..http import Client, HttpError
from .base import Provider, comment, external_refs, issue, issue_numbers, new_bundle


def _status(d: dict) -> str:
    if d.get("new_file"):
        return "added"
    if d.get("deleted_file"):
        return "deleted"
    if d.get("renamed_file"):
        return "renamed"
    return "modified"


class GitLab(Provider):
    name = "gitlab"
    suggestion_style = "gitlab"

    def __init__(self, ref, api_url=None, transport=None):
        super().__init__(ref, api_url, transport)
        base = api_url or f"{ref.scheme}://{ref.host}/api/v4"
        self.http = Client(base, auth.gitlab(ref.host.split(":")[0]), transport=transport)
        pid = urllib.parse.quote(f"{ref.owner}/{ref.repo}", safe="")
        self.proj = f"/projects/{pid}"
        self.mr = f"{self.proj}/merge_requests/{ref.number}"

    def _pages(self, path: str, limit: int = 3000) -> list:
        out, page = [], "1"
        while page and len(out) < limit:
            r = self.http.get(path, params={"per_page": 100, "page": page})
            data = r.json() or []
            out.extend(data)
            page = r.headers.get("x-next-page", "").strip()
            if not data:
                break
        return out[:limit]

    def fetch(self) -> dict:
        mr = self.preflight(lambda: self.http.get(self.mr).json())
        try:
            diffs = self._pages(f"{self.mr}/diffs")
        except HttpError as e:
            if e.status != 404:
                raise
            diffs = (self.http.get(f"{self.mr}/changes").json() or {}).get("changes", [])
        files = [make_file(d["new_path"], _status(d), d.get("diff"), d.get("old_path"),
                           binary=bool(d.get("too_large")) or (not d.get("diff") and not d.get("deleted_file")))
                 for d in diffs]
        comments = []
        for disc in self._pages(f"{self.mr}/discussions", 1000):
            for note in disc.get("notes", []):
                if note.get("system"):
                    continue
                pos = note.get("position") or {}
                comments.append(comment(note.get("author", {}).get("username"), note.get("body"),
                                        pos.get("new_path"), pos.get("new_line"), note.get("created_at"),
                                        note.get("resolved")))
        commits = [{"sha": c["id"], "message": c.get("message", "")} for c in self._pages(f"{self.mr}/commits", 250)]
        texts = [mr.get("title", ""), mr.get("description") or ""] + [c["message"] for c in commits]
        linked, seen = [], set()
        r = self.http.try_get(f"{self.mr}/closes_issues")
        for j in (r.json() or []) if r else []:
            seen.add(j.get("iid"))
            linked.append(issue(j.get("iid"), j.get("title"), j.get("description"), j.get("web_url")))
        for num in issue_numbers(texts, self.ref.host, self.ref.owner, self.ref.repo):
            if num in seen or len(linked) >= 5:
                continue
            r = self.http.try_get(f"{self.proj}/issues/{num}")
            if r:
                j = r.json()
                linked.append(issue(num, j.get("title"), j.get("description"), j.get("web_url")))
        refs = mr.get("diff_refs") or {}
        return new_bundle(
            self.ref, url=mr.get("web_url", self.ref.url), title=mr.get("title", ""),
            body=mr.get("description") or "", author=mr.get("author", {}).get("username", ""),
            state=mr.get("state", ""), draft=bool(mr.get("draft") or mr.get("work_in_progress")),
            base={"ref": mr.get("target_branch", ""), "sha": refs.get("base_sha", "")},
            head={"ref": mr.get("source_branch", ""), "sha": refs.get("head_sha") or mr.get("sha", "")},
            merge_base=refs.get("base_sha", ""), files=files, comments=comments, commits=commits,
            linked_issues=linked, external_refs=external_refs(texts), provider_data={"diff_refs": refs},
        )

    def read_file(self, path: str, sha: str) -> Optional[str]:
        r = self.http.try_get(f"{self.proj}/repository/files/{urllib.parse.quote(path, safe='')}/raw",
                              params={"ref": sha})
        return r.text() if r else None

    def checks(self, bundle: dict) -> List[dict]:
        r = self.http.try_get(f"{self.mr}/pipelines")
        pipes = (r.json() or []) if r else []
        if not pipes:
            return []
        p = pipes[0]
        out = [{"name": f"pipeline {p.get('id')}", "state": p.get("status"), "url": p.get("web_url")}]
        jobs = self.http.try_get(f"{self.proj}/pipelines/{p.get('id')}/jobs", params={"per_page": 100})
        for j in (jobs.json() or []) if jobs else []:
            if j.get("status") not in ("success", "skipped", "manual"):
                out.append({"name": j.get("name"), "state": j.get("status"), "url": j.get("web_url")})
        return out

    def _position(self, bundle: dict, c: dict) -> dict:
        refs = bundle["provider_data"].get("diff_refs", {})
        pos = {"position_type": "text", "base_sha": refs.get("base_sha"), "start_sha": refs.get("start_sha"),
               "head_sha": refs.get("head_sha"), "new_path": c["path"], "old_path": c.get("old_path") or c["path"],
               "new_line": c["line"]}
        if c.get("old_line"):
            pos["old_line"] = c["old_line"]
        return pos

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        body = plan["body"]
        if plan["event"] == "request_changes":
            body = "**Changes requested.**\n\n" + body
        try:  # Draft notes publish as one batch (one notification), like a GitHub review.
            for c in plan["inline"]:
                self.http.post(f"{self.mr}/draft_notes", {"note": c["body"], "position": self._position(bundle, c)})
            self.http.post(f"{self.mr}/draft_notes", {"note": body})
            self.http.post(f"{self.mr}/draft_notes/bulk_publish")
        except HttpError as e:
            if e.status != 404 or e.url.endswith("bulk_publish"):
                raise
            for c in plan["inline"]:
                self.http.post(f"{self.mr}/discussions", {"body": c["body"], "position": self._position(bundle, c)})
            self.http.post(f"{self.mr}/notes", {"body": body})
        if plan["event"] == "approve":
            self.http.post(f"{self.mr}/approve", {"sha": bundle["head"]["sha"]})
        return [bundle.get("url") or self.ref.url]
