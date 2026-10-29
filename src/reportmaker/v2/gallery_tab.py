"""M6 project-owned media library tab over the single V2 ReportSession."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QUrl, Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QLabel, QMessageBox, QPushButton,
    QHBoxLayout, QVBoxLayout, QWidget,
)

from ..media_import import (
    INPUT_SUFFIXES, PictureImportError, convert_picture_bytes, stage_pictures,
)
from ..photo_gallery import ProjectPictureList, clipboard_image_png, local_picture_paths
from .contrast import BUTTON_CHROME, FIELD_CHROME
from .commands import CommandGateway, CommandIntent
from .session import ReportSession


class GalleryTab(QWidget):
    """Gallery-only imports preserve unplaced assets and the shared undo ledger."""

    def __init__(self, session: ReportSession, gateway: CommandGateway, branch, parent=None):
        super().__init__(parent)
        self.setObjectName("v2GalleryTab")
        self.setStyleSheet(BUTTON_CHROME + FIELD_CHROME)
        self.session, self.gateway, self.branch = session, gateway, branch
        self.on_inserted = None
        layout = QVBoxLayout(self)
        title = QLabel("Project photo gallery · original working copies are never modified")
        title.setWordWrap(True)
        layout.addWidget(title)
        controls = QHBoxLayout()
        for label, name, callback in (
            ("Import files…", "v2GalleryImport", self.import_dialog),
            ("Paste picture", "v2GalleryPaste", self.paste_image),
            ("Insert selected in module", "v2GalleryInsert", self.insert_selected),
        ):
            button = QPushButton(label, self)
            button.setObjectName(name)
            button.clicked.connect(callback)
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.pictures = ProjectPictureList(
            lambda key: key in self.session.assets,
            lambda key: self.session.assets[key],
            self.session.generation, self,
        )
        self.pictures.on_external_import = self._external_drop
        layout.addWidget(self.pictures, 1)
        self.hint = QLabel("Drop local image files here. Pictures can be stored without placing them in a module.")
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        self.refresh()

    def refresh(self):
        self.pictures.session_token = self.session.generation
        names = {key: self.session.media_library.get(key, "Placed project photo")
                 for key in self.session.assets}
        self.pictures.populate(names)
        self.hint.setText(
            f"{len(names)} project-owned pictures"
            " · imports remain local and undoable"
        )

    def _import_approved(self, photos: tuple[tuple[str, bytes], ...],
                         expected_revision: int, expected_generation: str) -> bool:
        try:
            change = self.gateway.execute(CommandIntent(
                "import_library_photos", None, {"photos": photos},
                expected_revision, expected_generation,
            ))
        except (ValueError, RuntimeError, LookupError) as exc:
            self.hint.setText("Picture import rejected: " + str(exc))
            return False
        if change is not None:
            self.refresh()
        return change is not None

    def import_paths(self, paths: list[str] | tuple[str, ...], *,
                     expected_revision=None, expected_generation=None) -> bool:
        revision = self.session.revision if expected_revision is None else expected_revision
        generation = self.session.generation if expected_generation is None else expected_generation
        try:
            self.session.require_clean_drafts()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(value)) for value in paths])
            approved, errors = local_picture_paths(mime)
            if errors or not approved or len(approved) != len(paths):
                raise PictureImportError("; ".join(errors) or "Invalid local picture files")
            staged = stage_pictures(approved)
            photos = tuple((item.name, item.photo.data) for item in staged)
        except (ValueError, RuntimeError) as exc:
            self.hint.setText("Picture import rejected: " + str(exc))
            return False
        return self._import_approved(photos, revision, generation)

    def _external_drop(self, paths: list[str], errors: list[str]) -> None:
        if errors:
            self.hint.setText("Picture drop rejected: " + "; ".join(errors))
            return
        self.import_paths(paths)

    def import_dialog(self) -> bool:
        revision, generation = self.session.revision, self.session.generation
        patterns = " ".join("*" + suffix for suffix in sorted(INPUT_SUFFIXES))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import pictures to project library", "",
            f"Supported images ({patterns})")
        return (self.import_paths(paths, expected_revision=revision,
                                  expected_generation=generation) if paths else False)

    def paste_image(self) -> bool:
        revision, generation = self.session.revision, self.session.generation
        try:
            self.session.require_clean_drafts()
            mime = QApplication.clipboard().mimeData()
            if mime is None:
                raise PictureImportError("Clipboard has no picture")
            if mime.hasImage():
                image = mime.imageData()
                if isinstance(image, QPixmap):
                    image = image.toImage()
                if not isinstance(image, QImage):
                    raise PictureImportError("Clipboard does not contain native pixels")
                converted = convert_picture_bytes(clipboard_image_png(image))
                return self._import_approved(
                    (("Clipboard picture", converted.data),), revision, generation)
            paths, errors = local_picture_paths(mime)
            if errors or not paths:
                raise PictureImportError("Paste native pixels or local picture files")
            return self.import_paths(paths, expected_revision=revision,
                                     expected_generation=generation)
        except (ValueError, RuntimeError) as exc:
            self.hint.setText("Clipboard import rejected: " + str(exc))
            return False

    def insert_selected(self) -> bool:
        selected = self.pictures.currentItem()
        if selected is None:
            self.hint.setText("Choose a picture to insert")
            return False
        key = selected.data(Qt.ItemDataRole.UserRole)
        if not isinstance(key, str) or key not in self.session.assets:
            self.hint.setText("Selected picture is no longer in this project")
            return False
        if not self.branch.add_photo(asset_id=key):
            self.hint.setText("Select a valid destination module in Modules, then insert")
            return False
        if callable(self.on_inserted):
            self.on_inserted()
        return True
