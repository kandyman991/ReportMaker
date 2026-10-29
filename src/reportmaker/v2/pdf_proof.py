"""Optional PDF-paginated proof rendered from the exact local PDF exporter.

The proof uses bounded in-memory Qt PDF rendering after an atomic temporary
local export. No browser, network, private external paths or parallel report
model; stale source revisions discard the proof.
"""
from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtPdf import QPdfDocument
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from ..export import ExportStyle, export_project
from ..project_io import ReportProject
from .visual_export import annotated_png

MAX_PROOF_BYTES = 80 * 1024 * 1024


class PdfProofPanel(QWidget):
    """Page-for-page PDF proof, not a prediction of Microsoft Word pagination."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("v2PDFProofPanel")
        self.document = QPdfDocument(self)
        self.buffer = None
        self.page_count = 0
        self.is_current = False
        layout = QVBoxLayout(self)
        self.notice = QLabel("Generate a PDF proof to inspect exact exported pagination.")
        self.notice.setWordWrap(True)
        layout.addWidget(self.notice)
        nav = QHBoxLayout()
        nav.addWidget(QLabel("PDF page"))
        self.page = QSpinBox(self)
        self.page.setObjectName("v2PDFProofPage")
        self.page.setRange(1, 1)
        self.page.valueChanged.connect(self.render_page)
        nav.addWidget(self.page)
        nav.addStretch(1)
        layout.addLayout(nav)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("v2PDFProofScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.picture = QLabel(self)
        self.picture.setObjectName("v2PDFProofImage")
        self.picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setWidget(self.picture)
        layout.addWidget(self.scroll, 1)

    def invalidate(self):
        self.is_current = False
        self.page_count = 0
        self.document.close()
        if self.buffer is not None:
            self.buffer.close()
            self.buffer = None
        self.picture.clear()
        self.page.blockSignals(True)
        try:
            self.page.setRange(1, 1)
        finally:
            self.page.blockSignals(False)
        self.notice.setText("PDF proof is outdated; generate it again from applied edits.")

    def generate(self, project: ReportProject, style: ExportStyle,
                 *, locale_labels: dict[str, str] | None = None) -> bool:
        self.invalidate()
        try:
            with TemporaryDirectory(prefix="reportmaker-v2-proof-") as directory:
                path = Path(directory) / "proof.pdf"
                export_project(project, path, format="pdf", style=style,
                               visual_renderer=annotated_png, locale_labels=locale_labels)
                if path.stat().st_size > MAX_PROOF_BYTES:
                    raise ValueError("Proof exceeds the 80 MiB in-memory rendering limit")
                binary = path.read_bytes()
            self.buffer = QBuffer(self)
            self.buffer.setData(QByteArray(binary))
            if not self.buffer.open(QIODevice.OpenModeFlag.ReadOnly):
                raise ValueError("Cannot open local PDF proof buffer")
            self.document.load(self.buffer)
            if (self.document.status() != QPdfDocument.Status.Ready
                    or self.document.pageCount() <= 0):
                raise ValueError("Qt PDF could not load the rendered document")
            self.page_count = self.document.pageCount()
            self.is_current = True
            self.page.blockSignals(True)
            try:
                self.page.setRange(1, self.page_count)
                self.page.setValue(1)
            finally:
                self.page.blockSignals(False)
            self.render_page(1)
            self.notice.setText(
                f"Exact PDF export proof · {self.page_count} paginated pages. "
                "Word DOCX layout may differ; PDF uses available local fonts "
                "and may substitute Word-only run families. Unapplied drafts are excluded.")
            return True
        except (OSError, ValueError, RuntimeError) as exc:
            self.invalidate()
            self.notice.setText("PDF proof could not be generated: " + str(exc))
            return False

    def render_page(self, page: int):
        if not self.is_current or not 1 <= page <= self.page_count:
            return False
        dimensions = self.document.pagePointSize(page - 1)
        if dimensions.width() <= 0 or dimensions.height() <= 0:
            self.notice.setText("PDF page has invalid dimensions")
            return False
        scale = min(1150 / dimensions.width(), 1500 / dimensions.height())
        size = QSize(max(1, round(dimensions.width() * scale)),
                     max(1, round(dimensions.height() * scale)))
        image = self.document.render(page - 1, size)
        if image.isNull():
            self.notice.setText("PDF page could not be rendered")
            return False
        self.picture.setPixmap(QPixmap.fromImage(image))
        self.picture.setMinimumSize(size)
        return True
