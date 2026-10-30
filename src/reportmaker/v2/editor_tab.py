"""V2 document Editor tab sharing Branch Editor's canonical drafts and IDs.

Only the Branch Editor owns the hierarchical layout. This page is a bounded,
document-style projection: each edit is staged through the SAME DraftCoordinator,
then committed via the SAME validated CommandGateway used by the branch.
"""
from __future__ import annotations

from math import ceil

from PySide6.QtCore import Qt, QTimer
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
from .contrast import BUTTON_CHROME
from .editing_keys import handle_plain_paste
from .navigation import subtree_range, window_for
from .projections import NodeAddress, find_node, project_branch


FOREIGN_TIP = "Another editor owns unapplied changes to this field"


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

    def keyPressEvent(self, event):
        if not handle_plain_paste(self, event):
            super().keyPressEvent(event)


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


class NaturalPagePhoto(QLabel):
    """Keep report photos inside the responsive printable area at every width.

    A QLabel's default size hint is the pixmap's pixel width; a fixed 610px
    preview can otherwise force narrow paper offscreen with scrollbars hidden.
    """
    def __init__(self, image, parent=None):
        super().__init__(parent)
        pixmap = QPixmap.fromImage(image)
        self._ratio = pixmap.height() / max(1, pixmap.width())
        self.setPixmap(pixmap)
        self.setScaledContents(True)
        self.setMinimumSize(1, 1)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding,
                             QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def heightForWidth(self, width):
        return max(1, ceil(max(1, width) * self._ratio))

    def sizeHint(self):
        # Never turn original photo pixels into a minimum paper width.
        hint = super().sizeHint()
        hint.setWidth(1)
        hint.setHeight(1)
        return hint

    def minimumSizeHint(self):
        return self.sizeHint()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Qt does not consistently honor QLabel height-for-width in a
        # vertically growing paper layout. Set the aspect-height explicitly.
        height = self.heightForWidth(event.size().width())
        if self.height() != height:
            self.setFixedHeight(height)
            self.updateGeometry()


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
        # Do not shadow QWidget.style(), which Qt uses for native painting.
        self._export_style = style
        self.flow = QVBoxLayout(self)
        self.flow.setSpacing(8)
        self._sync_margins()

    def _sync_margins(self):
        # The same cm-to-pixel scale is applied to all four printable margins.
        # It is intentionally a responsive *projection*, not PDF pagination.
        scale = max(1, self.width()) / self._export_style.page_width_cm
        margins = tuple(round(scale * value) for value in (
            self._export_style.left_margin_cm, self._export_style.top_margin_cm,
            self._export_style.right_margin_cm, self._export_style.bottom_margin_cm))
        if self.flow.getContentsMargins() != margins:
            self.flow.setContentsMargins(*margins)

    def sizeHint(self):
        # The page is centred in the scroll area, and a centred widget gets at
        # most its size hint. Without this the paper shrank to the width of its
        # narrowest child (about 320 px) instead of the printable page width.
        size = super().sizeHint()
        size.setWidth(max(size.width(), self.maximumWidth()))
        return size

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_margins()


class DocumentEditorTab(QWidget):
    """Canonical block editor; no private Report copy or direct ProjectEditor access."""

    def __init__(self, session, branch, parent=None, *, owner: str = "page-editor"):
        super().__init__(parent)
        self.setObjectName("v2DocumentEditorTab")
        # Explicit button foreground/background only; document typography
        # and printable paper colors stay owned by the editor projection.
        self.setStyleSheet(BUTTON_CHROME)
        self.session, self.branch = session, branch
        # Every Editor copy stages under its own id, so two copies showing the
        # same field can never silently overwrite each other's draft.
        self.owner = owner
        self.port = branch.drafts.for_editor(owner)
        self.style = ExportStyle()
        self._owned = set()
        self._module_id = None
        self._page = 0
        self._page_size = 90
        self._page_count = 1
        self._token = None
        self._editors = {}
        self._tables = {}
        # Fields another editor (the Modules canvas) currently holds drafts for.
        self._foreign: set = set()
        self._sync_queued = False
        self._unsubscribe_changes = branch.drafts.subscribe_changes(self._draft_changed)
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
        self._unsubscribe_session = self.session.subscribe(self._changed)
        self.refresh()

    def can_dispose(self) -> bool:
        """False while this copy still holds unapplied edits of its own."""
        return not self._owned

    def dispose(self) -> None:
        """Stop listening before a closed copy of this tab is deleted."""
        self._unsubscribe_changes()
        self._unsubscribe_session()

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
        self._queue_sync()

    def _draft_changed(self, address, owner, previous_owner):
        if owner in (None, self.owner) and previous_owner in (None, self.owner):
            return  # this tab's own drafts
        self._queue_sync()

    def _queue_sync(self):
        if self._sync_queued or not self.isVisible():
            return
        self._sync_queued = True
        QTimer.singleShot(0, self.sync_foreign_drafts)

    def activate(self):
        self.refresh()
        self.sync_foreign_drafts()

    def _is_foreign(self, address) -> bool:
        return self.branch.drafts.draft_owner(address) not in (None, self.owner)

    def sync_foreign_drafts(self):
        """Make every field another editor holds a draft for read-only, in place.

        The page is cached between session revisions, and staging a draft does
        not publish one, so without this a field being edited in Modules would
        stay editable here with its old text; typing into it is rejected by the
        draft coordinator but the rejected characters would stay on screen.
        """
        self._sync_queued = False
        if self._token is None and not self._owned:
            if self.isVisible():
                self.refresh()  # canonical content changed: a rebuild shows everything
            return
        drafts = self.branch.drafts
        rebuild = False
        for address, edit in self._editors.items():
            foreign = self._is_foreign(address)
            if foreign:
                self._foreign.add(address)
            elif address in self._foreign:
                self._foreign.discard(address)
            else:
                continue
            edit.setReadOnly(foreign)
            edit.setToolTip(FOREIGN_TIP if foreign else "")
            text = drafts.text(address)
            if edit.toPlainText() != text:
                edit.blockSignals(True)
                try:
                    edit.setPlainText(text)
                finally:
                    edit.blockSignals(False)
                edit.updateGeometry()
        for address, table in self._tables.items():
            foreign = self._is_foreign(address)
            if foreign:
                self._foreign.add(address)
            elif address in self._foreign:
                self._foreign.discard(address)
            else:
                continue
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers if foreign
                                  else table.property("defaultTriggers"))
            rows, _stale = drafts.table_preview(address)
            if (len(rows) != table.rowCount()
                    or max((len(r) for r in rows), default=0) != table.columnCount()):
                rebuild = True
                continue
            table.blockSignals(True)
            try:
                for i, values in enumerate(rows):
                    for j, value in enumerate(values):
                        item = table.item(i, j)
                        if item is not None and item.text() != value.original:
                            item.setText(value.original)
            finally:
                table.blockSignals(False)
            table.resizeRowsToContents()
            table.updateGeometry()
        if rebuild and not self._owned:
            self._token = None
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

    def _text_edited(self, address, widget):
        if address in self._foreign or widget.isReadOnly():
            return
        self._record(address, lambda: self.port.stage_text(address, widget.toPlainText()))

    def _cell_edited(self, address, table, item):
        if address in self._foreign:
            return
        self._record(address, lambda: self.port.stage_cell(
            address, item.row(), item.column(), item.text()))

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
        self._foreign = set()

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
                            flow.addWidget(NaturalPagePhoto(image, page))
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
                foreign = self._is_foreign(address)
                # A field Modules is editing shows that draft, not stale text.
                edit.setPlainText(self.branch.drafts.text(address) if foreign else initial)
                if foreign:
                    edit.setReadOnly(True)
                    edit.setToolTip(FOREIGN_TIP)
                    self._foreign.add(address)
                edit.textChanged.connect(
                    lambda a=address, widget=edit: self._text_edited(a, widget))
                flow.addWidget(edit)
                self._editors[address] = edit
            elif row.kind == "table":
                node = find_node(report, NodeAddress(
                    report.id, row.parent_module_id, row.stable_id, "table"))
                address = NodeAddress(
                    report.id, row.parent_module_id, row.stable_id, "table")
                foreign = self._is_foreign(address)
                rows = (self.branch.drafts.table_preview(address)[0]
                        if foreign else node.rows)
                table = NaturalPageTable(len(rows),
                                        max((len(values) for values in rows), default=0),
                                        page)
                table.setObjectName("v2DocumentTable_" + row.stable_id)
                table.setAcceptDrops(False)
                table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
                # Bulk population is not a live edit: avoid O(cells * rows)
                # repeated geometry work before the table is even displayed.
                table.blockSignals(True)
                try:
                    for i, values in enumerate(rows):
                        for j, value in enumerate(values):
                            table.setItem(i, j, QTableWidgetItem(value.original))
                finally:
                    table.blockSignals(False)
                table.setProperty("defaultTriggers", table.editTriggers())
                if foreign:
                    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                    self._foreign.add(address)
                table.itemChanged.connect(
                    lambda item, a=address, grid=table: self._cell_edited(a, grid, item))
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
