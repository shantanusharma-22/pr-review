"""Stdlib unittest suite. Run: python -m unittest discover -s tests -v"""
import json
import os
import re
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from prr_lib import diff, findings  # noqa: E402
from prr_lib.http import Client, HttpError, Response, next_link  # noqa: E402
from prr_lib.providers import get_provider  # noqa: E402
from prr_lib.urls import parse_pr_url, parse_target, ref_from_remote  # noqa: E402

PATCH = "@@ -1,3 +1,4 @@\n a\n-b\n+B\n+C\n c"
UNIFIED = """diff --git a/src/app.py b/src/app.py
index 1..2 100644
--- a/src/app.py
+++ b/src/app.py
@@ -1,3 +1,4 @@
 a
-b
+B
+C
 c
diff --git a/old.txt b/new.txt
similarity index 90%
rename from old.txt
rename to new.txt
diff --git a/gone.py b/gone.py
deleted file mode 100644
--- a/gone.py
+++ /dev/null
@@ -1 +0,0 @@
-x
diff --git a/img.png b/img.png
new file mode 100644
Binary files /dev/null and b/img.png differ
"""


class Fake:
    """Route (METHOD, regex on URL) -> Response; records every call."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, headers, data, timeout):
        self.calls.append((method, url, json.loads(data) if data else None))
        for (m, rx), resp in self.routes.items():
            if m == method and re.search(rx, url):
                return resp() if callable(resp) else resp
        return Response(404, {}, b'{"message":"not found"}')


def J(obj, status=200, headers=None):
    return Response(status, headers or {}, json.dumps(obj).encode())


def T(text, status=200):
    return Response(status, {}, text.encode())


class UrlTests(unittest.TestCase):
    def test_github(self):
        r = parse_pr_url("https://github.com/acme/api/pull/42/files")
        self.assertEqual((r.provider, r.owner, r.repo, r.number), ("github", "acme", "api", 42))

    def test_github_enterprise(self):
        self.assertEqual(parse_pr_url("https://git.corp.io/a/b/pull/7").host, "git.corp.io")

    def test_gitlab_subgroups(self):
        r = parse_pr_url("https://gitlab.example.com:8443/grp/sub/proj/-/merge_requests/9")
        self.assertEqual((r.provider, r.host, r.owner, r.repo, r.number),
                         ("gitlab", "gitlab.example.com:8443", "grp/sub", "proj", 9))

    def test_bitbucket(self):
        r = parse_pr_url("https://bitbucket.org/ws/repo/pull-requests/3/diff")
        self.assertEqual((r.provider, r.owner, r.number), ("bitbucket", "ws", 3))

    def test_azure(self):
        r = parse_pr_url("https://dev.azure.com/org/My%20Project/_git/repo/pullrequest/11")
        self.assertEqual((r.provider, r.org, r.project, r.repo, r.number), ("azure", "org", "My Project", "repo", 11))
        r = parse_pr_url("https://org.visualstudio.com/DefaultCollection/Proj/_git/repo/pullrequest/5")
        self.assertTrue(r.legacy_azure)
        self.assertEqual(r.org, "org")

    def test_gitea(self):
        r = parse_pr_url("https://codeberg.org/forgejo/forgejo/pulls/123")
        self.assertEqual((r.provider, r.number), ("gitea", 123))

    def test_bad_url(self):
        with self.assertRaises(ValueError):
            parse_pr_url("https://example.com/whatever")

    def test_short_forms_and_remotes(self):
        self.assertEqual(parse_target("acme/api#5").provider, "github")
        self.assertEqual(parse_target("grp/sub/proj!5", provider="gitlab").owner, "grp/sub")
        self.assertEqual(ref_from_remote("git@github.com:acme/api.git", 3).repo, "api")
        r = ref_from_remote("git@ssh.dev.azure.com:v3/org/proj/repo", 4)
        self.assertEqual((r.provider, r.org, r.project, r.repo), ("azure", "org", "proj", "repo"))
        r = ref_from_remote("https://org@dev.azure.com/org/proj/_git/repo", 4)
        self.assertEqual((r.org, r.project), ("org", "proj"))
        r = ref_from_remote("ssh://git@gitlab.corp:2222/a/b/c.git", 1)
        self.assertEqual((r.provider, r.owner, r.repo), ("gitlab", "a/b", "c"))
        with self.assertRaises(ValueError):
            ref_from_remote("git@unknown.host:a/b.git", 1)


class DiffTests(unittest.TestCase):
    def test_split(self):
        files = {f["path"]: f for f in diff.split_unified_diff(UNIFIED)}
        self.assertEqual(files["src/app.py"]["additions"], 2)
        self.assertEqual(files["src/app.py"]["deletions"], 1)
        self.assertTrue(files["src/app.py"]["patch"].startswith("@@"))
        self.assertEqual(files["new.txt"]["status"], "renamed")
        self.assertEqual(files["new.txt"]["old_path"], "old.txt")
        self.assertEqual(files["gone.py"]["status"], "deleted")
        self.assertTrue(files["img.png"]["binary"])

    def test_new_side_lines(self):
        self.assertEqual(diff.new_side_lines(PATCH), {1: 1, 2: None, 3: None, 4: 3})

    def test_annotate(self):
        out = diff.annotate_patch(PATCH).splitlines()
        self.assertIn("     2 +B", out)
        self.assertTrue(out[2].strip().startswith("-b"))

    def test_classify_and_risk(self):
        self.assertTrue(diff.classify("yarn.lock")["lockfile"])
        self.assertTrue(diff.classify("web/dist/app.min.js")["generated"])
        self.assertTrue(diff.classify("pkg/foo_test.go")["test"])
        auth = diff.make_file("src/auth/session.py", patch=PATCH)
        doc = diff.make_file("docs/intro.md", patch=PATCH)
        self.assertGreater(auth["risk"], doc["risk"])
        self.assertNotIn("concurrency/state", diff.make_file("src/block.py")["risk_reasons"])

    def test_unified_from_contents(self):
        out = diff.unified_from_contents("a\nb\n", "a\nB\n")
        self.assertTrue(out.startswith("@@"))
        self.assertEqual(diff.new_side_lines(out), {1: 1, 2: None})


class HttpTests(unittest.TestCase):
    def test_retry_then_success(self):
        seq = [Response(503, {"retry-after": "0"}), J({"ok": 1})]
        c = Client("https://x", transport=lambda *a: seq.pop(0))
        c.sleep = lambda s: None
        self.assertEqual(c.get("/a").json(), {"ok": 1})

    def test_error_and_try_get(self):
        c = Client("https://x", transport=lambda *a: Response(404, {}, b"nope"))
        self.assertIsNone(c.try_get("/a"))
        c = Client("https://x", transport=lambda *a: Response(401, {}, b"bad"))
        with self.assertRaises(HttpError):
            c.get("/a")

    def test_next_link(self):
        h = '<https://api/x?page=2>; rel="next", <https://api/x?page=9>; rel="last"'
        self.assertEqual(next_link(h), "https://api/x?page=2")
        self.assertIsNone(next_link('<https://api/x?page=1>; rel="prev"'))


def bundle_with(patch=PATCH, path="src/app.py"):
    return {"files": [diff.make_file(path, patch=patch)], "comments": [], "head": {"sha": "h" * 40},
            "provider_data": {}}


class FindingsTests(unittest.TestCase):
    def review(self, **kw):
        r = {"decision": "comment", "summary": "- ok", "findings": [
            {"axis": "correctness", "severity": "major", "path": "src/app.py", "line": 3, "start_line": 2,
             "title": "Bug", "body": "why", "suggestion": "X\nY", "evidence": "patch"},
            {"axis": "spec", "severity": "question", "title": "Scope?", "evidence": "inferred"},
            {"axis": "standards", "severity": "minor", "path": "src/app.py", "line": 99, "title": "Off-diff line"}]}
        r.update(kw)
        return r

    def test_validate_rules(self):
        b = bundle_with()
        errs, _ = findings.validate(self.review(decision="approve",
                                                findings=[{"axis": "correctness", "severity": "blocker",
                                                           "title": "x"}]), b)
        self.assertTrue(any("cannot approve" in e for e in errs))
        errs, warns = findings.validate(self.review(decision="request_changes",
                                                    findings=[{"axis": "spec", "severity": "nit", "title": "n"}]), b)
        self.assertFalse(errs)
        self.assertTrue(any("prefer 'comment'" in w for w in warns))
        errs, _ = findings.validate({"decision": "maybe", "summary": "", "findings": []}, b)
        self.assertEqual(len(errs), 2)

    def test_plan_anchoring_and_suggestions(self):
        p = findings.plan(self.review(), bundle_with(), "gitlab")
        self.assertEqual(len(p["inline"]), 1)
        c = p["inline"][0]
        self.assertEqual((c["start_line"], c["line"]), (2, 3))
        self.assertIn("```suggestion:-1+0", c["body"])
        self.assertEqual(len(p["summary_only"]), 2)
        self.assertIn("<!-- pr-review-skill head=", p["body"])
        self.assertIn("_(inline)_", p["body"])

    def test_no_approve_and_dedupe(self):
        b = bundle_with()
        b["comments"] = [{"path": "src/app.py", "line": 3, "body": "Bug here, see above"}]
        p = findings.plan(self.review(decision="approve", findings=self.review()["findings"][:1]), b,
                          "github", allow_approve=False)
        self.assertEqual(p["event"], "comment")
        self.assertEqual(len(p["dropped_duplicates"]), 1)


GH = r"https://api\.github\.com/repos/acme/api"


class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {"GH_TOKEN": "t0k"}, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def routes(self):
        pr = {"title": "Fix #7", "body": "Closes #7", "user": {"login": "dev"}, "state": "open", "draft": False,
              "html_url": "https://github.com/acme/api/pull/42",
              "base": {"ref": "main", "sha": "b" * 40}, "head": {"ref": "feat", "sha": "h" * 40}}
        page2 = '<https://api.github.com/repos/acme/api/pulls/42/files?page=2>; rel="next"'
        return {
            ("GET", GH + r"/pulls/42$"): J(pr),
            ("GET", GH + r"/pulls/42/files\?per_page"): J([{"filename": "a.py", "status": "modified",
                                                           "patch": PATCH, "additions": 2, "deletions": 1}],
                                                         headers={"link": page2}),
            ("GET", GH + r"/pulls/42/files\?page=2"): J([{"filename": "b.py", "status": "removed",
                                                         "patch": "@@ -1 +0,0 @@\n-x"}]),
            ("GET", GH + r"/pulls/42/comments"): J([{"user": {"login": "r"}, "body": "hm", "path": "a.py",
                                                     "line": 2}]),
            ("GET", GH + r"/issues/42/comments"): J([]),
            ("GET", GH + r"/pulls/42/reviews"): J([]),
            ("GET", GH + r"/pulls/42/commits"): J([{"sha": "c" * 40, "commit": {"message": "fix ABC-12"}}]),
            ("GET", GH + r"/issues/7$"): J({"title": "Bug", "body": "Expected X", "html_url": "u"}),
            ("GET", GH + r"/compare/"): J({"merge_base_commit": {"sha": "m" * 40}}),
            ("POST", GH + r"/pulls/42/reviews"): J({"html_url": "https://github.com/acme/api/pull/42#review"}),
        }

    def test_fetch_and_post(self):
        fake = Fake(self.routes())
        p = get_provider(parse_pr_url("https://github.com/acme/api/pull/42"), transport=fake)
        b = p.fetch()
        self.assertEqual([f["path"] for f in b["files"]], ["a.py", "b.py"])
        self.assertEqual(b["files"][1]["status"], "deleted")
        self.assertEqual(b["merge_base"], "m" * 40)
        self.assertEqual(b["linked_issues"][0]["title"], "Bug")
        self.assertEqual(b["external_refs"], ["ABC-12"])
        plan = {"event": "request_changes", "body": "B",
                "inline": [{"path": "a.py", "line": 3, "start_line": 2, "body": "x"}]}
        p.post_review(b, plan)
        method, url, payload = fake.calls[-1]
        self.assertEqual(payload["event"], "REQUEST_CHANGES")
        self.assertEqual(payload["commit_id"], "h" * 40)
        self.assertEqual(payload["comments"][0]["start_line"], 2)

    def test_preflight_error(self):
        from prr_lib.providers import PreflightError
        fake = Fake({("GET", GH + r"/pulls/42$"): J({"message": "Bad credentials"}, 401)})
        p = get_provider(parse_pr_url("https://github.com/acme/api/pull/42"), transport=fake)
        with self.assertRaises(PreflightError):
            p.fetch()


GL = r"https://gitlab\.com/api/v4/projects/grp%2Fproj/merge_requests/9"


class GitLabTests(unittest.TestCase):
    def test_fetch_and_post_batched(self):
        refs = {"base_sha": "b" * 40, "start_sha": "s" * 40, "head_sha": "h" * 40}
        fake = Fake({
            ("GET", GL + r"$"): J({"title": "T", "description": "d", "author": {"username": "u"}, "state": "opened",
                                   "source_branch": "f", "target_branch": "main", "diff_refs": refs,
                                   "web_url": "w"}),
            ("GET", GL + r"/diffs"): J([{"new_path": "a.py", "old_path": "a.py", "diff": PATCH}],
                                       headers={"x-next-page": ""}),
            ("GET", GL + r"/discussions"): J([{"notes": [{"system": True, "body": "added commit"},
                                                         {"author": {"username": "r"}, "body": "nit",
                                                          "position": {"new_path": "a.py", "new_line": 2}}]}]),
            ("GET", GL + r"/commits"): J([]),
            ("GET", GL + r"/closes_issues"): J([{"iid": 3, "title": "Spec", "description": "Do X"}]),
            ("POST", GL + r"/draft_notes"): J({}, 201),
            ("POST", GL + r"/approve"): J({}, 201),
        })
        p = get_provider(parse_pr_url("https://gitlab.com/grp/proj/-/merge_requests/9"), transport=fake)
        b = p.fetch()
        self.assertEqual(len(b["comments"]), 1)
        self.assertEqual(b["linked_issues"][0]["id"], "3")
        plan = {"event": "approve", "body": "ok",
                "inline": [{"path": "a.py", "line": 4, "old_line": 3, "body": "c"}]}
        p.post_review(b, plan)
        posts = [(u, d) for m, u, d in fake.calls if m == "POST"]
        self.assertTrue(posts[0][0].endswith("/draft_notes"))
        self.assertEqual(posts[0][1]["position"]["old_line"], 3)
        self.assertEqual(posts[0][1]["position"]["head_sha"], "h" * 40)
        self.assertTrue(any(u.endswith("bulk_publish") for u, _ in posts))
        self.assertTrue(posts[-1][0].endswith("/approve"))


class BitbucketTests(unittest.TestCase):
    def test_fetch_and_post(self):
        base = r"https://api\.bitbucket\.org/2\.0/repositories/ws/repo/pullrequests/3"
        fake = Fake({
            ("GET", base + r"$"): J({"title": "T", "description": "", "author": {"display_name": "A"},
                                     "state": "OPEN", "source": {"branch": {"name": "f"}, "commit": {"hash": "h1"}},
                                     "destination": {"branch": {"name": "main"}, "commit": {"hash": "b1"}}}),
            ("GET", base + r"/diff"): T(UNIFIED),
            ("GET", base + r"/comments"): J({"values": [{"content": {"raw": "x"}, "user": {"display_name": "R"},
                                                         "inline": {"path": "src/app.py", "to": 2}}]}),
            ("GET", base + r"/commits"): J({"values": []}),
            ("POST", base + r"/comments"): J({"links": {"html": {"href": "link"}}}, 201),
            ("POST", base + r"/request-changes"): J({}),
        })
        p = get_provider(parse_pr_url("https://bitbucket.org/ws/repo/pull-requests/3"), transport=fake)
        b = p.fetch()
        self.assertEqual(len(b["files"]), 4)
        p.post_review(b, {"event": "request_changes", "body": "B",
                          "inline": [{"path": "src/app.py", "line": 3, "body": "c"}]})
        posts = [(u, d) for m, u, d in fake.calls if m == "POST"]
        self.assertEqual(posts[0][1]["inline"], {"path": "src/app.py", "to": 3})
        self.assertTrue(posts[-1][0].endswith("/request-changes"))


class AzureTests(unittest.TestCase):
    def test_fetch_builds_diffs_and_votes(self):
        base = r"https://dev\.azure\.com/org/proj/_apis/git/repositories/repo"
        pr = base + r"/pullRequests/11"

        def items(*_):
            return None

        fake = Fake({
            ("GET", pr + r"\?"): J({"title": "T", "description": "d", "createdBy": {"displayName": "A"},
                                    "status": "active", "sourceRefName": "refs/heads/f",
                                    "targetRefName": "refs/heads/main",
                                    "lastMergeTargetCommit": {"commitId": "t1"}}),
            ("GET", pr + r"/iterations\?"): J({"value": [{"id": 2, "sourceRefCommit": {"commitId": "h1"},
                                                          "commonRefCommit": {"commitId": "m1"}}]}),
            ("GET", pr + r"/iterations/2/changes"): J({"changeEntries": [
                {"item": {"path": "/src/a.py"}, "changeType": "edit"},
                {"item": {"path": "/src", "isFolder": True}, "changeType": "edit"}]}),
            ("GET", base + r"/items\?.*versionDescriptor.version=m1"): J({"content": "a\nb\n"}),
            ("GET", base + r"/items\?.*versionDescriptor.version=h1"): J({"content": "a\nB\n"}),
            ("GET", pr + r"/threads"): J({"value": []}),
            ("GET", pr + r"/commits"): J({"value": [{"commitId": "h1", "comment": "AB-1 change"}]}),
            ("GET", pr + r"/workitems"): J({"value": []}),
            ("POST", pr + r"/threads"): J({}, 200),
            ("GET", r"/_apis/connectionData"): J({"authenticatedUser": {"id": "me-id"}}),
            ("PUT", pr + r"/reviewers/me-id"): J({}),
        })
        p = get_provider(parse_pr_url("https://dev.azure.com/org/proj/_git/repo/pullrequest/11"), transport=fake)
        b = p.fetch()
        self.assertEqual(len(b["files"]), 1)
        f = b["files"][0]
        self.assertEqual((f["path"], f["additions"], f["deletions"]), ("src/a.py", 1, 1))
        self.assertEqual(b["merge_base"], "m1")
        p.post_review(b, {"event": "request_changes", "body": "B",
                          "inline": [{"path": "src/a.py", "line": 2, "body": "c"}]})
        thread = [d for m, u, d in fake.calls if m == "POST"][0]
        self.assertEqual(thread["threadContext"]["filePath"], "/src/a.py")
        vote = [d for m, u, d in fake.calls if m == "PUT"][0]
        self.assertEqual(vote["vote"], -5)


class GiteaTests(unittest.TestCase):
    def test_fetch_and_post(self):
        base = r"https://codeberg\.org/api/v1/repos/o/r"
        fake = Fake({
            ("GET", base + r"/pulls/5$"): J({"title": "T", "body": "", "user": {"login": "u"}, "state": "open",
                                             "base": {"ref": "main", "sha": "b"}, "head": {"ref": "f", "sha": "h"},
                                             "merge_base": "m"}),
            ("GET", base + r"/pulls/5\.diff"): T(UNIFIED),
            ("GET", base + r"/issues/5/comments"): J([]),
            ("GET", base + r"/pulls/5/reviews\?"): J([]),
            ("GET", base + r"/pulls/5/commits"): J([]),
            ("POST", base + r"/pulls/5/reviews"): J({"html_url": "x"}),
        })
        p = get_provider(parse_pr_url("https://codeberg.org/o/r/pulls/5"), transport=fake)
        b = p.fetch()
        self.assertEqual(b["merge_base"], "m")
        p.post_review(b, {"event": "approve", "body": "ok", "inline": [{"path": "src/app.py", "line": 2, "body": "c"}]})
        payload = fake.calls[-1][2]
        self.assertEqual(payload["event"], "APPROVED")
        self.assertEqual(payload["comments"][0]["new_position"], 2)


if __name__ == "__main__":
    unittest.main()
