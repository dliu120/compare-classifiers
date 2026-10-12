"""Canonical images: RGB, longest side at most 1440 px, metadata stripped, deterministic bytes."""

from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

MAX_SIDE = 1440
PNG_BYTE_LIMIT = 3 * 1024 * 1024
JPEG_QUALITY = 90
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"
IMAGES_DIR = "images"
WHITE = (255, 255, 255)


def canonicalize(source: Path | bytes) -> tuple[bytes, str]:
    """Return (encoded bytes, sha256 hex): PNG, or JPEG quality 90 when the PNG exceeds 3 MiB.

    Deterministic: the same input bytes give the same output bytes. The EXIF orientation is
    applied, then every piece of metadata (EXIF, ICC profile, text chunks) is dropped.
    """
    with Image.open(io.BytesIO(source) if isinstance(source, bytes) else source) as opened:
        image = _flatten(ImageOps.exif_transpose(opened))
    image = _fit(image)
    data = encode_png(image)
    if len(data) > PNG_BYTE_LIMIT:
        data = _encode(image, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return data, hashlib.sha256(data).hexdigest()


def encode_png(image: Image.Image) -> bytes:
    return _encode(image, "PNG", optimize=True)


def mime_type(data: bytes) -> str:
    if data.startswith(PNG_SIGNATURE):
        return "image/png"
    if data.startswith(JPEG_SIGNATURE):
        return "image/jpeg"
    raise ValueError("not PNG or JPEG bytes")


def data_url(png_bytes: bytes) -> str:
    encoded = base64.b64encode(png_bytes).decode("ascii")
    return f"data:{mime_type(png_bytes)};base64,{encoded}"


def write_image(family_dir: Path, data: bytes, sha256: str) -> str:
    """Store canonical bytes at ``<family_dir>/images/<sha256>.<ext>``; returns the relative
    path."""
    suffix = ".png" if mime_type(data) == "image/png" else ".jpg"
    relative = f"{IMAGES_DIR}/{sha256}{suffix}"
    path = family_dir / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return relative


def _flatten(image: Image.Image) -> Image.Image:
    """RGB pixels only: alpha composited on white, and a fresh image so no metadata survives."""
    has_alpha = image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info)
    if has_alpha:
        rgba = image.convert("RGBA")
        flat = Image.new("RGB", rgba.size, WHITE)
        flat.paste(rgba, mask=rgba.getchannel("A"))
        return flat
    rgb = image.convert("RGB")
    return Image.frombytes("RGB", rgb.size, rgb.tobytes())


def _fit(image: Image.Image) -> Image.Image:
    longest = max(image.size)
    if longest <= MAX_SIDE:
        return image
    scale = MAX_SIDE / longest
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def _encode(image: Image.Image, fmt: str, **options: Any) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format=fmt, **options)
    return buffer.getvalue()
