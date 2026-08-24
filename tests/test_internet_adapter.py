from __future__ import annotations

import hashlib
from io import BytesIO

import pytest

from fermion.adapters.internet import InternetAdapter
from fermion.software.application import Action


class _Headers(dict):
    def get_content_type(self):
        return self.get("content-type", "text/html")


class _Response:
    status = 200
    headers = _Headers({"content-type": "text/html"})

    def __init__(self, data: bytes):
        self.data = BytesIO(data)

    def read(self, size=-1):
        return self.data.read(size)

    def getcode(self):
        return 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_fetch_and_download_are_bounded_and_audited(tmp_path, monkeypatch):
    monkeypatch.setattr("fermion.adapters.internet.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    monkeypatch.setattr("fermion.adapters.internet.urlopen", lambda *_args, **_kwargs: _Response(b"example"))
    adapter = InternetAdapter(tmp_path / "downloads")
    fetched = adapter.execute(Action("fetch_url", {"url": "https://example.com/a#fragment"}))
    assert fetched.success and fetched.details["text"] == "example" and fetched.details["untrusted_content"]
    expected = hashlib.sha256(b"example").hexdigest()
    downloaded = adapter.execute(Action("download_url", {"url": "https://example.com/a", "filename": "sample.bin",
                                                       "expected_sha256": expected}))
    assert downloaded.success and downloaded.details["sha256_verified"] and not downloaded.details["executed"]
    assert (tmp_path / "downloads" / "sample.bin").read_bytes() == b"example"


def test_download_rejects_a_digest_mismatch_without_writing_a_file(tmp_path, monkeypatch):
    monkeypatch.setattr("fermion.adapters.internet.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    monkeypatch.setattr("fermion.adapters.internet.urlopen", lambda *_args, **_kwargs: _Response(b"example"))
    adapter = InternetAdapter(tmp_path / "downloads")
    result = adapter.execute(Action("download_url", {"url": "https://example.com/a", "filename": "sample.bin",
                                                       "expected_sha256": "0" * 64}))
    assert not result.success and "SHA-256" in (result.error or "")
    assert not (tmp_path / "downloads" / "sample.bin").exists()


def test_private_url_is_rejected(tmp_path):
    adapter = InternetAdapter(tmp_path / "downloads")
    result = adapter.execute(Action("fetch_url", {"url": "http://127.0.0.1:8765"}))
    assert not result.success and "loopback" in (result.error or "")


def test_search_unwraps_duckduckgo_result_links(tmp_path, monkeypatch):
    monkeypatch.setattr("fermion.adapters.internet.socket.getaddrinfo", lambda *_: [(None, None, None, None, ("8.8.8.8", 0))])
    html = b'<a href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fdocs">Example docs</a>'
    monkeypatch.setattr("fermion.adapters.internet.urlopen", lambda *_args, **_kwargs: _Response(html))
    result = InternetAdapter(tmp_path / "downloads").execute(Action("search_web", {"query": "example"}))
    assert result.success and result.details["results"] == [{"title": "Example docs", "url": "https://example.com/docs"}]
