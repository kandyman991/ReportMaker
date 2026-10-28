"""Project-owned thumbnail drag source, external file import target and report drop zones.

Internal asset-ID drags are separate from inbound local-file URLs. Never accept
remote URLs, arbitrary HTML or clipboard text as image import instructions.
"""
from __future__ import annotations

from collections import OrderedDict
import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QMimeData, QSize, Qt, QTimer
from PySide6.QtGui import QDrag, QIcon, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem

from .media_import import (INPUT_SUFFIXES, MAX_IMPORT_BATCH, MAX_SOURCE_BYTES,
                           PictureImportError)

PHOTO_MIME = "application/x-reportmaker-project-photo-asset"
MAX_THUMBNAILS = 80
MAX_VISIBLE_LOAD = 24
MAX_CLIPBOARD_PIXELS = 16_000_000  # bound native clipboard memory before encoding


def scaled_project_image(image_bytes: bytes, width: int, height: int) -> QImage:
    """Bound the displayed decode using the image reader's scaled-size request."""
    if not image_bytes or width <= 0 or height <= 0:
        return QImage()
    buffer = QBuffer()
    buffer.setData(QByteArray(image_bytes))
    if not buffer.open(QIODevice.OpenModeFlag.ReadOnly):
        return QImage()
    reader = QImageReader(buffer)
    reader.setAutoTransform(True)
    original = reader.size()
    if not original.isValid() or original.width() <= 0 or original.height() <= 0:
        return QImage()
    reader.setScaledSize(original.scaled(QSize(min(width, 900), min(height, 900)),
                                         Qt.AspectRatioMode.KeepAspectRatio))
    return reader.read()


def local_picture_paths(mime: QMimeData | None) -> tuple[list[str], list[str]]:
    """Validate OS file-URL payloads; never interpret strings as file paths.

    Return supported local paths and per-file errors separately so mixed drops
    can import the good files while reporting the rejected ones. The converter
    performs the final byte, decoded-format and resource-budget checks.
    """
    if mime is None or mime.hasFormat(PHOTO_MIME) or mime.hasHtml() or not mime.hasUrls():
        return [], []
    urls = mime.urls()
    if len(urls) > MAX_IMPORT_BATCH:
        return [], [f"Import at most {MAX_IMPORT_BATCH} image files at once"]
    paths, errors, seen = [], [], set()
    for url in urls:
        if not url.isLocalFile():
            errors.append("Remote URLs and non-file drops are not supported")
            continue
        value = url.toLocalFile()
        # Network shares and UNC paths are not independent local originals.
        if not value or value.startswith(("\\\\", "//")):
            errors.append("Network paths are not supported")
            continue
        path = Path(value)
        label = path.name[:100] or "Unnamed file"
        if not path.is_absolute() or not path.is_file():
            errors.append(f"{label}: not an existing local file")
            continue
        if any(part.is_symlink() or getattr(part, "is_junction", lambda: False)()
               for part in (path, *path.parents)):
            errors.append(f"{label}: links and junctions in image paths are not supported")
            continue
        if path.suffix.lower() not in INPUT_SUFFIXES:
            errors.append(f"{label}: unsupported image extension")
            continue
        normalized = os.path.normcase(os.path.abspath(value))
        if normalized not in seen:
            paths.append(str(path))
            seen.add(normalized)
    return paths, errors


def clipboard_image_png(image: QImage) -> bytes:
    """Encode native clipboard pixels locally with a pre-allocation pixel bound.

    Clipboard HTML and URLs are never fed to this function; the caller supplies
    only a native QImage, keeping parsing and transport separate from pixels.
    """
    if (not isinstance(image, QImage) or image.isNull()
            or image.width() <= 0 or image.height() <= 0
            or image.width() * image.height() > MAX_CLIPBOARD_PIXELS
            or image.sizeInBytes() > 4 * MAX_SOURCE_BYTES):
        raise PictureImportError("Clipboard image exceeds the 16 MP safety limit")
    buffer = QBuffer()
    if not buffer.open(QIODevice.OpenModeFlag.WriteOnly) or not image.save(buffer, "PNG"):
        raise PictureImportError("Cannot encode clipboard pixels as PNG")
    data = bytes(buffer.data())
    if not data or len(data) > MAX_SOURCE_BYTES:
        raise PictureImportError("Clipboard image exceeds the 64 MiB import limit")
    return data


class ExternalPictureDropMixin:
    """Strict Explorer inbound drop handlers, never project-photo receivers."""

    on_external_import: Callable[[list[str], list[str]], None] | None = None

    def _set_file_drop_hint(self, active: bool) -> None:
        self.setStyleSheet(
            f"#{self.objectName()} {{ border: 2px dashed #1672c7; "
            "background: #edf6ff; }" if active else "")

    def _can_accept_files(self, event) -> bool:
        paths, _errors = local_picture_paths(event.mimeData())
        # Qt identifies foreign-process Explorer drags with source() == None.
        # Never allow a gallery's own internal PHOTO_MIME drag to reimport.
        return event.source() is None and bool(paths) and callable(self.on_external_import)

    def _accept_file_copy(self, event) -> bool:
        if (not self._can_accept_files(event)
                or not (event.possibleActions() & Qt.DropAction.CopyAction)):
            self._set_file_drop_hint(False)
            event.ignore()
            return False
        # Explorer may propose Move (Shift+drop). Explicitly request Copy
        # rather than accepting a proposed action that could remove originals.
        self._set_file_drop_hint(True)
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        return True

    def dragEnterEvent(self, event):
        self._accept_file_copy(event)

    def dragMoveEvent(self, event):
        self._accept_file_copy(event)

    def dragLeaveEvent(self, event):
        self._set_file_drop_hint(False)
        event.accept()

    def dropEvent(self, event):
        if not self._accept_file_copy(event):
            return
        self._set_file_drop_hint(False)
        paths, errors = local_picture_paths(event.mimeData())
        callback = self.on_external_import
        # Delayed callback avoids opening nested dialogs in drop dispatch.
        QTimer.singleShot(0, lambda: callback(paths, errors))


class PictureGalleryDialog(ExternalPictureDropMixin, QDialog):
    """Gallery chrome is a drop surface as well as its thumbnail viewport."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)


class ProjectPictureList(ExternalPictureDropMixin, QListWidget):
    """Resizable icon grid. Only visible tiles are decoded; icon cache is bounded."""

    def __init__(self, allowed: Callable[[str], bool], assets: Callable[[str], bytes],
                 session_token: str, parent=None):
        super().__init__(parent)
        self.setObjectName("projectPictureLibrary")
        self.allowed = allowed
        self.assets = assets
        self.session_token = session_token
        self._cached: OrderedDict[tuple[str, int], QIcon] = OrderedDict()
        self._items_by_key: dict[str, QListWidgetItem] = {}
        self._thumb_side = 132
        self.setViewMode(QListWidget.ViewMode.IconMode)
        self.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.setMovement(QListWidget.Movement.Static)
        self.setWrapping(True)
        self.setWordWrap(True)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragDrop)
        self.setIconSize(QSize(self._thumb_side, self._thumb_side))
        self.setGridSize(QSize(self._thumb_side + 38, self._thumb_side + 55))
        self.setSpacing(7)
        self.verticalScrollBar().valueChanged.connect(self.schedule_visible)
        self._loading_scheduled = False

    def set_thumbnail_size(self, side: int) -> None:
        self._thumb_side = max(72, min(220, int(side)))
        self._cached.clear()
        self.setIconSize(QSize(self._thumb_side, self._thumb_side))
        self.setGridSize(QSize(self._thumb_side + 38, self._thumb_side + 55))
        for index in range(self.count()):
            self.item(index).setIcon(QIcon())
        self.schedule_visible()

    def populate(self, library: dict[str, str]) -> None:
        current = self.currentItem()
        selected = current.data(Qt.ItemDataRole.UserRole) if current else None
        self.clear()
        self._cached.clear()
        self._items_by_key.clear()
        for key, name in sorted(library.items(), key=lambda item: (item[1].casefold(), item[0])):
            if not self.allowed(key):
                continue
            tile = QListWidgetItem(name)
            tile.setData(Qt.ItemDataRole.UserRole, key)
            tile.setToolTip(name)
            tile.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(tile)
            self._items_by_key[key] = tile
        for i in range(self.count()):
            if self.item(i).data(Qt.ItemDataRole.UserRole) == selected:
                self.setCurrentRow(i)
                break
        else:
            if self.count():
                self.setCurrentRow(0)
        self.schedule_visible()

    def schedule_visible(self, *_args) -> None:
        if self._loading_scheduled:
            return
        self._loading_scheduled = True
        QTimer.singleShot(0, self._load_visible)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.schedule_visible()

    def _load_visible(self):
        self._loading_scheduled = False
        visible = self.viewport().rect()
        decoded = 0
        for index in range(self.count()):
            item = self.item(index)
            if not self.visualItemRect(item).intersects(visible):
                continue
            key = item.data(Qt.ItemDataRole.UserRole)
            cache_key = (key, self._thumb_side)
            icon = self._cached.get(cache_key)
            if icon is None:
                image = scaled_project_image(self.assets(key), self._thumb_side,
                                             self._thumb_side)
                icon = QIcon(QPixmap.fromImage(image)) if not image.isNull() else QIcon()
                self._cached[cache_key] = icon
                decoded += 1
                if len(self._cached) > MAX_THUMBNAILS:
                    # A QListWidgetItem also retains its QIcon. Evict both
                    # copies or scrolling eventually retains every thumbnail.
                    (old_key, _size), _old_icon = self._cached.popitem(last=False)
                    old_item = self._items_by_key.get(old_key)
                    if old_item is not None:
                        old_item.setIcon(QIcon())
            else:
                self._cached.move_to_end(cache_key)
            item.setIcon(icon)
            if decoded >= MAX_VISIBLE_LOAD:
                self.schedule_visible()
                break

    def startDrag(self, supportedActions):
        item = self.currentItem()
        if item is None:
            return
        key = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key, str) or not self.allowed(key):
            return
        # Payload contains ONLY the internal asset ID. The destination also
        # validates the actual drag source object and current project session.
        mime = QMimeData()
        mime.setData(PHOTO_MIME, QByteArray(key.encode("utf-8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        icon = item.icon().pixmap(90, 90)
        if not icon.isNull():
            drag.setPixmap(icon)
        drag.exec(Qt.DropAction.CopyAction)


class PictureDropZone(QFrame):
    """Only report-structure zones can receive a project-owned photo drag."""

    def __init__(self, module_id: str, index: int, resolver, insert, parent=None):
        super().__init__(parent)
        self.module_id, self.index = module_id, index
        self.resolve_photo = resolver
        self.insert_photo = insert
        self.setObjectName("pagePhotoDropZone")
        self.setAcceptDrops(True)
        self.setMinimumHeight(23)
        self._highlight(False)
        box = QHBoxLayout(self)
        box.setContentsMargins(6, 1, 6, 1)
        caption = QLabel("＋ Drop project photo here")
        caption.setObjectName("pagePhotoDropHint")
        caption.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        box.addWidget(caption)

    def _highlight(self, active):
        self.setStyleSheet("QFrame#pagePhotoDropZone { border: 2px dashed "
                           + ("#1672c7; background: #d7eafe;" if active
                              else "#b1bfd0; background: #f2f5f9;") + " }")

    def dragEnterEvent(self, event):
        if self.resolve_photo(event.source(), event.mimeData()) is None:
            event.ignore()
            return
        self._highlight(True)
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if self.resolve_photo(event.source(), event.mimeData()) is None:
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._highlight(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        key = self.resolve_photo(event.source(), event.mimeData())
        self._highlight(False)
        if key is None:
            event.ignore()
            return
        event.acceptProposedAction()
        # A refresh replaces page widgets. Never delete this zone synchronously
        # inside Qt's active drop-event dispatch.
        QTimer.singleShot(0, lambda: self.insert_photo(self.module_id, self.index, key))
