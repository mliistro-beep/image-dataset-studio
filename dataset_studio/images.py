# Image Dataset Studio — Copyright (C) 2026 Mauro Liistro
# SPDX-License-Identifier: AGPL-3.0-only
"""Utilità per le immagini condivise da motori, worker e interfaccia."""
from PIL import Image


def flatten_to_rgb(img: Image.Image) -> Image.Image:
    """Converte in RGB componendo l'eventuale trasparenza su sfondo bianco.
    convert("RGB") scarterebbe solo l'alfa, lasciando nere (o casuali) le zone trasparenti."""
    if img.mode == "P" and "transparency" in img.info:
        img = img.convert("RGBA")
    if img.mode in ("RGBA", "LA", "PA"):
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.getchannel("A"))
        return background
    return img.convert("RGB")
