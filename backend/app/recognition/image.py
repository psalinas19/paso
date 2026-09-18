"""Image preparation before upload.

Feeds the latency and cost budget (D4, D5): what gets sent is what gets paid
for and waited on, so the size is recorded on every call.
"""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from app.llm.base import PreparedImage

#: Photographs compress far better as JPEG than PNG, and handwriting survives
#: q=90 without visible artefacts. Canvas exports (phase 2) arrive as PNG and
#: stay PNG, which is crisper for thin strokes on white.
JPEG_QUALITY = 90
PHOTO_SUFFIXES = {".jpg", ".jpeg", ".heic", ".heif"}


class ImageTooLargeError(ValueError):
    pass


def prepare_image(path: Path, max_edge: int) -> PreparedImage:
    """Open, auto-orient, downscale and encode an image for the model."""
    if not path.is_file():
        raise FileNotFoundError(f"No existe la imagen: {path}")

    with Image.open(path) as opened:
        # Phones write orientation into EXIF rather than rotating the pixels.
        # Skipping this sends sideways handwriting to the model.
        image = ImageOps.exif_transpose(opened)
        image = image.convert("RGB")

        if max(image.size) > max_edge:
            image.thumbnail((max_edge, max_edge), Image.LANCZOS)

        as_photo = path.suffix.lower() in PHOTO_SUFFIXES
        buffer = io.BytesIO()
        if as_photo:
            image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True)
            media_type = "image/jpeg"
        else:
            image.save(buffer, format="PNG", optimize=True)
            media_type = "image/png"

        return PreparedImage(
            data=buffer.getvalue(),
            media_type=media_type,
            width=image.width,
            height=image.height,
            source_path=str(path),
        )
