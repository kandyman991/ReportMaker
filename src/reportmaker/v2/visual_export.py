"""V2-only Qt photo visual renderer; never mutates project-owned image bytes.

Export always receives detached PNG working bytes and the pure export service
retains its fail-closed default when no renderer was deliberately supplied.
"""
from __future__ import annotations

from PySide6.QtCore import QBuffer, QByteArray, QIODevice

from ..model import PhotoVisual
from ..photo_editor import render_photo


def annotated_png(image_bytes: bytes, visual: PhotoVisual) -> bytes:
    """Render the same approved placement layers used by the branch preview."""
    if not isinstance(image_bytes, bytes) or not isinstance(visual, PhotoVisual):
        raise ValueError("Invalid image or photo visual")
    rendered = render_photo(image_bytes, visual, max_edge=1800)
    if rendered.isNull() or rendered.width() < 1 or rendered.height() < 1:
        raise ValueError("Could not render the photo for export")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly):
        raise ValueError("Cannot open image export buffer")
    try:
        if not rendered.save(buffer, "PNG"):
            raise ValueError("Cannot encode photo visual as PNG")
        return bytes(buffer.data())
    finally:
        buffer.close()
