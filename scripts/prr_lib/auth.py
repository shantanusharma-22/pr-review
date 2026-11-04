"""Credential lookup. Tokens are read from env vars (or the provider's own CLI) and never printed."""
from __future__ import annotations

import base64
import os
import shutil
import subprocess
from typing import Dict, Optional


def _env(*names: str) -> Optional[str]:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return None


def _cli(cmd) -> Optional[str]:
    if not shutil.which(cmd[0]):
        return None
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    token = out.stdout.strip()
    return token if out.returncode == 0 and token and " " not in token else None


def trusted(host: str) -> bool:
    """True if generic (host-agnostic) tokens may be sent to `host`.

    A PR URL is attacker-influenced text, so a token from a generic variable such as GH_TOKEN is only sent
    to a host the user named in PR_REVIEW_TRUSTED_HOSTS (comma-separated; `host` or `host:port`).
    """
    allowed = {h.strip().lower() for h in os.environ.get("PR_REVIEW_TRUSTED_HOSTS", "").split(",") if h.strip()}
    host = host.lower()
    return host in allowed or host.split(":")[0] in allowed


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def github(host: str) -> Dict[str, str]:
    if host == "github.com":
        tok = _env("GH_TOKEN", "GITHUB_TOKEN")
    else:
        tok = _env("GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN")
        if not tok and trusted(host):
            tok = _env("GH_TOKEN", "GITHUB_TOKEN")
    tok = tok or _cli(["gh", "auth", "token", "--hostname", host])
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def gitlab(host: str) -> Dict[str, str]:
    tok = None
    if host == "gitlab.com" or trusted(host):
        tok = _env("GITLAB_TOKEN", "GL_TOKEN")
    tok = tok or _cli(["glab", "config", "get", "token", "--host", host])
    if tok:
        return {"PRIVATE-TOKEN": tok}
    job = _env("CI_JOB_TOKEN")
    if job and host == (_env("CI_SERVER_HOST") or "gitlab.com"):
        return {"JOB-TOKEN": job}
    return {}


def bitbucket(host: str = "bitbucket.org") -> Dict[str, str]:
    bearer = _env("BITBUCKET_ACCESS_TOKEN")
    if bearer:
        return {"Authorization": f"Bearer {bearer}"}
    user = _env("BITBUCKET_EMAIL", "BITBUCKET_USERNAME")
    secret = _env("BITBUCKET_API_TOKEN", "BITBUCKET_APP_PASSWORD")
    if user and secret:
        return {"Authorization": "Basic " + _b64(f"{user}:{secret}")}
    return {}


def azure(host: str = "dev.azure.com") -> Dict[str, str]:
    pat = _env("AZURE_DEVOPS_PAT", "AZURE_DEVOPS_EXT_PAT")
    if pat:
        return {"Authorization": "Basic " + _b64(":" + pat)}
    tok = _env("SYSTEM_ACCESSTOKEN")
    return {"Authorization": f"Bearer {tok}"} if tok else {}


def gitea(host: str) -> Dict[str, str]:
    if host == "codeberg.org":
        tok = _env("CODEBERG_TOKEN", "FORGEJO_TOKEN", "GITEA_TOKEN")
    elif trusted(host):
        tok = _env("GITEA_TOKEN", "FORGEJO_TOKEN")
    else:
        tok = None
    return {"Authorization": f"token {tok}"} if tok else {}


TRUST_HINT = (" For a self-hosted host, also set PR_REVIEW_TRUSTED_HOSTS=<host> so generic tokens are sent "
              "there (they are never sent to unlisted hosts).")

HINTS = {
    "github": "Set GH_TOKEN (or GITHUB_TOKEN), or run `gh auth login`. Needs read access to the repo; "
              "posting needs pull-request write.",
    "gitlab": "Set GITLAB_TOKEN (scope read_api; api to post), or run `glab auth login`.",
    "bitbucket": "Set BITBUCKET_EMAIL + BITBUCKET_API_TOKEN, or BITBUCKET_ACCESS_TOKEN "
                 "(scopes: pull requests read; write to post).",
    "azure": "Set AZURE_DEVOPS_PAT (Code: Read; Code: Read & write to post; Work Items: Read for linked items), "
             "or SYSTEM_ACCESSTOKEN in Azure Pipelines.",
    "gitea": "Set GITEA_TOKEN (or FORGEJO_TOKEN / CODEBERG_TOKEN) with repository read (write to post).",
    "local": "Local mode needs no token; check that the base/head refs exist.",
}
