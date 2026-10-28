"""Qt-only projection of canonical rich runs into an inline plain-text widget.

The QTextDocument is presentation/draft space, never a replacement report model.
All boundary conversions are explicit to avoid emoji UTF-16 offset mistakes.
"""
from __future__ import annotations

from PySide6.QtCore import QSignalBlocker, Qt
from PySide6.QtGui import QColor, QFont, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextListFormat

from ...rich_text import ParagraphStyle, RichFormatting, validate_rich
from ..adapters.formatting import to_utf16


def paint_rich(editor, text: str, rich: RichFormatting) -> None:
    validate_rich(rich, text)
    if editor.toPlainText() != text:
        raise ValueError("Cannot render rich formatting onto different wording")
    saved = editor.textCursor()
    # Suppress generated widget textChanged/cursor callbacks; rich styling is
    # staged by DraftCoordinator, not by copying QTextDocument/HTML content.
    with QSignalBlocker(editor):
        document = editor.document()
        whole = QTextCursor(document)
        whole.select(QTextCursor.SelectionType.Document)
        whole.setCharFormat(QTextCharFormat())
        block = document.begin()
        while block.isValid():
            if block.textList() is not None:
                block.textList().remove(block)
            cursor = QTextCursor(block)
            cursor.setBlockFormat(QTextBlockFormat())
            block = block.next()
        for run in rich.runs:
            fmt = QTextCharFormat()
            if run.family:
                fmt.setFontFamily(run.family)
            if run.size:
                fmt.setFontPointSize(run.size)
            fmt.setFontWeight(QFont.Weight.Bold if run.bold else QFont.Weight.Normal)
            fmt.setFontItalic(run.italic)
            fmt.setFontUnderline(run.underline)
            fmt.setFontStrikeOut(run.strike)
            fmt.setVerticalAlignment({
                "normal": QTextCharFormat.VerticalAlignment.AlignNormal,
                "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
                "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
            }[run.baseline])
            if run.color:
                fmt.setForeground(QColor(run.color))
            if run.highlight:
                fmt.setBackground(QColor(run.highlight))
            span = QTextCursor(document)
            span.setPosition(to_utf16(text, run.start))
            span.setPosition(to_utf16(text, run.end), QTextCursor.MoveMode.KeepAnchor)
            span.setCharFormat(fmt)
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
        # A contiguous numbered-list group must share ONE QTextList.
        # Creating one list per paragraph would restart every item at 1.
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
    editor.updateGeometry()
