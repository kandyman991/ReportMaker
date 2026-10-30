"""V2 annotation-tool ribbon using the existing, shared PictureEditorDialog.

The V1 editor's validated composition/render operations remain authoritative.
Only V2 chrome is adapted: visible icon-like tools and active selection instead
of a hidden dropdown. No new image model or secondary annotation store.
"""
from __future__ import annotations

from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QToolButton

from ...photo_editor import PictureEditorDialog, TOOLS
from ..contrast import PHOTO_EDITOR_CHROME, PHOTO_TOOL_CHROME

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
        # Apply V2-only light chrome with explicit dark foregrounds. A dark
        # system palette otherwise renders white glyphs on white tool buttons.
        self.setStyleSheet(PHOTO_EDITOR_CHROME)
        ribbon = self.layout().itemAt(0).layout()
        if ribbon is None:
            raise RuntimeError("Photo editor tools layout is unavailable")
        ribbon.removeWidget(self.tool_choice)
        self.tool_choice.hide()
        # Annotation tools and property/actions were previously forced into
        # one unbroken row, clipping controls on laptop-size Windows screens.
        # Move the existing action widgets into the second row unchanged.
        actions = QHBoxLayout()
        while ribbon.count():
            item = ribbon.takeAt(0)
            if item.widget() is not None:
                actions.addWidget(item.widget())
            else:
                actions.addItem(item)
        self.layout().insertLayout(1, actions)
        # The inherited eight-control photo properties row still forces a
        # >950px minimum width with Windows font metrics and display scaling.
        # Keep width/alignment/straighten together; move rotation/flip/reset
        # into a second row instead of clipping buttons off screen.
        properties = self.layout().itemAt(3).layout()
        if properties is None or properties.count() != 8:
            raise RuntimeError("Photo editor properties layout changed")
        transforms = QHBoxLayout()
        while properties.count() > 4:
            transforms.addItem(properties.takeAt(4))
        self.layout().insertLayout(4, transforms)
        # The inherited single-line export caveat is longer than 950px in
        # Windows Segoe UI metrics and can still force a 1114px dialog,
        # independent of the tool/property rows. Wrap it instead.
        notice = next((label for label in self.findChildren(QLabel)
                       if label.text().startswith("Annotations remain editable in .rmproj.")),
                      None)
        if notice is None:
            raise RuntimeError("Photo editor informational note is missing")
        notice.setObjectName("v2PhotoExportNotice")
        notice.setWordWrap(True)
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
            button.setStyleSheet(PHOTO_TOOL_CHROME)
            self.tool_buttons.addButton(button, index)
            ribbon.insertWidget(index, button)
            button.clicked.connect(
                lambda checked=False, i=index: self.tool_choice.setCurrentIndex(i))
        ribbon.addStretch(1)
        self.tool_choice.currentIndexChanged.connect(
            lambda index: self.tool_buttons.button(index).setChecked(True)
            if self.tool_buttons.button(index) is not None else None)
