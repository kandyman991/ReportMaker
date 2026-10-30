"""Keyboard behaviour shared by every inline text editor in the V2 workspace."""
from __future__ import annotations

from PySide6.QtCore import Qt

_PLAIN_PASTE = Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier


def handle_plain_paste(editor, event) -> bool:
    """Treat Ctrl+Shift+V as "paste as plain text" and report whether it was.

    Browsers and Office use this chord to paste without formatting, which is
    exactly what the AI copy/paste workflow wants. These editors only ever hold
    plain text, so it is equivalent to Ctrl+V. No application action may claim
    this chord, or it would silently swallow the paste.
    """
    if event.key() == Qt.Key.Key_V and event.modifiers() == _PLAIN_PASTE:
        editor.paste()
        event.accept()
        return True
    return False
