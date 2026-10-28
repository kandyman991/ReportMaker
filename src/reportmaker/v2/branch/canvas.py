"""Connected M1.3 Branch Editor with guarded inline titles and paragraphs.

The single canonical report drives visible order and connectors. Widgets hold
only drafts; no V1 UI, parallel report model or browser is imported here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil
from uuid import uuid4

from PySide6.QtCore import QEvent, QMimeData, QPoint, QPointF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QPainter, QPen, QTextCursor, QTextOption, QWheelEvent
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QLayout, QLineEdit, QPlainTextEdit,
    QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from ...engine import module_outline, validate_report_tree
from ...rich_text import RichFormatting, style_at
from ..adapters.formatting import (
    paragraph_uniform, selection_uniform, to_codepoint,
)
from .rich_preview import paint_rich
from ...model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)

from ..commands import CommandGateway, CommandIntent
from ..drafts import DraftCoordinator
from ..projections import NodeAddress, descendant_counts, project_branch
from ..session import PendingDraftError, ReportSession
from ..structure import plan_drop, plan_indent, plan_outdent, structural_node

_STEP = 25
_INTERNAL_MOVE_MIME = "application/x-reportmaker-v2-internal-move"


def _display(node, *, conclusion: bool = False) -> tuple[str, str, str]:
    """Read only canonical fields, including the original mixed block order."""
    if isinstance(node, Module):
        return ("conclusion" if conclusion else "module",
                "CONCLUSIONS" if conclusion else "MODULE", node.title.original)
    if isinstance(node, ParagraphBlock):
        return "paragraph", "TEXT", node.text.original
    if isinstance(node, HeadingBlock):
        return "heading", f"HEADING {node.level}", node.text.original
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


def _branch_rows(report: Report, *, expanded: frozenset[str] | None = None):
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
        if isinstance(node, Module) and (expanded is None or node.id in expanded):
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
    """Wrap to the card width and request the entire text height from Qt layout.

    Unlike a standard QPlainTextEdit, this editor is not a nested scrolling
    viewport. Width is allocated by its parent card's layout; the size hint
    follows wrapped document lines as the user types or the window resizes.
    """

    commitRequested = Signal()
    cancelRequested = Signal()
    formatRequested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.document().documentLayout().documentSizeChanged.connect(
            self.updateGeometry
        )
        self.cursorPositionChanged.connect(self._queue_caret_reveal)

    def _branch_canvas(self):
        parent = self.parentWidget()
        while parent is not None and not isinstance(parent, BranchCanvas):
            parent = parent.parentWidget()
        return parent

    def _queue_caret_reveal(self):
        if self.hasFocus():
            # The document and outer layout should finish adapting to the
            # latest edit before we reveal the caret in the *outer* viewport.
            QTimer.singleShot(0, self._reveal_caret)

    def _reveal_caret(self):
        if not self.hasFocus():
            return
        canvas = self._branch_canvas()
        if canvas is None:
            return
        caret = self.cursorRect()
        top = self.viewport().mapTo(canvas.viewport(), caret.topLeft()).y()
        bottom = self.viewport().mapTo(canvas.viewport(), caret.bottomLeft()).y()
        scrollbar = canvas.verticalScrollBar()
        edge = 16
        if bottom > canvas.viewport().height() - edge:
            scrollbar.setValue(scrollbar.value() + bottom
                               - canvas.viewport().height() + edge)
        elif top < edge:
            scrollbar.setValue(scrollbar.value() + top - edge)

    def wheelEvent(self, event):
        # With no internal editor scroll, the wheel must navigate the branch
        # even while the cursor is positioned over paragraph text.
        canvas = self._branch_canvas()
        if canvas is None:
            event.ignore()
            return
        point = self.viewport().mapTo(canvas.viewport(), event.position().toPoint())
        wheel = QWheelEvent(
            QPointF(point), event.globalPosition(), event.pixelDelta(),
            event.angleDelta(), event.buttons(), event.modifiers(),
            event.phase(), event.inverted(), event.source(),
        )
        QApplication.sendEvent(canvas.viewport(), wheel)
        event.setAccepted(wheel.isAccepted())

    def sizeHint(self) -> QSize:
        # QTextDocument.size().height() counts visual lines, *not* pixels
        # in a QPlainTextEdit. lineSpacing() is also insufficient when font
        # fallback (e.g. emoji/CJK) makes wrapped lines taller. Ask Qt's
        # actual text layout for each wrapped block's pixel bounding box.
        doc = self.document()
        layout = doc.documentLayout()
        pixels = 0.0
        block = doc.begin()
        while block.isValid():
            pixels += layout.blockBoundingRect(block).height()
            block = block.next()
        height = ceil(
            max(pixels, float(self.fontMetrics().lineSpacing()))
            + 2 * doc.documentMargin()
            + 2 * self.frameWidth() + 4
        )
        return QSize(super().sizeHint().width(), height)

    def minimumSizeHint(self) -> QSize:
        # QPlainTextEdit normally enforces a multi-line minimum viewport; a
        # one-line paragraph should be one line tall instead.
        return QSize(1, self.sizeHint().height())

    def resizeEvent(self, event) -> None:
        old_width = event.oldSize().width()
        super().resizeEvent(event)
        if old_width != self.width():
            # Word wrapping changed: the containing card must update its own
            # natural height, not introduce an editor scrollbar.
            self.updateGeometry()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
            event.accept()
        elif (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
              and event.modifiers() & Qt.KeyboardModifier.ControlModifier):
            self.commitRequested.emit()
            event.accept()
        elif (event.modifiers() == Qt.KeyboardModifier.ControlModifier
              and event.key() in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U)):
            self.formatRequested.emit({
                Qt.Key.Key_B: "bold", Qt.Key.Key_I: "italic",
                Qt.Key.Key_U: "underline",
            }[event.key()])
            event.accept()
        else:
            super().keyPressEvent(event)


@dataclass(frozen=True)
class _DragContext:
    """An unforgeable in-process drag, with a frozen revision/generation."""

    token: str
    source: NodeAddress
    revision: int
    generation: str


class DragHandle(QToolButton):
    """Explicit drag gesture; mouse selection in text editors is unaffected."""

    def __init__(self, canvas: "BranchCanvas", address: NodeAddress, parent=None):
        super().__init__(parent)
        self._canvas, self._address = canvas, address
        self._press_position = None
        self.setObjectName("v2DragHandle")
        self.setText("≡ Drag")
        self.setAccessibleName("Drag branch node")
        self.setToolTip("Drag to a marked Before, After or Inside position")
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setStyleSheet(
            "QToolButton#v2DragHandle { background: #e5edf6; color: #1e4568;"
            " border: 1px solid #91abc4; border-radius: 5px; padding: 3px 8px; }"
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_position = None
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if (self._press_position is not None
                and event.buttons() & Qt.MouseButton.LeftButton
                and (event.position().toPoint() - self._press_position).manhattanLength()
                >= QApplication.startDragDistance()):
            self._press_position = None
            self._canvas._start_drag(self._address, self)
            event.accept()
            return
        super().mouseMoveEvent(event)


class DropRow(QWidget):
    """One visible native Qt target; never stores an editable hierarchy."""

    def __init__(self, canvas: "BranchCanvas", address: NodeAddress, kind: str, parent=None):
        super().__init__(parent)
        self._canvas, self.address, self.kind = canvas, address, kind
        self._position = None
        self._valid = False
        self._reason = ""
        self.setObjectName("v2BranchRow")
        self.setAcceptDrops(True)
        self.setProperty("nodeId", address.block_id or address.module_id)
        self.setProperty("nodeKind", kind)
        self.marker = QLabel(self)
        self.marker.setObjectName("v2DropIndicator")
        self.marker.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.marker.hide()

    def position_at(self, y: float) -> str:
        fraction = min(1.0, max(0.0, y / max(1, self.height())))
        if self.kind == "root":
            return "inside"
        if self.kind in ("module", "conclusion"):
            return "before" if fraction < .25 else ("after" if fraction > .75 else "inside")
        # Integer pixel threshold is stable for odd/even Qt row heights on
        # Windows and Linux (the center pixel belongs to the After half).
        return "before" if y < max(1, self.height() // 2) else "after"

    def show_indicator(self, position: str, valid: bool, reason: str = "") -> None:
        if (self._position == position and self._valid == valid
                and self._reason == reason and not self.marker.isHidden()):
            return
        self._position, self._valid, self._reason = position, valid, reason
        verb = {"before": "BEFORE", "after": "AFTER", "inside": "INSIDE"}[position]
        self.marker.setText(verb if valid else "INVALID " + verb)
        self.marker.setToolTip(reason)
        accent = "#176eaa" if valid else "#ba4242"
        self.marker.setStyleSheet(
            f"QLabel#v2DropIndicator {{ background: {accent}; color: white;"
            " border-radius: 4px; padding: 2px 6px; font-weight: bold; }"
        )
        self.marker.adjustSize()
        self._place_indicator()
        self.marker.show()
        self.marker.raise_()
        self.update()

    def _place_indicator(self):
        if self._position is None:
            return
        y = (0 if self._position == "before"
             else self.height() - self.marker.height() if self._position == "after"
             else (self.height() - self.marker.height()) // 2)
        self.marker.move(max(0, self.width() - self.marker.width() - 6), max(0, y))

    def clear_indicator(self):
        if self._position is not None:
            self._position = None
            self.marker.hide()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_indicator()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._position is None:
            return
        painter = QPainter(self)
        painter.setPen(QPen(QColor("#176eaa" if self._valid else "#ba4242"), 3))
        if self._position == "before":
            painter.drawLine(0, 2, self.width(), 2)
        elif self._position == "after":
            painter.drawLine(0, self.height() - 2, self.width(), self.height() - 2)
        else:
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -3, -3), 7, 7)
        painter.end()

    def dragEnterEvent(self, event):
        self._canvas._preview_drop(self, event)

    def dragMoveEvent(self, event):
        self._canvas._preview_drop(self, event)

    def dragLeaveEvent(self, event):
        self._canvas._clear_drop_preview(self)
        event.accept()

    def dropEvent(self, event):
        self._canvas._commit_drop(self, event)


class BranchCanvas(QScrollArea):
    """Read-only geometry, editable source text; commands own all mutations."""
    feedback = Signal(str)
    selectionChanged = Signal()
    visibilityChanged = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("v2BranchCanvas")
        self.setWidgetResizable(True)
        # Long reports still scroll with wheel/touchpad, keyboard and focus;
        # the workspace never displays scrollbars. No child card scrollbars.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet("QScrollArea#v2BranchCanvas { background: #f3f6fa; }")
        self._host = QWidget()
        self._host.setObjectName("v2BranchContent")
        self._host.setStyleSheet("background: #f3f6fa;")
        self._body = QVBoxLayout(self._host)
        self._body.setContentsMargins(20, 20, 20, 28)
        self._body.setSpacing(5)
        # Let scroll content track changing child size hints (long paragraphs,
        # wrapping after width changes) rather than caching the first height.
        self._body.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self.setWidget(self._host)
        self._visible_nodes = ()
        self._session = None
        self._gateway = None
        self.drafts = None
        self._unsubscribe = None
        self._editors = {}
        self._draft_bars = {}
        self._ribbons = {}
        self._selected_module_id = None
        self._collapsed: set[str] = set()
        self._restore = None
        self._drag_context = None
        self._native_drag_active = False
        self._drag_refresh_pending = False
        # Prevent an already-rendered commit from rebuilding native editors
        # a second time when its deferred session notification arrives.
        self._last_rendered_token = None
        self._preview_row = None
        self._hover_key = None

    @property
    def visible_nodes(self) -> tuple[tuple[str, str, int, str], ...]:
        return self._visible_nodes

    @property
    def collapsed_module_ids(self) -> frozenset[str]:
        return frozenset(self._collapsed)

    def restore_collapsed(self, collapsed: frozenset[str]) -> None:
        """Apply locally stored IDs only after validating the current report."""
        if self._session is None or not isinstance(collapsed, frozenset):
            raise ValueError("A bound session and frozen collapse IDs are required")
        report = self._session.report_snapshot()
        valid = {row.stable_id for row in project_branch(report)
                 if row.kind in ("module", "conclusion")}
        self._collapsed = set(collapsed & valid)
        self._refresh()

    def toggle_branch(self, module_id: str) -> bool:
        if self._session is None:
            return False
        report = self._session.report_snapshot()
        rows = project_branch(report)
        module = next((r for r in rows if r.stable_id == module_id
                       and r.kind in ("module", "conclusion")), None)
        if module is None:
            return False
        try:
            # Recreating native editors must not discard an unapplied draft.
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        if module_id in self._collapsed:
            self._collapsed.remove(module_id)
        else:
            self._collapsed.add(module_id)
            # A selected descendant must not remain an invisible move target.
            by_id = {row.stable_id: row for row in rows}
            selected = by_id.get(self._selected_module_id)
            while selected is not None and selected.parent_module_id is not None:
                if selected.parent_module_id == module_id:
                    self._selected_module_id = module_id
                    break
                selected = by_id.get(selected.parent_module_id)
        self._restore = None
        self._refresh()
        self.visibilityChanged.emit()
        return True

    def reveal_module(self, module_id: str) -> bool:
        """TOC jump reveals collapsed ancestors and scrolls to the stable ID."""
        if self._session is None:
            return False
        rows = project_branch(self._session.report_snapshot())
        by_id = {row.stable_id: row for row in rows}
        target = by_id.get(module_id)
        if target is None or target.kind not in ("module", "conclusion"):
            return False
        to_expand = set()
        ancestor = target.parent_module_id
        while ancestor is not None:
            to_expand.add(ancestor)
            ancestor = by_id[ancestor].parent_module_id
        if self._collapsed.intersection(to_expand):
            try:
                self._session.require_clean_drafts()
            except PendingDraftError as exc:
                self.feedback.emit(str(exc))
                return False
            self._collapsed.difference_update(to_expand)
            self._restore = None
            self._selected_module_id = module_id
            self._refresh()
            self.visibilityChanged.emit()
        else:
            self._selected_module_id = module_id
            self.selectionChanged.emit()
        QTimer.singleShot(0, lambda mid=module_id: self._scroll_to_module(mid))
        return True

    def _scroll_to_module(self, module_id: str) -> None:
        if self._session is None:
            return
        for row in self._host.findChildren(DropRow):
            if row.kind in ("module", "conclusion") and row.address.module_id == module_id:
                top = row.mapTo(self._host, QPoint(0, 0)).y()
                self.verticalScrollBar().setValue(max(0, top - 28))
                return

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
            self._collapsed.clear()
            self._selected_module_id = None
            self._restore = None
            self._drag_context = None
            self._clear_drop_preview()
        # Native Qt handlers must finish before rebuilding. UI commands may
        # already have performed a synchronous refresh; avoid a second rebuild
        # of the same revision (which loses the restored caret and selection).
        token = (self._session.generation, self._session.revision)
        QTimer.singleShot(0, lambda t=token: self._refresh_for_change(t))

    def _refresh_for_change(self, token) -> None:
        if (self._session is not None
                and token == (self._session.generation, self._session.revision)
                and token != self._last_rendered_token):
            self._refresh()

    def _refresh(self) -> None:
        # QDrag.exec runs a nested Qt event loop. A successful drop publishes
        # a change before that loop returns; rebuilding here would delete the
        # source QToolButton (and its QDrag child) mid-gesture.
        if self._native_drag_active:
            self._drag_refresh_pending = True
            return
        if self._session is not None:
            report = self._session.report_snapshot()
            all_rows = project_branch(report)
            module_ids = {row.stable_id for row in all_rows
                          if row.kind in ("module", "conclusion")}
            self._collapsed.intersection_update(module_ids)
            if self._selected_module_id not in module_ids:
                self._selected_module_id = report.modules[0].id if report.modules else None
            # Reparenting can move the selected module under a *collapsed*
            # destination. Never leave toolbar actions targeting an invisible row.
            if self._selected_module_id is not None and self._collapsed:
                expanded = module_ids - self._collapsed
                visible_ids = {row.stable_id for row in project_branch(
                    report, expanded=frozenset(expanded))}
                if self._selected_module_id not in visible_ids:
                    by_id = {row.stable_id: row for row in all_rows}
                    current = by_id.get(self._selected_module_id)
                    while current is not None and current.stable_id not in visible_ids:
                        current = by_id.get(current.parent_module_id)
                    self._selected_module_id = (
                        current.stable_id if current is not None
                        and current.kind in ("module", "conclusion") else
                        (report.modules[0].id if report.modules else None)
                    )
            self._render(report)
            self._last_rendered_token = (self._session.generation, self._session.revision)
            self.selectionChanged.emit()

    def set_report(self, report: Report) -> None:
        """Legacy inspection API; cannot discard a pending inline draft."""
        validate_report_tree(report)
        if self.drafts is not None and self.drafts.pending:
            raise PendingDraftError("Resolve inline draft first")
        if self._session is not None and report != self._session.report_snapshot():
            raise ValueError("A bound Branch Editor can display only its canonical session")
        self._render(deepcopy(report))

    def eventFilter(self, watched, event):
        # Ribbons only appear for the actually focused inline text editor, not
        # on every card. NoFocus actions preserve the editor's Qt selection.
        if (event.type() in (QEvent.Type.FocusIn, QEvent.Type.FocusOut)
                and isinstance(watched, InlineParagraph)):
            QTimer.singleShot(0, self._sync_active_ribbon)
        # A projection refresh may focus widgets implicitly when old cards are
        # deleted. Only an actual user click selects a different insert target.
        if event.type() == QEvent.Type.MouseButtonPress:
            module_id = watched.property("moduleId")
            if module_id and watched in self._editors.values():
                if module_id != self._selected_module_id:
                    self._selected_module_id = module_id
                    self.selectionChanged.emit()
        return super().eventFilter(watched, event)

    def _arm_drag(self, source: NodeAddress) -> QMimeData | None:
        """Create an internal move token only for a live clean canonical node."""
        if self._session is None:
            return None
        try:
            self._session.require_clean_drafts()
            report = self._session.report_snapshot()
            rows = project_branch(report)
            identifier = source.block_id or source.module_id
            row = next((r for r in rows if r.stable_id == identifier), None)
            if (source.report_id != report.id or row is None
                    or row.kind in ("root", "conclusion")
                    or (source.block_id is None and row.kind != "module")
                    or (source.block_id is not None
                        and (row.kind == "module" or row.parent_module_id != source.module_id))):
                raise ValueError("Drag source is not a movable branch node")
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return None
        context = _DragContext(uuid4().hex, source, self._session.revision,
                               self._session.generation)
        self._drag_context = context
        mime = QMimeData()
        # The opaque token proves the MIME object was issued by this canvas.
        # No customer text, asset, or serialized report ever leaves the process.
        mime.setData(_INTERNAL_MOVE_MIME, context.token.encode("ascii"))
        return mime

    def _start_drag(self, source: NodeAddress, handle: DragHandle) -> None:
        mime = self._arm_drag(source)
        if mime is None:
            return
        drag = QDrag(handle)
        drag.setMimeData(mime)
        handle.setCursor(Qt.CursorShape.ClosedHandCursor)
        self._native_drag_active = True
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self._native_drag_active = False
            # Keep the QDrag source alive until exec returns; queue any
            # deferred canonical redraw for after this mouse callback.
            try:
                handle.setCursor(Qt.CursorShape.OpenHandCursor)
            except RuntimeError:
                pass  # Window shutdown can still destroy the source explicitly.
            self._drag_context = None
            self._clear_drop_preview()
            if self._drag_refresh_pending:
                self._drag_refresh_pending = False
                QTimer.singleShot(0, self._refresh)

    def _clear_drop_preview(self, row: DropRow | None = None) -> None:
        if row is not None and row is not self._preview_row:
            row.clear_indicator()
            return
        if self._preview_row is not None:
            self._preview_row.clear_indicator()
        self._preview_row = None
        self._hover_key = None

    def _candidate(self, row: DropRow, event):
        context = self._drag_context
        if (self._session is None or context is None
                or not event.mimeData().hasFormat(_INTERNAL_MOVE_MIME)
                or bytes(event.mimeData().data(_INTERNAL_MOVE_MIME))
                != context.token.encode("ascii")):
            return None, None, "Only internal Branch Editor moves are accepted"
        position = row.position_at(event.position().y())
        if (self._session.revision != context.revision
                or self._session.generation != context.generation):
            return position, None, "Report changed during drag; start again"
        try:
            self._session.require_clean_drafts()
            report = self._session.report_snapshot()
            plan = plan_drop(report, context.source, row.address, position)
            if plan.noop:
                return position, None, "Already at this position"
            return position, plan, ""
        except (ValueError, LookupError, RuntimeError) as exc:
            return position, None, str(exc)

    def _preview_drop(self, row: DropRow, event) -> None:
        position, plan, reason = self._candidate(row, event)
        if position is None:
            event.ignore()
            return
        if self._preview_row is not row:
            self._clear_drop_preview()
        self._preview_row = row
        row.show_indicator(position, plan is not None, reason)
        key = (row.address, position, plan is not None, reason)
        if self._hover_key != key:
            self._hover_key = key
            self.feedback.emit(
                f"Drop {position.upper()} to move" if plan is not None
                else f"Cannot drop {position.upper()}: {reason}"
            )
        if plan is not None:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            # Keep native drag-enter/move events routed to this row even if the
            # current zone is invalid; crossing into a legal zone must update
            # the preview without first leaving and reentering the widget.
            # IgnoreAction keeps the OS no-drop cursor until a legal zone.
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()

    def _commit_drop(self, row: DropRow, event) -> None:
        position, plan, reason = self._candidate(row, event)
        context = self._drag_context
        self._clear_drop_preview()
        if plan is None or context is None:
            self.feedback.emit(reason or "Drop cancelled")
            event.ignore()
            return
        try:
            # Revalidate the frozen drag revision at the command gateway. A
            # queued edit or session switch cannot turn a stale drag into a move.
            change = self._gateway.execute(CommandIntent(
                "move_node", context.source, {"anchor": row.address, "position": position},
                context.revision, context.generation,
            ))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Drop rejected: " + str(exc))
            event.ignore()
            return
        if change is not None:
            self._selected_module_id = (
                plan.source_id if plan.source_kind == "module"
                else plan.destination_parent_id)
            self.feedback.emit(f"Moved {position.upper()} — Undo is available")
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def _changed(self, address, text, buttons):
        try:
            self.drafts.update(address, text)
            # A native editor may inherit nearby visual character formatting
            # while typing; the staged Unicode ranges are authoritative.
            # Highlighter-only refresh does not mutate Qt's text undo stack.
            editor = self._editors.get(address)
            if isinstance(editor, InlineParagraph):
                try:
                    paint_rich(editor, text, self.drafts.rich(address))
                except ValueError:
                    # Ambiguous styled delimiter edits retain their visible
                    # draft and fail closed on Apply, as before.
                    pass
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
            # QTextCursor offsets count UTF-16 code units, not Python code
            # points. Astral Unicode (emoji) otherwise truncates the caret.
            limit = len(editor.toPlainText().encode("utf-16-le")) // 2
            c.setPosition(max(0, min(anchor, limit)))
            c.setPosition(max(0, min(position, limit)),
                          QTextCursor.MoveMode.KeepAnchor)
            editor.setTextCursor(c)

    def apply_draft(self, address) -> bool:
        if self.drafts is None:
            return False
        self._capture(address)
        try:
            change = self.drafts.commit(address)
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

    def _run(self, kind, target=None, *, expected_revision=None,
             expected_generation=None, **args):
        if self._session is None:
            return False
        deleted_parent = None
        if kind == "delete_node" and target is not None and target.block_id is None:
            before = self._session.report_snapshot()
            row = next((r for r in project_branch(before) if r.stable_id == target.module_id), None)
            deleted_parent = row.parent_module_id if row else None
        try:
            change = self._gateway.execute(CommandIntent(
                kind, target, args,
                self._session.revision if expected_revision is None else expected_revision,
                self._session.generation if expected_generation is None else expected_generation))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        reveal_insert_parent = False
        if change is not None:
            # Inserting through the toolbar into a collapsed container must
            # reveal the new block, not silently create invisible content.
            if kind in ("add_nested_module", "add_paragraph", "add_heading") and target is not None:
                reveal_insert_parent = target.module_id in self._collapsed
                self._collapsed.discard(target.module_id)
            new_id = next(iter(change.changed_ids))
            report_id = self._session.report_snapshot().id
            if kind in ("add_module", "add_nested_module"):
                self._selected_module_id = new_id
                self._restore = (NodeAddress(report_id, new_id), 0, -1)
            elif kind in ("add_paragraph", "add_heading"):
                self._selected_module_id = target.module_id
                self._restore = (NodeAddress(report_id, target.module_id, new_id, "text"), 0, 0)
            elif kind == "duplicate_node":
                if target.block_id is None:
                    self._selected_module_id = new_id
                    self._restore = (NodeAddress(report_id, new_id), 0, -1)
                else:
                    self._selected_module_id = target.module_id
                    self._restore = (NodeAddress(report_id, target.module_id, new_id, "text"), 0, 0)
                self.feedback.emit("Duplicated with fresh IDs — Undo is available")
            elif kind == "delete_node":
                if target.block_id is None:
                    self._selected_module_id = deleted_parent
                    if deleted_parent is None:
                        remaining = self._session.report_snapshot().modules
                        self._selected_module_id = remaining[0].id if remaining else None
                else:
                    self._selected_module_id = target.module_id
                self._restore = None
                self.feedback.emit("Deleted — Undo is available")
        self._refresh()
        if reveal_insert_parent:
            self.visibilityChanged.emit()
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

    def add_heading(self, *, module_id: str | None = None,
                    index: int | None = None, level: int = 2) -> bool:
        if self._session is None:
            return False
        owner = module_id if module_id is not None else self._selected_module_id
        if owner is None:
            self.feedback.emit("Select a module title first")
            return False
        args = {"text": "", "level": level}
        if index is not None:
            args["index"] = index
        return self._run("add_heading",
                         NodeAddress(self._session.report_snapshot().id, owner),
                         **args)

    def insert_heading_after(self, address: NodeAddress) -> bool:
        """Insert into the exact mixed-order slot after a visible content leaf."""
        if self._session is None or not isinstance(address, NodeAddress):
            return False
        report = self._session.report_snapshot()
        if address.report_id != report.id or address.block_id is None:
            return False
        try:
            from ..projections import find_node
            container = find_node(report, NodeAddress(report.id, address.module_id))
            slot = next(i for i, block in enumerate(container.blocks)
                        if block.id == address.block_id)
        except (LookupError, StopIteration, ValueError):
            return False
        return self.add_heading(module_id=address.module_id, index=slot + 1)

    def _sibling_move_target(self, offset: int):
        """Find an adjacent *mixed* sibling without modifying the report."""
        if self._session is None or self._selected_module_id is None:
            return None
        report = self._session.report_snapshot()
        rows = project_branch(report)
        selected = next((row for row in rows
                         if row.stable_id == self._selected_module_id
                         and row.kind == "module"), None)
        if selected is None:
            return None
        siblings = sorted(
            (row for row in rows if row.parent_module_id == selected.parent_module_id
             and row.kind not in ("root", "conclusion")),
            key=lambda row: row.mixed_sibling_index,
        )
        current = next(i for i, row in enumerate(siblings)
                       if row.stable_id == selected.stable_id)
        other = current + offset
        if other < 0 or other >= len(siblings):
            return None
        return report, selected, siblings[other]

    def can_move_selected(self, offset: int) -> bool:
        """Same boundary policy for toolbar/shortcuts as for the command."""
        return self._sibling_move_target(offset) is not None

    def _move_selected_sibling(self, offset: int) -> bool:
        """Move selected module by one *mixed* sibling slot via the gateway."""
        move = self._sibling_move_target(offset)
        if move is None:
            self.feedback.emit("Select a module with an adjacent sibling to move")
            return False
        report, selected, neighbor = move
        anchor = (NodeAddress(report.id, neighbor.stable_id)
                  if neighbor.kind == "module"
                  else NodeAddress(report.id, neighbor.parent_module_id,
                                   neighbor.stable_id, "text"))
        return self._run("move_node", NodeAddress(report.id, selected.stable_id),
                         anchor=anchor, position="before" if offset < 0 else "after")

    def move_selected_up(self) -> bool:
        return self._move_selected_sibling(-1)

    def move_selected_down(self) -> bool:
        return self._move_selected_sibling(1)

    def _selected_address(self):
        if self._session is None or self._selected_module_id is None:
            return None
        return NodeAddress(self._session.report_snapshot().id, self._selected_module_id)

    def _planned_indent(self, address, *, outdent=False):
        if self._session is None or address is None:
            return None
        try:
            report = self._session.report_snapshot()
            return (plan_outdent if outdent else plan_indent)(report, address)
        except (ValueError, LookupError):
            return None

    def can_indent_selected(self) -> bool:
        return self._planned_indent(self._selected_address()) is not None

    def can_outdent_selected(self) -> bool:
        return self._planned_indent(self._selected_address(), outdent=True) is not None

    def _structural_move(self, address, *, outdent=False) -> bool:
        planned = self._planned_indent(address, outdent=outdent)
        if planned is None:
            self.feedback.emit("Outdent requires a nested module" if outdent
                               else "Indent requires an immediately preceding module")
            return False
        anchor, position = planned
        return self._run("move_node", address, anchor=anchor, position=position)

    def indent_selected(self) -> bool:
        return self._structural_move(self._selected_address())

    def outdent_selected(self) -> bool:
        return self._structural_move(self._selected_address(), outdent=True)

    def can_duplicate_selected(self) -> bool:
        return self._can_act_on(self._selected_address())

    def can_delete_selected(self) -> bool:
        return self._can_act_on(self._selected_address())

    def _can_act_on(self, address) -> bool:
        if self._session is None or address is None:
            return False
        try:
            structural_node(self._session.report_snapshot(), address)
            return True
        except (ValueError, LookupError):
            return False

    def duplicate_node(self, address) -> bool:
        return self._run("duplicate_node", address)

    def duplicate_selected(self) -> bool:
        return self.duplicate_node(self._selected_address())

    def delete_node(self, address) -> bool:
        if self._session is None:
            return False
        try:
            self._session.require_clean_drafts()
            before = self._session.report_snapshot()
            node = structural_node(before, address)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        revision, generation = self._session.revision, self._session.generation
        kind = "module and its contents" if node.kind == "module" else f"{node.kind} block"
        answer = QMessageBox.question(
            self, "Confirm delete", f"Delete this {kind}?\n\n"
            "This removes the report placement, not the original media file. "
            "You can undo this change.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        # A modal dialog enters a nested event loop. Validate the original
        # generation/revision, not a newly loaded or edited report's revision.
        return self._run("delete_node", address, expected_revision=revision,
                         expected_generation=generation)

    def delete_selected(self) -> bool:
        return self.delete_node(self._selected_address())

    def _context_menu(self, address, global_position) -> None:
        if not self._can_act_on(address):
            return
        self._selected_module_id = address.module_id
        self.selectionChanged.emit()
        menu = QMenu(self)
        if address.block_id is None:
            toggle = menu.addAction("Expand branch" if address.module_id in self._collapsed
                                    else "Collapse branch")
            toggle.triggered.connect(lambda: self.toggle_branch(address.module_id))
            menu.addSeparator()
            indent = menu.addAction("Indent under previous module")
            indent.setEnabled(self._planned_indent(address) is not None)
            indent.triggered.connect(lambda: self._structural_move(address))
            outdent = menu.addAction("Outdent after parent")
            outdent.setEnabled(self._planned_indent(address, outdent=True) is not None)
            outdent.triggered.connect(lambda: self._structural_move(address, outdent=True))
            menu.addSeparator()
        if address.block_id is None:
            insert = menu.addAction("Insert heading inside")
            insert.triggered.connect(
                lambda checked=False, mid=address.module_id:
                self.add_heading(module_id=mid))
        else:
            insert = menu.addAction("Insert heading after")
            insert.triggered.connect(
                lambda checked=False, a=address: self.insert_heading_after(a))
        menu.addSeparator()
        duplicate = menu.addAction("Duplicate")
        duplicate.triggered.connect(lambda: self.duplicate_node(address))
        delete = menu.addAction("Delete…")
        delete.triggered.connect(lambda: self.delete_node(address))
        menu.exec(global_position)

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

    def _sync_active_ribbon(self) -> None:
        focused = next((
            (address, editor) for address, editor in self._editors.items()
            if isinstance(editor, InlineParagraph) and editor.hasFocus()
        ), None)
        if focused is not None:
            address, editor = focused
            self._ensure_ribbon(address, editor)
        for address, (ribbon, _) in self._ribbons.items():
            ribbon.setVisible(focused is not None and address == focused[0])
        if focused is not None:
            self._sync_ribbon(focused[0])

    def _ensure_ribbon(self, address, editor) -> None:
        if address in self._ribbons:
            return
        card = editor.parentWidget()
        ribbon = QWidget(card)
        ribbon.setObjectName("v2RichRibbon")
        ribbon.setStyleSheet(
            "QWidget#v2RichRibbon { background: #eaf0f8; border-radius: 5px; }"
            "QToolButton { color: #183750; background: #ffffff;"
            " border: 1px solid #aabbd0; border-radius: 4px; padding: 3px 6px; }"
            "QToolButton:checked { background: #9cc5fc; border: 2px solid #1d5fbc; }"
            "QToolButton:disabled { color: #94a3b8; }")
        rows = QVBoxLayout(ribbon)
        rows.setContentsMargins(5, 5, 5, 5)
        rows.setSpacing(3)
        buttons = {}

        def add_button(line, name, symbol, description, action, *, checked=False):
            button = QToolButton(ribbon)
            button.setObjectName(name)
            button.setText(symbol)
            button.setToolTip(description)
            button.setAccessibleName(description)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            button.setCheckable(checked)
            button.clicked.connect(action)
            line.addWidget(button)
            buttons[name] = button

        char = QHBoxLayout()
        char.setSpacing(3)
        for field, symbol, name, description in (
            ("bold", "B", "v2RichBold", "Bold selected text"),
            ("italic", "I", "v2RichItalic", "Italic selected text"),
            ("underline", "U̲", "v2RichUnderline", "Underline selected text"),
            ("strike", "S̶", "v2RichStrike", "Strike through selected text"),
        ):
            add_button(char, name, symbol, description,
                       lambda checked=False, a=address, f=field:
                       self._format_inline(a, f), checked=True)
        add_button(char, "v2RichSmaller", "A−", "Decrease selected font size",
                   lambda checked=False, a=address: self._resize_inline(a, -2))
        add_button(char, "v2RichLarger", "A+", "Increase selected font size",
                   lambda checked=False, a=address: self._resize_inline(a, 2))
        char.addStretch(1)
        rows.addLayout(char)

        paragraph = QHBoxLayout()
        paragraph.setSpacing(3)
        for align, symbol, name in (
            ("left", "⇤", "v2RichAlignLeft"),
            ("center", "≡", "v2RichAlignCenter"),
            ("right", "⇥", "v2RichAlignRight"),
            ("justify", "☷", "v2RichAlignJustify"),
        ):
            add_button(paragraph, name, symbol, "Align " + align,
                       lambda checked=False, a=address, v=align:
                       self._format_paragraph(a, "align", v), checked=True)
        add_button(paragraph, "v2RichBullets", "• List", "Toggle bullet list",
                   lambda checked=False, a=address:
                   self._format_paragraph(a, "list_kind", "bullet", toggle=True),
                   checked=True)
        add_button(paragraph, "v2RichNumbers", "1. List", "Toggle numbered list",
                   lambda checked=False, a=address:
                   self._format_paragraph(a, "list_kind", "decimal", toggle=True),
                   checked=True)
        paragraph.addStretch(1)
        rows.addLayout(paragraph)
        card.layout().insertWidget(1, ribbon)
        ribbon.hide()
        self._ribbons[address] = ribbon, buttons

    def _selected_rich(self, address):
        editor = self._editors.get(address)
        if not isinstance(editor, InlineParagraph) or self.drafts is None:
            raise ValueError("Inline rich-text editor is no longer active")
        cursor = editor.textCursor()
        value = editor.toPlainText()
        start = to_codepoint(value, cursor.selectionStart())
        end = to_codepoint(value, cursor.selectionEnd())
        return editor, value, start, end, self.drafts.rich(address)

    def _stage_format(self, address, start, end, field, value, *, paragraph=False):
        try:
            changed = self.drafts.format(
                address, start, end, field, value, paragraph=paragraph)
            if changed:
                editor = self._editors.get(address)
                if editor is not None:
                    paint_rich(editor, editor.toPlainText(), self.drafts.rich(address))
                self.feedback.emit("Unapplied formatting — Apply or Revert before Save/Undo")
                # The Apply/Revert bar must also appear for formatting-only drafts.
                bar = self._draft_bars.get(address)
                if bar is not None:
                    bar.setVisible(self.drafts.is_dirty(address))
            self._sync_ribbon(address)
            return changed
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _format_inline(self, address, field):
        try:
            _, text, start, end, rich = self._selected_rich(address)
            if start == end:
                self.feedback.emit("Select text before applying character formatting")
                return False
            return self._stage_format(address, start, end, field,
                                      not selection_uniform(text, rich, start, end, field))
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _resize_inline(self, address, delta):
        try:
            _, text, start, end, rich = self._selected_rich(address)
            if start == end:
                self.feedback.emit("Select text before changing font size")
                return False
            present = style_at(rich, start)
            base = 16 if self._editors[address].objectName() == "v2InlineHeading" else 14
            old_size = present.size if present is not None and present.size else base
            size = max(6, min(96, old_size + delta))
            return self._stage_format(address, start, end, "size", size)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _format_paragraph(self, address, field, value, *, toggle=False):
        try:
            _, text, start, end, rich = self._selected_rich(address)
            if toggle and paragraph_uniform(text, rich, start, end, field, value):
                value = "none"
            return self._stage_format(
                address, start, end, field, value, paragraph=True)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _sync_ribbon(self, address) -> None:
        item = self._ribbons.get(address)
        if item is None or self.drafts is None:
            return
        ribbon, buttons = item
        if not ribbon.isVisible():
            return
        try:
            editor, text, start, end, rich = self._selected_rich(address)
            selected = end > start
            for name, field in (
                ("v2RichBold", "bold"), ("v2RichItalic", "italic"),
                ("v2RichUnderline", "underline"), ("v2RichStrike", "strike"),
            ):
                button = buttons[name]
                button.setEnabled(selected)
                button.setChecked(selection_uniform(text, rich, start, end, field)
                                  if selected else False)
            for name in ("v2RichSmaller", "v2RichLarger"):
                buttons[name].setEnabled(selected)
            for name, value in (
                ("v2RichAlignLeft", "left"), ("v2RichAlignCenter", "center"),
                ("v2RichAlignRight", "right"), ("v2RichAlignJustify", "justify"),
            ):
                buttons[name].setChecked(
                    paragraph_uniform(text, rich, start, end, "align", value))
            buttons["v2RichBullets"].setChecked(
                paragraph_uniform(text, rich, start, end, "list_kind", "bullet"))
            buttons["v2RichNumbers"].setChecked(
                paragraph_uniform(text, rich, start, end, "list_kind", "decimal"))
        except (ValueError, LookupError, RuntimeError):
            ribbon.hide()

    def _inline(self, card, address, kind, original):
        text = self.drafts.text(address)
        if kind in ("module", "conclusion"):
            editor = InlineTitle(card)
            editor.setObjectName("v2InlineTitle")
            editor.setText(text)
            editor.setStyleSheet("color: #182b3a; font-size: 15px; font-weight: bold;")
        else:
            editor = InlineParagraph(card)
            editor.setObjectName("v2InlineHeading" if kind == "heading" else "v2InlineParagraph")
            editor.setPlainText(text)
            editor.setTabChangesFocus(True)
            editor.setStyleSheet("color: #182b3a; font-size: 16px; font-weight: bold;"
                                 if kind == "heading" else
                                 "color: #182b3a; font-size: 14px;")
            try:
                staged_rich = self.drafts.rich(address)
            except ValueError:
                # An unsafe edit of a styled paragraph boundary must remain
                # visible and revertible. Commit will reject it without losing
                # either the canonical model or the pending draft.
                staged_rich = RichFormatting()
            paint_rich(editor, text, staged_rich)
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
        self._draft_bars[address] = buttons
        if isinstance(editor, QLineEdit):
            editor.textEdited.connect(lambda t, a=address, b=buttons: self._changed(a, t, b))
            editor.returnPressed.connect(lambda a=address: self.apply_draft(a))
        else:
            editor.textChanged.connect(lambda e=editor, a=address, b=buttons:
                                       self._changed(a, e.toPlainText(), b))
            editor.commitRequested.connect(lambda a=address: self.apply_draft(a))
            editor.cursorPositionChanged.connect(lambda a=address: self._sync_ribbon(a))
            editor.selectionChanged.connect(lambda a=address: self._sync_ribbon(a))
            editor.formatRequested.connect(
                lambda field, a=address: self._format_inline(a, field))
        editor.cancelRequested.connect(lambda a=address: self.revert_draft(a))
        card.layout().addWidget(editor)
        card.layout().addWidget(buttons)

    def _render(self, report: Report):
        validate_report_tree(report)
        all_rows = project_branch(report)
        expanded = frozenset(row.stable_id for row in all_rows
                             if row.kind in ("module", "conclusion")
                             and row.stable_id not in self._collapsed)
        rows = tuple(_branch_rows(report, expanded=expanded))
        projection = project_branch(report, expanded=expanded,
                                    revision=self._session.revision if self._session else 0)
        numbers = {entry.module_id: entry.number for entry in module_outline(report)}
        summaries = descendant_counts(report)
        if len(rows) != len(projection) or any(a[0] != b.stable_id for a, b in zip(rows, projection)):
            raise ValueError("Branch layout diverged from canonical projection")
        scroll = self.verticalScrollBar().value()
        self._editors.clear()
        self._draft_bars.clear()
        self._ribbons.clear()
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for (identifier, kind, caption, text, depth, ancestors, has_next), meta in zip(rows, projection):
            address = (NodeAddress(report.id, identifier)
                       if kind in ("root", "module", "conclusion")
                       else NodeAddress(report.id, meta.parent_module_id, identifier, "text"))
            row = DropRow(self, address, kind, self._host)
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
            numbered = (f"MODULE {numbers[identifier]}" if kind == "module"
                        else caption)
            label = QLabel(numbered, card)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet("color: #526c83; font-size: 10px; font-weight: bold;")
            header = QHBoxLayout()
            header.setContentsMargins(0, 0, 0, 0)
            header.addWidget(label)
            header.addStretch(1)
            if kind in ("module", "conclusion"):
                toggle = QToolButton(card)
                toggle.setObjectName("v2ToggleBranch")
                toggle.setProperty("nodeId", identifier)
                toggle.setText("▸" if identifier in self._collapsed else "▾")
                toggle.setAccessibleName(("Expand " if identifier in self._collapsed
                                          else "Collapse ") + text)
                toggle.setToolTip("Show or hide branch descendants")
                toggle.clicked.connect(lambda checked=False, mid=identifier:
                                       self.toggle_branch(mid))
                header.addWidget(toggle)
            if kind not in ("root", "conclusion"):
                header.addWidget(DragHandle(self, address, card))
                options = QToolButton(card)
                options.setObjectName("v2NodeActions")
                options.setText("⋯")
                options.setToolTip(
                    "Indent, outdent, duplicate or delete" if kind == "module"
                    else "Duplicate or delete this content block"
                )
                options.clicked.connect(
                    lambda checked=False, a=address, b=options:
                    self._context_menu(a, b.mapToGlobal(b.rect().bottomLeft()))
                )
                header.addWidget(options)
                card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                card.customContextMenuRequested.connect(
                    lambda pt, a=address, c=card:
                    self._context_menu(a, c.mapToGlobal(pt))
                )
            card_layout.addLayout(header)
            if self.drafts is not None and kind in ("module", "conclusion", "paragraph", "heading"):
                address = (NodeAddress(report.id, identifier)
                           if kind in ("module", "conclusion")
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
            if kind in ("module", "conclusion") and identifier in self._collapsed:
                count = summaries[identifier]
                summary = QLabel(
                    f"{count.modules} submodules · {count.text} text · "
                    f"{count.photos} photos · {count.tables} tables · "
                    f"{count.page_breaks} breaks", card,
                )
                summary.setObjectName("v2CollapsedSummary")
                summary.setTextFormat(Qt.TextFormat.PlainText)
                summary.setStyleSheet("color: #526c83; font-size: 11px;")
                card_layout.addWidget(summary)
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
