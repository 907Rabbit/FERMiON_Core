"""Audited, bounded Internet access for the FERMiON control plane.

The adapter makes network access a declared application capability rather than
giving a language model arbitrary shell access.  Retrieved pages are untrusted
data; callers must not treat their contents as instructions.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
import socket
import time
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote_plus, unquote, urlparse, urlunparse
from urllib.request import Request, urlopen

from fermion.software.application import (Action, ActionResult, ApplicationInterface, CapabilityDefinition,
                                          CapabilitySet, Checkpoint, Observation, RollbackResult,
                                          VerificationResult)


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            self._href = dict(attrs).get("href")
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.links.append((" ".join("".join(self._text).split()), self._href))
            self._href = None


class InternetAdapter(ApplicationInterface):
    """Read web pages, search the public web, and download verified files only on approval."""

    _CAPABILITIES = (
        CapabilityDefinition("search_web", False, True, "Search the public web and return result titles and URLs."),
        CapabilityDefinition("fetch_url", False, True, "Fetch bounded public HTTP(S) content as untrusted data."),
        CapabilityDefinition("download_url", True, True,
                             "Download a public URL only when its user-supplied SHA-256 matches."),
    )
    _MAX_TEXT = 2 * 1024 * 1024
    _MAX_DOWNLOAD = 100 * 1024 * 1024
    _MAX_REDIRECTS = 4
    _USER_AGENT = "FERMiON/0.1 (+local audited application interface)"

    def __init__(self, download_root: Path) -> None:
        self.download_root = download_root.resolve()
        self.download_root.mkdir(parents=True, exist_ok=True)
        self._last_state: dict[str, Any] = {"last_url": None, "last_sha256": None, "downloads": []}

    @staticmethod
    def _public_url(value: Any) -> str:
        parsed = urlparse(str(value).strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("URL must be a public HTTP(S) URL without credentials")
        host = parsed.hostname.lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
            raise ValueError("local and .local hosts are not permitted")
        try:
            addresses = {item[4][0] for item in socket.getaddrinfo(host, None)}
        except socket.gaierror as error:
            raise ValueError(f"cannot resolve host: {host}") from error
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if not ip.is_global:
                raise ValueError("private, loopback, and link-local network addresses are not permitted")
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.params, parsed.query, ""))

    def _retrieve(self, value: Any, limit: int) -> tuple[str, bytes, str]:
        url = self._public_url(value)
        for _ in range(self._MAX_REDIRECTS + 1):
            request = Request(url, headers={"User-Agent": self._USER_AGENT, "Accept": "text/html,text/plain,application/json,*/*;q=0.2"})
            with urlopen(request, timeout=20) as response:  # nosec B310: URL is validated above
                status = getattr(response, "status", response.getcode())
                location = response.headers.get("Location")
                if 300 <= status < 400 and location:
                    url = self._public_url(location)
                    continue
                content_type = response.headers.get_content_type() if hasattr(response.headers, "get_content_type") else "application/octet-stream"
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError(f"response exceeds the {limit} byte limit")
                return url, data, content_type
        raise ValueError("too many redirects")

    def observe(self) -> Observation:
        return Observation(time.time(), "internet", dict(self._last_state), {"interface": "bounded-public-http"})

    def capabilities(self) -> CapabilitySet:
        return CapabilitySet("internet", self._CAPABILITIES)

    def _remember(self, url: str, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        self._last_state["last_url"] = url
        self._last_state["last_sha256"] = digest
        return digest

    @staticmethod
    def _expected_sha256(value: Any) -> str:
        expected = str(value).strip().lower()
        if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
            raise ValueError("expected_sha256 must be a 64-character hexadecimal SHA-256 digest")
        return expected

    def execute(self, action: Action) -> ActionResult:
        if self.capabilities().get(action.operation) is None:
            return ActionResult(action.action_id, False, False, error="undeclared capability")
        try:
            if action.operation == "search_web":
                query = str(action.arguments["query"]).strip()
                if not query or len(query) > 300:
                    raise ValueError("query must contain 1..300 characters")
                count = int(action.arguments.get("max_results", 8))
                if count < 1 or count > 20:
                    raise ValueError("max_results must be 1..20")
                url, data, _ = self._retrieve(f"https://lite.duckduckgo.com/lite/?q={quote_plus(query)}", self._MAX_TEXT)
                parser = _LinkParser()
                parser.feed(data.decode("utf-8", errors="replace"))
                results = []
                for title, link in parser.links:
                    if link.startswith("//"):
                        link = "https:" + link
                    if "uddg=" in link:
                        link = unquote(parse_qs(urlparse(link).query).get("uddg", [link])[0])
                    try:
                        checked = self._public_url(link)
                    except ValueError:
                        continue
                    if title and checked not in {item["url"] for item in results}:
                        results.append({"title": title, "url": checked})
                    if len(results) >= count:
                        break
                digest = self._remember(url, data)
                return ActionResult(action.action_id, True, False,
                                    {"query": query, "results": results, "source_url": url, "sha256": digest,
                                     "untrusted_content": True})
            if action.operation == "fetch_url":
                url, data, content_type = self._retrieve(action.arguments["url"], self._MAX_TEXT)
                digest = self._remember(url, data)
                return ActionResult(action.action_id, True, False,
                                    {"url": url, "content_type": content_type, "sha256": digest,
                                     "text": data.decode("utf-8", errors="replace"), "untrusted_content": True})
            expected_sha256 = self._expected_sha256(action.arguments["expected_sha256"])
            url, data, content_type = self._retrieve(action.arguments["url"], self._MAX_DOWNLOAD)
            digest = hashlib.sha256(data).hexdigest()
            if digest != expected_sha256:
                raise ValueError("download SHA-256 does not match the user-approved expected_sha256")
            name = Path(str(action.arguments["filename"])).name
            if not name or name in {".", ".."} or len(name) > 120:
                raise ValueError("filename must be a simple filename of at most 120 characters")
            destination = (self.download_root / name).resolve()
            if not destination.is_relative_to(self.download_root):
                raise ValueError("download destination escapes the downloads directory")
            temporary = destination.with_suffix(destination.suffix + ".partial")
            temporary.write_bytes(data)
            temporary.replace(destination)
            self._remember(url, data)
            self._last_state["downloads"] = [*self._last_state["downloads"], {"path": str(destination), "sha256": digest}]
            return ActionResult(action.action_id, True, True,
                                {"url": url, "path": str(destination), "content_type": content_type, "sha256": digest,
                                 "expected_sha256": expected_sha256, "sha256_verified": True, "bytes": len(data),
                                 "executed": False, "untrusted_content": True})
        except (KeyError, OSError, ValueError) as error:
            return ActionResult(action.action_id, False, False, error=f"{type(error).__name__}: {error}")

    def verify(self, result: ActionResult, expected_effect: dict[str, Any] | None = None) -> VerificationResult:
        observed = self.observe().state
        if not result.success:
            return VerificationResult(False, expected_effect, observed, result.error or "action failed")
        if expected_effect is None:
            return VerificationResult(True, None, observed)
        matches = all(result.details.get(key) == value for key, value in expected_effect.items())
        return VerificationResult(matches, expected_effect, observed, "" if matches else "network result differs from expectation")

    def checkpoint(self) -> Checkpoint:
        state = dict(self._last_state)
        digest = hashlib.sha256(json.dumps(state, sort_keys=True).encode("utf-8")).hexdigest()
        return Checkpoint(uuid.uuid4().hex, state, digest, time.time())

    def rollback(self, checkpoint: Checkpoint) -> RollbackResult:
        expected = hashlib.sha256(json.dumps(checkpoint.logical_state, sort_keys=True).encode("utf-8")).hexdigest()
        if expected != checkpoint.digest:
            return RollbackResult(False, checkpoint.checkpoint_id, self.checkpoint().digest, "checkpoint digest mismatch")
        self._last_state = dict(checkpoint.logical_state)
        return RollbackResult(True, checkpoint.checkpoint_id, checkpoint.digest)
