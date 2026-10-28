"""Qt-only projection of canonical rich runs into an inline plain-text widget.

Character styles are painted by QSyntaxHighlighter, not written into the
QTextDocument undo stack. Paragraph/list block formats use native Qt objects
only when the structure or paragraph styles change. Neither representation
is a second model or a saved HTML document.
"""
from __future__ import annotations

from copy import deepcopy

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import (
    QColor, QFont, QSyntaxHighlighter, QTextBlockFormat, QTextCharFormat,
    QTextCursor, QTextListFormat,
)

from ...rich_text import ParagraphStyle, RichFormatting, validate_rich
from ..adapters.formatting import to_utf16


class RichRunHighlighter(QSyntaxHighlighter):
    """Display canonical character styles without generating Qt undo actions."""

    def __init__(self, document):
        super().__init__(document)
        self._text = ""
        self._rich = RichFormatting()
        self._block_positions: dict[int, int] = {0: 0}

    def set_rich(self, text: str, rich: RichFormatting) -> None:
        if text == self._text and rich == self._rich:
            return
        self._text = text
        self._rich = deepcopy(rich)
        # Block positions are Qt UTF-16 offsets; one linear pass avoids
        # rescanning the entire prefix for every block of a long report.
        block_positions = {}
        units = codepoints = 0
        for line in text.split("\n"):
            block_positions[units] = codepoints
            units += len(line.encode("utf-16-le")) // 2 + 1
            codepoints += len(line) + 1
        self._block_positions = block_positions
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:
        start = self._block_positions.get(self.currentBlock().position())
        # Qt may highlight while a keystroke is still in progress, before
        # the coordinator has rebased the staged formatting to the new text.
        if start is None or self._text[start:start + len(text)] != text:
            return
        end = start + len(text)
        for run in self._rich.runs:
            if run.end <= start:
                continue
            if run.start >= end:
                break
            left, right = max(start, run.start), min(end, run.end)
            if left >= right:
                continue
            fmt = QTextCharFormat()
            if run.family:
                fmt.setFontFamily(run.family)
            if run.size:
                fmt.setFontPointSize(run.size)
            # False means inherit the editor's base style (e.g. bold headings),
            # not explicitly force Normal weight on an underline-only run.
            if run.bold:
                fmt.setFontWeight(QFont.Weight.Bold)
            if run.italic:
                fmt.setFontItalic(True)
            if run.underline:
                fmt.setFontUnderline(True)
            if run.strike:
                fmt.setFontStrikeOut(True)
            if run.baseline != "normal":
                fmt.setVerticalAlignment({
                    "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
                    "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
                }[run.baseline])
            if run.color:
                fmt.setForeground(QColor(run.color))
            if run.highlight:
                fmt.setBackground(QColor(run.highlight))
            local_left, local_right = left - start, right - start
            self.setFormat(to_utf16(text, local_left),
                           to_utf16(text, local_right) - to_utf16(text, local_left),
                           fmt)


def paint_rich(editor, text: str, rich: RichFormatting) -> None:
    validate_rich(rich, text)
    if editor.toPlainText() != text:
        raise ValueError("Cannot render rich formatting onto different wording")

    document = editor.document()
    highlighter = getattr(editor, "_v2_rich_highlighter", None)
    if highlighter is None:
        highlighter = RichRunHighlighter(document)
        editor._v2_rich_highlighter = highlighter

    previous = getattr(editor, "_v2_preview_paragraphs", [])
    previous_count = getattr(editor, "_v2_preview_block_count", document.blockCount())
    # Normal text typing must not overwrite the user's native Ctrl+Z history.
    # Rebuild Qt list/block objects only for paragraph changes or split/join.
    if previous != rich.paragraphs or previous_count != document.blockCount():
        saved = editor.textCursor()
        undo_enabled = document.isUndoRedoEnabled()
        with QSignalBlocker(editor):
            # Native block/list reformatting is a projection, not a text edit;
            # it must never show up as an undoable user command.
            document.setUndoRedoEnabled(False)
            try:
                block = document.begin()
                while block.isValid():
                    if block.textList() is not None:
                        block.textList().remove(block)
                    cursor = QTextCursor(block)
                    cursor.setBlockFormat(QTextBlockFormat())
                    block = block.next()
                for para in rich.paragraphs:
                    fmt = QTextBlockFormat()
                    fmt.setAlignment({
                        "left": Qt.AlignmentFlag.AlignLeft,
                        "center": Qt.AlignmentFlag.AlignHCenter,
                        "right": Qt.AlignmentFlag.AlignRight,
                        "justify": Qt.AlignmentFlag.AlignJustify,
                    }[para.align])
                    fmt.setLeftMargin(para.indent * 24)
                    fmt.setLineHeight(int(para.line_height * 100),
                                      QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
                    if para.shading:
                        fmt.setBackground(QColor(para.shading))
                    at = QTextCursor(document)
                    at.setPosition(to_utf16(text, para.start))
                    at.setBlockFormat(fmt)
                specs = {p.start: p for p in rich.paragraphs}
                offsets = 0
                last_list = None
                last_kind = "none"
                block = document.begin()
                while block.isValid():
                    spec = specs.get(offsets, ParagraphStyle(offsets))
                    if spec.list_kind in ("bullet", "decimal", "lower-alpha", "upper-alpha"):
                        if last_list is not None and last_kind == spec.list_kind:
                            last_list.add(block)
                        else:
                            style = {
                                "bullet": QTextListFormat.Style.ListDisc,
                                "decimal": QTextListFormat.Style.ListDecimal,
                                "lower-alpha": QTextListFormat.Style.ListLowerAlpha,
                                "upper-alpha": QTextListFormat.Style.ListUpperAlpha,
                            }[spec.list_kind]
                            list_format = QTextListFormat()
                            list_format.setStyle(style)
                            c = QTextCursor(block)
                            c.createList(list_format)
                            last_list = block.textList()
                        last_kind = spec.list_kind
                    else:
                        last_list = None
                        last_kind = "none"
                    offsets += len(block.text()) + 1
                    block = block.next()
                editor.setTextCursor(saved)
            finally:
                document.setUndoRedoEnabled(undo_enabled)
    editor._v2_preview_paragraphs = deepcopy(rich.paragraphs)
    editor._v2_preview_block_count = document.blockCount()
    highlighter.set_rich(text, rich)
    editor.updateGeometry()
