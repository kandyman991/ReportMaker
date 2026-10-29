"""Canonical M6 preview and guarded DOCX/PDF commands.

The continuous preview is explicitly schematic; the existing exporter owns
actual page dimensions, pagination, headers, footers and serialized output.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from ..export import ExportError, ExportStyle, export_project, prepare_export
from .localized_export import TranslationRequiredError, localized_project
from .session import ReportSession
from .visual_export import annotated_png


class PreviewTab(QWidget):
    def __init__(self, session: ReportSession, parent=None):
        super().__init__(parent)
        self.setObjectName("v2PreviewTab")
        self.session = session
        self.style = ExportStyle()
        self._token = None
        outer = QVBoxLayout(self)
        self.notice = QLabel(
            "Continuous schematic preview, not exact DOCX/PDF pagination. "
            "Actual page layout is determined by the export settings.")
        self.notice.setWordWrap(True)
        outer.addWidget(self.notice)
        language_row = QHBoxLayout()
        language_row.addWidget(QLabel("Document content language"))
        self.language = QComboBox(self)
        self.language.setObjectName("v2PreviewLanguage")
        self.language.currentIndexChanged.connect(self.invalidate)
        self.language.currentIndexChanged.connect(self.refresh)
        language_row.addWidget(self.language, 1)
        outer.addLayout(language_row)
        buttons = QHBoxLayout()
        for label, kind in (("Export editable DOCX…", "docx"), ("Export PDF…", "pdf")):
            button = QPushButton(label)
            button.setObjectName("v2Export" + kind.upper())
            button.clicked.connect(lambda checked=False, fmt=kind: self.export_dialog(fmt))
            buttons.addWidget(button)
        buttons.addStretch()
        outer.addLayout(buttons)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setObjectName("v2PrintPreviewScroll")
        outer.addWidget(self.scroll, 1)
        self.refresh()

    def invalidate(self):
        self._token = None

    def set_style(self, style: ExportStyle) -> None:
        self.style = style
        self.invalidate()
        self.refresh()

    def _current_language(self):
        return self.language.currentData()

    def _sync_languages(self):
        report = self.session.report_snapshot()
        chosen = self.language.currentData()
        wanted = [(None, "Original report text")]
        wanted.extend((tag, f"{tag} · checked translation")
                      for tag in report.output_languages
                      if tag.casefold() != report.primary_language.casefold())
        if [(self.language.itemData(i), self.language.itemText(i))
            for i in range(self.language.count())] == wanted:
            return
        self.language.blockSignals(True)
        try:
            self.language.clear()
            for code, caption in wanted:
                self.language.addItem(caption, code)
            index = self.language.findData(chosen)
            self.language.setCurrentIndex(index if index >= 0 else 0)
        finally:
            self.language.blockSignals(False)

    def refresh(self):
        self._sync_languages()
        token = (self.session.generation, self.session.revision,
                 self.session._draft_guard(), self._current_language())
        if token == self._token:
            return
        self._token = token
        shell = QWidget(self)
        wrapper = QVBoxLayout(shell)
        page = QFrame(shell)
        page.setObjectName("v2PrintPreviewPaper")
        page.setStyleSheet(
            "QFrame#v2PrintPreviewPaper { background: white; "
            "border: 1px solid #b7bcc4; color: #17212c; }")
        page.setMaximumWidth(max(500, min(1100, round(850 * self.style.page_width_cm / 21))))
        flow = QVBoxLayout(page)
        flow.setContentsMargins(
            max(18, round(35 * self.style.left_margin_cm / 2.1)),
            max(18, round(35 * self.style.top_margin_cm / 3.0)),
            max(18, round(35 * self.style.right_margin_cm / 2.1)),
            max(18, round(35 * self.style.bottom_margin_cm / 2.5)))
        flow.setSpacing(8)

        def text(value, *, strong=False, margin=0):
            label = QLabel(str(value), page)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setWordWrap(True)
            label.setContentsMargins(max(0, margin), 0, 0, 0)
            if strong:
                label.setStyleSheet("font-weight: bold; font-size: 16px;")
            flow.addWidget(label)
            return label

        try:
            project = self.session.project_snapshot()
            if self._current_language() is not None:
                project = localized_project(project, self._current_language())
            plan = prepare_export(project, visual_renderer=annotated_png)
            if self.style.logo:
                logo = QPixmap()
                if logo.loadFromData(self.style.logo):
                    logo_label = QLabel(page)
                    logo_label.setPixmap(logo.scaledToWidth(min(210, logo.width()),
                        Qt.TransformationMode.SmoothTransformation))
                    flow.addWidget(logo_label)
            if self.style.company_name:
                text(self.style.company_name)
            text(plan.title, strong=True)
            text("Report information", strong=True)
            for name, value in plan.info:
                text(f"{name}: {value}")
            text("Summary · derived from the report hierarchy", strong=True)
            for entry in plan.outline:
                text((entry.number + " " if entry.number else "") + entry.title,
                     margin=14 * min(10, entry.depth))
            text("Report content", strong=True)
            for item in plan.items:
                if item.kind == "module":
                    text(item.text, strong=True, margin=10 * min(8, item.depth))
                elif item.kind in ("paragraph", "heading"):
                    text(item.text, strong=(item.kind == "heading"),
                         margin=12)
                elif item.kind == "table":
                    table = QWidget(page)
                    grid = QGridLayout(table)
                    for i, values in enumerate(item.rows):
                        for j, value in enumerate(values):
                            cell = QLabel(value, table)
                            cell.setTextFormat(Qt.TextFormat.PlainText)
                            cell.setWordWrap(True)
                            cell.setStyleSheet("border: 1px solid #abb6c4; padding: 5px;")
                            grid.addWidget(cell, i, j)
                    flow.addWidget(table)
                elif item.kind == "photo":
                    image = QImage.fromData(item.image)
                    if image.isNull():
                        raise ExportError("Could not decode preview photograph")
                    picture = QLabel(page)
                    picture.setAlignment(Qt.AlignmentFlag.AlignLeft)
                    picture.setPixmap(QPixmap.fromImage(image).scaledToWidth(
                        min(image.width(), 650),
                        Qt.TransformationMode.SmoothTransformation))
                    flow.addWidget(picture)
                    if item.text:
                        text(item.text)
                elif item.kind == "page_break":
                    text("— Manual page break in exported document —")
            if self.style.footer_note:
                text("Footer: " + self.style.footer_note)
            self.notice.setText(
                ("Language-specific content preview · metadata labels and report "
                 "information are shown as stored; no automatic translation. "
                 if self._current_language() is not None else "") +
                "Continuous schematic preview of applied content · DOCX/PDF "
                "export uses real pagination. Unapplied drafts are not displayed."
                if self.session._draft_guard() else
                "Unapplied edits exist: preview shows the last approved report. "
                "Apply or Revert drafts before exporting.")
        except (ValueError, RuntimeError) as exc:
            text("Preview unavailable: " + str(exc))
            self.notice.setText("Preview could not be rendered; export will fail closed.")
        wrapper.addWidget(page, 0, Qt.AlignmentFlag.AlignHCenter)
        wrapper.addStretch(1)
        self.scroll.setWidget(shell)

    def export_to(self, path: str | Path, format: str) -> bool:
        try:
            self.session.require_clean_drafts()
            project = self.session.project_snapshot()
            if self._current_language() is not None:
                project = localized_project(project, self._current_language())
            export_project(project, path, format=format, style=self.style,
                           visual_renderer=annotated_png)
        except (OSError, ValueError, RuntimeError) as exc:
            self.notice.setText("Export rejected; existing file left unchanged: " + str(exc))
            self.invalidate()  # Next visit refreshes the normal applied-content preview.
            return False
        self.notice.setText(f"Exported {Path(path).name} from the applied canonical report")
        return True

    def export_dialog(self, format: str) -> bool:
        if format not in ("docx", "pdf"):
            raise ValueError("Unsupported export format")
        if not self.session._draft_guard():
            self.notice.setText("Apply or Revert pending edits before export")
            return False
        target, _ = QFileDialog.getSaveFileName(
            self, "Export " + format.upper(), "",
            f"{format.upper()} document (*.{format})")
        if not target:
            return False
        path = Path(target)
        if path.suffix.lower() != "." + format:
            path = path.with_suffix("." + format)
        return self.export_to(path, format)
