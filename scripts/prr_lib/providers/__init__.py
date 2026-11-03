"""Provider registry."""
from __future__ import annotations

from ..urls import PRRef
from .azure import Azure
from .base import PreflightError, Provider
from .bitbucket import Bitbucket
from .gitea import Gitea
from .github import GitHub
from .gitlab import GitLab
from .local import Local

REGISTRY = {"github": GitHub, "gitlab": GitLab, "bitbucket": Bitbucket, "azure": Azure,
            "gitea": Gitea, "local": Local}


def get_provider(ref: PRRef, api_url=None, transport=None, **local_kw) -> Provider:
    cls = REGISTRY[ref.provider]
    if cls is Local:
        return Local(ref, api_url, transport, **local_kw)
    return cls(ref, api_url=api_url, transport=transport)


__all__ = ["get_provider", "Provider", "PreflightError", "REGISTRY"]
