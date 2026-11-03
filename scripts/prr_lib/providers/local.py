"""Local git mode: review <base>...<head> in the current checkout. Works with any git host."""
from __future__ import annotations

import subprocess
from typing import List, Optional

from ..diff import split_unified_diff
from ..urls import PRRef
from .base import PreflightError, Provider, external_refs, new_bundle


def git(*args: str, cwd: Optional[str] = None, check: bool = True) -> str:
    out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if check and out.returncode != 0:
        raise PreflightError("local", out.returncode, f"git {' '.join(args)}: {out.stderr.strip()[:300]}")
    return out.stdout


def default_base(cwd: Optional[str] = None) -> str:
    ref = git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", cwd=cwd, check=False).strip()
    if ref:
        return ref
    for cand in ("origin/main", "origin/master", "main", "master", "origin/develop", "develop"):
        if git("rev-parse", "-q", "--verify", cand + "^{commit}", cwd=cwd, check=False).strip():
            return cand
    raise PreflightError("local", 1, "Could not guess the base branch; pass --base <ref>.")


class Local(Provider):
    name = "local"
    supports_post = False
    suggestion_style = "plain"

    def __init__(self, ref: PRRef, api_url=None, transport=None, base: Optional[str] = None,
                 head: str = "HEAD", fetch_ref: Optional[str] = None, remote: str = "origin",
                 cwd: Optional[str] = None):
        super().__init__(ref, api_url, transport)
        self.cwd = cwd
        if fetch_ref:  # e.g. refs/pull/123/head, refs/merge-requests/7/head, refs/changes/45/12345/2
            git("fetch", "--quiet", remote, f"+{fetch_ref}:refs/pr-review/head", cwd=cwd)
            head = "refs/pr-review/head"
        self.base = base
        self.head = head

    def fetch(self) -> dict:
        git("rev-parse", "--is-inside-work-tree", cwd=self.cwd)
        base = self.base or default_base(self.cwd)
        base_sha = git("rev-parse", "--verify", base + "^{commit}", cwd=self.cwd).strip()
        worktree = self.head.upper() == "WORKTREE"   # include uncommitted (tracked) changes
        head_sha = git("rev-parse", "--verify", ("HEAD" if worktree else self.head) + "^{commit}",
                       cwd=self.cwd).strip()
        mb = git("merge-base", base_sha, head_sha, cwd=self.cwd).strip()
        rng = [mb] if worktree else [f"{mb}..{head_sha}"]
        diff = git("diff", "--no-color", "--no-ext-diff", "-M", *rng, cwd=self.cwd)
        if not diff.strip():
            raise PreflightError("local", 1, f"Empty diff between {base} and {self.head}.")
        log = git("log", "--format=%H%x1f%B%x1e", f"{mb}..{head_sha}", cwd=self.cwd)
        commits = []
        for rec in log.split("\x1e"):
            if "\x1f" in rec:
                sha, msg = rec.strip().split("\x1f", 1)
                commits.append({"sha": sha, "message": msg.strip()})
        head_name = self.head if self.head not in ("HEAD", "WORKTREE", "worktree") else \
            git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.cwd, check=False).strip()
        title = commits[-1]["message"].splitlines()[0] if commits else head_name
        texts = [head_name] + [c["message"] for c in commits]
        return new_bundle(
            self.ref, title=title, body="", author=git("log", "-1", "--format=%an", head_sha, cwd=self.cwd).strip(),
            state="local", base={"ref": base, "sha": base_sha}, head={"ref": head_name, "sha": head_sha},
            merge_base=mb, files=split_unified_diff(diff), commits=commits, external_refs=external_refs(texts),
            provider_data={"worktree": worktree},
            notes=["Local mode: no PR description, discussion or linked issues; pass --spec if a spec exists."],
        )

    def read_file(self, path: str, sha: str) -> Optional[str]:
        if sha == "WORKTREE":
            root = git("rev-parse", "--show-toplevel", cwd=self.cwd).strip()
            try:
                with open(f"{root}/{path}", encoding="utf-8", errors="replace") as fh:
                    return fh.read()
            except OSError:
                return None
        out = subprocess.run(["git", "show", f"{sha}:{path}"], cwd=self.cwd, capture_output=True)
        return out.stdout.decode("utf-8", errors="replace") if out.returncode == 0 else None

    def list_files(self, sha: str) -> List[str]:
        return git("ls-tree", "-r", "--name-only", sha, cwd=self.cwd).splitlines()
