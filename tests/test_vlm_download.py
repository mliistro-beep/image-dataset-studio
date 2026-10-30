# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Download dei VLM: avanzamento con i contatori di huggingface_hub (byte di hf_xet e numero di file),
file esclusi, download lasciati in background dallo Stop."""
import os
import re
import sys
import threading
import time
import types
from typing import Any

import pytest

from dataset_studio.engines import vlm

MB = 1048576


def _fake_hub(monkeypatch, simulate, hub_cache="/nonexistent/hf-hub-cache"):
    """huggingface_hub finto: snapshot_download esegue `simulate(tqdm_class)` al posto della rete.
    Ritorna la lista degli argomenti ricevuti."""
    received = []

    def snapshot_download(repo_id, revision=None, tqdm_class=None, **kwargs):
        received.append(kwargs)
        simulate(tqdm_class)

    fake: Any = types.ModuleType("huggingface_hub")
    fake.snapshot_download = snapshot_download
    fake.constants = types.SimpleNamespace(HF_HUB_CACHE=hub_cache)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)
    return received


def _hub_2_xet(tqdm_class):
    """Come huggingface_hub 2.x: due contatori di byte che partono da total=0 e crescono, più quello dei file.
    Prima arrivano i file piccoli (pochi KB), poi i pesi."""
    transfer = tqdm_class(desc="Downloading bytes", total=0, unit="B", file=None)
    reconstruct = tqdm_class(desc="Reconstructing (incomplete total...)", total=0, unit="B", file=None)
    files = tqdm_class(desc="Fetching 3 files", total=3, file=None)
    for size in (2891, 2647):
        for bar in (reconstruct, transfer):
            bar.total += size
            bar.update(size)
        files.update(1)
    for bar in (reconstruct, transfer):
        bar.total += 400 * MB
    for step in range(40):
        transfer.update(10 * MB)
        if step % 10 == 9:
            reconstruct.update(100 * MB)
    files.update(1)
    for bar in (transfer, reconstruct, files):
        bar.close()


def _hub_2_xet_small_files_cached(tqdm_class):
    """File piccoli già in cache: il contatore dei file avanza prima che arrivino i byte dei pesi."""
    transfer = tqdm_class(desc="Downloading bytes", total=0, unit="B", file=None)
    files = tqdm_class(desc="Fetching 33 files", total=33, file=None)
    files.update(5)
    transfer.total += 400 * MB
    for _ in range(4):
        transfer.update(100 * MB)
    files.update(28)
    for bar in (transfer, files):
        bar.close()


def _hub_files_only(tqdm_class):
    """Come le versioni vecchie: tqdm_class serve solo per il contatore dei file."""
    files = tqdm_class(desc="Fetching 4 files", total=4, file=None)
    for _ in range(4):
        files.update(1)
    files.close()


def _run(monkeypatch, simulate):
    _fake_hub(monkeypatch, simulate)
    calls = []
    vlm.download_snapshot("org/model", "abc123", lambda msg: None, lambda msg, pct: calls.append((msg, pct)))
    return calls


def _done_mb(msg):
    match = re.search(r": (\d+)/(\d+) MB", msg)
    assert match, msg
    return int(match.group(1))


def test_xet_download_reports_only_meaningful_byte_progress(monkeypatch):
    calls = _run(monkeypatch, _hub_2_xet)

    assert calls
    messages = [msg for msg, _ in calls]
    assert all(" MB " in msg for msg in messages), messages
    assert not any("0/0 MB" in msg for msg in messages)


def test_xet_download_progress_never_goes_backwards(monkeypatch):
    calls = _run(monkeypatch, _hub_2_xet)

    done = [_done_mb(msg) for msg, _ in calls]
    percents = [pct for _, pct in calls]
    assert done == sorted(done)
    assert percents == sorted(percents)
    assert percents[-1] == pytest.approx(100.0)


def test_file_counter_is_ignored_once_hub_has_a_byte_counter(monkeypatch):
    calls = _run(monkeypatch, _hub_2_xet_small_files_cached)

    assert [pct for _, pct in calls] == [25.0, 50.0, 75.0, 100.0]


def test_file_counter_is_used_when_hub_reports_no_bytes(monkeypatch):
    calls = _run(monkeypatch, _hub_files_only)

    assert [pct for _, pct in calls] == [25.0, 50.0, 75.0, 100.0]
    assert all(" 4 " in msg or "/4 " in msg for msg, _ in calls)


def test_gguf_weights_are_not_downloaded(monkeypatch):
    # moondream2 contiene anche 3,7 GB di GGUF per llama.cpp, che transformers non usa
    received = _fake_hub(monkeypatch, lambda tqdm_class: None)

    vlm.download_snapshot("org/model", "abc123", lambda msg: None, lambda msg, pct: None)

    assert "*.gguf" in received[0]["ignore_patterns"]


def test_stopped_download_is_tracked_until_it_ends(monkeypatch):
    release = threading.Event()
    _fake_hub(monkeypatch, lambda tqdm_class: release.wait(5))

    with pytest.raises(InterruptedError):
        vlm.download_snapshot("org/model", "abc123", lambda msg: None, lambda msg, pct: None,
                              should_stop=lambda: True)
    in_background = vlm.downloads_in_background()
    release.set()
    deadline = time.monotonic() + 5
    while vlm.downloads_in_background() and time.monotonic() < deadline:
        time.sleep(0.01)

    assert in_background
    assert not vlm.downloads_in_background()


def test_finished_download_is_not_in_background(monkeypatch):
    _fake_hub(monkeypatch, lambda tqdm_class: None)

    vlm.download_snapshot("org/model", "abc123", lambda msg: None, lambda msg, pct: None)

    assert not vlm.downloads_in_background()


def _partial(folder, name, size, age_seconds):
    """File nella cartella blobs con la data di modifica di `age_seconds` fa."""
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"x" * size)
    mtime = time.time() - age_seconds
    os.utime(path, (mtime, mtime))
    return path


def test_old_partial_downloads_are_removed(tmp_path):
    # huggingface_hub 2.x scarica in "<hash>.<uuid>.incomplete", un nome diverso a ogni tentativo:
    # un parziale lasciato da un processo terminato (Stop + chiusura, os._exit) non viene più ripreso
    orphan = _partial(tmp_path, "aaa.1234abcd.incomplete", 300, age_seconds=3600)
    active = _partial(tmp_path, "aaa.5678ef01.incomplete", 200, age_seconds=5)
    weights = _partial(tmp_path, "bbb", 100, age_seconds=3600)

    removed = vlm.remove_orphan_partials(str(tmp_path))

    assert removed == (1, 300)
    assert not orphan.exists()
    assert active.exists()
    assert weights.exists()


def test_orphan_cleanup_ignores_a_missing_cache(tmp_path):
    assert vlm.remove_orphan_partials(str(tmp_path / "missing")) == (0, 0)


def test_download_removes_the_repo_orphans_before_fetching(monkeypatch, tmp_path):
    blobs = tmp_path / "models--org--model" / "blobs"
    orphan = _partial(blobs, "aaa.1234abcd.incomplete", 3 * MB, age_seconds=3600)
    other_repo = _partial(tmp_path / "models--org--other" / "blobs", "ccc.9999aaaa.incomplete", 10, 3600)
    seen_at_fetch = []
    _fake_hub(monkeypatch, lambda tqdm_class: seen_at_fetch.append(orphan.exists()), hub_cache=str(tmp_path))
    logs: list[str] = []

    vlm.download_snapshot("org/model", "abc123", logs.append, lambda msg, pct: None)

    assert seen_at_fetch == [False]
    assert other_repo.exists()
    assert any("3 MB" in msg for msg in logs), logs
