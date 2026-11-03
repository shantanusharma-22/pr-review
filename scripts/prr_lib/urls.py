"""Turn a PR URL, `owner/repo#N`, or a bare number (+ git remote) into a PRRef."""
from __future__ import annotations

import re
import subprocess
import urllib.parse
from dataclasses import asdict, dataclass
from typing import Optional

PROVIDERS = ("github", "gitlab", "bitbucket", "azure", "gitea", "local")


@dataclass
class PRRef:
    provider: str
    host: str = ""
    scheme: str = "https"
    owner: str = ""      # GitHub/Gitea owner, Bitbucket workspace, GitLab namespace (may contain '/')
    repo: str = ""
    number: int = 0
    org: str = ""        # Azure DevOps organization
    project: str = ""    # Azure DevOps project
    url: str = ""
    legacy_azure: bool = False

    @property
    def slug(self) -> str:
        parts = [self.provider, self.org, self.project, self.owner, self.repo, str(self.number)]
        return re.sub(r"[^A-Za-z0-9._-]+", "-", "-".join(p for p in parts if p)).strip("-")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PRRef":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


def parse_pr_url(url: str) -> PRRef:
    u = urllib.parse.urlparse(url.strip())
    host = (u.hostname or "").lower()
    netloc = host + (f":{u.port}" if u.port else "")
    scheme = u.scheme or "https"
    path = urllib.parse.unquote(u.path).rstrip("/")

    if host == "dev.azure.com":
        m = re.match(r"^/([^/]+)/([^/]+)/_git/([^/]+)/pullrequest/(\d+)", path, re.I)
        if m:
            return PRRef("azure", host, scheme, repo=m.group(3), number=int(m.group(4)),
                         org=m.group(1), project=m.group(2), url=url)
    if host.endswith(".visualstudio.com"):
        m = re.match(r"^/(?:DefaultCollection/)?([^/]+)/_git/([^/]+)/pullrequest/(\d+)", path, re.I)
        if m:
            return PRRef("azure", host, scheme, repo=m.group(2), number=int(m.group(3)),
                         org=host.split(".")[0], project=m.group(1), url=url, legacy_azure=True)
    if host == "bitbucket.org":
        m = re.match(r"^/([^/]+)/([^/]+)/pull-requests/(\d+)", path)
        if m:
            return PRRef("bitbucket", host, scheme, m.group(1), m.group(2), int(m.group(3)), url=url)
    m = re.match(r"^/(.+)/([^/]+)/-/merge_requests/(\d+)", path)
    if m:
        return PRRef("gitlab", netloc, scheme, m.group(1), m.group(2), int(m.group(3)), url=url)
    m = re.match(r"^/([^/]+)/([^/]+)/pull/(\d+)", path)
    if m:
        return PRRef("github", netloc, scheme, m.group(1), m.group(2), int(m.group(3)), url=url)
    m = re.match(r"^/([^/]+)/([^/]+)/pulls/(\d+)", path)
    if m:
        return PRRef("gitea", netloc, scheme, m.group(1), m.group(2), int(m.group(3)), url=url)
    raise ValueError(f"Unrecognised pull/merge request URL: {url}")


def provider_for_host(host: str) -> Optional[str]:
    host = host.lower().split(":")[0]
    known = {"github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket",
             "dev.azure.com": "azure", "ssh.dev.azure.com": "azure", "codeberg.org": "gitea"}
    if host in known:
        return known[host]
    if host.endswith(".visualstudio.com"):
        return "azure"
    for key in ("gitlab", "gitea", "forgejo", "github"):
        if key in host:
            return "gitea" if key == "forgejo" else key
    return None


def parse_remote(remote: str):
    """Return (host, path) for scp-style, ssh:// and https:// git remotes."""
    remote = remote.strip()
    m = re.match(r"^(?:[\w.-]+@)?([^:/\s]+):(?!//)(.+?)(?:\.git)?/?$", remote)
    if m and "://" not in remote:
        return m.group(1).lower(), m.group(2)
    u = urllib.parse.urlparse(remote)
    path = u.path.lstrip("/")
    path = path[:-4] if path.endswith(".git") else path
    host = (u.hostname or "").lower()
    if u.scheme in ("http", "https") and u.port:
        host += f":{u.port}"
    return host, path.rstrip("/")


def ref_from_remote(remote: str, number: int, provider: Optional[str] = None) -> PRRef:
    host, path = parse_remote(remote)
    provider = provider or provider_for_host(host)
    if not provider:
        raise ValueError(f"Cannot infer provider for host '{host}'; pass --provider.")
    if provider == "azure":
        parts = path.split("/")
        if host == "ssh.dev.azure.com" and parts and parts[0] == "v3":
            org, project, repo = parts[1], parts[2], parts[3]
            return PRRef("azure", "dev.azure.com", repo=repo, number=number, org=org, project=project)
        if "_git" in parts:
            i = parts.index("_git")
            repo, project = parts[i + 1], parts[i - 1]
            if host.endswith(".visualstudio.com"):
                return PRRef("azure", host, repo=repo, number=number, org=host.split(".")[0],
                             project=project, legacy_azure=True)
            return PRRef("azure", "dev.azure.com", repo=repo, number=number, org=parts[0], project=project)
        raise ValueError(f"Unrecognised Azure DevOps remote: {remote}")
    if host == "ssh.github.com":
        host = "github.com"
    owner, _, repo = path.rpartition("/")
    if not owner:
        raise ValueError(f"Cannot parse owner/repo from remote: {remote}")
    return PRRef(provider, host, owner=owner, repo=repo, number=number)


def git_remote_url(cwd: Optional[str] = None, name: str = "origin") -> str:
    out = subprocess.run(["git", "remote", "get-url", name], cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise ValueError("Not inside a git repo with an 'origin' remote; pass a full PR URL instead.")
    return out.stdout.strip()


def parse_target(target: str, provider: Optional[str] = None, host: Optional[str] = None,
                 cwd: Optional[str] = None) -> PRRef:
    target = target.strip()
    if target.startswith(("http://", "https://")):
        return parse_pr_url(target)
    m = re.fullmatch(r"(.+)/([\w.-]+)[#!](\d+)", target)
    if m:
        prov = provider or "github"
        default_hosts = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org",
                         "gitea": "codeberg.org"}
        if prov not in default_hosts and not host:
            raise ValueError(f"Short form owner/repo#N is not supported for {prov}; pass the full URL.")
        return PRRef(prov, host or default_hosts[prov], owner=m.group(1), repo=m.group(2), number=int(m.group(3)))
    m = re.fullmatch(r"[#!]?(\d+)", target)
    if m:
        return ref_from_remote(git_remote_url(cwd), int(m.group(1)), provider)
    raise ValueError(f"Unrecognised target '{target}'. Use a PR/MR URL, owner/repo#N, a number, or --local.")
