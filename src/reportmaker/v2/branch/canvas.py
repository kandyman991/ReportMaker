"""Connected M1.3 Branch Editor with guarded inline titles and paragraphs.

The single canonical report drives visible order and connectors. Widgets hold
only drafts; no V1 UI, parallel report model or browser is imported here.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from math import ceil
import re
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QCoreApplication, QEvent, QMimeData, QPoint, QPointF, QRect, QSize, Qt, QTimer, Signal, QUrl
from PySide6.QtGui import QColor, QDrag, QImage, QPalette, QPixmap, QPainter, QPen, QTextCursor, QTextOption, QWheelEvent
from PySide6.QtWidgets import (
    QAbstractButton, QApplication, QFileDialog, QInputDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLayout, QLineEdit,
    QPlainTextEdit, QDialog, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from ...engine import module_outline, validate_report_tree
from ...media_import import (INPUT_SUFFIXES, PictureImportError,
                             convert_picture, convert_picture_bytes, stage_pictures)
from ...photo_gallery import clipboard_image_png, local_picture_paths
from ..editing_keys import handle_plain_paste
from ...photo_editor import render_photo
from .photo_tools import V2PictureEditorDialog as PictureEditorDialog
from ...rich_text import RichFormatting, style_at
from ..adapters.formatting import (
    paragraph_uniform, selection_uniform, to_codepoint,
)
from ..contrast import BUTTON_CHROME, FIELD_CHROME
from .rich_preview import paint_rich
from ...model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, PhotoVisual, Report, TableBlock,
)

from ..commands import CommandGateway, CommandIntent
from ..navigation import search_report, subtree_range, window_for
from ..drafts import DraftCoordinator
from ..projections import NodeAddress, descendant_counts, find_node, project_branch
from ..session import StaleIntentError, PendingDraftError, ReportSession
from ..structure import plan_drop, plan_indent, plan_outdent, structural_node

_STEP = 25
# Indentation per nesting level may shrink to this (before zoom) so a deeply
# nested module still leaves its card readable instead of scrolling off-screen.
_MIN_STEP = 6
# Side margin of the canvas (each side). It may shrink to this, but only after the
# indentation is already at its minimum and the deepest card still does not fit.
_SIDE_MARGIN = 20
_MIN_SIDE_MARGIN = 8
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


class ElidedLabel(QLabel):
    """A caption that shortens itself in the middle instead of widening its card.

    The numbered caption of a deeply nested module ("MODULE 1.1.1.1.1.1.1...") grows by
    two characters per level. As a plain QLabel its full width became the card's minimum
    width, which pushed a deep card past the right edge on exactly the machines whose
    font was a little wider. The full text stays in the tooltip and the accessible name.
    """

    _KEEP = 12  # characters that always stay readable

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full = text
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setAccessibleName(text)

    def full_text(self) -> str:
        return self._full

    def sizeHint(self) -> QSize:
        size = super().sizeHint()
        size.setWidth(self.fontMetrics().horizontalAdvance(self._full) + 2 * self.margin() + 2)
        return size

    def minimumSizeHint(self) -> QSize:
        size = super().minimumSizeHint()
        short = self._full[:self._KEEP] + ("…" if len(self._full) > self._KEEP else "")
        size.setWidth(self.fontMetrics().horizontalAdvance(short) + 2 * self.margin() + 2)
        return size

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        available = max(1, self.width() - 2 * self.margin() - 2)
        shown = self.fontMetrics().elidedText(self._full, Qt.TextElideMode.ElideMiddle, available)
        if shown != self.text():
            super().setText(shown)
        self.setToolTip(self._full if shown != self._full else "")

    def setText(self, text: str) -> None:
        self._full = text
        self.setAccessibleName(text)
        super().setText(text)
        self.updateGeometry()


class ConnectorGutter(QWidget):
    """Draw explicit parent/child lines without changing report structure."""

    def __init__(self, depth: int, ancestors: tuple[bool, ...], has_next: bool,
                 parent: QWidget | None = None, *, zoom_pct: int = 100) -> None:
        super().__init__(parent)
        self._depth = depth
        self._ancestors = ancestors
        self._has_next = has_next
        self._base = max(1, round(18 * zoom_pct / 100))
        self._origin = max(1, round(11 * zoom_pct / 100))
        self._full_elbow = max(1, round(16 * zoom_pct / 100))
        self._step = 0
        self.set_step(max(1, round(_STEP * zoom_pct / 100)))
        self.setMinimumHeight(48)

    @property
    def step(self) -> int:
        return self._step

    @property
    def depth(self) -> int:
        return self._depth

    def set_step(self, step: int) -> None:
        """Indentation per level; the canvas narrows it when the window is tight."""
        step = max(1, int(step))
        if step == self._step:
            return
        self._step = step
        # Never collapse connector geometry into the same position at depth.
        self.setFixedWidth(self._base + step * max(0, self._depth))
        self._elbow = max(1, min(self._full_elbow, step + self._base - self._origin - 2))
        self.update()

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
                x = self._origin + self._step * level
                painter.drawLine(x, 0, x, self.height())
        level = self._depth - 1
        x = self._origin + self._step * level
        painter.drawLine(x, 0, x, middle)
        painter.drawLine(x, middle, x + self._elbow, middle)
        if self._has_next:
            painter.drawLine(x, middle, x, self.height())
        painter.end()


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
        if handle_plain_paste(self, event):
            return
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


class InlineTitle(InlineParagraph):
    """A module title: one logical line that wraps instead of being cut off.

    A QLineEdit cannot wrap, so a long title was silently truncated by the
    card. This reuses the natural-height paragraph editor and keeps the small
    part of the QLineEdit API the canvas and its callers use (``text``,
    ``setText``, ``selectedText``, ``setSelection``, ``textEdited``,
    ``returnPressed``). Titles never contain line
    breaks and carry no character formatting.
    """

    returnPressed = Signal()
    textEdited = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._programmatic = False
        self.setTabChangesFocus(True)
        self.textChanged.connect(self._user_text_changed)

    def text(self) -> str:
        return self.toPlainText()

    def setText(self, value: str) -> None:
        # Like QLineEdit.setText: no textEdited signal, caret at the end.
        self._programmatic = True
        try:
            self.setPlainText(_single_line(value))
        finally:
            self._programmatic = False
        self.moveCursor(QTextCursor.MoveOperation.End)

    def selectedText(self) -> str:
        return self.textCursor().selectedText()

    def setSelection(self, start: int, length: int) -> None:
        cursor = self.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(start + length, QTextCursor.MoveMode.KeepAnchor)
        self.setTextCursor(cursor)

    def _user_text_changed(self) -> None:
        if not self._programmatic:
            self.textEdited.emit(self.text())

    def insertFromMimeData(self, source) -> None:
        if source.hasText():
            self.insertPlainText(_single_line(source.text()))

    def keyPressEvent(self, event):
        if handle_plain_paste(self, event):  # Ctrl+Shift+V pastes plain text
            return
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.cancelRequested.emit()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.returnPressed.emit()
        elif (event.modifiers() == Qt.KeyboardModifier.ControlModifier
              and key in (Qt.Key.Key_B, Qt.Key.Key_I, Qt.Key.Key_U)):
            pass  # titles have no bold/italic/underline
        else:
            QPlainTextEdit.keyPressEvent(self, event)
            return
        event.accept()


def _single_line(value: str) -> str:
    for separator in ("\r\n", "\r", "\n", "\u2028", "\u2029"):
        value = value.replace(separator, " ")
    return value


class PhotoThumbnail(QWidget):
    """Responsive, intrinsic-height, non-scrolling photo view.

    Only the shared project's immutable asset is decoded; each placement's
    visual is independently rendered with annotations and transformations.
    Qt layouts measure heightForWidth rather than a fixed image-card height.
    """

    def __init__(self, image: QImage, width_pct: int, alignment: str, parent=None,
                 *, zoom_pct: int = 100):
        super().__init__(parent)
        self._image = image
        self._width_pct = width_pct
        self._alignment = alignment
        self._zoom_pct = zoom_pct
        self.setObjectName("v2PhotoThumbnail")
        self.setAccessibleName("Project-owned photo preview")
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def heightForWidth(self, width: int) -> int:
        if self._image.isNull():
            return 28
        draw_width = max(1, min(self._image.width() * self._zoom_pct // 100,
                                width * self._width_pct // 100))
        return max(1, round(draw_width * self._image.height() / self._image.width()))

    def sizeHint(self) -> QSize:
        return QSize(450, self.heightForWidth(450))

    def minimumSizeHint(self) -> QSize:
        return QSize(1, self.heightForWidth(1))

    def paintEvent(self, event):
        if self._image.isNull():
            return
        draw_width = max(1, min(self._image.width() * self._zoom_pct // 100,
                                self.width() * self._width_pct // 100))
        draw_height = min(self.height(), self.heightForWidth(self.width()))
        x = (0 if self._alignment == "left" else
             max(0, self.width() - draw_width) if self._alignment == "right" else
             max(0, (self.width() - draw_width) // 2))
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(QRect(x, 0, draw_width, draw_height), self._image)
        painter.end()


@dataclass(frozen=True)
class _DragContext:
    """An unforgeable in-process drag, with a frozen revision/generation."""

    token: str
    source: NodeAddress
    revision: int
    generation: str


class DragHandle(QToolButton):
    """Explicit drag gesture; mouse selection in text editors is unaffected."""

    FULL_TEXT = "≡ Drag"
    COMPACT_TEXT = "≡"  # when the canvas is too narrow for the word; same tooltip and name

    def set_compact(self, compact: bool) -> None:
        self.setText(self.COMPACT_TEXT if compact else self.FULL_TEXT)

    def __init__(self, canvas: "BranchCanvas", address: NodeAddress, parent=None):
        super().__init__(parent)
        self._canvas, self._address = canvas, address
        self._press_position = None
        self.setObjectName("v2DragHandle")
        self.setText(self.FULL_TEXT)
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
        """Put the label where it hides none of this card's own buttons.

        The coloured edge line is painted by the row itself; the label only
        names the position. It prefers the right edge but slides left past any
        button it would cover, and drops below the header if the row is too
        narrow for that.
        """
        if self._position is None:
            return
        width, height = self.marker.width(), self.marker.height()
        blocked = [QRect(button.mapTo(self, QPoint(0, 0)), button.size())
                   for button in self.findChildren(QAbstractButton)
                   if button.isVisibleTo(self)]
        ideal = (0 if self._position == "before"
                 else self.height() - height if self._position == "after"
                 else (self.height() - height) // 2)
        gap = 6
        candidates = [max(0, ideal)]
        # Below the lowest button that shares the ideal band, or above for "after".
        band = [b for b in blocked if b.bottom() >= candidates[0]
                and b.top() <= candidates[0] + height]
        if band:
            candidates.append(max(b.bottom() for b in band) + 2)
            candidates.append(max(0, min(b.top() for b in band) - height - 2))
        for y in candidates:
            x = self.width() - width - gap
            while x >= 0:
                spot = QRect(x, y, width, height)
                hit = next((b for b in blocked if b.intersects(spot)), None)
                if hit is None:
                    self.marker.move(x, y)
                    return
                x = hit.left() - width - gap
        self.marker.move(gap, max(0, ideal))

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
        # Do not reset the frozen revision when the cursor crosses adjacent
        # branch rows during one native drag.
        self._canvas._clear_drop_preview(self)
        event.accept()

    def dropEvent(self, event):
        self._canvas._commit_drop(self, event)


class BranchCanvas(QScrollArea):
    """Read-only geometry, editable source text; commands own all mutations."""
    feedback = Signal(str)
    selectionChanged = Signal()
    visibilityChanged = Signal()

    def __init__(self, parent: QWidget | None = None, *, owner: str = "branch") -> None:
        super().__init__(parent)
        if not isinstance(owner, str) or not owner.strip():
            raise ValueError("A Modules canvas needs a nonempty draft owner id")
        # The id under which this canvas stages drafts. Several canvases can show
        # the same report at once; each stages under its own id so that two of
        # them can never silently overwrite one field's draft.
        self._owner = owner
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
        self._unsubscribe_pending = None
        self._unsubscribe_changes = None
        self._editors = {}
        self._draft_bars = {}
        self._pending_panel = None
        self._pending_message = None
        self._table_cells = {}
        self._table_selected = {}
        self._ribbons = {}
        self._gutters: list[ConnectorGutter] = []
        self._rows: list[DropRow] = []
        self._card_layouts: list[QVBoxLayout] = []
        self._handles: list[DragHandle] = []
        self._compact_level = 0
        self._fitting = False
        # Another editor changed which fields it holds drafts for: redraw
        # once typing pauses so those fields turn read-only here.
        self._foreign_timer = QTimer(self)
        self._foreign_timer.setSingleShot(True)
        self._foreign_timer.setInterval(250)
        self._foreign_timer.timeout.connect(self._refresh_foreign_state)
        self._foreign_stale = False
        self._selected_module_id = None
        self._collapsed: set[str] = set()
        # Transient navigation only. Never enter the canonical report or export.
        self._focus_id: str | None = None
        self._focus_saved = None
        self._page = 0
        self._page_size = 120
        self._page_count = 1
        self._zoom_pct = 100
        self._search_hits = ()
        self._search_index = -1
        self._search_target = None
        self._search_query = ""
        self._restore = None
        self._drag_context = None
        self._native_drag_active = False
        self._drag_refresh_pending = False
        self._external_drag = None
        self._external_mime = None
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
        """TOC jump, including a hidden window or collapsed ancestor."""
        if self._session is None:
            return False
        if not any(r.stable_id == module_id and r.kind in ("module", "conclusion")
                   for r in project_branch(self._session.report_snapshot())):
            return False
        return self.reveal_node(module_id)

    def _scroll_to_module(self, module_id: str) -> None:
        if self._session is None:
            return
        for row in self._host.findChildren(DropRow):
            if row.kind in ("module", "conclusion") and row.address.module_id == module_id:
                top = row.mapTo(self._host, QPoint(0, 0)).y()
                self.verticalScrollBar().setValue(max(0, top - 28))
                return

    @property
    def focus_module_id(self) -> str | None:
        return self._focus_id

    @property
    def zoom_percent(self) -> int:
        return self._zoom_pct

    @property
    def active_row_count(self) -> int:
        return len(self._visible_nodes)

    @property
    def page_count(self) -> int:
        return self._page_count

    def focus_module(self, module_id: str | None = None) -> bool:
        """Isolate a canonical subtree and remember the former canvas context."""
        if self._session is None:
            return False
        rows = project_branch(self._session.report_snapshot())
        module_id = module_id or self._selected_module_id
        if not any(r.stable_id == module_id and r.kind in ("module", "conclusion")
                   for r in rows):
            return False
        try:
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        if self._focus_id is None:
            self._focus_saved = (self._selected_module_id,
                                 self.verticalScrollBar().value(),
                                 self.horizontalScrollBar().value(),
                                 frozenset(self._collapsed), self._page)
        self._focus_id = module_id
        by_id = {row.stable_id: row for row in rows}
        ancestor = module_id
        while ancestor is not None:
            self._collapsed.discard(ancestor)
            ancestor = by_id[ancestor].parent_module_id
        self._selected_module_id = module_id
        self._restore = None
        self._page = 0
        self._refresh()
        self.verticalScrollBar().setValue(0)
        self.visibilityChanged.emit()
        return True

    def exit_focus(self) -> bool:
        if self._focus_id is None:
            return False
        try:
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        selected, scroll, horizontal, collapsed, page = self._focus_saved
        self._focus_id = None
        self._focus_saved = None
        self._selected_module_id = selected
        self._collapsed = set(collapsed)
        self._page = page
        self._restore = None
        self._refresh()
        self.verticalScrollBar().setValue(scroll)
        self.horizontalScrollBar().setValue(horizontal)
        generation = self._session.generation
        # Let Qt finish the new layout before restoring both pan axes.
        # Do not replay this callback after another page/focus transition.
        QTimer.singleShot(0, lambda vertical=scroll, horizontal=horizontal,
                          gen=generation, saved_page=page:
                          (self.verticalScrollBar().setValue(vertical),
                           self.horizontalScrollBar().setValue(horizontal))
                          if (self._session.generation == gen and self._focus_id is None
                              and self._page == saved_page) else None)
        self.visibilityChanged.emit()
        return True

    def change_page(self, direction: int) -> bool:
        """Deterministic bounded-widget navigation, never dropping pending drafts."""
        if direction not in (-1, 1) or not 0 <= self._page + direction < self._page_count:
            return False
        try:
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        self._page += direction
        self._restore = None
        self._refresh()
        self.verticalScrollBar().setValue(0)
        return True

    def set_zoom(self, percent: int) -> bool:
        if type(percent) is not int or not 55 <= percent <= 160:
            raise ValueError("Canvas zoom must be 55–160%")
        if percent == self._zoom_pct:
            return True
        try:
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        self._zoom_pct = percent
        self._restore = None
        self._refresh()
        return True

    def zoom_by(self, delta: int) -> bool:
        return self.set_zoom(max(55, min(160, self._zoom_pct + delta)))

    def pan_by(self, delta: int) -> None:
        if type(delta) is not int:
            raise ValueError("Invalid canvas pan distance")
        scroll = self.horizontalScrollBar()
        scroll.setValue(scroll.value() + delta)

    def fit_to_screen(self) -> bool:
        if self._session is None:
            return False
        report = self._session.report_snapshot()
        rows = project_branch(report)
        if self._focus_id is not None:
            start, end = subtree_range(rows, self._focus_id)
            rows = rows[start:end]
        # Fit content width, not DOCX page dimensions or picture layer scale.
        depth = max((row.depth - (rows[0].depth - 1 if self._focus_id else 0)
                     for row in rows), default=1)
        target = int(100 * max(200, self.viewport().width() - 50) /
                     max(450, 470 + depth * _STEP))
        return self.set_zoom(max(55, min(160, target)))

    def search(self, query: str):
        if self._session is None:
            return ()
        self._search_query = query
        self._search_hits = search_report(self._session.report_snapshot(), query)
        self._search_index = -1
        self._search_target = None
        if self._search_hits:
            self.next_match()
        return self._search_hits

    def next_match(self) -> bool:
        if not self._search_hits:
            return False
        next_index = (self._search_index + 1) % len(self._search_hits)
        hit = self._search_hits[next_index]
        if not self.reveal_node(hit.stable_id):
            return False
        self._search_index = next_index
        self.feedback.emit(f"Match {next_index + 1} of {len(self._search_hits)}")
        return True

    def reveal_node(self, stable_id: str) -> bool:
        """Reveal even a collapsed or windowed leaf, by stable canonical ID."""
        if self._session is None:
            return False
        full = project_branch(self._session.report_snapshot())
        by_id = {row.stable_id: row for row in full}
        target = by_id.get(stable_id)
        if target is None:
            return False
        # A simple TOC selection/scroll may safely move with an unapplied
        # draft: it does not reconstruct, commit or delete the live editor.
        if (stable_id in {row[0] for row in self._visible_nodes}
                and target.kind in ("module", "conclusion")
                and self.drafts is not None and self.drafts.pending):
            self._selected_module_id = stable_id
            self.selectionChanged.emit()
            generation = self._session.generation
            QTimer.singleShot(0, lambda ident=stable_id, gen=generation:
                              self._scroll_to_node(ident)
                              if self._session.generation == gen else None)
            return True
        try:
            self._session.require_clean_drafts()
        except PendingDraftError as exc:
            self.feedback.emit(str(exc))
            return False
        if self._focus_id is not None:
            start, end = subtree_range(full, self._focus_id)
            if not start <= full.index(target) < end and not self.exit_focus():
                return False
        parent = target.parent_module_id
        while parent is not None:
            self._collapsed.discard(parent)
            parent = by_id[parent].parent_module_id
        self._selected_module_id = (
            stable_id if target.kind in ("module", "conclusion")
            else target.parent_module_id)
        self._search_target = stable_id
        expanded = frozenset(r.stable_id for r in full
                             if r.kind in ("module", "conclusion")
                             and r.stable_id not in self._collapsed)
        visible = project_branch(self._session.report_snapshot(), expanded=expanded)
        if self._focus_id is not None:
            start, end = subtree_range(visible, self._focus_id)
            visible = visible[start:end]
        offset = next((i for i, row in enumerate(visible) if row.stable_id == stable_id), None)
        if offset is None:
            return False
        self._page = offset // self._page_size
        self._restore = None
        self._refresh()
        generation = self._session.generation
        QTimer.singleShot(0, lambda ident=stable_id, gen=generation:
                          self._scroll_to_node(ident) if self._session.generation == gen else None)
        self.visibilityChanged.emit()
        return True

    def _scroll_to_node(self, stable_id: str) -> None:
        for row in self._host.findChildren(DropRow):
            if row.address.block_id == stable_id or row.address.module_id == stable_id:
                top = row.mapTo(self._host, QPoint(0, 0)).y()
                self.verticalScrollBar().setValue(max(0, top - 25))
                return

    def select_adjacent_module(self, direction: int) -> bool:
        if direction not in (-1, 1) or self._session is None:
            return False
        rows = project_branch(self._session.report_snapshot())
        if self._focus_id is not None:
            start, end = subtree_range(rows, self._focus_id)
            rows = rows[start:end]
        ids = [r.stable_id for r in rows if r.kind in ("module", "conclusion")]
        if not ids:
            return False
        here = ids.index(self._selected_module_id) if self._selected_module_id in ids else 0
        new = here + direction
        return 0 <= new < len(ids) and self.reveal_node(ids[new])

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 10 if event.angleDelta().y() > 0 else -10
            if event.angleDelta().y() and self.zoom_by(delta):
                event.accept()
                return
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            scroll = self.horizontalScrollBar()
            scroll.setValue(scroll.value() - event.angleDelta().y())
            event.accept()
            return
        # Keep wheel/touchpad navigation useful across bounded row windows.
        # This advances only at a viewport boundary, never during a draft or
        # native drag, and never creates an unbounded set of live editors.
        direction = event.pixelDelta().y() or event.angleDelta().y()
        scroll = self.verticalScrollBar()
        if (direction < 0 and self._page < self._page_count - 1
                and scroll.value() >= scroll.maximum() - 1
                and not self._native_drag_active and self.change_page(1)):
            event.accept()
            return
        if (direction > 0 and self._page > 0 and scroll.value() == 0
                and not self._native_drag_active and self.change_page(-1)):
            generation = self._session.generation
            QTimer.singleShot(0, lambda gen=generation:
                              self.verticalScrollBar().setValue(
                                  self.verticalScrollBar().maximum())
                              if self._session.generation == gen else None)
            event.accept()
            return
        super().wheelEvent(event)

    def _zoom_row(self, row: QWidget) -> None:
        """Scale editor typography/labels while keeping report geometry untouched."""
        if self._zoom_pct == 100:
            return
        factor = self._zoom_pct / 100
        children = row.findChildren(QWidget)
        for child in reversed(children):
            css = child.styleSheet()
            if css and "font-size:" in css:
                child.setStyleSheet(re.sub(
                    r"font-size:\s*(\d+)px",
                    lambda m: f"font-size: {max(7, round(int(m.group(1)) * factor))}px", css))
            if isinstance(child, (QLineEdit, QPlainTextEdit)):
                font = child.font()
                if font.pointSizeF() > 0:
                    font.setPointSizeF(max(6, font.pointSizeF() * factor))
                    child.setFont(font)

    def editor_for(self, address: NodeAddress):
        return self._editors.get(address)

    @property
    def owner(self) -> str:
        return self._owner

    def bind_session(self, session: ReportSession, gateway: CommandGateway,
                     drafts: DraftCoordinator | None = None) -> None:
        """Show ``session``. A second canvas passes the first one's ``drafts`` so
        that the session has one draft guard and one view of every pending edit."""
        if self.drafts is not None and self.drafts.pending:
            raise PendingDraftError("Resolve drafts before switching sessions")
        self._detach()
        self._session, self._gateway = session, gateway
        self.drafts = drafts if drafts is not None else DraftCoordinator(session, gateway)
        self._unsubscribe_pending = self.drafts.subscribe_pending(
            lambda _pending: self._update_pending_panel())
        self._unsubscribe_changes = self.drafts.subscribe_changes(self._draft_changed)
        self._unsubscribe = session.subscribe(self._on_change)
        self._refresh()

    def _detach(self) -> None:
        for name in ("_unsubscribe", "_unsubscribe_pending", "_unsubscribe_changes"):
            stop = getattr(self, name, None)
            if stop is not None:
                stop()
                setattr(self, name, None)

    def can_dispose(self) -> bool:
        """False while this canvas still holds unapplied edits of its own."""
        return self.drafts is None or not self.drafts.pending_addresses(owner=self._owner)

    def dispose(self) -> None:
        """Stop listening before a closed copy of this canvas is deleted."""
        self._foreign_timer.stop()
        self._detach()

    def _on_change(self, change) -> None:
        # New/Open changes generation: never restore selection or caret from
        # the previous report, even if a stale Qt redraw was queued.
        if change is None:
            self._collapsed.clear()
            self._focus_id = None
            self._focus_saved = None
            self._page = 0
            self._search_hits = ()
            self._search_index = -1
            self._search_target = None
            self._search_query = ""
            self._selected_module_id = None
            self._restore = None
            self._drag_context = None
            self._external_drag = None
            self._external_mime = None
            self._clear_drop_preview()
        elif self._search_query:
            # A committed rename/delete invalidates stale results; the
            # canonical report remains the only source of search content.
            self._search_hits = search_report(
                self._session.report_snapshot(), self._search_query)
            self._search_index = -1
            if self._search_target not in {h.stable_id for h in self._search_hits}:
                self._search_target = None
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
            if self._focus_id is not None and self._focus_id not in module_ids:
                self._focus_id = None
                self._focus_saved = None
                self._page = 0
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
            if event.type() == QEvent.Type.FocusIn:
                cell = self._table_cells.get(watched)
                if cell is not None:
                    table_address, row_index, column_index = cell
                    self._table_selected[table_address] = (row_index, column_index)
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

    def _blocked_by_pending_edits(self) -> bool:
        """Offer visible recovery without auto-committing or discarding work."""
        if self.drafts is None or not self.drafts.pending:
            return False
        self.verticalScrollBar().setValue(0)
        self._update_pending_panel()
        self.feedback.emit(
            "Action blocked by unapplied edits — see the yellow Apply/Discard panel")
        return True

    def _arm_drag(self, source: NodeAddress) -> QMimeData | None:
        """Create an internal move token only for a live clean canonical node."""
        if self._session is None or self._blocked_by_pending_edits():
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
            self._external_drag = None
            self._external_mime = None
            self._clear_drop_preview()
            if self._drag_refresh_pending:
                self._drag_refresh_pending = False
                QTimer.singleShot(0, self._refresh)

    def _clear_drop_preview(self, row: DropRow | None = None) -> None:
        if row is not None and row is not self._preview_row:
            row.clear_indicator()
            return
        if self._preview_row is not None:
            try:
                self._preview_row.clear_indicator()
            except RuntimeError:
                pass  # A queued session redraw may already own this row's deletion.
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
        if (not event.mimeData().hasFormat(_INTERNAL_MOVE_MIME)
                and event.source() is None and event.mimeData().hasUrls()):
            self._preview_external_drop(row, event)
            return
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
        if (not event.mimeData().hasFormat(_INTERNAL_MOVE_MIME)
                and event.source() is None and event.mimeData().hasUrls()):
            self._commit_external_drop(row, event)
            return
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

    def _photo_drop_target(self, address: NodeAddress, position: str):
        """Resolve a native file drop to the same mixed canonical slots."""
        report = self._session.report_snapshot()
        if address.report_id != report.id:
            raise StaleIntentError("Drop belongs to an older project")
        rows = project_branch(report)
        row = next((entry for entry in rows
                    if entry.stable_id == (address.block_id or address.module_id)), None)
        if row is None or row.kind == "root":
            raise ValueError("Choose a module or content insertion location")
        if position == "inside" and row.kind in ("module", "conclusion"):
            return row.stable_id, len(find_node(report, NodeAddress(report.id, row.stable_id)).blocks)
        if position in ("before", "after") and row.parent_module_id is not None:
            return row.parent_module_id, row.mixed_sibling_index + (position == "after")
        raise ValueError("Drop inside a module, or before/after a content block")

    def _preview_external_drop(self, row: DropRow, event):
        # A new native MIME object marks a new drag gesture. Crossing between
        # rows with the same MIME must NOT silently renew a stale revision.
        mime = event.mimeData()
        if self._external_drag is None or mime is not self._external_mime:
            self._external_drag = (self._session.generation, self._session.revision)
            self._external_mime = mime
        position = row.position_at(event.position().y())
        paths, errors = local_picture_paths(event.mimeData())
        try:
            if event.source() is not None or not paths or errors:
                raise ValueError("; ".join(errors) or "Only local image file URLs are supported")
            if not (event.possibleActions() & Qt.DropAction.CopyAction):
                raise ValueError("Only copying image files is supported")
            if self._external_drag != (self._session.generation, self._session.revision):
                raise StaleIntentError("Report changed during external drag")
            self._session.require_clean_drafts()
            self._photo_drop_target(row.address, position)
            valid, reason = True, ""
        except (ValueError, LookupError, RuntimeError) as exc:
            valid, reason = False, str(exc)
        if self._preview_row is not row:
            self._clear_drop_preview()
        self._preview_row = row
        row.show_indicator(position, valid, reason)
        if valid:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        elif paths and not errors:
            # A supported local file may cross an invalid zone before an
            # acceptable one; keep native move feedback alive across rows.
            event.setDropAction(Qt.DropAction.IgnoreAction)
            event.accept()
        else:
            # Never swallow foreign/empty/remote HTML and URL payloads.
            event.ignore()

    def _commit_external_drop(self, row: DropRow, event):
        generation_revision = self._external_drag
        position = row.position_at(event.position().y())
        paths, errors = local_picture_paths(event.mimeData())
        self._clear_drop_preview()
        self._external_drag = None
        self._external_mime = None
        try:
            if (generation_revision is None
                    or generation_revision != (self._session.generation, self._session.revision)
                    or errors or not paths
                    or not (event.possibleActions() & Qt.DropAction.CopyAction)):
                raise StaleIntentError("Invalid or stale native image drop")
            self._session.require_clean_drafts()
            module_id, index = self._photo_drop_target(row.address, position)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.CopyAction)
        event.accept()
        gen, rev = generation_revision
        # Never retain a QDropEvent across the asynchronous image conversion.
        QTimer.singleShot(0, lambda captured=tuple(paths), mid=module_id,
                          at=index, g=gen, r=rev:
                          self.import_photo_paths(captured, module_id=mid, index=at,
                                                  expected_revision=r, expected_generation=g))

    def import_photo_paths(self, paths, *, module_id=None, index=None,
                           expected_revision=None, expected_generation=None) -> bool:
        """Convert validated local originals once, then commit an atomic batch."""
        if self._session is None:
            return False
        rev = self._session.revision if expected_revision is None else expected_revision
        gen = self._session.generation if expected_generation is None else expected_generation
        owner = self._selected_module_id if module_id is None else module_id
        if owner is None:
            self.feedback.emit("Select the destination module first")
            return False
        try:
            self._session.require_clean_drafts()
            if (gen, rev) != (self._session.generation, self._session.revision):
                raise StaleIntentError("Image selection belongs to an obsolete report")
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
            approved, errors = local_picture_paths(mime)
            if errors or len(approved) != len(paths) or not approved:
                raise PictureImportError("; ".join(errors) or "Invalid local file selection")
            staged = stage_pictures(approved)
            # The dialog/decoder may reenter event processing; freeze the
            # original revision and let the command gateway reject stale data.
            photos = tuple((item.name, item.photo.data) for item in staged)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Image import rejected: " + str(exc))
            return False
        return self._run("import_photos",
                         NodeAddress(self._session.report_snapshot().id, owner),
                         expected_revision=rev, expected_generation=gen,
                         photos=photos, **({} if index is None else {"index": index}))

    def _import_photo_after(self, address, *, expected_revision=None,
                            expected_generation=None):
        report = self._session.report_snapshot()
        if address.report_id != report.id:
            return False
        row = next((item for item in project_branch(report)
                    if item.stable_id == address.block_id
                    and item.parent_module_id == address.module_id), None)
        if row is None:
            return False
        return self.import_photo_dialog(
            module_id=address.module_id, index=row.mixed_sibling_index + 1,
            expected_revision=expected_revision, expected_generation=expected_generation)

    def import_photo_dialog(self, *, module_id=None, index=None,
                            expected_revision=None, expected_generation=None):
        if self._session is None or self._blocked_by_pending_edits():
            return False
        rev = self._session.revision if expected_revision is None else expected_revision
        gen = self._session.generation if expected_generation is None else expected_generation
        patterns = " ".join("*" + suffix for suffix in sorted(INPUT_SUFFIXES))
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import local pictures", "", f"Supported images ({patterns})")
        return (self.import_photo_paths(paths, module_id=module_id, index=index,
                                        expected_revision=rev, expected_generation=gen)
                if paths else False)

    def paste_photo(self, *, module_id=None, index=None):
        """Explicit native-image clipboard import; never parse browser HTML."""
        if self._session is None or self._blocked_by_pending_edits():
            return False
        rev, gen = self._session.revision, self._session.generation
        owner = self._selected_module_id if module_id is None else module_id
        if owner is None:
            self.feedback.emit("Select the destination module first")
            return False
        try:
            self._session.require_clean_drafts()
            mime = QApplication.clipboard().mimeData()
            if mime is None:
                raise PictureImportError("Clipboard does not contain native image data")
            if mime.hasImage():
                image = mime.imageData()
                if isinstance(image, QPixmap):
                    image = image.toImage()
                if not isinstance(image, QImage):
                    raise PictureImportError("Clipboard does not contain native pixels")
                # HTML may accompany native pixels, but is never examined.
                photo = convert_picture_bytes(clipboard_image_png(image))
                return self._run("import_photo",
                                 NodeAddress(self._session.report_snapshot().id, owner),
                                 expected_revision=rev, expected_generation=gen,
                                 image_bytes=photo.data, name="Clipboard photo",
                                 **({} if index is None else {"index": index}))
            paths, errors = local_picture_paths(mime)
            if errors or not paths:
                raise PictureImportError("Clipboard must contain native pixels or local image files")
            return self.import_photo_paths(paths, module_id=owner, index=index,
                                           expected_revision=rev, expected_generation=gen)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Image paste rejected: " + str(exc))
            return False

    def edit_photo(self, address: NodeAddress) -> bool:
        if self._session is None:
            return False
        rev, gen = self._session.revision, self._session.generation
        try:
            self._session.require_clean_drafts()
            photo = find_node(self._session.report_snapshot(), address)
            if not isinstance(photo, PhotoBlock):
                raise ValueError("Select a valid photo block")
            dialog = PictureEditorDialog(
                self, self._session.assets[photo.asset_id], photo.visual,
                self._session.report_snapshot().primary_language)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return False
            return self._run("set_photo_visual", address, visual=deepcopy(dialog.visual),
                             expected_revision=rev, expected_generation=gen)
        except (ValueError, LookupError, RuntimeError, KeyError) as exc:
            self.feedback.emit("Photo editing rejected: " + str(exc))
            return False

    def _confirm_visual_reset(self, address: NodeAddress) -> bool:
        photo = find_node(self._session.report_snapshot(), address)
        if not isinstance(photo, PhotoBlock):
            raise ValueError("Select a photo block")
        if photo.visual == PhotoVisual():
            return True
        answer = QMessageBox.question(
            self, "Reset photo edits?",
            "Replacing this photo will reset this placement's crop, rotation, "
            "scale, and editable annotations. The original project-owned image "
            "and its other placements will not change. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        return answer == QMessageBox.StandardButton.Yes

    def replace_photo_from_file(self, address: NodeAddress) -> bool:
        if self._session is None:
            return False
        rev, gen = self._session.revision, self._session.generation
        try:
            self._session.require_clean_drafts()
            if not self._confirm_visual_reset(address):
                return False
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        patterns = " ".join("*" + suffix for suffix in sorted(INPUT_SUFFIXES))
        path, _ = QFileDialog.getOpenFileName(
            self, "Replace with local photo", "", f"Supported images ({patterns})")
        if not path:
            return False
        try:
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(path)])
            approved, errors = local_picture_paths(mime)
            if errors or len(approved) != 1:
                raise PictureImportError("; ".join(errors) or "Unsafe local file")
            new_photo = convert_picture(approved[0])
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Photo replacement rejected: " + str(exc))
            return False
        return self._run("replace_photo_import", address,
                         expected_revision=rev, expected_generation=gen,
                         name=Path(path).stem, image_bytes=new_photo.data)

    def replace_photo(self, address: NodeAddress, *, asset_id: str | None = None) -> bool:
        if self._session is None:
            return False
        rev, gen = self._session.revision, self._session.generation
        try:
            self._session.require_clean_drafts()
            if not self._confirm_visual_reset(address):
                return False
            if asset_id is None:
                names = self._session.media_library
                choices = {f"{names.get(key, 'Project photo')} [{key}]": key
                           for key in sorted(self._session.assets)}
                if not choices:
                    raise ValueError("No approved project photos available")
                label, accepted = QInputDialog.getItem(
                    self, "Replace photo", "Use existing project-owned image:",
                    list(choices), 0, False)
                if not accepted:
                    return False
                asset_id = choices[label]
            return self._run("replace_photo", address, asset_id=asset_id,
                             expected_revision=rev, expected_generation=gen)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _photo_card(self, card: QFrame, address: NodeAddress, block: PhotoBlock):
        try:
            image = render_photo(self._session.assets[block.asset_id], block.visual, 1000)
            preview = PhotoThumbnail(image, block.visual.width_pct,
                                     block.visual.alignment, card,
                                     zoom_pct=self._zoom_pct)
            card.layout().addWidget(preview)
        except (ValueError, KeyError):
            note = QLabel("Image unavailable — check project-owned asset", card)
            note.setObjectName("v2PhotoAssetError")
            card.layout().addWidget(note)
        toolbar = QHBoxLayout()
        for caption, name, callback in (
            ("Edit photo", "v2PhotoEdit", lambda: self.edit_photo(address)),
            ("Replace", "v2PhotoReplace", lambda: self.replace_photo(address)),
            ("From file", "v2PhotoReplaceFile", lambda: self.replace_photo_from_file(address)),
        ):
            button = QPushButton(caption, card)
            button.setObjectName(name)
            button.setToolTip(caption + " (the pending edits must be applied first)")
            button.clicked.connect(lambda checked=False, cb=callback: cb())
            toolbar.addWidget(button)
        toolbar.addStretch(1)
        card.layout().addLayout(toolbar)
        caption_addr = NodeAddress(address.report_id, address.module_id,
                                   address.block_id, "caption")
        caption_editor = InlineParagraph(card)
        caption_editor.setObjectName("v2PhotoCaption")
        caption_editor.setPlaceholderText("Photo caption (optional)")
        # Native dark themes otherwise use a faint white placeholder on the
        # white branch/photo card. Keep a readable subdued dark hint.
        palette = caption_editor.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#536375"))
        caption_editor.setPalette(palette)
        caption_editor.setPlainText(self.drafts.text(caption_addr))
        stale = self.drafts.text_stale(caption_addr)
        external = self.drafts.draft_owner(caption_addr) not in (None, self._owner)
        caption_editor.setReadOnly(stale or external)
        if external and not stale:
            caption_editor.setProperty("foreignLocked", True)
        if stale or external:
            note = QLabel(("Caption changed while a draft was pending; copy text and Revert."
                           if stale and not external else
                           "Caption draft belongs to the other editor; resolve it there."),
                          card)
            note.setObjectName("v2PhotoDraftWarning")
            note.setWordWrap(True)
            card.layout().addWidget(note)
        self._editors[caption_addr] = caption_editor
        buttons = QWidget(card)
        layout = QHBoxLayout(buttons)
        apply = QPushButton("Apply caption", buttons)
        apply.setObjectName("v2ApplyPhotoCaption")
        revert = QPushButton("Revert caption", buttons)
        revert.setObjectName("v2RevertPhotoCaption")
        apply.setEnabled(not stale and not external)
        revert.setEnabled(not external)
        self._style_draft_buttons(apply, revert)
        layout.addWidget(apply)
        layout.addWidget(revert)
        layout.addStretch(1)
        buttons.setVisible(self.drafts.is_dirty(caption_addr))
        self._draft_bars[caption_addr] = buttons
        caption_editor.textChanged.connect(
            lambda e=caption_editor, a=caption_addr, b=buttons:
            self._changed(a, e.toPlainText(), b))
        caption_editor.commitRequested.connect(lambda a=caption_addr: self.apply_draft(a))
        caption_editor.cancelRequested.connect(lambda a=caption_addr: self.revert_draft(a))
        apply.clicked.connect(lambda checked=False, a=caption_addr: self.apply_draft(a))
        revert.clicked.connect(lambda checked=False, a=caption_addr: self.revert_draft(a))
        card.layout().addWidget(caption_editor)
        card.layout().addWidget(buttons)

    @staticmethod
    def _style_draft_buttons(apply: QPushButton, revert: QPushButton) -> None:
        """Keep Apply/Revert legible in native Windows light/dark themes."""
        apply.setStyleSheet(
            "QPushButton { color: #ffffff; background: #1d4ed8;"
            " border: 1px solid #1e40af; border-radius: 4px;"
            " padding: 5px 12px; font-weight: bold; }"
            "QPushButton:disabled { color: #4b5563; background: #e5e7eb;"
            " border-color: #9ca3af; }")
        revert.setStyleSheet(
            "QPushButton { color: #192d40; background: #ffffff;"
            " border: 1px solid #64748b; border-radius: 4px;"
            " padding: 5px 12px; font-weight: bold; }"
            "QPushButton:disabled { color: #6b7280; background: #e5e7eb; }")

    def _update_pending_panel(self) -> None:
        panel, message = self._pending_panel, self._pending_message
        if panel is None or message is None or self.drafts is None:
            return
        pending = self.drafts.pending_addresses()
        own = self.drafts.pending_addresses(owner=self._owner)
        if pending:
            message.setText(
                "UNAPPLIED EDITS — Insert, move, drag and Save are paused. "
                + (f"{len(own)} change(s) in Modules: Apply all to keep them "
                   "or Discard to revert them."
                   if own else "Edits belong to another tab; resolve them there.")
                + (" Pending Editor edits must also be resolved in Editor."
                   if len(own) != len(pending) and own else ""))
        panel.setVisible(bool(pending))
        apply = panel.findChild(QPushButton, "v2ApplyAllBranchDrafts")
        discard = panel.findChild(QPushButton, "v2DiscardAllBranchDrafts")
        if apply is not None:
            apply.setEnabled(bool(own))
        if discard is not None:
            discard.setEnabled(bool(own))

    def apply_all_branch_drafts(self) -> bool:
        """Atomic explicit approval; never auto-commit a toolbar or drag action."""
        if self.drafts is None:
            return False
        own = self.drafts.pending_addresses(owner=self._owner)
        if not own:
            self.feedback.emit("No Modules drafts to apply; check the Editor tab")
            return False
        try:
            self.drafts.commit_batch(own, owner=self._owner)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Edits retained; cannot apply: " + str(exc))
            self._update_pending_panel()
            return False
        self._refresh()
        self.feedback.emit("Module edits applied; Insert, drag and Save are available")
        return True

    def apply_all_drafts(self) -> str | None:
        """Apply every pending draft (all editors) as one undoable change.

        Called only for an explicit Save / Save As / New / Open / Close.
        Returns None when nothing is left pending, otherwise the reason the
        drafts could not be applied. On failure every draft is kept untouched.
        """
        if self.drafts is None or not self.drafts.pending:
            return None
        for address, editor in self._editors.items():
            if editor.hasFocus():
                self._capture(address)
                break
        try:
            self.drafts.apply_all()
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Edits retained; cannot apply: " + str(exc))
            self._update_pending_panel()
            return str(exc) or exc.__class__.__name__
        self._refresh()
        self._update_pending_panel()
        self.feedback.emit("Pending edits applied as one change — Undo available")
        return None

    def discard_all_drafts(self) -> None:
        """Remove only pending draft fields across editors after explicit choice."""
        if self.drafts is None or not self.drafts.pending:
            return
        self.drafts.discard_all()
        self._refresh()
        self._update_pending_panel()
        self.feedback.emit("Unapplied edits discarded by user request")

    def discard_all_branch_drafts(self) -> bool:
        """Require explicit confirmation before discarding uncommitted work."""
        if self.drafts is None:
            return False
        own = self.drafts.pending_addresses(owner=self._owner)
        if not own:
            return False
        answer = QMessageBox.question(
            self, "Discard unapplied Modules edits?",
            f"Discard {len(own)} unapplied edit(s) in Modules? "
            "These changes have not been saved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return False
        for address in own:
            self.drafts.discard(address, owner=self._owner)
        self._refresh()
        self.feedback.emit("Unapplied Modules edits discarded")
        return True

    def _changed(self, address, text, buttons):
        try:
            self.drafts.update(address, text, owner=self._owner)
            # A native editor may inherit nearby visual character formatting
            # while typing; the staged Unicode ranges are authoritative.
            # Highlighter-only refresh does not mutate Qt's text undo stack.
            editor = self._editors.get(address)
            if isinstance(editor, InlineParagraph) and address.field == "text":
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
            # A field owned by another editor must not keep rejected characters or stay
            # writable, even if its notification never arrived. Next turn: this runs
            # inside the editor's own textChanged.
            QTimer.singleShot(0, self.lock_foreign_fields)

    def _capture(self, address):
        editor = self._editors.get(address)
        if isinstance(editor, QPlainTextEdit):
            c = editor.textCursor()
            self._restore = (address, c.position(), c.anchor())

    def _restore_cursor(self):
        state, self._restore = self._restore, None
        if state is None:
            return
        address, position, anchor = state
        editor = self._editors.get(address)
        if isinstance(editor, QPlainTextEdit):
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
            change = self.drafts.commit(address, owner=self._owner)
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
        self.drafts.discard(address, owner=self._owner)
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
        except PendingDraftError:
            # A blocked toolbar command must reveal explicit recovery controls.
            self._blocked_by_pending_edits()
            return False
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit(str(exc))
            return False
        reveal_insert_parent = False
        if change is not None:
            # Inserting through the toolbar into a collapsed container must
            # reveal the new block, not silently create invisible content.
            if kind in ("add_nested_module", "add_paragraph", "add_heading", "add_table",
                        "add_page_break", "add_photo", "import_photo", "import_photos") and target is not None:
                reveal_insert_parent = target.module_id in self._collapsed
                self._collapsed.discard(target.module_id)
            new_id = next(iter(change.changed_ids))
            report_id = self._session.report_snapshot().id
            if kind in ("add_module", "add_nested_module"):
                self._selected_module_id = new_id
                self._restore = (NodeAddress(report_id, new_id), 0, -1)
            elif kind in ("add_paragraph", "add_heading", "add_table",
                          "add_page_break", "add_photo", "import_photo", "import_photos"):
                self._selected_module_id = target.module_id
                self._restore = (
                    (NodeAddress(report_id, target.module_id, new_id,
                                 "cell" if kind == "add_table" else "text",
                                 0 if kind == "add_table" else None,
                                 0 if kind == "add_table" else None), 0, 0)
                    if kind in ("add_paragraph", "add_heading", "add_table")
                    else None)
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

    def add_table(self, *, module_id: str | None = None,
                  index: int | None = None) -> bool:
        if self._session is None:
            return False
        owner = self._selected_module_id if module_id is None else module_id
        if owner is None:
            self.feedback.emit("Select a module first")
            return False
        args = {} if index is None else {"index": index}
        return self._run("add_table",
                         NodeAddress(self._session.report_snapshot().id, owner), **args)

    def add_page_break(self, *, module_id: str | None = None,
                       index: int | None = None) -> bool:
        return self._insert_content("page_break", module_id=module_id, index=index)

    def add_photo(self, *, module_id: str | None = None,
                  index: int | None = None, asset_id: str | None = None) -> bool:
        return self._insert_content("photo", module_id=module_id, index=index,
                                    asset_id=asset_id)

    def _insert_content(self, kind: str, *, module_id: str | None = None,
                        index: int | None = None, asset_id: str | None = None,
                        expected_revision: int | None = None,
                        expected_generation: str | None = None) -> bool:
        if self._session is None:
            return False
        report = self._session.report_snapshot()
        owner = self._selected_module_id if module_id is None else module_id
        if owner is None:
            self.feedback.emit("Select an owning module first")
            return False
        revision = self._session.revision if expected_revision is None else expected_revision
        generation = self._session.generation if expected_generation is None else expected_generation
        args = {} if index is None else {"index": index}
        if kind == "photo":
            available = tuple(sorted(self._session.assets))
            if not available:
                self.feedback.emit(
                    "No project-owned photos yet; import via Photo Gallery in M4")
                return False
            if asset_id is None:
                names = self._session.media_library
                choices = {f"{names.get(key, 'Project photo')} [{key}]": key
                           for key in available}
                label, accepted = QInputDialog.getItem(
                    self, "Insert existing photo", "Project-owned photo:",
                    list(choices), 0, False)
                if not accepted:
                    return False
                asset_id = choices[label]
            if asset_id not in available:
                self.feedback.emit("Selected photo is no longer part of this project")
                return False
            args["asset_id"] = asset_id
        elif kind not in ("paragraph", "heading", "table", "page_break"):
            raise ValueError("Unsupported contextual insertion")
        if kind in ("paragraph", "heading"):
            args["text"] = ""
        if kind == "heading":
            args["level"] = 2
        return self._run("add_" + kind, NodeAddress(report.id, owner),
                         expected_revision=revision,
                         expected_generation=generation, **args)

    def insert_content_after(self, address: NodeAddress, kind: str,
                             *, asset_id: str | None = None,
                             expected_revision: int | None = None,
                             expected_generation: str | None = None) -> bool:
        """Insert after the canonical mixed index (not a separately kept UI list)."""
        if self._session is None or not isinstance(address, NodeAddress):
            return False
        report = self._session.report_snapshot()
        if address.report_id != report.id or address.block_id is None:
            return False
        row = next((item for item in project_branch(report)
                    if item.stable_id == address.block_id
                    and item.parent_module_id == address.module_id
                    and item.kind not in ("module", "conclusion")), None)
        if row is None:
            return False
        return self._insert_content(
            kind, module_id=row.parent_module_id,
            index=row.mixed_sibling_index + 1, asset_id=asset_id,
            expected_revision=expected_revision,
            expected_generation=expected_generation)

    def insert_table_after(self, address: NodeAddress) -> bool:
        return self.insert_content_after(address, "table")

    def insert_heading_after(self, address: NodeAddress) -> bool:
        return self.insert_content_after(address, "heading")

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
        if address.block_id is not None:
            node = find_node(self._session.report_snapshot(), address)
            if isinstance(node, PhotoBlock):
                photo_address = NodeAddress(address.report_id, address.module_id,
                                            address.block_id, "photo")
                edit_photo = menu.addAction("Edit photo layers…")
                edit_photo.triggered.connect(lambda: self.edit_photo(photo_address))
                replace_photo = menu.addAction("Replace with existing photo…")
                replace_photo.triggered.connect(lambda: self.replace_photo(photo_address))
                new_file = menu.addAction("Replace with local photo…")
                new_file.triggered.connect(lambda: self.replace_photo_from_file(photo_address))
                menu.addSeparator()
        if address.block_id is None and address.module_id != self._session.report_snapshot().id:
            focus = menu.addAction("Focus on this subtree")
            focus.triggered.connect(lambda checked=False, mid=address.module_id:
                                    self.focus_module(mid))
            if self._focus_id is not None:
                exit_action = menu.addAction("Exit focus")
                exit_action.triggered.connect(self.exit_focus)
            menu.addSeparator()
        insert_menu = menu.addMenu("Insert inside" if address.block_id is None
                                   else "Insert after")
        source_revision, source_generation = self._session.revision, self._session.generation
        for kind, caption in (
            ("paragraph", "Paragraph"), ("heading", "Heading"),
            ("table", "Table"), ("page_break", "Page break"),
            ("photo", "Existing project photo"),
        ):
            action = insert_menu.addAction(caption)
            if kind == "photo":
                action.setEnabled(bool(self._session.assets))
                if not self._session.assets:
                    action.setToolTip("Import project media through Gallery in M4")
            if address.block_id is None:
                action.triggered.connect(
                    lambda checked=False, k=kind, mid=address.module_id,
                           rev=source_revision, gen=source_generation:
                    self._insert_content(k, module_id=mid, expected_revision=rev,
                                         expected_generation=gen))
            else:
                action.triggered.connect(
                    lambda checked=False, k=kind, a=address,
                           rev=source_revision, gen=source_generation:
                    self.insert_content_after(a, k, expected_revision=rev,
                                               expected_generation=gen))
        from_disk = insert_menu.addAction("Import local photo…")
        if address.block_id is None:
            from_disk.triggered.connect(
                lambda checked=False, mid=address.module_id,
                       rev=source_revision, gen=source_generation:
                self.import_photo_dialog(module_id=mid, expected_revision=rev,
                                         expected_generation=gen))
        else:
            from_disk.triggered.connect(
                lambda checked=False, a=address, rev=source_revision,
                       gen=source_generation:
                self._import_photo_after(a, expected_revision=rev,
                                         expected_generation=gen))
        if address.block_id is None:
            submodule = insert_menu.addAction("Submodule")
            submodule.setEnabled(address.module_id !=
                                 self._session.report_snapshot().conclusion.id)
            submodule.triggered.connect(
                lambda checked=False, a=address, rev=source_revision,
                       gen=source_generation:
                self._run("add_nested_module", a,
                          expected_revision=rev, expected_generation=gen,
                          title="New submodule"))
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
            if isinstance(editor, InlineParagraph) and address.field == "text"
            and editor.hasFocus()
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
                address, start, end, field, value, paragraph=paragraph,
                owner=self._owner)
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

    def table_editor_for(self, table_address, row: int, column: int):
        return self._editors.get(NodeAddress(
            table_address.report_id, table_address.module_id, table_address.block_id,
            "cell", row, column))

    def _table_changed(self, address, row, column, text) -> None:
        try:
            self.drafts.update_cell(address, row, column, text, owner=self._owner)
            self._draft_bars[address].setVisible(self.drafts.is_dirty(address))
            self.feedback.emit("Unapplied table edit — Apply or Revert before Save/Undo")
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Table draft retained: " + str(exc))
            QTimer.singleShot(0, self.lock_foreign_fields)

    def _capture_table_cell(self, address):
        row, column = self._table_selected.get(address, (0, 0))
        cell_address = NodeAddress(
            address.report_id, address.module_id, address.block_id,
            "cell", row, column)
        if cell_address in self._editors:
            self._capture(cell_address)

    def apply_table_draft(self, address) -> bool:
        if self.drafts is None or not self.drafts.is_dirty(address):
            return False
        self._capture_table_cell(address)
        try:
            self.drafts.commit(address, owner=self._owner)
        except (ValueError, LookupError, RuntimeError) as exc:
            self.feedback.emit("Table draft retained: " + str(exc))
            return False
        self._refresh()
        self.feedback.emit("Table applied — Undo available")
        return True

    def revert_table_draft(self, address) -> None:
        if self.drafts is None:
            return
        self._capture_table_cell(address)
        self.drafts.discard(address, owner=self._owner)
        self._refresh()
        self.feedback.emit("Table draft reverted")

    def _table_action(self, address, operation: str):
        try:
            rows = self.drafts.table_rows(address)
            selected_row, selected_column = self._table_selected.get(address, (0, 0))
            if operation == "insert_row":
                index = min(len(rows), selected_row + 1)
            elif operation == "delete_row":
                index = selected_row
            elif operation == "insert_column":
                index = selected_column + 1
            elif operation == "delete_column":
                index = selected_column
            else:
                raise ValueError("Unsupported table operation")
            if not self.drafts.modify_table(address, operation, index, owner=self._owner):
                return False
            next_rows = self.drafts.table_rows(address)
            row = max(0, min(selected_row + (operation == "insert_row"),
                             len(next_rows) - 1))
            col = max(0, min(selected_column + (operation == "insert_column"),
                             len(next_rows[row]) - 1))
            self._table_selected[address] = row, col
            self._restore = (NodeAddress(
                address.report_id, address.module_id, address.block_id,
                "cell", row, col), 0, 0)
            self._refresh()
            self.feedback.emit("Unapplied table structure — Apply or Revert")
            return True
        except (ValueError, LookupError, RuntimeError, IndexError) as exc:
            self.feedback.emit(str(exc))
            return False

    def _inline_table(self, card, address):
        rows, stale = self.drafts.table_preview(address)
        external = self.drafts.draft_owner(address) not in (None, self._owner)
        if external:
            label = QLabel("Pending edits belong to the other editor; return there "
                           "to Apply or Revert.", card)
            label.setObjectName("v2ExternalDraftNotice")
            label.setWordWrap(True)
            card.layout().addWidget(label)
        if stale:
            warning = QLabel(
                "Table changed while your edits were pending. You can copy your staged "
                "text, then Revert; Apply and further edits are blocked.", card)
            warning.setTextFormat(Qt.TextFormat.PlainText)
            warning.setWordWrap(True)
            warning.setObjectName("v2StaleTableDraftWarning")
            card.layout().addWidget(warning)
        surface = QWidget(card)
        surface.setObjectName("v2InlineTable")
        grid = QGridLayout(surface)
        grid.setContentsMargins(0, 3, 0, 3)
        grid.setHorizontalSpacing(3)
        grid.setVerticalSpacing(3)
        if not rows:
            empty = QLabel("Empty table — use + Row to begin", surface)
            empty.setTextFormat(Qt.TextFormat.PlainText)
            grid.addWidget(empty, 0, 0)
        for i, values in enumerate(rows):
            for j, cell in enumerate(values):
                editor = InlineParagraph(surface)
                editor.setObjectName("v2TableCell")
                editor.setAccessibleName(f"Table row {i + 1}, column {j + 1}")
                editor.setPlainText(cell.original)
                editor.setReadOnly(stale or external)
                if external and not stale:
                    editor.setProperty("foreignLocked", True)
                editor.setStyleSheet(
                    "color: #182b3a; background: #f9fbff;"
                    "border: 1px solid #aabbd0; border-radius: 3px;"
                    "font-size: 13px; padding: 3px;")
                editor.setTabChangesFocus(True)
                cell_address = NodeAddress(
                    address.report_id, address.module_id, address.block_id,
                    "cell", i, j)
                editor.installEventFilter(self)
                self._editors[cell_address] = editor
                self._table_cells[editor] = (address, i, j)
                editor.textChanged.connect(
                    lambda e=editor, a=address, r=i, c=j:
                    self._table_changed(a, r, c, e.toPlainText()))
                editor.commitRequested.connect(
                    lambda a=address: self.apply_table_draft(a))
                editor.cancelRequested.connect(
                    lambda a=address: self.revert_table_draft(a))
                grid.addWidget(editor, i, j)
        card.layout().addWidget(surface)
        operations = QWidget(card)
        actions = QHBoxLayout(operations)
        widths = {len(row) for row in rows}
        rectangular = len(widths) <= 1
        width = next(iter(widths), 0)
        actions.setContentsMargins(0, 3, 0, 0)
        for operation, label, tooltip in (
            ("insert_row", "+ Row", "Insert row below selected cell"),
            ("delete_row", "− Row", "Delete selected row"),
            ("insert_column", "+ Column", "Insert column after selected cell"),
            ("delete_column", "− Column", "Delete selected column"),
        ):
            button = QToolButton(operations)
            button.setObjectName("v2Table" + "".join(part.title() for part in operation.split("_")))
            button.setText(label)
            button.setAccessibleName(tooltip)
            button.setToolTip(tooltip)
            button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            enabled = rectangular and {
                "insert_row": not rows or width > 0,
                "delete_row": len(rows) > 1,
                "insert_column": bool(rows),
                "delete_column": width > 1,
            }[operation]
            button.setEnabled(enabled and not stale and not external)
            if not rectangular:
                button.setToolTip("Ragged tables permit cell edits only")
            button.clicked.connect(
                lambda checked=False, a=address, op=operation:
                self._table_action(a, op))
            actions.addWidget(button)
        actions.addStretch(1)
        card.layout().addWidget(operations)
        bar = QWidget(card)
        buttons = QHBoxLayout(bar)
        buttons.setContentsMargins(0, 3, 0, 0)
        apply = QPushButton("Apply table", bar)
        apply.setObjectName("v2ApplyTableDraft")
        apply.setEnabled(not stale and not external)
        revert = QPushButton("Revert table", bar)
        revert.setObjectName("v2RevertTableDraft")
        revert.setEnabled(not external)
        self._style_draft_buttons(apply, revert)
        apply.clicked.connect(lambda checked=False, a=address: self.apply_table_draft(a))
        revert.clicked.connect(lambda checked=False, a=address: self.revert_table_draft(a))
        buttons.addWidget(apply)
        buttons.addWidget(revert)
        buttons.addStretch(1)
        bar.setVisible(self.drafts.is_dirty(address))
        card.layout().addWidget(bar)
        self._draft_bars[address] = bar

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
            except (ValueError, StaleIntentError):
                # An unsafe edit of a styled paragraph boundary must remain
                # visible and revertible. Commit will reject it without losing
                # either the canonical model or the pending draft.
                staged_rich = RichFormatting()
            paint_rich(editor, text, staged_rich)
        external = self.drafts.draft_owner(address) not in (None, self._owner)
        stale = self.drafts.text_stale(address)
        if stale:
            message = ("Source changed while a draft was pending. Copy staged text "
                       "if needed, then return to its owning editor to Revert."
                       if external else
                       "Source changed while a draft was pending. "
                       "Copy staged text if needed, then Revert.")
            note = QLabel(message, card)
            note.setWordWrap(True)
            note.setObjectName("v2StaleTextDraftWarning")
            card.layout().addWidget(note)
        if external:
            note = QLabel("Unapplied changes belong to the other editor. "
                          "Apply or Revert them there.", card)
            note.setWordWrap(True)
            note.setObjectName("v2ExternalDraftNotice")
            card.layout().addWidget(note)
        if stale or external:
            editor.setReadOnly(True)
        if external and not stale:
            editor.setProperty("foreignLocked", True)  # lock_foreign_fields may unlock it
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
        apply.setEnabled(not external and not stale)
        revert.setEnabled(not external)
        self._style_draft_buttons(apply, revert)
        apply.setToolTip("Commit this edit before adding blocks or saving")
        revert.setToolTip("Discard only this unapplied edit")
        bar.addWidget(apply)
        bar.addWidget(revert)
        bar.addStretch(1)
        apply.clicked.connect(lambda checked=False, a=address: self.apply_draft(a))
        revert.clicked.connect(lambda checked=False, a=address: self.revert_draft(a))
        buttons.setVisible(self.drafts.is_dirty(address))
        self._draft_bars[address] = buttons
        if isinstance(editor, InlineTitle):
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
        if self._focus_id is not None:
            start, end = subtree_range(projection, self._focus_id)
            rows, projection = rows[start:end], projection[start:end]
        _, page_count = window_for(projection, 0, size=self._page_size)
        self._page_count = page_count
        self._page = min(self._page, page_count - 1)
        start = self._page * self._page_size
        end = start + self._page_size
        rows, projection = rows[start:end], projection[start:end]
        # Never leave the toolbar operating on a different hidden window.
        if projection:
            shown_modules = {r.stable_id for r in projection
                             if r.kind in ("module", "conclusion")}
            shown_owners = shown_modules | {r.parent_module_id for r in projection
                                             if r.parent_module_id is not None}
            if self._selected_module_id not in shown_owners:
                first = projection[0]
                # The root report row has no owning module. Prefer the first
                # actually visible module to keep toolbar actions usable when
                # paging back to window 1 from a much later window.
                first_module = next((r.stable_id for r in projection
                                     if r.kind in ("module", "conclusion")), None)
                self._selected_module_id = first_module or first.parent_module_id
        scroll = self.verticalScrollBar().value()
        self._pending_panel = None
        self._pending_message = None
        self._editors.clear()
        self._draft_bars.clear()
        self._table_cells.clear()
        self._ribbons.clear()
        self._gutters.clear()
        self._rows.clear()
        self._card_layouts.clear()
        self._handles.clear()
        self._compact_level = 0
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        # Always visible above the report, including when drafts are in
        # scrolled, collapsed or paged-away cards.
        panel = QFrame(self._host)
        panel.setObjectName("v2PendingDraftPanel")
        panel.setStyleSheet(
            "QFrame#v2PendingDraftPanel { background: #fff0c2;"
            " border: 2px solid #9a6700; border-radius: 6px; }")
        panel_row = QHBoxLayout(panel)
        message = QLabel(panel)
        message.setObjectName("v2PendingDraftMessage")
        message.setWordWrap(True)
        message.setStyleSheet("QLabel { color: #332400; font-size: 13px; font-weight: bold; }")
        panel_row.addWidget(message, 1)
        apply = QPushButton("Apply all edits", panel)
        apply.setObjectName("v2ApplyAllBranchDrafts")
        apply.setToolTip("Commit all Modules drafts together as one Undo step")
        discard = QPushButton("Discard edits…", panel)
        discard.setObjectName("v2DiscardAllBranchDrafts")
        discard.setToolTip("Ask before discarding unapplied Modules edits")
        self._style_draft_buttons(apply, discard)
        apply.clicked.connect(lambda checked=False: self.apply_all_branch_drafts())
        discard.clicked.connect(lambda checked=False: self.discard_all_branch_drafts())
        panel_row.addWidget(apply)
        panel_row.addWidget(discard)
        self._body.addWidget(panel)
        self._pending_panel, self._pending_message = panel, message
        self._update_pending_panel()
        if self._page_count > 1:
            label = QLabel(f"Branch window {self._page + 1} of {self._page_count}"
                           f" — {len(rows)} visible report nodes", self._host)
            label.setObjectName("v2WindowStatus")
            label.setAccessibleName("Current branch window")
            self._body.addWidget(label)
        if self._page_count > 1 and self._page > 0:
            button = QPushButton(f"Previous branch window ({self._page} of {self._page_count})", self._host)
            button.setObjectName("v2PreviousWindow")
            button.clicked.connect(lambda: self.change_page(-1))
            self._body.addWidget(button)
        if projection and projection[0].parent_module_id is not None:
            # A window can start halfway through a long module. Show its owner
            # rather than letting insertion actions target an invisible context.
            owner_id = projection[0].parent_module_id
            owner_title = find_node(report, NodeAddress(report.id, owner_id)).title.original
            owner = QLabel("Within module: " + owner_title, self._host)
            owner.setObjectName("v2WindowOwner")
            self._body.addWidget(owner)
        for (identifier, kind, caption, text, depth, ancestors, has_next), meta in zip(rows, projection):
            address = (NodeAddress(report.id, identifier)
                       if kind in ("root", "module", "conclusion")
                       else NodeAddress(report.id, meta.parent_module_id, identifier, "text"))
            row = DropRow(self, address, kind, self._host)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.setSpacing(0)
            gutter = ConnectorGutter(depth, ancestors, has_next, row,
                                     zoom_pct=self._zoom_pct)
            self._gutters.append(gutter)
            self._rows.append(row)
            line.addWidget(gutter)
            card = QFrame(row)
            card.setObjectName("v2BranchCard")
            card.setStyleSheet(
                "QFrame#v2BranchCard { background: #ffffff;"
                " border: 1px solid #cbd5e1; border-radius: 8px; }"
                + BUTTON_CHROME + FIELD_CHROME)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 9, 15, 10)
            self._card_layouts.append(card_layout)
            card_layout.setSpacing(3)
            numbered = (f"MODULE {numbers[identifier]}" if kind == "module"
                        else caption)
            label = ElidedLabel(numbered, card)
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
                handle = DragHandle(self, address, card)
                self._handles.append(handle)
                header.addWidget(handle)
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
            if self.drafts is not None and kind == "photo":
                photo_addr = NodeAddress(report.id, meta.parent_module_id, identifier, "photo")
                photo_block = find_node(report, photo_addr)
                self._photo_card(card, photo_addr, photo_block)
            elif self.drafts is not None and kind == "table":
                self._inline_table(card, NodeAddress(
                    report.id, meta.parent_module_id, identifier, "table"))
            elif self.drafts is not None and kind in ("module", "conclusion", "paragraph", "heading"):
                address = (NodeAddress(report.id, identifier)
                           if kind in ("module", "conclusion")
                           else NodeAddress(report.id, meta.parent_module_id, identifier, "text"))
                self._inline(card, address, kind, text)
            else:
                display = ("Page break" if kind == "page-break" else
                           ("Photo" + (": " + text if text else
                                       " (thumbnail and captions in M4)")
                            if kind == "photo" else text or "(Empty)"))
                value = QLabel(display, card)
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
            self._zoom_row(row)
            if identifier == self._search_target:
                card.setStyleSheet("QFrame#v2BranchCard { background: #fff5d1;"
                                   " border: 2px solid #a36a00; border-radius: 8px; }"
                                   + BUTTON_CHROME + FIELD_CHROME)
            self._body.addWidget(row)
        if self._page_count > 1 and self._page < self._page_count - 1:
            button = QPushButton(
                f"Next branch window ({self._page + 2} of {self._page_count})", self._host)
            button.setObjectName("v2NextWindow")
            button.clicked.connect(lambda: self.change_page(1))
            self._body.addWidget(button)
        self._body.addStretch(1)
        active_table_ids = {r.stable_id for r in all_rows if r.kind == "table"}
        self._table_selected = {
            addr: cell for addr, cell in self._table_selected.items()
            if addr.report_id == report.id and addr.block_id in active_table_ids
        }
        self._visible_nodes = tuple(
            (identifier, kind, depth, text)
            for identifier, kind, _, text, depth, _, _ in rows
        )
        self._apply_indent()
        # Stylesheets are polished when the rows are first shown, which can change
        # a card's minimum width; measure once more after that.
        QTimer.singleShot(0, self._apply_indent)
        self.verticalScrollBar().setValue(scroll)
        if self._restore is not None:
            QTimer.singleShot(0, self._restore_cursor)

    def _draft_changed(self, address, owner, previous_owner) -> None:
        if owner in (None, self._owner) and previous_owner in (None, self._owner):
            return  # this canvas's own drafts already redraw themselves
        # Lock right now, inside the notification: never wait for a timer or an
        # event-loop turn, so a field another editor owns is not writable here even
        # for an instant. The redraw below only adds the notices and button states.
        self.lock_foreign_fields()
        self._foreign_stale = True
        if self.isVisible():
            self._foreign_timer.start()

    def _is_foreign(self, address) -> bool:
        return self.drafts is not None and self.drafts.draft_owner(address) not in (None, self._owner)

    def lock_foreign_fields(self) -> None:
        """Make this canvas agree with who owns each draft, in place.

        A field another editor holds a draft for becomes read-only and shows that
        draft; a field that editor let go of (applied or reverted) is writable again
        with the committed text. Cheap and synchronous (it only touches this canvas's
        own widgets), so it runs inside the draft notification, on show, and after a
        rejected keystroke. The debounced redraw afterwards only adds notices and
        tidies the rest, so no caller ever waits on it. Only fields this method
        locked are unlocked here; a field read-only for another reason (a stale
        draft) is left to the redraw.
        """
        if self.drafts is None:
            return
        for address, editor in self._editors.items():
            owned_elsewhere = self._is_foreign(
                NodeAddress(address.report_id, address.module_id, address.block_id, "table")
                if address.field == "cell" else address)
            locked = bool(editor.property("foreignLocked"))
            if owned_elsewhere:
                if not locked:
                    editor.setProperty("foreignLocked", True)
                if not editor.isReadOnly():
                    editor.setReadOnly(True)
                if address.field != "cell":
                    self._show_draft_text(address, editor)
                    self._lock_draft_bar(address, True)
            elif locked:
                editor.setProperty("foreignLocked", False)
                editor.setReadOnly(False)
                if address.field != "cell":
                    self._show_draft_text(address, editor)
                    self._lock_draft_bar(address, False)

    def _show_draft_text(self, address, editor) -> None:
        text = self.drafts.text(address)
        current = editor.text() if isinstance(editor, InlineTitle) else editor.toPlainText()
        if current != text:
            editor.blockSignals(True)
            try:
                editor.setPlainText(text)
            finally:
                editor.blockSignals(False)

    def _lock_draft_bar(self, address, locked: bool) -> None:
        bar = self._draft_bars.get(address)
        if bar is None:
            return
        bar.setVisible(self.drafts.is_dirty(address))
        for name in ("v2ApplyDraft", "v2RevertDraft"):
            button = bar.findChild(QPushButton, name)
            if button is not None:
                button.setEnabled(not locked)

    def _refresh_foreign_state(self) -> None:
        if not self._foreign_stale:
            return
        if any(editor.hasFocus() for editor in self._editors.values()):
            # Never rebuild under the caret; try again shortly.
            self._foreign_timer.start()
            return
        self._foreign_stale = False
        self._refresh()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_indent()
        self.lock_foreign_fields()  # before the user can type, not after a timer
        if self._foreign_stale:
            self._foreign_timer.start()

    def _apply_indent(self) -> None:
        """Fit every row inside the viewport by measuring, not estimating.

        A deeply nested card used to run past the right edge of a narrow window,
        where its buttons could not be reached (the canvas has no horizontal
        scrollbar). Each stage below is tried only if the previous one was not
        enough, always against the rows' live minimum widths, so it holds for
        whatever font, text size or style sheet is in effect rather than for a
        width cached when the rows were built:

        1. the indentation per level shrinks, never below ``_MIN_STEP``;
        2. the side margin shrinks, never below ``_MIN_SIDE_MARGIN``;
        3. the cards' inner side margins shrink (15 -> 8 px);
        4. the drag handle shows only its glyph.

        Everything is restored as soon as there is room again. Connector lines
        shrink with the step and never collapse.
        """
        gutters, rows = self._gutters, self._rows
        if not gutters or len(gutters) != len(rows) or self._fitting:
            return
        self._fitting = True  # layout requests processed below can resize us again
        try:
            self._fit_rows(gutters, rows)
        finally:
            self._fitting = False

    def _fit_rows(self, gutters, rows) -> None:
        factor = self._zoom_pct / 100
        natural = max(1, round(_STEP * factor))
        floor = max(1, round(_MIN_STEP * factor))
        viewport = self.viewport().width()

        def set_side(side: int) -> None:
            margins = self._body.contentsMargins()
            if margins.left() != side or margins.right() != side:
                self._body.setContentsMargins(side, margins.top(), side, margins.bottom())

        def set_compact(level: int) -> None:
            if level == self._compact_level:
                return
            self._compact_level = level
            inner = 8 if level >= 1 else 15
            for layout in self._card_layouts:
                margins = layout.contentsMargins()
                layout.setContentsMargins(inner, margins.top(), inner, margins.bottom())
            for handle in self._handles:
                handle.set_compact(level >= 2)
            # Qt only invalidates nested layouts' cached sizes when it processes the
            # posted layout requests; do that now so the next measurement is live.
            QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)

        def worst_overflow(side: int) -> int:
            inner = viewport - 2 * side
            return max((row.minimumSizeHint().width() - inner for row in rows), default=0)

        side = _SIDE_MARGIN
        set_side(side)
        set_compact(0)
        step = natural
        for gutter in gutters:
            gutter.set_step(step)
        for _ in range(3):  # a cheap fixed-point loop: a row's width is linear in the step
            inner = viewport - 2 * side
            wanted = step
            for gutter, row in zip(gutters, rows, strict=True):
                if gutter.depth:
                    over = row.minimumSizeHint().width() - inner
                    if over > 0:
                        wanted = min(wanted, step - -(-over // gutter.depth))
            wanted = max(floor, wanted)
            if wanted == step:
                break
            step = wanted
            for gutter in gutters:
                gutter.set_step(step)
        overflow = worst_overflow(side)
        if overflow > 0 and side > _MIN_SIDE_MARGIN:
            side = max(_MIN_SIDE_MARGIN, side - -(-overflow // 2))
            set_side(side)
            overflow = worst_overflow(side)
        for level in (1, 2):
            if overflow <= 0:
                break
            set_compact(level)
            overflow = worst_overflow(side)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if event.oldSize().width() != event.size().width():
            self._apply_indent()
