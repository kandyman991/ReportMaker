"""V2 document Editor tab sharing Branch Editor's canonical drafts and IDs.

Only the Branch Editor owns the hierarchical layout. This page is a bounded,
document-style projection: each edit is staged through the SAME DraftCoordinator,
then committed via the SAME validated CommandGateway used by the branch.
"""
from __future__ import annotations

from math import ceil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)
from PySide6.QtGui import QPixmap

from ..engine import module_outline
from ..export import ExportStyle
from ..model import HeadingBlock, ParagraphBlock, PhotoBlock, TableBlock
from ..photo_editor import render_photo
from .navigation import subtree_range, window_for
from .projections import NodeAddress, find_node, project_branch


class NaturalPageText(QPlainTextEdit):
    """Full wrapping document height; scroll is owned by the outer page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(
            self.updateGeometry)

    def sizeHint(self):
        pixels = 0.0
        layout = self.document().documentLayout()
        block = self.document().begin()
        while block.isValid():
            pixels += layout.blockBoundingRect(block).height()
            block = block.next()
        height = ceil(max(pixels, float(self.fontMetrics().lineSpacing()))
                      + 2 * self.document().documentMargin()
                      + 2 * self.frameWidth() + 8)
        size = super().sizeHint()
        size.setHeight(height)
        return size

    def minimumSizeHint(self):
        size = self.sizeHint()
        size.setWidth(1)
        return size

    def resizeEvent(self, event):
        before = event.oldSize().width()
        super().resizeEvent(event)
        if before != self.width():
            self.updateGeometry()

    def wheelEvent(self, event):
        # Never trap scroll within a paragraph; allow the parent document to move.
        event.ignore()


class NaturalPageTable(QTableWidget):
    """Size the complete editable grid to its content; outer page owns scroll."""

    def __init__(self, rows: int, columns: int, parent=None):
        super().__init__(rows, columns, parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setWordWrap(True)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents)
        # Resizing a cell must also resize the outer card immediately; no
        # nested grid viewport may swallow a long edit until a window resize.
        self.itemChanged.connect(self._content_changed)

    def _content_changed(self, _item):
        self.resizeRowsToContents()
        self.updateGeometry()

    def sizeHint(self):
        size = super().sizeHint()
        header = (self.horizontalHeader().height()
                  if self.horizontalHeader().isVisible() else 0)
        size.setHeight(max(35, header + sum(self.rowHeight(i)
                       for i in range(self.rowCount())) + 2 * self.frameWidth() + 6))
        return size

    def minimumSizeHint(self):
        size = self.sizeHint()
        size.setWidth(1)
        return size

    def resizeEvent(self, event):
        changed_width = event.oldSize().width() != event.size().width()
        super().resizeEvent(event)
        if changed_width:
            self.resizeRowsToContents()
            self.updateGeometry()

    def wheelEvent(self, event):
        event.ignore()


class NaturalPagePaper(QFrame):
    """Responsive paper outline: one physical scale for width and margins.

    This is a *continuous* editable document, not simulated Word page breaks.
    At narrow viewport widths the whole paper and its margins scale together,
    rather than hiding fixed 500px content under a disabled scrollbar.
    """

    PIXELS_PER_CM = 40.0

    def __init__(self, style: ExportStyle, parent=None):
        super().__init__(parent)
        self.setObjectName("v2DocumentPaper")
        self.setMinimumWidth(0)
        self.setMaximumWidth(round(self.PIXELS_PER_CM * style.page_width_cm))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setStyleSheet("QFrame#v2DocumentPaper { background: white;"
                           " border: 1px solid #b1b8c1; }")
        self.style = style
        self.flow = QVBoxLayout(self)
        self.flow.setSpacing(8)
        self._sync_margins()

    def _sync_margins(self):
        # The same cm-to-pixel scale is applied to all four printable margins.
        # It is intentionally a responsive *projection*, not PDF pagination.
        scale = max(1, self.width()) / self.style.page_width_cm
        margins = tuple(round(scale * value) for value in (
            self.style.left_margin_cm, self.style.top_margin_cm,
            self.style.right_margin_cm, self.style.bottom_margin_cm))
        if self.flow.getContentsMargins() != margins:
            self.flow.setContentsMargins(*margins)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_margins()


class DocumentEditorTab(QWidget):
    """Canonical block editor; no private Report copy or direct ProjectEditor access."""

    def __init__(self, session, branch, parent=None):
        super().__init__(parent)
        self.setObjectName("v2DocumentEditorTab")
        self.session, self.branch = session, branch
        self.port = branch.drafts.for_editor("page-editor")
        self.style = ExportStyle()
        self._owned = set()
        self._module_id = None
        self._page = 0
        self._page_size = 90
        self._page_count = 1
        self._token = None
        outer = QVBoxLayout(self)
        self.info = QLabel(
            "Document-oriented editor · continuous schematic, not exact Word pagination. "
            "All changes are staged in the shared report session.")
        self.info.setWordWrap(True)
        outer.addWidget(self.info)
        controls = QHBoxLayout()
        self.module_choice = QComboBox(self)
        self.module_choice.setObjectName("v2DocumentScope")
        self.module_choice.currentIndexChanged.connect(self._scope_changed)
        controls.addWidget(self.module_choice, 1)
        for label, name, callback in (
            ("Apply", "v2EditorApply", self.apply_changes),
            ("Revert", "v2EditorRevert", self.revert_changes),
            ("Previous", "v2EditorPrevious", lambda: self.change_page(-1)),
            ("Next", "v2EditorNext", lambda: self.change_page(1)),
        ):
            button = QPushButton(label, self)
            button.setObjectName(name)
            button.clicked.connect(callback)
            setattr(self, name, button)
            controls.addWidget(button)
        outer.addLayout(controls)
        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("v2DocumentScroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(self.scroll, 1)
        self.session.subscribe(self._changed)
        self.refresh()

    def set_style(self, style: ExportStyle) -> None:
        if self._owned:
            raise RuntimeError("Apply or Revert document drafts before changing page geometry")
        self.style = style
        self._token = None
        self.refresh()

    def _changed(self, change):
        # Session switches are blocked while any draft remains pending.
        # Do not replace focused widgets synchronously during Qt edit events.
        self._token = None

    def activate(self):
        self.refresh()

    def _scope_changed(self, index):
        if index < 0:
            return
        selected = self.module_choice.itemData(index)
        if self._owned:
            self.info.setText("Apply or Revert document edits before changing scope.")
            self.module_choice.blockSignals(True)
            try:
                old = self.module_choice.findData(self._module_id)
                if old >= 0:
                    self.module_choice.setCurrentIndex(old)
            finally:
                self.module_choice.blockSignals(False)
            return
        self._module_id = selected
        self._page = 0
        self._token = None
        self.refresh()

    def change_page(self, direction):
        if direction not in (-1, 1) or self._owned:
            self.info.setText("Apply or Revert document edits before changing page window.")
            return False
        if not 0 <= self._page + direction < self._page_count:
            return False
        self._page += direction
        self._token = None
        self.refresh()
        self.scroll.verticalScrollBar().setValue(0)
        return True

    def _record(self, address, operation):
        try:
            operation()
            if self.port.owns(address):
                self._owned.add(address)
            else:
                self._owned.discard(address)
            self._pending_status()
        except (ValueError, LookupError, RuntimeError) as exc:
            self.info.setText("Edit rejected; original draft retained: " + str(exc))

    def _pending_status(self):
        self.v2EditorApply.setEnabled(bool(self._owned))
        self.v2EditorRevert.setEnabled(bool(self._owned))
        self.v2EditorPrevious.setEnabled(self._page > 0 and not self._owned)
        self.v2EditorNext.setEnabled(self._page < self._page_count - 1 and not self._owned)
        if self._owned:
            self.info.setText(
                f"{len(self._owned)} unapplied document field(s) · "
                "Apply or Revert before Save, export, or switching document windows.")
        else:
            self.info.setText(
                "Continuous schematic editor over canonical blocks · "
                "DOCX/PDF determines actual page breaks. No independent report model.")

    def refresh(self):
        if self._owned:
            self._pending_status()
            return
        token = (self.session.generation, self.session.revision,
                 self._module_id, self._page)
        if token == self._token:
            return
        report = self.session.report_snapshot()
        self._token = token
        choices = [(None, "Entire report")]
        choices.extend(
            (entry.module_id, ("  " * min(entry.depth, 8)) +
             (entry.number + " " if entry.number else "") + entry.title)
            for entry in module_outline(report))
        if self._module_id not in {mid for mid, _ in choices}:
            self._module_id = None
        self.module_choice.blockSignals(True)
        try:
            self.module_choice.clear()
            for mid, title in choices:
                self.module_choice.addItem(title, mid)
            self.module_choice.setCurrentIndex(self.module_choice.findData(self._module_id))
        finally:
            self.module_choice.blockSignals(False)

        rows = project_branch(report)
        if self._module_id is not None:
            begin, end = subtree_range(rows, self._module_id)
            rows = rows[begin:end]
        selected, self._page_count = window_for(rows, self._page, size=self._page_size)
        self._page = min(self._page, self._page_count - 1)
        self._token = (self.session.generation, self.session.revision,
                       self._module_id, self._page)
        shell = QWidget(self)
        root = QVBoxLayout(shell)
        page = NaturalPagePaper(self.style, shell)
        flow = page.flow
        self._editors = {}
        self._tables = {}

        def label(value, *, bold=False, indent=0):
            line = QLabel(str(value), page)
            line.setTextFormat(Qt.TextFormat.PlainText)
            line.setWordWrap(True)
            line.setContentsMargins(min(100, indent), 0, 0, 0)
            if bold:
                line.setStyleSheet("font-size: 16px; font-weight: bold;")
            flow.addWidget(line)

        if self._module_id is None and self._page == 0:
            label(report.title.original, bold=True)
            snapshot = report.customer_snapshot
            if snapshot is not None:
                label("Customer: " + snapshot.customer_name)
            label("Summary · same canonical module tree", bold=True)
            for entry in module_outline(report):
                label((entry.number + " " if entry.number else "") + entry.title,
                      indent=entry.depth * 14)
        label(f"Document window {self._page + 1} of {self._page_count}")
        for row in selected:
            if row.kind in ("root", "module", "conclusion"):
                label(row.text, bold=True, indent=row.depth * 9)
                continue
            address = NodeAddress(report.id, row.parent_module_id, row.stable_id, "text")
            if row.kind in ("paragraph", "heading", "photo"):
                if row.kind == "photo":
                    node = find_node(report, NodeAddress(
                        report.id, row.parent_module_id, row.stable_id, "photo"))
                    try:
                        image = render_photo(self.session.assets[node.asset_id],
                                             node.visual, 900)
                        if not image.isNull():
                            picture = QLabel(page)
                            picture.setPixmap(QPixmap.fromImage(image).scaledToWidth(
                                min(610, image.width()),
                                Qt.TransformationMode.SmoothTransformation))
                            flow.addWidget(picture)
                    except (ValueError, KeyError):
                        label("Project photo unavailable")
                    address = NodeAddress(
                        report.id, row.parent_module_id, row.stable_id, "caption")
                    initial = node.caption.original if node.caption else ""
                else:
                    node = find_node(report, address)
                    initial = node.text.original
                    if row.kind == "heading":
                        label("Heading", bold=True)
                edit = NaturalPageText(page)
                edit.setObjectName("v2DocumentField_" + row.stable_id)
                # Present supported base font semantics consistently with
                # the Word profile. Rich inline runs remain canonical and are
                # edited in the Branch formatting toolbar, not silently lost.
                font = edit.font()
                family = (self.style.heading_font if row.kind == "heading"
                          else self.style.normal_font)
                if family:
                    font.setFamily(family)
                font.setPointSizeF(self.style.heading_size_pt if
                                   row.kind == "heading" else
                                   self.style.normal_size_pt)
                font.setBold(row.kind == "heading")
                edit.setFont(font)
                edit.setPlainText(initial)
                if self.branch.drafts.draft_owner(address) not in (None, "page-editor"):
                    edit.setReadOnly(True)
                    edit.setToolTip("Another editor owns unapplied changes to this field")
                else:
                    edit.textChanged.connect(
                        lambda a=address, widget=edit:
                        self._record(a, lambda: self.port.stage_text(
                            a, widget.toPlainText())))
                flow.addWidget(edit)
                self._editors[address] = edit
            elif row.kind == "table":
                node = find_node(report, NodeAddress(
                    report.id, row.parent_module_id, row.stable_id, "table"))
                address = NodeAddress(
                    report.id, row.parent_module_id, row.stable_id, "table")
                table = NaturalPageTable(len(node.rows),
                                        max((len(values) for values in node.rows), default=0),
                                        page)
                table.setObjectName("v2DocumentTable_" + row.stable_id)
                table.setAcceptDrops(False)
                table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
                for i, values in enumerate(node.rows):
                    for j, value in enumerate(values):
                        table.setItem(i, j, QTableWidgetItem(value.original))
                if self.branch.drafts.draft_owner(address) not in (None, "page-editor"):
                    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                else:
                    table.itemChanged.connect(
                        lambda item, a=address:
                        self._record(a, lambda: self.port.stage_cell(
                            a, item.row(), item.column(), item.text())))
                table.resizeRowsToContents()
                table.updateGeometry()
                flow.addWidget(table)
                self._tables[address] = table
            elif row.kind == "page-break":
                label("— Manual exported page break —")
        root.addWidget(page, 0, Qt.AlignmentFlag.AlignHCenter)
        root.addStretch(1)
        self.scroll.setWidget(shell)
        self._pending_status()

    def apply_changes(self):
        if not self._owned:
            return False
        try:
            # One compound canonical commit, never a partially applied
            # prefix of draft fields. On failure all drafts stay editable.
            self.port.apply_batch(tuple(self._owned))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.info.setText("Apply failed; all document drafts retained: " + str(exc))
            return False
        self._owned.clear()
        self._token = None
        self.refresh()
        return True

    def revert_changes(self):
        for address in tuple(self._owned):
            self.port.revert(address)
            self._owned.remove(address)
        self._token = None
        self.refresh()
        return True
