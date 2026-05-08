"""Shared JPEG/PNG upload checks for report images and profile avatars."""

from __future__ import annotations

from typing import Optional


def validate_uploaded_jpeg_png(uploaded_file, *, max_size_mb: int = 5) -> Optional[str]:
    """
    Validate an uploaded image file.

    Returns None if OK, otherwise a short user-facing error message (Macedonian).
    """
    if not uploaded_file:
        return None

    try:
        size = uploaded_file.size
    except (AttributeError, OSError, TypeError):
        return "Невалидна датотека за слика."

    if size > max_size_mb * 1024 * 1024:
        return f"Сликата мора да биде најмногу {max_size_mb} MB."

    raw_ct = (getattr(uploaded_file, "content_type", "") or "").strip().lower()
    content_type = raw_ct.split(";")[0].strip() if raw_ct else ""
    allowed_types = {
        "image/jpeg",
        "image/jpg",
        "image/pjpeg",
        "image/png",
        "image/x-png",
    }

    def _jpeg_magic(data: bytes) -> bool:
        return len(data) >= 3 and data[:3] == b"\xff\xd8\xff"

    def _png_magic(data: bytes) -> bool:
        return len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n"

    try:
        uploaded_file.seek(0)
        header = uploaded_file.read(16)
        uploaded_file.seek(0)
    except (AttributeError, OSError, TypeError, ValueError):
        header = b""

    if content_type and content_type not in allowed_types:
        if not (_jpeg_magic(header) or _png_magic(header)):
            return "Дозволени се само JPG или PNG слики."

    try:
        from PIL import Image

        with Image.open(uploaded_file) as im:
            im.load()
        uploaded_file.seek(0)
    except Exception:
        return "Сликата не може да се обработи. Обидете се со друга JPG или PNG датотека."

    return None
