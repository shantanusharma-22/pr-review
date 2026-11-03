"""Provider-neutral diff utilities."""
from __future__ import annotations

import difflib
import math
import re
from typing import Dict, List, Optional

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

LOCKFILES = {
    "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock",
    "Cargo.lock", "poetry.lock", "Pipfile.lock", "uv.lock", "pdm.lock", "go.sum", "composer.lock",
    "Gemfile.lock", "packages.lock.json", "gradle.lockfile", "flake.lock", "pubspec.lock",
    "Podfile.lock", "mix.lock", "Package.resolved",
}
MANIFESTS = {
    "package.json", "requirements.txt", "pyproject.toml", "setup.py", "setup.cfg", "Pipfile", "go.mod",
    "Cargo.toml", "pom.xml", "build.gradle", "build.gradle.kts", "Gemfile", "composer.json",
    "Directory.Packages.props", "pubspec.yaml", "Package.swift", "mix.exs", "deno.json",
}
GENERATED_RE = re.compile(
    r"(^|/)(dist|build|out|vendor|node_modules|third_party|__generated__|generated|gen)/"
    r"|\.min\.(js|css)$|\.map$|\.snap$|\.pb\.go$|_pb2(_grpc)?\.pyi?$|\.pb\.(cc|h)$"
    r"|\.g\.dart$|\.freezed\.dart$|\.designer\.cs$|\.generated\.\w+$"
)
TEST_RE = re.compile(
    r"(^|/)(tests?|__tests__|spec|specs|testdata|fixtures)/"
    r"|(_test|\.test|\.spec|_spec|Test|Tests)\.\w+$|(^|/)test_[^/]+\.py$"
)
DOC_RE = re.compile(r"\.(md|mdx|rst|txt|adoc)$|(^|/)docs?/", re.I)

RISK_RULES = [
    (r"auth|login|logout|session|oauth|oidc|saml|jwt|token|password|passwd|credential|"
     r"permission|rbac|acl|polic(y|ies)|tenant", 5, "auth/permissions"),
    (r"security|sanitiz|escap|csrf|cors|xss|upload|deserializ|pickle|(?<![a-z])(eval|exec)(?![a-z])|shell|subprocess", 5,
     "security-sensitive"),
    (r"migrations?/|migrate|schema\.(sql|rb|prisma|graphql)|\.sql$|alembic|flyway|liquibase", 5,
     "db schema/migration"),
    (r"crypto|encrypt|decrypt|cipher|hmac|signature|cert|tls|ssl|secret", 4, "crypto/secrets"),
    (r"payment|billing|invoice|charge|refund|wallet|ledger|pricing|checkout", 4, "money"),
    (r"\.github/workflows/|\.gitlab-ci|azure-pipelines|jenkinsfile|bitbucket-pipelines|\.circleci/|"
     r"\.gitea/workflows|\.forgejo/workflows|\.buildkite", 4, "CI/CD"),
    (r"dockerfile|docker-compose|compose\.ya?ml|\.tf$|\.tfvars$|(^|/)(helm|k8s|kubernetes|charts|"
     r"deploy|infra|terraform)/", 3, "infra"),
    (r"(^|/)(api|routes?|controllers?|handlers?|endpoints?|public)/|\.proto$|openapi|swagger|"
     r"\.graphql$|(^|/)index\.(ts|js)$|__init__\.py$", 3, "public API surface"),
    (r"concurren|thread|async|worker|queue|(?<![a-z])lock|mutex|semaphore|scheduler|cron|retry|cache", 3,
     "concurrency/state"),
    (r"agent|orchestrat|planner|supervisor|llm|prompt|tool_?call", 2, "agent/LLM code"),
    (r"config|settings|\.env|feature.?flag", 2, "config"),
]
_RISK_COMPILED = [(re.compile(p, re.I), w, label) for p, w, label in RISK_RULES]


def _basename(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def classify(path: str) -> Dict[str, bool]:
    base = _basename(path)
    return {
        "lockfile": base in LOCKFILES,
        "manifest": base in MANIFESTS or base.endswith((".csproj", ".fsproj")),
        "generated": bool(GENERATED_RE.search(path)) and base not in LOCKFILES,
        "test": bool(TEST_RE.search(path)),
        "doc": bool(DOC_RE.search(path)),
    }


def count_changes(patch: Optional[str]):
    adds = dels = 0
    for line in (patch or "").splitlines():
        if line.startswith("+") and not line.startswith("+++ "):
            adds += 1
        elif line.startswith("-") and not line.startswith("--- "):
            dels += 1
    return adds, dels


def make_file(path: str, status: str = "modified", patch: Optional[str] = None,
              old_path: Optional[str] = None, additions: Optional[int] = None,
              deletions: Optional[int] = None, binary: bool = False) -> dict:
    path = path.lstrip("/")
    if patch is not None and not patch.strip():
        patch = None
    a, d = count_changes(patch)
    f = {
        "path": path,
        "old_path": (old_path.lstrip("/") if old_path and old_path.lstrip("/") != path else None),
        "status": status,
        "additions": additions if additions is not None else a,
        "deletions": deletions if deletions is not None else d,
        "patch": patch,
        "binary": binary,
    }
    f.update(classify(path))
    f["risk"], f["risk_reasons"] = risk_score(f)
    return f


def risk_score(f: dict):
    path = f["path"]
    score, reasons = 0, []
    for rx, weight, label in _RISK_COMPILED:
        if rx.search(path):
            score += weight
            reasons.append(label)
    if f.get("manifest"):
        score += 3
        reasons.append("dependencies")
    if f.get("lockfile"):
        score += 2
        reasons.append("dependencies (lockfile)")
    if f.get("test") and f.get("status") == "deleted":
        score += 4
        reasons.append("test removed")
    elif f.get("test"):
        score -= 1
    if f.get("doc") and not reasons:
        score -= 2
    changes = (f.get("additions") or 0) + (f.get("deletions") or 0)
    score += min(3, int(math.log10(changes + 1) * 1.5))
    if f.get("generated"):
        score = min(score, 0)
    return score, reasons


def split_unified_diff(text: str) -> List[dict]:
    """Split a multi-file `git diff` into make_file() records. Patches keep only hunks."""
    files: List[dict] = []
    cur: Optional[dict] = None

    def flush():
        if cur is not None:
            files.append(make_file(cur["path"] or cur["old"] or "unknown", cur["status"],
                                   "\n".join(cur["hunks"]) if cur["hunks"] else None,
                                   cur["old"], binary=cur["binary"]))

    for line in text.splitlines():
        if line.startswith("diff --git "):
            flush()
            m = re.match(r'^diff --git "?a/(.+?)"? "?b/(.+?)"?$', line)
            cur = {"old": m.group(1) if m else None, "path": m.group(2) if m else None,
                   "status": "modified", "hunks": [], "binary": False, "in_hunks": False}
            continue
        if cur is None:
            continue
        if cur["in_hunks"] and line[:1] in ("+", "-", " ", "\\", ""):
            cur["hunks"].append(line)
            continue
        if line.startswith("@@"):
            cur["in_hunks"] = True
            cur["hunks"].append(line)
        elif line.startswith("new file mode"):
            cur["status"] = "added"
        elif line.startswith("deleted file mode"):
            cur["status"] = "deleted"
        elif line.startswith("rename from "):
            cur["old"], cur["status"] = line[len("rename from "):], "renamed"
        elif line.startswith("rename to "):
            cur["path"] = line[len("rename to "):]
        elif line.startswith("Binary files") or line.startswith("GIT binary patch"):
            cur["binary"] = True
        elif line.startswith("--- ") and not line.startswith("--- /dev/null"):
            cur["old"] = _strip_prefix(line[4:])
        elif line.startswith("+++ "):
            if line.startswith("+++ /dev/null"):
                cur["status"] = "deleted"
            else:
                cur["path"] = _strip_prefix(line[4:])
    flush()
    for f in files:
        if f["status"] == "deleted" and f.get("old_path"):
            f["path"], f["old_path"] = f["old_path"], None
    return files


def _strip_prefix(p: str) -> str:
    p = p.strip().strip('"').split("\t")[0]
    return p[2:] if p[:2] in ("a/", "b/") else p


def new_side_lines(patch: Optional[str]) -> Dict[int, Optional[int]]:
    """Map each commentable new-side line number to its old line (None for added lines)."""
    res: Dict[int, Optional[int]] = {}
    old = new = 0
    for line in (patch or "").splitlines():
        m = HUNK_RE.match(line)
        if m:
            old, new = int(m.group(1)), int(m.group(3))
            continue
        if line.startswith("+"):
            res[new] = None
            new += 1
        elif line.startswith("-"):
            old += 1
        elif line.startswith("\\"):
            continue
        else:
            res[new] = old
            old += 1
            new += 1
    return res


def annotate_patch(patch: Optional[str]) -> str:
    """Prefix every hunk line with its new-side line number so findings can be anchored exactly."""
    if not patch:
        return "  [no textual patch: binary, too large, or deferred]"
    out, new = [], 0
    for line in patch.splitlines():
        m = HUNK_RE.match(line)
        if m:
            new = int(m.group(3))
            out.append(line)
            continue
        if line.startswith("-"):
            out.append(f"{'':>6} {line}")
        elif line.startswith("\\"):
            out.append(f"{'':>6} {line}")
        else:
            out.append(f"{new:>6} {line if line else ' '}")
            new += 1
    return "\n".join(out)


def unified_from_contents(old: Optional[str], new: Optional[str], context: int = 3) -> Optional[str]:
    """Build hunks-only unified diff text from two file contents (used where APIs lack diffs)."""
    a = (old or "").splitlines()
    b = (new or "").splitlines()
    lines = list(difflib.unified_diff(a, b, lineterm="", n=context))
    body = [ln for ln in lines[2:]] if len(lines) > 2 else []
    return "\n".join(body) if body else None
