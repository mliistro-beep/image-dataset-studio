# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Download dei file WD14 con una risposta HTTP finta."""
import io
from typing import List

import pytest

from dataset_studio.engines import wd14


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, fail_after: int = -1):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}
        self.fail_after = fail_after
        self.reads = 0

    def read(self, size=-1):
        if self.reads == self.fail_after:
            raise OSError("connection reset")
        self.reads += 1
        return super().read(size)


def fake_urlopen(response, calls):
    def urlopen(req, **kwargs):
        calls.append(kwargs)
        return response
    return urlopen


def download(dest, should_stop=lambda: False):
    wd14.download_file("http://example.invalid/f", str(dest), "f", lambda *a: None, lambda *a: None, should_stop)


def test_download_writes_file_and_uses_timeout(tmp_path, monkeypatch):
    calls: List[dict] = []
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(FakeResponse(b"x" * 1000), calls))

    download(tmp_path / "model.onnx")

    assert (tmp_path / "model.onnx").read_bytes() == b"x" * 1000
    assert calls[0].get("timeout")
    assert sorted(p.name for p in tmp_path.iterdir()) == ["model.onnx"]


def test_download_error_removes_tmp(tmp_path, monkeypatch):
    data = b"x" * (wd14.DOWNLOAD_CHUNK_SIZE * 3)
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(FakeResponse(data, fail_after=1), []))

    with pytest.raises(OSError):
        download(tmp_path / "model.onnx")

    assert list(tmp_path.iterdir()) == []


def test_download_stop_removes_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(FakeResponse(b"x" * 1000), []))

    with pytest.raises(InterruptedError):
        download(tmp_path / "model.onnx", should_stop=lambda: True)

    assert list(tmp_path.iterdir()) == []


def test_download_truncated_response_is_an_error(tmp_path, monkeypatch):
    response = FakeResponse(b"x" * 1000)
    response.headers = {"Content-Length": "5000"}
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(response, []))

    with pytest.raises(OSError):
        download(tmp_path / "model.onnx")

    assert list(tmp_path.iterdir()) == []


def test_download_rename_failure_removes_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(FakeResponse(b"x" * 1000), []))
    real_replace = wd14.os.replace

    def fail_replace(src, dst):
        raise OSError("cross-device link")
    monkeypatch.setattr(wd14.os, "replace", fail_replace)
    monkeypatch.setattr(wd14.os, "rename", fail_replace)

    with pytest.raises(OSError):
        download(tmp_path / "model.onnx")

    monkeypatch.setattr(wd14.os, "replace", real_replace)
    assert list(tmp_path.iterdir()) == []


def test_stop_is_not_masked_when_tmp_cleanup_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(wd14.urllib.request, "urlopen", fake_urlopen(FakeResponse(b"x" * 1000), []))

    def fail_remove(path):
        raise PermissionError("locked")
    monkeypatch.setattr(wd14.os, "remove", fail_remove)

    # Lo Stop dell'utente deve restare InterruptedError, non diventare un errore da mostrare
    with pytest.raises(InterruptedError):
        download(tmp_path / "model.onnx", should_stop=lambda: True)
