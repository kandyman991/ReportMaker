"""V2-only explicit foreground/background pairs for Windows Qt palettes.

No application-global stylesheet and no modification of V1 widgets. Controls
must remain readable under native light and dark themes and when disabled.
"""

BUTTON_CHROME = """
QPushButton, QToolButton {
    color: #182d42; background-color: #ecf3fa;
    border: 1px solid #8fa5bb; border-radius: 4px;
    padding: 5px 9px; min-height: 22px;
}
QPushButton:hover, QToolButton:hover {
    color: #10253d; background-color: #d9e9fb; border-color: #2865a0;
}
QPushButton:pressed, QToolButton:pressed {
    color: #ffffff; background-color: #175a96; border-color: #104977;
}
QToolButton:checked {
    color: #ffffff; background-color: #1268a3;
    border: 2px solid #073d67; font-weight: bold;
}
QToolButton:checked:hover {
    color: #ffffff; background-color: #145b91;
}
QPushButton:disabled, QToolButton:disabled {
    color: #536375; background-color: #e5ebf1; border-color: #aeb9c5;
}
QPushButton:focus, QToolButton:focus {
    border: 2px solid #1665c2;
}
"""

FIELD_CHROME = """
QLineEdit, QPlainTextEdit, QComboBox, QSpinBox, QListWidget {
    color: #182d42; background-color: #ffffff;
    border: 1px solid #91a6bb; border-radius: 3px;
    selection-background-color: #155e9b; selection-color: #ffffff;
}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled,
QSpinBox:disabled, QListWidget:disabled {
    color: #526377; background-color: #e9eef3; border-color: #b3bfca;
}
QComboBox QAbstractItemView {
    color: #182d42; background-color: #ffffff;
    selection-background-color: #155e9b; selection-color: #ffffff;
}
"""

PHOTO_EDITOR_CHROME = """
QDialog#pictureEditorDialog {
    color: #182d42; background-color: #eef3f8;
}
QDialog#pictureEditorDialog QLabel { color: #182d42; background-color: #eef3f8; }
""" + BUTTON_CHROME + FIELD_CHROME

PHOTO_TOOL_CHROME = """
QToolButton {
    color: #1b3550; background-color: #f5f8fc;
    border: 1px solid #8ea6bf; border-radius: 5px;
    padding: 5px; font-size: 16px; font-weight: bold;
    min-width: 26px; min-height: 26px;
}
QToolButton:hover {
    color: #0e2b47; background-color: #deecfa; border-color: #2165a1;
}
QToolButton:checked {
    color: #ffffff; background-color: #1268a3;
    border: 2px solid #073d67;
}
QToolButton:checked:hover { color: #ffffff; background-color: #095180; }
QToolButton:disabled {
    color: #536375; background-color: #e6ecf2; border-color: #b3bfca;
}
QToolButton:focus { border: 2px solid #e89a00; }
"""
