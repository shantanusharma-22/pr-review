"""Azure DevOps Services (dev.azure.com and legacy *.visualstudio.com)."""
from __future__ import annotations

import html
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

from .. import auth
from ..diff import make_file, risk_score, unified_from_contents
from ..http import Client
from .base import Provider, comment, external_refs, issue, new_bundle

API = {"api-version": "7.1"}
EAGER_DIFF_LIMIT = 60   # fetch file contents up front only for PRs this small
VOTES = {"approve": 10, "comment": 0, "request_changes": -5}  # -5 = "waiting for author"


def _strip_html(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s or "")).strip()


def _status(change_type: str) -> str:
    ct = (change_type or "").lower()
    if "add" in ct:
        return "added"
    if "delete" in ct:
        return "deleted"
    if "rename" in ct:
        return "renamed"
    return "modified"


class Azure(Provider):
    name = "azure"
    suggestion_style = "github"   # Azure Repos renders ```suggestion blocks

    def __init__(self, ref, api_url=None, transport=None):
        super().__init__(ref, api_url, transport)
        base = api_url or (f"https://{ref.org}.visualstudio.com" if ref.legacy_azure
                           else f"https://dev.azure.com/{ref.org}")
        self.http = Client(base, auth.azure(), transport=transport)
        proj = urllib.parse.quote(ref.project)
        self.repo = f"/{proj}/_apis/git/repositories/{urllib.parse.quote(ref.repo)}"
        self.pr = f"{self.repo}/pullRequests/{ref.number}"

    def fetch(self) -> dict:
        pr = self.preflight(lambda: self.http.get(self.pr, params=API).json())
        iters = (self.http.get(f"{self.pr}/iterations", params=API).json() or {}).get("value", [])
        last = iters[-1] if iters else {}
        head = (last.get("sourceRefCommit") or pr.get("lastMergeSourceCommit") or {}).get("commitId", "")
        merge_base = (last.get("commonRefCommit") or pr.get("lastMergeTargetCommit") or {}).get("commitId", "")
        target = (pr.get("lastMergeTargetCommit") or {}).get("commitId", "")
        entries = []
        if last:
            params = dict(API, **{"$top": 2000, "$compareTo": 0})
            j = self.http.get(f"{self.pr}/iterations/{last['id']}/changes", params=params).json() or {}
            entries = [e for e in j.get("changeEntries", [])
                       if not (e.get("item") or {}).get("isFolder") and (e.get("item") or {}).get("path")]
        files = []
        for e in entries:
            f = make_file(e["item"]["path"], _status(e.get("changeType")), None,
                          e.get("originalPath") or e.get("sourceServerItem"), additions=0, deletions=0)
            f["patch_deferred"] = True
            files.append(f)
        stub = {"merge_base": merge_base, "head": {"sha": head}}
        if len(files) <= EAGER_DIFF_LIMIT:
            with ThreadPoolExecutor(max_workers=6) as pool:
                for f, patch in zip(files, pool.map(lambda x: self.load_patch(stub, x), files)):
                    _apply_patch(f, patch)
        comments = []
        threads = (self.http.get(f"{self.pr}/threads", params=API).json() or {}).get("value", [])
        for t in threads:
            ctx = t.get("threadContext") or {}
            line = ((ctx.get("rightFileStart") or {}).get("line"))
            for c in t.get("comments", []):
                if c.get("commentType") == "system":
                    continue
                comments.append(comment((c.get("author") or {}).get("displayName"), c.get("content"),
                                        ctx.get("filePath"), line, c.get("publishedDate"),
                                        t.get("status") in ("fixed", "closed", "wontFix", "byDesign")))
        commits = [{"sha": c.get("commitId"), "message": c.get("comment", "")}
                   for c in (self.http.get(f"{self.pr}/commits", params=API).json() or {}).get("value", [])]
        linked = []
        wi = self.http.try_get(f"{self.pr}/workitems", params=API)
        ids = [str(w.get("id")) for w in ((wi.json() or {}).get("value", []) if wi else [])][:5]
        if ids:
            r = self.http.try_get("/_apis/wit/workitems", params=dict(API, ids=",".join(ids)))
            for w in ((r.json() or {}).get("value", []) if r else []):
                fl = w.get("fields") or {}
                body = _strip_html(fl.get("System.Description", "")) + "\n" + \
                    _strip_html(fl.get("Microsoft.VSTS.Common.AcceptanceCriteria", ""))
                linked.append(issue(w.get("id"), fl.get("System.Title"), body.strip(), w.get("url")))
        texts = [pr.get("title", ""), pr.get("description") or ""] + [c["message"] for c in commits]
        return new_bundle(
            self.ref, url=self.ref.url or pr.get("url", ""), title=pr.get("title", ""),
            body=pr.get("description") or "", author=(pr.get("createdBy") or {}).get("displayName", ""),
            state=pr.get("status", ""), draft=bool(pr.get("isDraft")),
            base={"ref": pr.get("targetRefName", "").replace("refs/heads/", ""), "sha": target},
            head={"ref": pr.get("sourceRefName", "").replace("refs/heads/", ""), "sha": head},
            merge_base=merge_base, files=files, comments=comments, commits=commits,
            linked_issues=linked, external_refs=external_refs(texts),
            provider_data={"iteration": last.get("id")},
        )

    def read_file(self, path: str, sha: str) -> Optional[str]:
        if not sha:
            return None
        params = dict(API, **{"path": "/" + path.lstrip("/"), "versionDescriptor.version": sha,
                              "versionDescriptor.versionType": "commit", "includeContent": "true"})
        r = self.http.try_get(f"{self.repo}/items", params=params)
        if not r:
            return None
        j = r.json() or {}
        if (j.get("contentMetadata") or {}).get("isBinary"):
            return None
        return j.get("content")

    def load_patch(self, bundle: dict, f: dict) -> Optional[str]:
        if f.get("patch") or not f.get("patch_deferred"):
            return f.get("patch")
        old = None if f["status"] == "added" else self.read_file(f.get("old_path") or f["path"], bundle["merge_base"])
        new = None if f["status"] == "deleted" else self.read_file(f["path"], bundle["head"]["sha"])
        return unified_from_contents(old, new)

    def checks(self, bundle: dict) -> List[dict]:
        r = self.http.try_get(f"{self.pr}/statuses", params=API)
        return [{"name": "/".join(filter(None, [(s.get("context") or {}).get("genre"),
                                               (s.get("context") or {}).get("name")])),
                 "state": s.get("state"), "url": s.get("targetUrl")}
                for s in ((r.json() or {}).get("value", []) if r else [])]

    def post_review(self, bundle: dict, plan: dict) -> List[str]:
        for c in plan["inline"]:
            start = c.get("start_line") or c["line"]
            self.http.post(f"{self.pr}/threads", params=API, json_body={
                "comments": [{"parentCommentId": 0, "content": c["body"], "commentType": 1}],
                "status": "active",
                "threadContext": {"filePath": "/" + c["path"],
                                  "rightFileStart": {"line": start, "offset": 1},
                                  "rightFileEnd": {"line": c["line"], "offset": 1}}})
        self.http.post(f"{self.pr}/threads", params=API, json_body={
            "comments": [{"parentCommentId": 0, "content": plan["body"], "commentType": 1}],
            "status": "active" if plan["event"] != "approve" else "closed"})
        if VOTES[plan["event"]]:
            me = (self.http.get("/_apis/connectionData").json() or {}).get("authenticatedUser", {}).get("id")
            if me:
                self.http.put(f"{self.pr}/reviewers/{me}", params=API, json_body={"vote": VOTES[plan["event"]]})
        return [bundle.get("url") or self.ref.url]


def _apply_patch(f: dict, patch: Optional[str]) -> None:
    from ..diff import count_changes
    f["patch"] = patch
    f["patch_deferred"] = False
    f["additions"], f["deletions"] = count_changes(patch)
    f["risk"], f["risk_reasons"] = risk_score(f)
