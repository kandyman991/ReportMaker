"""Editable paper surface over canonical report blocks, never an HTML document store.

Only text, heading, table-cell and photo-caption widgets are editable. The
module tree, summary, photos and page breaks are protected projections.
Changes are batched in one validated ProjectEditor transaction.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from .engine import module_outline
from .model import (
    HeadingBlock, LocalizedText, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, TableBlock,
)
from .photo_editor import render_photo
from .rich_editor import SafeRichTextEdit, apply_rich, capture_rich


def locate_block(report, module_id, block_id):
    """Resolve stable IDs on the validated candidate, never widget list indexes."""
    stack = list(report.ordered_sections())
    while stack:
        module = stack.pop()
        if module.id == module_id:
            for block in module.blocks:
                if block.id == block_id:
                    return block
            raise LookupError("Page block no longer exists")
        stack.extend(b.module for b in module.blocks if isinstance(b, NestedModuleBlock))
    raise LookupError("Page module no longer exists")


class EditableDocumentPage(QScrollArea):
    """Directly editable document-like page, with strictly protected structure."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("editableDocumentPage")
        self.setWidgetResizable(True)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.setStyleSheet(
            "QScrollArea#editableDocumentPage { background: #d8dce2; border: 0; }"
            "QFrame#editablePaper { background: #ffffff; color: #202124; "
            "border: 1px solid #a9afb7; }"
            "QFrame#editablePaper QLabel { color: #202124; }"
            "QFrame#editablePaper QTextEdit, QFrame#editablePaper QPlainTextEdit, "
            "QFrame#editablePaper QTableWidget { background: #ffffff; "
            "color: #202124; selection-background-color: #c2dcff; "
            "selection-color: #101820; }"
        )
        self.fields = {}
        self.pending = set()
        self._building = False
        self.on_style_request = None

    def _track(self, key, widget, signal):
        self.fields[key] = widget
        signal.connect(lambda *_args, entry=key: self._mark_pending(entry))

    def _mark_pending(self, entry):
        if not self._building:
            self.pending.add(entry)

    @staticmethod
    def _heading(value, layout, size=15):
        label = QLabel(value)
        label.setWordWrap(True)
        label.setStyleSheet("font-weight: 700; font-size: %dpx;" % size)
        layout.addWidget(label)
        return label

    def rebuild(self, report, assets):
        """Regenerate from canonical model; caller must first commit pending edits."""
        if self.pending:
            raise RuntimeError("Cannot replace unsaved page edits")
        self._building = True
        try:
            self.fields = {}
            shell = QWidget()
            shell.setStyleSheet("background: #d8dce2;")
            outer = QVBoxLayout(shell)
            outer.setContentsMargins(14, 14, 14, 14)
            paper = QFrame()
            paper.setObjectName("editablePaper")
            paper.setMinimumWidth(440)
            paper.setMaximumWidth(800)
            layout = QVBoxLayout(paper)
            layout.setContentsMargins(38, 34, 38, 40)
            layout.setSpacing(9)
            self._heading(report.title.original, layout, 22)
            self._heading("Report information · protected (edit in Report Information)", layout, 11)
            metadata = report.customer_snapshot
            for label, value in (
                ("Customer", metadata.customer_name if metadata else ""),
                ("Site", metadata.site_name if metadata else ""),
                ("Machine", metadata.machine_name if metadata else ""),
                ("Created", report.created_date.isoformat()),
                ("Intervention", report.start_date.isoformat() + " – " + report.end_date.isoformat()),
                ("Ticket", report.ticket),
                ("Personnel", ", ".join(report.technicians)),
                ("Types", ", ".join(report.intervention_types)),
                ("Other type detail", report.other_intervention_detail
                 if "other" in report.intervention_types else ""),
            ):
                if value:
                    data = QLabel(label + ": " + value)
                    data.setWordWrap(True)
                    layout.addWidget(data)
            self._heading("Summary · generated from module tree", layout, 15)
            for entry in module_outline(report):
                line = (entry.number + " " if entry.number else "") + entry.title
                item = QLabel(line)
                item.setWordWrap(True)
                item.setContentsMargins(min(entry.depth, 12) * 14, 0, 0, 0)
                layout.addWidget(item)

            def draw(module, depth):
                label = self._heading(module.title.original, layout, max(13, 19 - depth))
                label.setToolTip("Protected module title. Rename using the module tree.")
                for block in module.blocks:
                    key = (module.id, block.id)
                    if isinstance(block, (ParagraphBlock, HeadingBlock)):
                        edit = SafeRichTextEdit()
                        edit.setObjectName("pageText_" + block.id)
                        edit.setAcceptRichText(False)
                        edit.setAcceptDrops(False)  # no file/HTML/structural drops
                        edit.setMinimumHeight(64)
                        edit.setMaximumHeight(250)
                        edit.setStyleSheet(
                            "QTextEdit { border: 1px solid #c5cbd2; "
                            "padding: 3px; } QTextEdit:focus { border: 1px solid #3778bb; }"
                        )
                        apply_rich(edit, block.text.original, block.rich)
                        layout.addWidget(edit)
                        self._track((*key, "text"), edit, edit.textChanged)
                        if isinstance(block, HeadingBlock):
                            edit.setToolTip("Editable heading text; use Style for font formatting")
                        controls = QHBoxLayout()
                        controls.addStretch()
                        style_button = QPushButton("Style in ribbon…")
                        style_button.setObjectName("pageStyle_" + block.id)
                        style_button.clicked.connect(
                            lambda _checked=False, m=module.id, b=block.id:
                                self.on_style_request(m, b) if self.on_style_request else None)
                        controls.addWidget(style_button)
                        layout.addLayout(controls)
                    elif isinstance(block, TableBlock):
                        table = QTableWidget(len(block.rows),
                                             max((len(r) for r in block.rows), default=0))
                        table.setObjectName("pageTable_" + block.id)
                        table.setAcceptDrops(False)
                        table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
                        for i, row in enumerate(block.rows):
                            for j, cell in enumerate(row):
                                table.setItem(i, j, QTableWidgetItem(cell.original))
                        table.setMinimumHeight(min(270, 72 + len(block.rows) * 29))
                        layout.addWidget(table)
                        self._track((*key, "table"), table, table.itemChanged)
                    elif isinstance(block, PhotoBlock):
                        try:
                            image = render_photo(assets.get(block.asset_id, b""), block.visual, 800)
                        except ValueError:
                            image = None
                        picture = QLabel("[Photo unavailable]" if image is None or image.isNull() else "")
                        picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        if image is not None and not image.isNull():
                            picture.setPixmap(QPixmap.fromImage(image).scaledToWidth(
                                max(1, min(590, image.width()) * block.visual.width_pct // 100),
                                Qt.TransformationMode.SmoothTransformation))
                        picture.setToolTip("Protected image: use Edit selected picture for transformations")
                        layout.addWidget(picture)
                        caption = QPlainTextEdit()
                        caption.setObjectName("pageCaption_" + block.id)
                        caption.setPlaceholderText("Edit photo caption here")
                        caption.setPlainText(block.caption.original if block.caption else "")
                        caption.setMaximumHeight(70)
                        caption.setAcceptDrops(False)
                        layout.addWidget(caption)
                        self._track((*key, "caption"), caption, caption.textChanged)
                    elif isinstance(block, PageBreakBlock):
                        line = QLabel("────────── Page break (protected) ──────────")
                        line.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        layout.addWidget(line)
                    elif isinstance(block, NestedModuleBlock):
                        draw(block.module, depth + 1)

            for module in report.modules:
                draw(module, 0)
            draw(report.conclusion, 0)
            layout.addStretch(1)
            outer.addWidget(paper, alignment=Qt.AlignmentFlag.AlignHCenter)
            outer.addStretch(1)
            self.setWidget(shell)
        finally:
            self._building = False

    def commit(self, project_editor):
        """Apply only changed widget fields in a single atomic validated command."""
        if not self.pending:
            return False
        changes = {}
        for key in self.pending:
            widget = self.fields[key]
            kind = key[2]
            if kind == "text":
                changes[key] = capture_rich(widget)
            elif kind == "table":
                changes[key] = [
                    [widget.item(i, j).text() if widget.item(i, j) else ""
                     for j in range(widget.columnCount())]
                    for i in range(widget.rowCount())
                ]
            else:
                changes[key] = widget.toPlainText()

        def apply(report):
            for (module_id, block_id, kind), value in changes.items():
                block = locate_block(report, module_id, block_id)
                if kind == "text":
                    if not isinstance(block, (ParagraphBlock, HeadingBlock)):
                        raise ValueError("Changed page block type")
                    text, rich = value
                    block.text.update_original(text)
                    block.rich = deepcopy(rich)
                elif kind == "caption":
                    if not isinstance(block, PhotoBlock):
                        raise ValueError("Changed page caption type")
                    if block.caption is None:
                        block.caption = LocalizedText(report.primary_language, value)
                    else:
                        block.caption.update_original(value)
                elif kind == "table":
                    if not isinstance(block, TableBlock) or len(value) != len(block.rows) or any(
                        len(row) != len(prior) for row, prior in zip(value, block.rows)
                    ):
                        raise ValueError("Page table structure changed")
                    for row, original_row in zip(value, block.rows):
                        for text, cell in zip(row, original_row):
                            cell.update_original(text)

        project_editor.apply(apply)
        self.pending.clear()
        return True
