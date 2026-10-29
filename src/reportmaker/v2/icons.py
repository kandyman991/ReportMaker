"""Small stroke icon set for the V2 chrome, drawn from SVG path data.

Icons are rendered with QtSvg into device-pixel-ratio-aware pixmaps, tinted by
state (normal / checked / disabled), so the same artwork follows the theme and
stays sharp on high-DPI Windows screens. No image files are shipped.
"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS: dict[str, str] = {
    "layers": '<path d="M12 3 3 8l9 5 9-5-9-5Z"/><path d="m3 12.5 9 5 9-5"/><path d="m3 17 9 5 9-5"/>',
    "file": '<path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5M10 13h6M10 17h6"/>',
    "image": '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="1.6"/><path d="m21 16-5-5-8 9"/>',
    "chat": '<path d="M4 5h16v11H10l-5 4v-4H4z"/>',
    "eye": '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
}


def _pixmap(name: str, color: str, size: int, dpr: float) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
           f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixels = max(1, round(size * dpr))
    pixmap = QPixmap(pixels, pixels)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    return pixmap


def icon(name: str, *, normal: str, checked: str, disabled: str, size: int = 22) -> QIcon:
    """A QIcon with a pixmap per state. Raises KeyError for an unknown name."""
    if name not in PATHS:
        raise KeyError(name)
    screen = QGuiApplication.primaryScreen()
    dpr = max(1.0, screen.devicePixelRatio()) if screen is not None else 1.0
    result = QIcon()
    result.addPixmap(_pixmap(name, normal, size, dpr), QIcon.Mode.Normal, QIcon.State.Off)
    result.addPixmap(_pixmap(name, checked, size, dpr), QIcon.Mode.Normal, QIcon.State.On)
    result.addPixmap(_pixmap(name, checked, size, dpr), QIcon.Mode.Active, QIcon.State.On)
    result.addPixmap(_pixmap(name, disabled, size, dpr), QIcon.Mode.Disabled, QIcon.State.Off)
    return result
