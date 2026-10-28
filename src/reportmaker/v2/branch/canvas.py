"""Connected, read-only M1.1 Branch Editor scaffold over the shared model.

This is a projection of ReportMaker's single ordered hierarchy, not a new
report document or a parallel navigation tree. Inline editing, draft guards
and efficient viewport virtualization are separate reviewed M1.2/M1.3/M5
work. No legacy UI or browser module is imported here.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget,
)

from ...engine import validate_report_tree
from ...model import (
    HeadingBlock, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, Report, TableBlock,
)

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
        self.setFixedWidth(18 + _STEP * max(0, min(depth, 32)))
        self.setMinimumHeight(48)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self._depth:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#8199ae"), 2))
        middle = self.height() // 2
        for level, continues in enumerate(self._ancestors[:31]):
            if continues:
                x = 11 + _STEP * level
                painter.drawLine(x, 0, x, self.height())
        level = min(self._depth - 1, 31)
        x = 11 + _STEP * level
        painter.drawLine(x, 0, x, middle)
        painter.drawLine(x, middle, x + 16, middle)
        if self._has_next:
            painter.drawLine(x, middle, x, self.height())
        painter.end()


class BranchCanvas(QScrollArea):
    """V2's sole primary workspace, currently a canonical read-only scaffold."""

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
        self._visible_nodes: tuple[tuple[str, str, int, str], ...] = ()

    @property
    def visible_nodes(self) -> tuple[tuple[str, str, int, str], ...]:
        """Read-only view metadata for tests; never a second report model."""
        return self._visible_nodes

    def set_report(self, report: Report) -> None:
        """Replace the projection only after full validation of detached data."""
        validate_report_tree(report)
        rows = tuple(_branch_rows(deepcopy(report)))
        while self._body.count():
            item = self._body.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for identifier, kind, caption, text, depth, ancestors, has_next in rows:
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
            card.setStyleSheet(
                "QFrame#v2BranchCard { background: white; border: 1px solid #cbd5e1;"
                "border-radius: 8px; }"
            )
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(15, 9, 15, 10)
            card_layout.setSpacing(3)
            label = QLabel(caption, card)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet("color: #526c83; font-size: 10px; font-weight: bold;")
            value = QLabel(text or "(Empty)", card)
            value.setObjectName("v2BranchValue")
            value.setTextFormat(Qt.TextFormat.PlainText)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet(
                "color: #182b3a; font-size: 15px; font-weight: %s;"
                % ("bold" if kind in ("root", "module", "conclusion") else "normal")
            )
            card_layout.addWidget(label)
            card_layout.addWidget(value)
            line.addWidget(card, 1)
            self._body.addWidget(row)
        self._body.addStretch(1)
        self._visible_nodes = tuple(
            (identifier, kind, depth, text)
            for identifier, kind, _, text, depth, _, _ in rows
        )
