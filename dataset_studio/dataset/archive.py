# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Estrazione degli archivi sorgente e creazione dell'archivio compresso finale."""
import os
import shutil
import tarfile
import zipfile
from typing import List

from ..config import IMAGE_EXTENSIONS
from ..i18n import tr


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


def extract_archive(file_path: str, dest_dir: str) -> List[str]:
    """Estrae immagini e relativi .txt (appiattendo le sottocartelle). Ritorna i nomi delle immagini."""
    clean_dir(dest_dir)
    extracted = []

    if zipfile.is_zipfile(file_path):
        with zipfile.ZipFile(file_path, 'r') as zf:
            members = [m for m in zf.infolist() if not m.is_dir()]
            member_dict = {os.path.basename(m.filename): m for m in members}
            for filename, member in member_dict.items():
                if os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS:
                    with zf.open(member) as src_f, open(os.path.join(dest_dir, filename), "wb") as dst_f:
                        shutil.copyfileobj(src_f, dst_f)
                    extracted.append(filename)
                    txt_filename = os.path.splitext(filename)[0] + ".txt"
                    if txt_filename in member_dict:
                        with zf.open(member_dict[txt_filename]) as src_f, open(os.path.join(dest_dir, txt_filename), "wb") as dst_f:
                            shutil.copyfileobj(src_f, dst_f)

    elif tarfile.is_tarfile(file_path):
        with tarfile.open(file_path, 'r:*') as tf:
            members = [m for m in tf.getmembers() if m.isfile()]
            member_dict = {os.path.basename(m.name): m for m in members}
            for filename, member in member_dict.items():
                if os.path.splitext(filename)[1].lower() in IMAGE_EXTENSIONS:
                    source_file = tf.extractfile(member)
                    if source_file:
                        with open(os.path.join(dest_dir, filename), "wb") as target_file:
                            shutil.copyfileobj(source_file, target_file)
                        extracted.append(filename)
                    txt_filename = os.path.splitext(filename)[0] + ".txt"
                    if txt_filename in member_dict:
                        txt_source = tf.extractfile(member_dict[txt_filename])
                        if txt_source:
                            with open(os.path.join(dest_dir, txt_filename), "wb") as txt_file:
                                shutil.copyfileobj(txt_source, txt_file)
    else:
        raise ValueError(tr("archive.unknown_format"))

    return sorted(extracted)


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
        with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root_dir, _, files in os.walk(folder):
                for file in files:
                    full_p = os.path.join(root_dir, file)
                    zf.write(full_p, os.path.relpath(full_p, folder))
    else:
        mode = "w:gz" if archive_ext == ".tar.gz" else "w:bz2"
        with tarfile.open(archive_path, mode) as tf:
            tf.add(folder, arcname=folder_name)
    return archive_path
