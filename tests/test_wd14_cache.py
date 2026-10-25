# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Verifica dei modelli WD14 già in cache (file troncati prima del controllo su Content-Length)."""
import hashlib
import io

import pytest

from dataset_studio.engines import wd14

REPO = "Owner/model"
ONNX_DATA = b"onnx" * 5000
CSV_DATA = b"tag_id,name,category,count\n1,1girl,0,100\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}


@pytest.fixture
def hub(tmp_path, monkeypatch):
    """HuggingFace finto: HEAD con x-linked-etag come quello vero, GET con il contenuto."""
    state = {
        "files": {"model.onnx": ONNX_DATA, "selected_tags.csv": CSV_DATA},
        # Come HF: sha256 per i file LFS, sha1 del blob git per i file normali
        "etags": {"model.onnx": f'"{sha256(ONNX_DATA)}"', "selected_tags.csv": f'"{git_sha1(CSV_DATA)}"'},
        "heads": [], "gets": [], "offline": False,
    }

    def head_headers(url):
        state["heads"].append(url)
        if state["offline"]:
            raise OSError("network unreachable")
        return {"X-Linked-Etag": state["etags"][url.rsplit("/", 1)[1]]}

    def urlopen(req, **kwargs):
        name = req.full_url.rsplit("/", 1)[1]
        state["gets"].append(name)
        return FakeResponse(state["files"][name])

    monkeypatch.setattr(wd14, "CACHE_BASE_DIR", str(tmp_path))
    monkeypatch.setattr(wd14, "_head_headers", head_headers)
    monkeypatch.setattr(wd14.urllib.request, "urlopen", urlopen)
    return state


def ensure(log=None, should_stop=lambda: False):
    log = [] if log is None else log
    return wd14.ensure_model_files(REPO, lambda *a: None, log.append, should_stop)


def write_cache(onnx: bytes = ONNX_DATA, csv_data: bytes = CSV_DATA):
    onnx_path, csv_path = wd14.model_paths(REPO)
    with open(onnx_path, "wb") as f:
        f.write(onnx)
    with open(csv_path, "wb") as f:
        f.write(csv_data)
    return onnx_path, csv_path


def read(path) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def test_normalize_etag_strips_quotes_and_weak_prefix():
    assert wd14.normalize_etag('"abc"') == "abc"
    assert wd14.normalize_etag('W/"abc"') == "abc"
    assert wd14.normalize_etag(None) is None


def test_file_matches_digest_sha256_and_git_sha1(tmp_path):
    path = tmp_path / "f"
    path.write_bytes(CSV_DATA)

    assert wd14.file_matches_digest(str(path), sha256(CSV_DATA), lambda: False)
    assert wd14.file_matches_digest(str(path), git_sha1(CSV_DATA), lambda: False)
    assert not wd14.file_matches_digest(str(path), sha256(b"other"), lambda: False)


def test_fresh_download_is_verified_and_marked(hub):
    onnx_path, csv_path = ensure()

    assert read(onnx_path) == ONNX_DATA and read(csv_path) == CSV_DATA
    assert wd14.is_marked_verified(onnx_path) and wd14.is_marked_verified(csv_path)


def test_truncated_cached_model_is_downloaded_again(hub):
    onnx_path, _ = write_cache(onnx=ONNX_DATA[:1000])

    ensure()

    assert hub["gets"] == ["model.onnx"]
    assert read(onnx_path) == ONNX_DATA
    assert wd14.is_marked_verified(onnx_path)


def test_valid_cached_files_are_marked_without_download(hub):
    onnx_path, csv_path = write_cache()

    ensure()

    assert hub["gets"] == []
    assert wd14.is_marked_verified(onnx_path) and wd14.is_marked_verified(csv_path)


def test_marked_files_need_no_network(hub):
    write_cache()
    ensure()
    hub["heads"].clear()
    hub["offline"] = True

    ensure()

    assert hub["heads"] == [] and hub["gets"] == []


def test_marker_is_ignored_when_file_size_changes(hub):
    onnx_path, _ = write_cache()
    ensure()
    with open(onnx_path, "wb") as f:
        f.write(ONNX_DATA[:10])

    assert not wd14.is_marked_verified(onnx_path)
    ensure()
    assert read(onnx_path) == ONNX_DATA


def test_offline_uses_cached_files_with_a_warning(hub):
    onnx_path, _ = write_cache(onnx=ONNX_DATA[:1000])
    hub["offline"] = True
    log = []

    assert ensure(log) is not None

    # Senza rete non si può distinguere: si usa la cache, si avvisa e si riprova al prossimo avvio
    assert hub["gets"] == []
    assert read(onnx_path) == ONNX_DATA[:1000]
    assert not wd14.is_marked_verified(onnx_path)
    assert any("model.onnx" in line for line in log)


def test_unknown_etag_format_keeps_cache_unmarked(hub):
    onnx_path, _ = write_cache()
    hub["etags"]["model.onnx"] = '"not-a-digest"'

    ensure()

    assert hub["gets"] == []
    assert not wd14.is_marked_verified(onnx_path)


def test_corrupt_download_is_removed_and_reported(hub):
    hub["files"]["model.onnx"] = b"corrupt" * 100
    onnx_path, _ = wd14.model_paths(REPO)

    with pytest.raises(OSError):
        ensure()

    assert not wd14.os.path.exists(onnx_path)
    assert not wd14.is_marked_verified(onnx_path)


def test_stop_during_verification_is_interrupted(hub):
    write_cache()

    with pytest.raises(InterruptedError):
        ensure(should_stop=lambda: True)
