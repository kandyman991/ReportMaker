"""Native Word-style formatting ribbon for a structured report text block.

Editing is intentional and limited to the selected canonical Paragraph/Heading
block. No HTML/remote images can be pasted. The application saves semantic
Unicode code-point ranges, never Qt HTML or a parallel copy of report text.
"""
from __future__ import annotations

from copy import deepcopy
from bisect import bisect_right

from PySide6.QtCore import Qt, QEvent, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QTextCharFormat, QTextBlockFormat, QTextCursor, QTextListFormat, QTextFormat
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
    families = fmt.fontFamilies() if fmt.hasProperty(QTextFormat.Property.FontFamilies) else []
    base = families[0] if families else ""
    point_size = fmt.fontPointSize()
    vertical = fmt.verticalAlignment()
    result = TextRun(start=start, end=end,
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
    return result


def _para_to_qt(spec: ParagraphStyle):
    fmt = QTextBlockFormat()
    fmt.setAlignment({
        "left": Qt.AlignmentFlag.AlignLeft,
        "center": Qt.AlignmentFlag.AlignHCenter,
        "right": Qt.AlignmentFlag.AlignRight,
        "justify": Qt.AlignmentFlag.AlignJustify,
    }[spec.align])
    fmt.setLeftMargin(spec.indent * 24)
    fmt.setLineHeight(int(spec.line_height * 100), QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
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
        pf = _para_from_qt(bf, start, kind)
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
    validate_rich(result, text)
    return text, result


class SafeRichTextEdit(QTextEdit):
    """Only plain content crosses clipboard boundary. No URLs or external HTML."""
    def insertFromMimeData(self, source):
        if source.hasText():
            self.insertPlainText(source.text())


class RichTextRibbon(QWidget):
    """Microsoft-Word-inspired functional Font and Paragraph ribbon."""

    formatApplied = Signal()  # Valid edits only; never signal while typing a font name.
    def __init__(self, editor: SafeRichTextEdit, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setObjectName("richTextRibbon")
        self._buttons = {}
        self._tips = {}
        # A pressed button has a solid outline as well as a contrasting fill.
        # Mixed selections use a dashed outline, never a false checked state.
        self.setStyleSheet("""
            QPushButton[richToggle="true"] { min-width: 27px; min-height: 25px; padding: 2px 5px; }
            QPushButton[richToggle="true"]:checked {
                background-color: palette(highlight); color: palette(highlighted-text);
                border: 2px solid palette(highlight); font-weight: 800;
            }
            QPushButton[richMixed="true"] {
                border: 2px dashed palette(highlight); font-weight: 800;
            }
        """)
        container = QVBoxLayout(self)
        container.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("richRibbonScroller")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidgetResizable(False)
        inner = QWidget()
        vertical = QVBoxLayout(inner)
        vertical.setSpacing(3)
        vertical.setContentsMargins(2, 2, 2, 2)
        first, second = QHBoxLayout(), QHBoxLayout()
        vertical.addLayout(first)
        vertical.addLayout(second)
        # Keep the ribbon outside the editor's splitter; navigation remains
        # discoverable when the central pane is narrower than both tool rows.
        header = QHBoxLayout()
        title = QLabel("FONT  ·  PARAGRAPH")
        title.setObjectName("richRibbonTitle")
        header.addWidget(title)
        header.addStretch(1)
        hint = QLabel("More tools")
        hint.setObjectName("richRibbonScrollHint")
        header.addWidget(hint)
        for symbol, direction, name in (
            ("◀", -1, "richRibbonScrollLeft"),
            ("▶", 1, "richRibbonScrollRight"),
        ):
            control = QToolButton()
            control.setText(symbol)
            control.setObjectName(name)
            control.setToolTip("Scroll formatting tools horizontally")
            control.setAccessibleName("Previous formatting tools" if direction < 0
                                      else "Next formatting tools")
            control.clicked.connect(
                lambda _checked=False, step=direction: scroll.horizontalScrollBar().setValue(
                    scroll.horizontalScrollBar().value() + step * 260))
            header.addWidget(control)
        container.addLayout(header)
        container.addWidget(scroll)
        self.scroller = scroll
        self.setMinimumWidth(0)
        self.family = QFontComboBox()
        self.family.setObjectName("richFontFamily")
        self.family.setCurrentFont(QFont(DEFAULT_FONT))
        # QFontComboBox changes its currentFont *during each keystroke*.
        # Never apply a partially typed name (or restore editor focus) until commit.
        self.family.setAccessibleName("Font family")
        self.family.setToolTip("Font family — type a name, then press Enter or select a font")
        self.family.activated.connect(lambda *_: self.choose_family())
        self.family.lineEdit().editingFinished.connect(self.choose_family)
        self.family.lineEdit().installEventFilter(self)
        first.addWidget(self.family, 2)
        self.size = QComboBox()
        self.size.setObjectName("richFontSize")
        self.size.setEditable(True)
        self.size.addItems([str(x) for x in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 32, 36, 48, 72)])
        self.size.setCurrentText(str(DEFAULT_SIZE))
        self.size.setAccessibleName("Font size")
        self.size.setToolTip("Font size in points (6–96)")
        self.size.lineEdit().installEventFilter(self)
        self.size.activated.connect(lambda *_: self.choose_size())
        self.size.lineEdit().editingFinished.connect(self.choose_size)
        first.addWidget(self.size)
        self.button(first, "A+", lambda: self.scale_size(1), "richGrowFont")
        self.button(first, "A−", lambda: self.scale_size(-1), "richShrinkFont")
        self.button(first, "Aa", self.change_case, "richChangeCase")
        self.button(first, "⌫", self.clear_format, "richClearFormat", "Clear formatting")
        first.addStretch(1)
        self.button(first, "• ≡", lambda: self.listify("bullet"), "richBullets", "Bulleted list", checkable=True)
        self.button(first, "1. ≡", lambda: self.listify("decimal"), "richNumbering", "Numbered list", checkable=True)
        self.button(first, "A↧Z", self.sort_lines, "richSortParagraphs", "Sort selected paragraphs")
        self.button(first, "⇤", lambda: self.indent(-1), "richOutdent", "Decrease indent")
        self.button(first, "⇥", lambda: self.indent(1), "richIndent", "Increase indent")
        self.button(first, "¶", self.show_paragraph_marks, "richShowMarks", "Show paragraph marks", checkable=True)
        for label, prop, ident in (
            ("B", "bold", "richBold"), ("I", "italic", "richItalic"),
            ("U", "underline", "richUnderline"), ("S̶", "strike", "richStrike"),
            ("x₂", "sub", "richSubscript"), ("x²", "super", "richSuperscript")
        ):
            names = {"bold": "Bold (Ctrl+B)", "italic": "Italic (Ctrl+I)",
                     "underline": "Underline (Ctrl+U)", "strike": "Strikethrough",
                     "sub": "Subscript", "super": "Superscript"}
            self.button(second, label, lambda _checked=False, key=prop: self.toggle(key),
                        ident, names[prop], checkable=True)
        self.button(second, "A▾", lambda: self.pick_color(False), "richTextColor", "Text color")
        self.button(second, "▰", lambda: self.pick_color(True), "richHighlight", "Text highlight color")
        for label, align, ident, name in (
            ("≡↤", Qt.AlignmentFlag.AlignLeft, "richAlignLeft", "Align left"),
            ("≡", Qt.AlignmentFlag.AlignHCenter, "richAlignCenter", "Align center"),
            ("↦≡", Qt.AlignmentFlag.AlignRight, "richAlignRight", "Align right"),
            ("☰", Qt.AlignmentFlag.AlignJustify, "richJustify", "Justify text")
        ):
            self.button(second, label, lambda _checked=False, value=align: self.align(value),
                        ident, name, checkable=True)
        self.button(second, "↕", self.line_spacing, "richLineSpacing", "Line spacing")
        self.button(second, "▧", self.shade, "richShading", "Paragraph shading")
        self.button(second, "▣", self.border, "richBorder", "Paragraph border", checkable=True)
        second.addStretch(1)
        # Qt requires the child layout to be completely populated BEFORE
        # setWidget(). In RC2 it was attached while both tool rows were empty,
        # so the scroll area retained a zero/obsolete size and clipped controls.
        inner.adjustSize()
        scroll.setWidget(inner)
        # QScrollArea with a non-resizable content widget otherwise has a
        # zero-height size hint on some Qt/Windows DPI and splitter layouts.
        # Reserve the real height of both rows and the horizontal scrollbar.
        scroll.setFixedHeight(inner.sizeHint().height() +
                              scroll.horizontalScrollBar().sizeHint().height() +
                              2 * scroll.frameWidth() + 4)
        self.setMinimumHeight(container.sizeHint().height())
        self.editor.currentCharFormatChanged.connect(self.sync)
        self.editor.cursorPositionChanged.connect(self.sync)
        self.editor.selectionChanged.connect(self.sync)
        self.editor.textChanged.connect(self.sync)
        self.sync()

    def button(self, layout, label, callback, ident, tooltip=None, *, checkable=False):
        button = QPushButton(label)
        button.setObjectName(ident)
        name = tooltip or label
        button.setToolTip(name)
        button.setAccessibleName(name)
        button.setCheckable(checkable)
        if checkable:
            button.setProperty("richToggle", True)
            button.setProperty("richMixed", False)
        button.clicked.connect(callback)
        layout.addWidget(button)
        self._buttons[ident] = button
        self._tips[ident] = name
        return button

    def eventFilter(self, watched, event):
        # Escape abandons an incomplete/invalid font or size without changing
        # selection, content, or the current editor insertion format.
        if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
            if watched is self.family.lineEdit():
                self._sync_selectors(force=True)
                return True
            if watched is self.size.lineEdit():
                self._sync_selectors(force=True)
                return True
        return super().eventFilter(watched, event)

    def apply_char(self, setter, *, restore_focus=True):
        fmt = QTextCharFormat()
        setter(fmt)
        cur = self.editor.textCursor()
        cur.mergeCharFormat(fmt)
        self.editor.mergeCurrentCharFormat(fmt)
        self.sync()
        self.formatApplied.emit()
        if restore_focus:
            self.editor.setFocus()

    def _selected_formats(self):
        cursor = self.editor.textCursor()
        if not cursor.hasSelection():
            return [self.editor.currentCharFormat()]
        start, end = cursor.selectionStart(), cursor.selectionEnd()
        formats = []
        block = self.editor.document().findBlock(start)
        while block.isValid() and block.position() < end:
            iterator = block.begin()
            while not iterator.atEnd():
                fragment = iterator.fragment()
                if (fragment.isValid() and fragment.position() < end
                        and fragment.position() + fragment.length() > start):
                    formats.append(fragment.charFormat())
                iterator += 1
            block = block.next()
        return formats or [cursor.charFormat()]

    @staticmethod
    def _char_flag(fmt, name):
        if name == "bold":
            return fmt.fontWeight() >= QFont.Weight.Bold
        if name == "italic":
            return fmt.fontItalic()
        if name == "underline":
            return fmt.fontUnderline()
        if name == "strike":
            return fmt.fontStrikeOut()
        if name == "sub":
            return fmt.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSubScript
        return fmt.verticalAlignment() == QTextCharFormat.VerticalAlignment.AlignSuperScript

    @staticmethod
    def _uniform(values):
        """Return True, False, or None for mixed selections."""
        return values[0] if all(x == values[0] for x in values) else None

    def _style_state(self, name):
        return self._uniform([self._char_flag(fmt, name)
                              for fmt in self._selected_formats()])

    def _selected_blocks(self):
        cursor = self.editor.textCursor()
        start = cursor.selectionStart()
        # An end exactly at the next paragraph's start excludes that paragraph.
        end = max(start, cursor.selectionEnd() - 1) if cursor.hasSelection() else start
        block = self.editor.document().findBlock(start)
        blocks = []
        while block.isValid() and block.position() <= end:
            blocks.append(block)
            block = block.next()
        return blocks

    @staticmethod
    def _alignment(fmt):
        align = fmt.alignment()
        if align & Qt.AlignmentFlag.AlignHCenter:
            return "richAlignCenter"
        if align & Qt.AlignmentFlag.AlignRight:
            return "richAlignRight"
        if align & Qt.AlignmentFlag.AlignJustify:
            return "richJustify"
        return "richAlignLeft"

    def _set_button_state(self, ident, state):
        button = self._buttons[ident]
        mixed = state is None
        if button.property("richMixed") != mixed or button.isChecked() != (state is True):
            button.setProperty("richMixed", mixed)
            button.setChecked(state is True)
            button.style().unpolish(button)
            button.style().polish(button)
            button.update()
        button.setToolTip(self._tips[ident] + (" (mixed selection)" if mixed else ""))
        button.setAccessibleDescription("Mixed selection" if mixed else
                                        "Active" if state else "Inactive")

    def _sync_selectors(self, *, force=False):
        fmt = self.editor.currentCharFormat()
        families = fmt.fontFamilies() if fmt.hasProperty(QTextFormat.Property.FontFamilies) else []
        family = families[0] if families else DEFAULT_FONT
        if force or not self.family.lineEdit().hasFocus():
            self.family.blockSignals(True)
            try:
                self.family.setCurrentFont(QFont(family))
                self.family.setCurrentText(family)
            finally:
                self.family.blockSignals(False)
        if force or not self.size.lineEdit().hasFocus():
            self.size.blockSignals(True)
            try:
                self.size.setCurrentText(f"{fmt.fontPointSize() or DEFAULT_SIZE:g}")
            finally:
                self.size.blockSignals(False)

    def sync(self, *_args):
        # Only observe document formatting; never apply commands from sync().
        self._sync_selectors()
        for name, ident in (
            ("bold", "richBold"), ("italic", "richItalic"),
            ("underline", "richUnderline"), ("strike", "richStrike"),
            ("sub", "richSubscript"), ("super", "richSuperscript")
        ):
            self._set_button_state(ident, self._style_state(name))
        blocks = self._selected_blocks()
        alignments = [self._alignment(block.blockFormat()) for block in blocks]
        for ident in ("richAlignLeft", "richAlignCenter", "richAlignRight", "richJustify"):
            self._set_button_state(ident, self._uniform([item == ident for item in alignments]))
        kinds = [("none" if block.textList() is None else
                  "bullet" if block.textList().format().style() == QTextListFormat.Style.ListDisc
                  else "decimal")
                 for block in blocks]
        for ident, kind in (("richBullets", "bullet"), ("richNumbering", "decimal")):
            self._set_button_state(ident, self._uniform([item == kind for item in kinds]))
        self._set_button_state("richBorder", self._uniform(
            [bool(block.blockFormat().property(_BORDER_PROPERTY)) for block in blocks]))
        from PySide6.QtGui import QTextOption
        self._set_button_state("richShowMarks", bool(
            self.editor.document().defaultTextOption().flags()
            & QTextOption.Flag.ShowLineAndParagraphSeparators))

    def choose_family(self):
        # Only accept an installed exact family, not QFontComboBox's transient
        # nearest-match value while the user edits the text.
        typed = self.family.currentText().strip()
        match = next((family for family in QFontDatabase.families()
                      if family.casefold() == typed.casefold()), None)
        if match is not None:
            formats = self._selected_formats()
            if any((fmt.fontFamilies()[0] if fmt.fontFamilies() else DEFAULT_FONT) != match
                   for fmt in formats):
                self.apply_char(lambda fmt: fmt.setFontFamily(match), restore_focus=False)
        self._sync_selectors(force=True)

    def choose_size(self):
        try:
            value = float(self.size.currentText().replace(",", "."))
            if not 6 <= value <= 96:
                raise ValueError()
        except ValueError:
            self._sync_selectors(force=True)
            return
        if any(fmt.fontPointSize() != value for fmt in self._selected_formats()):
            self.apply_char(lambda fmt: fmt.setFontPointSize(value), restore_focus=False)
        self._sync_selectors(force=True)

    def scale_size(self, direction):
        size = self.editor.currentCharFormat().fontPointSize() or DEFAULT_SIZE
        self.apply_char(lambda f: f.setFontPointSize(max(6, min(96, size + direction))))

    def toggle(self, value):
        # A mixed selection becomes fully enabled; a fully enabled selection
        # becomes disabled. Never use a stale insertion-format proxy for a span.
        enabled = self._style_state(value) is not True
        if value == "bold":
            self.apply_char(lambda fmt: fmt.setFontWeight(
                QFont.Weight.Bold if enabled else QFont.Weight.Normal))
        elif value in ("italic", "underline", "strike"):
            setter = {
                "italic": QTextCharFormat.setFontItalic,
                "underline": QTextCharFormat.setFontUnderline,
                "strike": QTextCharFormat.setFontStrikeOut,
            }[value]
            self.apply_char(lambda fmt: setter(fmt, enabled))
        else:
            align = (QTextCharFormat.VerticalAlignment.AlignSubScript if value == "sub"
                     else QTextCharFormat.VerticalAlignment.AlignSuperScript)
            self.apply_char(lambda fmt: fmt.setVerticalAlignment(
                align if enabled else QTextCharFormat.VerticalAlignment.AlignNormal))

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
            fmt.setLineHeight(round(float(chosen) * 100), QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
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
        self.sync()
        self.editor.setFocus()
