"""Tiny stdlib HTTP client: retries on 429/5xx, safe redirects, injectable transport."""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional


class HttpError(Exception):
    def __init__(self, status: int, url: str, body: str):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} for {url}: {body[:300]}")


@dataclass
class Response:
    status: int
    headers: Dict[str, str] = field(default_factory=dict)  # lower-case keys
    body: bytes = b""

    def json(self):
        text = self.body.decode("utf-8", errors="replace").strip()
        return json.loads(text) if text else None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


Transport = Callable[[str, str, Dict[str, str], Optional[bytes], float], Response]


class _SafeRedirect(urllib.request.HTTPRedirectHandler):
    """Follow redirects but drop credentials when the host changes."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None:
            old, nw = urllib.parse.urlparse(req.full_url), urllib.parse.urlparse(newurl)
            if old.netloc != nw.netloc or (old.scheme == "https" and nw.scheme != "https"):
                for h in ("Authorization", "Private-token", "Job-token"):
                    new.headers.pop(h, None)
                    new.unredirected_hdrs.pop(h, None)
        return new


_OPENER = urllib.request.build_opener(_SafeRedirect())


def urllib_transport(method, url, headers, data, timeout) -> Response:
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with _OPENER.open(req, timeout=timeout) as r:
            return Response(r.status, {k.lower(): v for k, v in r.headers.items()}, r.read())
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        return Response(e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, body)
    except urllib.error.URLError as e:
        raise HttpError(0, url, f"network error: {e.reason}") from e


SENSITIVE_HEADERS = ("authorization", "private-token", "job-token")
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def _strip_credentials_over_http(base_url: str, headers: Dict[str, str]) -> Dict[str, str]:
    """Never send credentials in clear text (unless loopback or PR_REVIEW_ALLOW_HTTP=1)."""
    u = urllib.parse.urlparse(base_url)
    if u.scheme == "https" or (u.hostname or "") in _LOOPBACK or os.environ.get("PR_REVIEW_ALLOW_HTTP") == "1":
        return headers
    return {k: v for k, v in headers.items() if k.lower() not in SENSITIVE_HEADERS}


class Client:
    def __init__(self, base_url: str, headers: Optional[Dict[str, str]] = None,
                 timeout: float = 30.0, retries: int = 3, transport: Optional[Transport] = None):
        self.base_url = base_url.rstrip("/")
        self.headers = _strip_credentials_over_http(base_url, dict(headers or {}))
        self.headers.setdefault("User-Agent", "pr-review-skill")
        self.timeout = timeout
        self.retries = retries
        self.transport = transport or urllib_transport
        self.sleep = time.sleep

    def url(self, path: str, params: Optional[dict] = None) -> str:
        url = path if path.startswith(("http://", "https://")) else f"{self.base_url}/{path.lstrip('/')}"
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params, doseq=True)
        return url

    def request(self, method: str, path: str, params: Optional[dict] = None, json_body=None,
                headers: Optional[Dict[str, str]] = None, ok=(200, 201, 202, 204)) -> Response:
        url = self.url(path, params)
        hdrs = dict(self.headers)
        hdrs.update(headers or {})
        data = None
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        attempt = 0
        while True:
            resp = self.transport(method, url, hdrs, data, self.timeout)
            if resp.status in (429, 500, 502, 503, 504) and attempt < self.retries:
                wait = _retry_after(resp.headers) or (2 ** attempt)
                self.sleep(min(wait, 30))
                attempt += 1
                continue
            if resp.status not in ok:
                raise HttpError(resp.status, url, resp.text())
            return resp

    def get(self, path, params=None, headers=None) -> Response:
        return self.request("GET", path, params=params, headers=headers)

    def try_get(self, path, params=None, headers=None) -> Optional[Response]:
        """GET that returns None on 404 (useful for optional files)."""
        try:
            return self.get(path, params=params, headers=headers)
        except HttpError as e:
            if e.status == 404:
                return None
            raise

    def post(self, path, json_body=None, params=None) -> Response:
        return self.request("POST", path, params=params, json_body=json_body)

    def put(self, path, json_body=None, params=None) -> Response:
        return self.request("PUT", path, params=params, json_body=json_body)


def _retry_after(headers: Dict[str, str]) -> Optional[float]:
    value = headers.get("retry-after")
    if value and value.strip().isdigit():
        return float(value)
    reset = headers.get("x-ratelimit-reset")
    if reset and reset.isdigit() and headers.get("x-ratelimit-remaining") == "0":
        return max(1.0, float(reset) - time.time())
    return None


def next_link(link_header: Optional[str]) -> Optional[str]:
    """Parse an RFC 5988 Link header and return the rel="next" URL."""
    if not link_header:
        return None
    for part in link_header.split(","):
        seg = part.split(";")
        if len(seg) >= 2 and any(s.strip() == 'rel="next"' for s in seg[1:]):
            return seg[0].strip().strip("<>")
    return None
