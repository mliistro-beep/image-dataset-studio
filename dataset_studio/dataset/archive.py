# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Estrazione degli archivi sorgente e creazione dell'archivio compresso finale."""
import os
import posixpath
import shutil
import tarfile
import zipfile
from typing import IO, Any, Callable, Dict, List, Literal, Optional

from ..config import IMAGE_EXTENSIONS
from ..i18n import tr


# Limite dei nomi di file su Linux (255 byte), con margine per il suffisso "_N", l'estensione e ".txt"
STEM_MAX_BYTES = 255 - 32


def archive_filter() -> str:
    return tr("archive.filter")


def clean_dir(path: str):
    """Svuota e ricrea una cartella."""
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
        except Exception as e:
            print(f"⚠️ temp cleanup error: {e}")
    os.makedirs(path, exist_ok=True)


def _fit_stem(stem: str) -> str:
    """Tiene la fine del nome (cartella più vicina e file) entro STEM_MAX_BYTES byte UTF-8, senza punto iniziale."""
    data = stem.encode("utf-8")
    if len(data) > STEM_MAX_BYTES:
        stem = data[-STEM_MAX_BYTES:].decode("utf-8", errors="ignore")   # un carattere tagliato a metà si scarta
    return stem.lstrip(".") or "image"


def flat_names(paths: List[str]) -> Dict[str, str]:
    """Nome senza cartelle per ogni percorso dell'archivio, con il nome senza estensione sempre diverso.

    Il confronto è sul nome senza estensione perché il .txt lo condivide: a.png e a.jpg avrebbero lo stesso
    a.txt. Se due immagini lo condividono tutte prendono la cartella come prefisso (setA/001.png ->
    setA_001.png): con il solo nome base un'immagine sovrascriveva l'altra, e un prefisso solo sui duplicati
    separerebbe le immagini della stessa cartella nella numerazione. Componenti "." e ".." vengono scartate,
    e i nomi troppo lunghi per il filesystem vengono accorciati dall'inizio."""
    stems = [os.path.splitext(posixpath.basename(p))[0] for p in paths]
    if len(set(stems)) == len(paths) and all(len(s.encode("utf-8")) <= STEM_MAX_BYTES for s in stems):
        return {p: posixpath.basename(p) for p in paths}
    result: Dict[str, str] = {}
    taken = set()
    for path in sorted(paths):
        parts = [part for part in posixpath.normpath(path).split("/") if part not in ("", ".", "..")]
        stem, ext = os.path.splitext("_".join(parts))
        stem = _fit_stem(stem)
        candidate, n = stem, 2
        while candidate in taken:
            candidate = f"{stem}_{n}"
            n += 1
        result[path] = candidate + ext
        taken.add(candidate)
    return result


def _copy_member(source: Optional[IO[bytes]], dest_path: str) -> bool:
    if source is None:   # tarfile.extractfile: membro non regolare
        return False
    with source, open(dest_path, "wb") as out:
        shutil.copyfileobj(source, out)
    return True


def _extract_members(members: Dict[str, Any], open_member: Callable[[Any], Optional[IO[bytes]]],
                     dest_dir: str) -> List[str]:
    """members: {percorso nell'archivio: membro}. Il .txt di un'immagine è quello nella sua stessa cartella."""
    images = [p for p in members if os.path.splitext(p)[1].lower() in IMAGE_EXTENSIONS]
    names = flat_names(images)
    extracted = []
    for path in sorted(images):
        name = names[path]
        if not _copy_member(open_member(members[path]), os.path.join(dest_dir, name)):
            continue
        extracted.append(name)
        txt_path = os.path.splitext(path)[0] + ".txt"
        if txt_path in members:
            _copy_member(open_member(members[txt_path]), os.path.join(dest_dir, os.path.splitext(name)[0] + ".txt"))
    return sorted(extracted)


def extract_archive(file_path: str, dest_dir: str) -> List[str]:
    """Estrae immagini e relativi .txt (appiattendo le sottocartelle). Ritorna i nomi delle immagini."""
    clean_dir(dest_dir)

    if zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, 'r') as zf:
            zip_members = {m.filename: m for m in zf.infolist() if not m.is_dir()}
            return _extract_members(zip_members, zf.open, dest_dir)
    if tarfile.is_tarfile(file_path):
        with tarfile.open(file_path, 'r:*') as tf:
            tar_members = {m.name: m for m in tf.getmembers() if m.isfile()}
            return _extract_members(tar_members, tf.extractfile, dest_dir)
    raise ValueError(tr("archive.unknown_format"))


def archive_stem(file_path: str) -> str:
    name = os.path.basename(file_path)
    for ext in (".tar.gz", ".tar.bz2", ".tar.xz", ".tgz", ".tbz2", ".txz", ".tar", ".zip"):
        if name.lower().endswith(ext):
            return name[:-len(ext)]
    return os.path.splitext(name)[0]


def create_archive(folder: str, out_dir: str, archive_ext: str = ".zip") -> str:
    """Comprime `folder` in `out_dir`. Ritorna il path dell'archivio creato."""
    folder_name = os.path.basename(folder.rstrip(os.sep))
    archive_path = os.path.join(out_dir, f"{folder_name}{archive_ext}")
    if archive_ext == ".zip":
        write_zip(folder, archive_path)
    else:
        mode: Literal["w:gz", "w:bz2"] = "w:gz" if archive_ext == ".tar.gz" else "w:bz2"
        with tarfile.open(archive_path, mode) as tf:
            tf.add(folder, arcname=folder_name)
    return archive_path


def write_zip(folder: str, archive_path: str):
    """Comprime il contenuto di `folder` (percorsi relativi, senza cartella radice) in uno ZIP."""
    with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root_dir, _, files in os.walk(folder):
            for file in files:
                full_p = os.path.join(root_dir, file)
                zf.write(full_p, os.path.relpath(full_p, folder))
