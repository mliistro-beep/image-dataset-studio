# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Avanzamento del download VLM con i contatori di huggingface_hub (byte di hf_xet e numero di file)."""
import re
import sys
import types
from typing import Any

import pytest

from dataset_studio.engines import vlm

MB = 1048576


def _fake_hub(monkeypatch, simulate):
    """huggingface_hub finto: snapshot_download esegue `simulate(tqdm_class)` al posto della rete."""
    fake: Any = types.ModuleType("huggingface_hub")
    fake.snapshot_download = lambda repo_id, revision=None, tqdm_class=None: simulate(tqdm_class)
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake)


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
