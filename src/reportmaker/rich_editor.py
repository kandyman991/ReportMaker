"""Native Word-style formatting ribbon for a structured report text block.

Editing is intentional and limited to the selected canonical Paragraph/Heading
block. No HTML/remote images can be pasted. The application saves semantic
Unicode code-point ranges, never Qt HTML or a parallel copy of report text.
"""
from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextBlockFormat, QTextCursor, QTextListFormat, QTextFormat
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, QFontComboBox,
    QPushButton, QToolButton, QColorDialog, QLabel, QInputDialog, QTextEdit,
    QScrollArea,
)

from .rich_text import TextRun, ParagraphStyle, RichFormatting, validate_rich

DEFAULT_FONT = "Cambria"
DEFAULT_SIZE = 11

# QTextBlockFormat has no border()/setBorder() API (those belong to
# QTextFrameFormat). Keep border intent as a safe Qt user property on the
# paragraph block; the derived paper preview and exports render the border.
_BORDER_PROPERTY = int(QTextFormat.Property.UserProperty) + 1


def _offsets(value: str):
    result = [0]
    for char in value:
        result.append(result[-1] + (2 if ord(char) > 0xFFFF else 1))
    return result


def _py_index(offsets, utf16_position):
    return max(0, bisect_right(offsets, utf16_position) - 1)


def _format_to_qt(info: TextRun) -> QTextCharFormat:
    fmt = QTextCharFormat()
    if info.family:
        fmt.setFontFamily(info.family)
    if info.size:
        fmt.setFontPointSize(info.size)
    fmt.setFontWeight(QFont.Weight.Bold if info.bold else QFont.Weight.Normal)
    fmt.setFontItalic(info.italic)
    fmt.setFontUnderline(info.underline)
    fmt.setFontStrikeOut(info.strike)
    fmt.setVerticalAlignment({
        "normal": QTextCharFormat.VerticalAlignment.AlignNormal,
        "sub": QTextCharFormat.VerticalAlignment.AlignSubScript,
        "super": QTextCharFormat.VerticalAlignment.AlignSuperScript,
    }[info.baseline])
    if info.color:
        fmt.setForeground(QColor(info.color))
    if info.highlight:
        fmt.setBackground(QColor(info.highlight))
    return fmt


def _format_from_qt(fmt: QTextCharFormat, start: int, end: int) -> TextRun:
    base = fmt.fontFamily()
    point_size = fmt.fontPointSize()
    vertical = fmt.verticalAlignment()
    return TextRun(start=start, end=end,
                   family=base if base and base != DEFAULT_FONT else "",
                   size=round(point_size, 2) if point_size >= 6 else 0,
                   bold=fmt.fontWeight() >= QFont.Weight.Bold,
                   italic=fmt.fontItalic(), underline=fmt.fontUnderline(),
                   strike=fmt.fontStrikeOut(),
                   baseline=("sub" if vertical == QTextCharFormat.VerticalAlignment.AlignSubScript
                             else "super" if vertical == QTextCharFormat.VerticalAlignment.AlignSuperScript
                             else "normal"),
                   color=fmt.foreground().color().name() if fmt.hasProperty(QTextFormat.Property.ForegroundBrush) else "",
                   highlight=fmt.background().color().name() if fmt.hasProperty(QTextFormat.Property.BackgroundBrush) else "")


def _para_to_qt(spec: ParagraphStyle):
    fmt = QTextBlockFormat()
    fmt.setAlignment({
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }[spec.align])
    fmt.setLeftMargin(spec.indent * 24)
    fmt.setLineHeight(int(spec.line_height * 100), QTextBlockFormat.LineHeightTypes.ProportionalHeight)
    if spec.shading:
        fmt.setBackground(QColor(spec.shading))
    if spec.border:
        fmt.setProperty(_BORDER_PROPERTY, True)
    return fmt


def _para_from_qt(fmt: QTextBlockFormat, start: int, list_kind: str):
    align = fmt.alignment()
    alignment = ("center" if align & Qt.AlignmentFlag.AlignHCenter else
                 "right" if align & Qt.AlignmentFlag.AlignRight else
                 "justify" if align & Qt.AlignmentFlag.AlignJustify else "left")
    ratio = (fmt.lineHeight() / 100.0 if
             fmt.lineHeightType() == QTextBlockFormat.LineHeightTypes.ProportionalHeight else 1.0)
    return ParagraphStyle(start=start, align=alignment,
                          indent=max(0, min(12, round(fmt.leftMargin() / 24))),
                          list_kind=list_kind, line_height=max(1.0, min(3.0, round(ratio, 2))),
                          shading=fmt.background().color().name() if
                          fmt.hasProperty(QTextFormat.Property.BackgroundBrush) else "",
                          border=bool(fmt.property(_BORDER_PROPERTY)))


def apply_rich(editor: QTextEdit, text: str, rich: RichFormatting):
    validate_rich(rich, text)
    editor.blockSignals(True)
    try:
        editor.setPlainText(text)
        editor.document().setDefaultFont(QFont(DEFAULT_FONT, DEFAULT_SIZE))
        positions = _offsets(text)
        cursor = QTextCursor(editor.document())
        for run in rich.runs:
            cursor.setPosition(positions[run.start])
            cursor.setPosition(positions[run.end], QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(_format_to_qt(run))
        for paragraph in rich.paragraphs:
            cursor.setPosition(positions[paragraph.start])
            cursor.setBlockFormat(_para_to_qt(paragraph))
            if paragraph.list_kind != "none":
                listfmt = QTextListFormat()
                listfmt.setIndent(max(1, paragraph.indent + 1))
                listfmt.setStyle({
                    "bullet": QTextListFormat.Style.ListDisc,
                    "decimal": QTextListFormat.Style.ListDecimal,
                    "lower-alpha": QTextListFormat.Style.ListLowerAlpha,
                    "upper-alpha": QTextListFormat.Style.ListUpperAlpha,
                }[paragraph.list_kind])
                cursor.createList(listfmt)
        editor.moveCursor(QTextCursor.MoveOperation.Start)
    finally:
        editor.blockSignals(False)


def capture_rich(editor: QTextEdit) -> tuple[str, RichFormatting]:
    print('RICHDIAG: capture enter',flush=True)
    text = editor.toPlainText()
    positions = _offsets(text)
    result = RichFormatting()
    doc = editor.document()
    block = doc.begin()
    while block.isValid():
        start = _py_index(positions, block.position())
        bf = block.blockFormat()
        listing = block.textList()
        kind = "none"
        if listing is not None:
            kind = {
                QTextListFormat.Style.ListDisc: "bullet",
                QTextListFormat.Style.ListDecimal: "decimal",
                QTextListFormat.Style.ListLowerAlpha: "lower-alpha",
                QTextListFormat.Style.ListUpperAlpha: "upper-alpha",
            }.get(listing.format().style(), "none")
        print('RICHDIAG: before para from qt',flush=True)
        pf = _para_from_qt(bf, start, kind)
        print('RICHDIAG: after para from qt',flush=True)
        if pf != ParagraphStyle(start):
            result.paragraphs.append(pf)
        iterator = block.begin()
        while not iterator.atEnd():
            fragment = iterator.fragment()
            if fragment.isValid() and fragment.length():
                left = _py_index(positions, fragment.position())
                right = _py_index(positions, fragment.position() + fragment.length())
                if left < right:
                    candidate = _format_from_qt(fragment.charFormat(), left, right)
                    if (candidate.family or candidate.size or candidate.bold or candidate.italic
                        or candidate.underline or candidate.strike or candidate.baseline != "normal"
                        or candidate.color or candidate.highlight):
                        if (result.runs and result.runs[-1].end == left
                            and (vars(result.runs[-1]) | {"start": left, "end": right}) == vars(candidate)):
                            result.runs[-1].end = right
                        else:
                            result.runs.append(candidate)
            iterator += 1
        block = block.next()
    print('RICHDIAG: before capture validation',flush=True)
    validate_rich(result, text)
    print('RICHDIAG: capture return',flush=True)
    return text, result


class SafeRichTextEdit(QTextEdit):
    """Only plain content crosses clipboard boundary. No URLs or external HTML."""
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())


class RichTextRibbon(QWidget):
    """Microsoft-Word-inspired functional Font and Paragraph ribbon."""
    def __init__(self, editor: SafeRichTextEdit, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("richTextRibbon")
        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("richRibbonScroller")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(False)
        scroll.setMaximumHeight(102)
        inner = QWidget()
        vertical = QVBoxLayout(inner)
        vertical.setSpacing(3)
        vertical.setContentsMargins(2, 2, 2, 2)
        first, second = QHBoxLayout(), QHBoxLayout()
        vertical.addLayout(first)
        vertical.addLayout(second)
        scroll.setWidget(inner)
        container.addWidget(scroll)
        self.setMinimumWidth(0)
        self.family = QFontComboBox()
        self.family.setObjectName("richFontFamily")
        self.family.setCurrentFont(QFont(DEFAULT_FONT))
        self.family.currentFontChanged.connect(
            lambda font: self.apply_char(lambda f: f.setFontFamily(font.family())))
        first.addWidget(self.family, 2)
        self.size = QComboBox()
        self.size.setObjectName("richFontSize")
        self.size.setEditable(True)
        self.size.addItems([str(x) for x in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72)])
        self.size.setCurrentText(str(DEFAULT_SIZE))
        self.size.activated.connect(lambda *_: self.choose_size())
        self.size.lineEdit().editingFinished.connect(self.choose_size)
        first.addWidget(self.size)
        self.button(first, "A+", lambda: self.scale_size(1), "richGrowFont")
        self.button(first, "A−", lambda: self.scale_size(-1), "richShrinkFont")
        self.button(first, "Aa", self.change_case, "richChangeCase")
        self.button(first, "Clear", self.clear_format, "richClearFormat")
        first.addStretch(1)
        self.button(first, "• List", lambda: self.listify("bullet"), "richBullets")
        self.button(first, "1. List", lambda: self.listify("decimal"), "richNumbering")
        self.button(first, "Sort", self.sort_lines, "richSortParagraphs")
        self.button(first, "Outdent", lambda: self.indent(-1), "richOutdent")
        self.button(first, "Indent", lambda: self.indent(1), "richIndent")
        self.button(first, "¶", self.show_paragraph_marks, "richShowMarks")
        for label, prop, ident in (
            ("B", "bold", "richBold"), ("I", "italic", "richItalic"),
            ("U", "underline", "richUnderline"), ("S̶", "strike", "richStrike"),
            ("x₂", "sub", "richSubscript"), ("x²", "super", "richSuperscript")
        ):
            self.button(second, label, lambda key=prop: self.toggle(key), ident)
        self.button(second, "A Color", lambda: self.pick_color(False), "richTextColor")
        self.button(second, "Highlight", lambda: self.pick_color(True), "richHighlight")
        for label, align, ident in (
            ("Left", Qt.AlignmentFlag.AlignLeft, "richAlignLeft"),
            ("Center", Qt.AlignmentFlag.AlignHCenter, "richAlignCenter"),
            ("Right", Qt.AlignmentFlag.AlignRight, "richAlignRight"),
            ("Justify", Qt.AlignmentFlag.AlignJustify, "richJustify")
        ):
            self.button(second, label, lambda value=align: self.align(value), ident)
        self.button(second, "Line", self.line_spacing, "richLineSpacing")
        self.button(second, "Shade", self.shade, "richShading")
        self.button(second, "Border", self.border, "richBorder")
        second.addStretch(1)
        inner.adjustSize()
        self.editor.currentCharFormatChanged.connect(self.sync)

    def button(self, layout, label, callback, ident):
        button = QPushButton(label)
        button.setObjectName(ident)
        button.setToolTip(label)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def apply_char(self, setter):
        print('RICHDIAG: apply char enter',flush=True)
        fmt = QTextCharFormat()
        setter(fmt)
        cur = self.editor.textCursor()
        print('RICHDIAG: pre selection merge',flush=True)
        cur.mergeCharFormat(fmt)
        print('RICHDIAG: post selection merge',flush=True)
        self.editor.mergeCurrentCharFormat(fmt)
        print('RICHDIAG: post current merge',flush=True)
        self.editor.setFocus()

    def sync(self, fmt):
        print('RICHDIAG: sync enter',flush=True)
        self.family.blockSignals(True)
        print('RICHDIAG: before sync family',flush=True)
        self.family.setCurrentFont(QFont(fmt.fontFamily() or DEFAULT_FONT))
        print('RICHDIAG: after sync family',flush=True)
        self.family.blockSignals(False)
        self.size.blockSignals(True)
        self.size.setCurrentText(str(round(fmt.fontPointSize() or DEFAULT_SIZE)))
        self.size.blockSignals(False)
        print('RICHDIAG: sync complete',flush=True)

    def choose_size(self):
        try:
            value = float(self.size.currentText().replace(",", "."))
            if not 6 <= value <= 96:
                raise ValueError()
        except ValueError:
            return
        self.apply_char(lambda fmt: fmt.setFontPointSize(value))

    def scale_size(self, direction):
        size = self.editor.currentCharFormat().fontPointSize() or DEFAULT_SIZE
        self.apply_char(lambda f: f.setFontPointSize(max(6, min(96, size + direction))))

    def toggle(self, value):
        fmt = self.editor.currentCharFormat()
        if value == "bold":
            self.apply_char(lambda f: f.setFontWeight(
                QFont.Weight.Normal if fmt.fontWeight() >= QFont.Weight.Bold else QFont.Weight.Bold))
        elif value in ("italic", "underline", "strike"):
            getter, setter = {
                "italic": (fmt.fontItalic, QTextCharFormat.setFontItalic),
                "underline": (fmt.fontUnderline, QTextCharFormat.setFontUnderline),
                "strike": (fmt.fontStrikeOut, QTextCharFormat.setFontStrikeOut),
            }[value]
            self.apply_char(lambda f: setter(f, not getter()))
        else:
            wanted = (QTextCharFormat.VerticalAlignment.AlignSubScript if value == "sub"
                      else QTextCharFormat.VerticalAlignment.AlignSuperScript)
            current = QTextCharFormat.VerticalAlignment.AlignNormal if fmt.verticalAlignment() == wanted else wanted
            self.apply_char(lambda f: f.setVerticalAlignment(current))

    def pick_color(self, background):
        choice = QColorDialog.getColor(QColor("#ffff00" if background else "#202124"), self)
        if choice.isValid():
            self.apply_char(lambda f: f.setBackground(choice) if background else f.setForeground(choice))

    def clear_format(self):
        self.apply_char(lambda f: f.setFontWeight(QFont.Weight.Normal))
        cursor = self.editor.textCursor()
        fmt = QTextCharFormat()
        fmt.setFont(QFont(DEFAULT_FONT, DEFAULT_SIZE))
        fmt.setFontUnderline(False)
        fmt.setFontStrikeOut(False)
        fmt.setVerticalAlignment(QTextCharFormat.VerticalAlignment.AlignNormal)
        fmt.setForeground(QColor("#202124"))
        fmt.setBackground(QColor("#ffffff"))
        cursor.setCharFormat(fmt)
        self.editor.setFocus()

    def change_case(self):
        cursor = self.editor.textCursor()
        if cursor.hasSelection():
            content = cursor.selectedText().replace("\u2029", "\n")
            value = content.upper() if content != content.upper() else content.lower()
            cursor.insertText(value)
        self.editor.setFocus()

    def align(self, alignment):
        self.editor.setAlignment(alignment)
        self.editor.setFocus()

    def indent(self, delta):
        cursor = self.editor.textCursor()
        fmt = cursor.blockFormat()
        fmt.setLeftMargin(max(0, min(288, fmt.leftMargin() + delta * 24)))
        cursor.setBlockFormat(fmt)
        self.editor.setFocus()

    def listify(self, kind):
        cursor = self.editor.textCursor()
        existing = cursor.currentList()
        if existing:
            existing.remove(cursor.block())
        else:
            fmt = QTextListFormat()
            fmt.setStyle(QTextListFormat.Style.ListDisc if kind == "bullet"
                         else QTextListFormat.Style.ListDecimal)
            fmt.setIndent(1)
            cursor.createList(fmt)
        self.editor.setFocus()

    def line_spacing(self):
        items = ["1.0", "1.15", "1.5", "2.0", "2.5", "3.0"]
        chosen, ok = QInputDialog.getItem(self, "Line spacing", "Multiplier", items, 1, False)
        if ok:
            cursor = self.editor.textCursor()
            fmt = cursor.blockFormat()
            fmt.setLineHeight(round(float(chosen) * 100), QTextBlockFormat.LineHeightTypes.ProportionalHeight)
            cursor.setBlockFormat(fmt)
        self.editor.setFocus()

    def shade(self):
        shade = QColorDialog.getColor(QColor("#eeeeee"), self)
        if shade.isValid():
            cursor = self.editor.textCursor()
            fmt = cursor.blockFormat()
            fmt.setBackground(shade)
            cursor.setBlockFormat(fmt)
        self.editor.setFocus()

    def border(self):
        cursor = self.editor.textCursor()
        fmt = cursor.blockFormat()
        fmt.setProperty(_BORDER_PROPERTY, not bool(fmt.property(_BORDER_PROPERTY)))
        cursor.setBlockFormat(fmt)
        self.editor.setFocus()

    def sort_lines(self):
        """Sort selected paragraphs; never re-order canonical report modules."""
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return
        text = cursor.selectedText().replace("\u2029", "\n")
        lines = text.split("\n")
        if len(lines) < 2:
            return
        lines.sort(key=lambda x: x.casefold())
        cursor.insertText("\n".join(lines))
        self.editor.setFocus()

    def show_paragraph_marks(self):
        from PySide6.QtGui import QTextOption
        options = self.editor.document().defaultTextOption()
        flag = QTextOption.Flag.ShowLineAndParagraphSeparators
        options.setFlags(options.flags() ^ flag)
        self.editor.document().setDefaultTextOption(options)
        self.editor.viewport().update()
        self.editor.setFocus()
