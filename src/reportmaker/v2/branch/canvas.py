"""Connected M1.3 Branch Editor with guarded inline titles and paragraphs.

The single canonical report drives visible order and connectors. Widgets hold
only drafts; no V1 UI, parallel report model or browser is imported here.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen, QTextCursor
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ...engine import validate_report_tree
from ...model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)

from ..commands import CommandGateway, CommandIntent
from ..drafts import DraftCoordinator
from ..projections import NodeAddress, project_branch
from ..session import PendingDraftError, ReportSession

_STEP = 25


def _display(node, *, conclusion: bool = False) -> tuple[str, str, str]:
    """Read only canonical fields, including the original mixed block order."""
    if isinstance(node, Module):
        return ("conclusion" if conclusion else "module",
                "CONCLUSIONS" if conclusion else "MODULE", node.title.original)
    if isinstance(node, ParagraphBlock):
        return "paragraph", "TEXT", node.text.original
    if isinstance(node, HeadingBlock):
        return "heading", "HEADING", node.text.original
    if isinstance(node, TableBlock):
        return "table", "TABLE", "\n".join(
            "  |  ".join(cell.original for cell in row) for row in node.rows
        ) or "(Empty table)"
    if isinstance(node, PhotoBlock):
        caption = node.caption.original if node.caption else ""
        return "photo", "PHOTO", caption or "(Project-owned photo)"
    if isinstance(node, PageBreakBlock):
        return "page-break", "PAGE BREAK", "Page break"
    raise TypeError("Unsupported report block")


def _branch_rows(report: Report):
    """Iterative preorder; wrapper modules share the canonical module ID.

    Ancestor continuation flags affect only the connector drawing. Neither
    rows nor any Qt widget are a persisted or editable report structure.
    """
    yield report.id, "root", "MAIN", report.title.original, 0, (), False
    sections = report.ordered_sections()
    stack = [
        (module, 1, (), index != len(sections) - 1, module is report.conclusion)
        for index, module in reversed(list(enumerate(sections)))
    ]
    while stack:
        node, depth, ancestors, has_next, is_conclusion = stack.pop()
        kind, label, text = _display(node, conclusion=is_conclusion)
        yield node.id, kind, label, text, depth, ancestors, has_next
        if isinstance(node, Module):
            for index in range(len(node.blocks) - 1, -1, -1):
                block = node.blocks[index]
                child = block.module if isinstance(block, NestedModuleBlock) else block
                stack.append((
                    child, depth + 1, ancestors + (has_next,),
                    index != len(node.blocks) - 1, False,
                ))


class ConnectorGutter(QWidget):
    """Draw explicit parent/child lines without changing report structure."""

    def __init__(self, depth: int, ancestors: tuple[bool, ...], has_next: bool,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._depth = depth
        self._ancestors = ancestors
        self._has_next = has_next
        # The canonical model permits 256 nesting levels; never collapse
        # connector geometry into the same position after level 32.
        self.setFixedWidth(18 + _STEP * max(0, depth))
        self.setMinimumHeight(48)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._depth:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#8199ae"), 2))
        middle = self.height() // 2
        for level, continues in enumerate(self._ancestors):
            if continues:
                x = 11 + _STEP * level
                painter.drawLine(x, 0, x, self.height())
        level = self._depth - 1
        x = 11 + _STEP * level
        painter.drawLine(x, 0, x, middle)
        painter.drawLine(x, middle, x + 16, middle)
        if self._has_next:
            painter.drawLine(x, middle, x, self.height())
        painter.end()


class InlineTitle(QLineEdit):
    cancelRequested = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class InlineParagraph(QPlainTextEdit):
    commitRequested = Signal()
    cancelRequested = Signal()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
        elif (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
              and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.commitRequested.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class BranchCanvas(QScrollArea):
    """Read-only geometry, editable source text; commands own all mutations."""
    feedback = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("v2BranchCanvas")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea#v2BranchCanvas { background: #f3f6fa; }")
        self._host = QWidget()
        self._host.setObjectName("v2BranchContent")
        self._host.setStyleSheet("background: #f3f6fa;")
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(20, 20, 20, 28)
        self._body.setSpacing(5)
        self.setWidget(self._host)
        self._visible_nodes = ()
        self._session = None
        self._gateway = None
        self.drafts = None
        self._unsubscribe = None
        self._editors = {}
        self._selected_module_id = None
        self._restore = None

    @property
    def visible_nodes(self) -> tuple[tuple[str, str, int, str], ...]:
        return self._visible_nodes

    def editor_for(self, address: NodeAddress):
        return self._editors.get(address)

    def bind_session(self, session: ReportSession, gateway: CommandGateway) -> None:
        if self.drafts is not None and self.drafts.pending:
            raise PendingDraftError("Resolve drafts before switching sessions")
        if self._unsubscribe is not None:
            self._unsubscribe()
        self._session, self._gateway = session, gateway
        self.drafts = DraftCoordinator(session, gateway)
        self._unsubscribe = session.subscribe(self._on_change)
        self._refresh()

    def _on_change(self, change) -> None:
        # New/Open changes generation: never restore selection or caret from
        # the previous report, even if a stale Qt redraw was queued.
        if change is None:
            self._selected_module_id = None
            self._restore = None
        # Do not delete the currently emitting widget inside its Qt callback.
        QTimer.singleShot(0, self._refresh)

    def _refresh(self) -> None:
        if self._session is not None:
            report = self._session.report_snapshot()
            module_ids = {row.stable_id for row in project_branch(report)
                          if row.kind in ("module", "conclusion")}
            if self._selected_module_id not in module_ids:
                self._selected_module_id = report.modules[0].id if report.modules else None
            self._render(report)

    def set_report(self, report: Report) -> None:
        """Legacy inspection API; cannot discard a pending inline draft."""
        validate_report_tree(report)
        if self.drafts is not None and self.drafts.pending:
            raise PendingDraftError("Resolve inline draft first")
        if self._session is not None and report != self._session.report_snapshot():
            raise ValueError("A bound Branch Editor can display only its canonical session")
        self._render(deepcopy(report))

    def eventFilter(self, watched, event):
        # A projection refresh may focus widgets implicitly when old cards are
        # deleted. Only an actual user click selects a different insert target.
        if event.type() == QEvent.Type.MouseButtonPress:
            module_id = watched.property("moduleId")
            if module_id and watched in self._editors.values():
                self._selected_module_id = module_id
        return super().eventFilter(watched, event)

    def _changed(self, address, text, buttons):
        try:
            self.drafts.update(address, text)
            buttons.setVisible(self.drafts.is_dirty(address))
            self.feedback.emit("Unapplied draft — Apply or Revert before Save/Undo")
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))

    def _capture(self, address):
        editor = self._editors.get(address)
        if isinstance(editor, QLineEdit):
            # Qt selection offsets use UTF-16 units, including emoji pairs.
            selected_length = len(editor.selectedText().encode("utf-16-le")) // 2
            self._restore = (address, editor.cursorPosition(),
                             editor.selectionStart(), selected_length)
        elif isinstance(editor, QPlainTextEdit):
            c = editor.textCursor()
            self._restore = (address, c.position(), c.anchor())

    def _restore_cursor(self):
        state, self._restore = self._restore, None
        if state is None:
            return
        address, position, anchor, *selection = state
        editor = self._editors.get(address)
        if isinstance(editor, QLineEdit):
            editor.setFocus()
            limit = len(editor.text().encode("utf-16-le")) // 2
            editor.setCursorPosition(min(position, limit))
            if selection and selection[0] and anchor >= 0:
                start = min(anchor, limit)
                editor.setSelection(start, min(selection[0], limit - start))
        elif isinstance(editor, QPlainTextEdit):
            editor.setFocus()
            c = editor.textCursor()
            c.setPosition(min(anchor, len(editor.toPlainText())))
            c.setPosition(min(position, len(editor.toPlainText())),
                          QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(c)

    def apply_draft(self, address) -> bool:
        if self.drafts is None:
            return False
        self._capture(address)
        try:
            self.drafts.commit(address)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Draft retained: " + str(exc))
            return False
        self._refresh()
        self.feedback.emit("Edit applied")
        return True

    def revert_draft(self, address) -> None:
        if self.drafts is None:
            return
        self._capture(address)
        self.drafts.discard(address)
        self._refresh()
        self.feedback.emit("Draft reverted")

    def _run(self, kind, target=None, **args):
        if self._session is None:
            return False
        try:
            change = self._gateway.execute(CommandIntent(
                kind, target, args, self._session.revision, self._session.generation))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        if change is not None:
            new_id = next(iter(change.changed_ids))
            report_id = self._session.report_snapshot().id
            if kind in ("add_module", "add_nested_module"):
                self._selected_module_id = new_id
                self._restore = (NodeAddress(report_id, new_id), 0, -1)
            elif kind == "add_paragraph":
                self._restore = (NodeAddress(report_id, target.module_id, new_id, "text"), 0, 0)
        self._refresh()
        return True

    def add_module(self):
        return self._run("add_module", title="New module")

    def add_nested_module(self):
        if self._session is None or not self._selected_module_id:
            self.feedback.emit("Select a module title first")
            return False
        return self._run("add_nested_module",
                         NodeAddress(self._session.report_snapshot().id, self._selected_module_id),
                         title="New submodule")

    def add_paragraph(self):
        if self._session is None or not self._selected_module_id:
            self.feedback.emit("Select a module title first")
            return False
        return self._run("add_paragraph",
                         NodeAddress(self._session.report_snapshot().id, self._selected_module_id),
                         text="")

    def _history(self, operation):
        if self._session is None:
            return False
        try:
            change = getattr(self._gateway, operation)(
                self._session.generation, self._session.revision)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        if change is not None:
            self._refresh()
        return change is not None

    def undo(self):
        return self._history("undo")

    def redo(self):
        return self._history("redo")

    def _inline(self, card, address, kind, original):
        text = self.drafts.text(address)
        if kind in ("module", "conclusion"):
            editor = InlineTitle(card)
            editor.setObjectName("v2InlineTitle")
            editor.setText(text)
            editor.setStyleSheet("color: #182b3a; font-size: 15px; font-weight: bold;")
        else:
            editor = InlineParagraph(card)
            editor.setObjectName("v2InlineParagraph")
            editor.setPlainText(text)
            editor.setMinimumHeight(74)
            editor.setMaximumHeight(230)
            editor.setTabChangesFocus(True)
            editor.setStyleSheet("color: #182b3a; font-size: 14px;")
        editor.setProperty("nodeId", address.block_id or address.module_id)
        editor.setProperty("moduleId", address.module_id)
        editor.installEventFilter(self)
        self._editors[address] = editor
        buttons = QWidget(card)
        bar = QHBoxLayout(buttons)
        bar.setContentsMargins(0, 3, 0, 0)
        apply = QPushButton("Apply", buttons)
        apply.setObjectName("v2ApplyDraft")
        revert = QPushButton("Revert", buttons)
        revert.setObjectName("v2RevertDraft")
        bar.addWidget(apply)
        bar.addWidget(revert)
        bar.addStretch(1)
        apply.clicked.connect(lambda checked=False, a=address: self.apply_draft(a))
        revert.clicked.connect(lambda checked=False, a=address: self.revert_draft(a))
        buttons.setVisible(self.drafts.is_dirty(address))
        if isinstance(editor, QLineEdit):
            editor.textEdited.connect(lambda t, a=address, b=buttons: self._changed(a, t, b))
            editor.returnPressed.connect(lambda a=address: self.apply_draft(a))
        else:
            editor.textChanged.connect(lambda e=editor, a=address, b=buttons:
                                       self._changed(a, e.toPlainText(), b))
            editor.commitRequested.connect(lambda a=address: self.apply_draft(a))
        editor.cancelRequested.connect(lambda a=address: self.revert_draft(a))
        card.layout().addWidget(editor)
        card.layout().addWidget(buttons)

    def _render(self, report: Report):
        validate_report_tree(report)
        rows = tuple(_branch_rows(report))
        projection = project_branch(report, revision=self._session.revision if self._session else 0)
        if len(rows) != len(projection) or any(a[0] != b.stable_id for a, b in zip(rows, projection)):
            raise ValueError("Branch layout diverged from canonical projection")
        scroll = self.verticalScrollBar().value()
        self._editors.clear()
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for (identifier, kind, caption, text, depth, ancestors, has_next), meta in zip(rows, projection):
            row = QWidget(self._host)
            row.setObjectName("v2BranchRow")
            row.setProperty("nodeId", identifier)
            row.setProperty("nodeKind", kind)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(0)
            line.addWidget(ConnectorGutter(depth, ancestors, has_next, row))
            card = QFrame(row)
            card.setObjectName("v2BranchCard")
            card.setStyleSheet("QFrame#v2BranchCard { background: white; border: 1px solid #cbd5e1; border-radius: 8px; }")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 9, 15, 10)
            card_layout.setSpacing(3)
            label = QLabel(caption, card)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet("color: #526c83; font-size: 10px; font-weight: bold;")
            card_layout.addWidget(label)
            if self.drafts is not None and kind in ("module", "conclusion", "paragraph"):
                address = (NodeAddress(report.id, identifier) if kind != "paragraph"
                           else NodeAddress(report.id, meta.parent_module_id, identifier, "text"))
                self._inline(card, address, kind, text)
            else:
                value = QLabel(text or "(Empty)", card)
                value.setObjectName("v2BranchValue")
                value.setTextFormat(Qt.TextFormat.PlainText)
                value.setWordWrap(True)
                value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                value.setStyleSheet("color: #182b3a; font-size: 15px;")
                card_layout.addWidget(value)
            line.addWidget(card, 1)
            self._body.addWidget(row)
        self._body.addStretch(1)
        self._visible_nodes = tuple(
            (identifier, kind, depth, text)
            for identifier, kind, _, text, depth, _, _ in rows
        )
        self.verticalScrollBar().setValue(scroll)
        if self._restore is not None:
            QTimer.singleShot(0, self._restore_cursor)
