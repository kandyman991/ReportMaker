"""V2 annotation-tool ribbon using the existing, shared PictureEditorDialog.

The V1 editor's validated composition/render operations remain authoritative.
Only V2 chrome is adapted: visible icon-like tools and active selection instead
of a hidden dropdown. No new image model or secondary annotation store.
"""
from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QToolButton

from ...photo_editor import PictureEditorDialog, TOOLS

_GLYPHS = {
    "select": "↖",
    "crop": "⌗",
    "arrow": "➜",
    "line": "╱",
    "rectangle": "▭",
    "ellipse": "◯",
    "highlight": "▤",
    "text": "T",
    "callout": "▢",
    "pen": "✎",
}


class V2PictureEditorDialog(PictureEditorDialog):
    def __init__(self, parent, image_bytes, visual, language):
        super().__init__(parent, image_bytes, visual, language)
        ribbon = self.layout().itemAt(0).layout()
        if ribbon is None:
            raise RuntimeError("Photo editor tools layout is unavailable")
        ribbon.removeWidget(self.tool_choice)
        self.tool_choice.hide()
        self.tool_buttons = QButtonGroup(self)
        self.tool_buttons.setExclusive(True)
        for index, kind in enumerate(TOOLS):
            button = QToolButton(self)
            button.setObjectName(f"v2PhotoTool_{kind}")
            button.setText(_GLYPHS[kind])
            button.setToolTip(kind.replace("_", " ").capitalize())
            button.setAccessibleName(f"{kind.capitalize()} photo tool")
            button.setCheckable(True)
            button.setChecked(index == 0)
            button.setStyleSheet(
                "QToolButton { border: 1px solid #aabbd0; padding: 5px;"
                " border-radius: 5px; background: #f7f9fc; }"
                "QToolButton:checked { background: #1268a3; color: white;"
                " border: 2px solid #073d67; }"
            )
            self.tool_buttons.addButton(button, index)
            ribbon.insertWidget(index, button)
            button.clicked.connect(
                lambda checked=False, i=index: self.tool_choice.setCurrentIndex(i))
        self.tool_choice.currentIndexChanged.connect(
            lambda index: self.tool_buttons.button(index).setChecked(True)
            if self.tool_buttons.button(index) is not None else None)
