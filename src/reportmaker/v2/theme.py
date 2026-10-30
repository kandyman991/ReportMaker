"""V2 design tokens and the application-chrome stylesheet.

The tokens come from the "Workshop" UI proposal. Every foreground/background
pair that carries text is contrast-checked in ``tests/test_v2_theme.py`` (WCAG
4.5:1 for text, 3:1 for control borders), which is what stops the unreadable
dark-theme regressions tracked in issues #99, #101 and #103 from returning.

Scope of this module today: the *chrome* (toolbars, rail, menus, status bar,
buttons, inputs, scrollbars). The Branch Editor canvas still carries its own
light colours in ``branch/canvas.py``, so only ``LIGHT`` is applied. ``DARK`` is
defined and contrast-tested so the canvas can be tokenised in a follow-up
without redesigning the palette.
"""
from __future__ import annotations

from typing import Mapping

LIGHT: dict[str, str] = {
    "bg": "#F3F5F8", "surface": "#FFFFFF", "sunken": "#EAEEF3",
    "line": "#D3DAE3", "line2": "#7F8D9E",
    "text": "#121C26", "text2": "#3D4B5A", "text3": "#52606F",
    "accent": "#0B5CC9", "accent-ink": "#FFFFFF",
    "accent-soft": "#E1ECFB", "accent-soft-ink": "#0A4CA8",
    "warn-bg": "#FFF1CC", "warn-line": "#8A5A00", "warn-ink": "#4A3000",
    "danger": "#B3261E", "success": "#17663F",
}

DARK: dict[str, str] = {
    "bg": "#0E1319", "surface": "#161D25", "sunken": "#1E2731",
    "line": "#2A3541", "line2": "#7C8B9B",
    "text": "#EAF0F6", "text2": "#C3CEDA", "text3": "#9DABBB",
    "accent": "#7DB2FF", "accent-ink": "#08172E",
    "accent-soft": "#1B2E4D", "accent-soft-ink": "#BBD6FF",
    "warn-bg": "#3B2D0A", "warn-line": "#C99A2E", "warn-ink": "#FFE3A0",
    "danger": "#FF9C94", "success": "#7FD6A2",
}

SCHEMES: dict[str, dict[str, str]] = {"light": LIGHT, "dark": DARK}
APPLIED_SCHEMES = ("light",)  # dark waits for the canvas colours to be tokenised

# (foreground token, background token) pairs that carry text: need >= 4.5:1.
TEXT_PAIRS = (
    ("text", "surface"), ("text2", "surface"), ("text3", "surface"), ("text3", "bg"),
    ("text3", "sunken"), ("text2", "sunken"), ("text", "bg"),
    ("accent", "surface"), ("accent", "bg"), ("accent-ink", "accent"),
    ("accent-soft-ink", "accent-soft"), ("warn-ink", "warn-bg"),
    ("danger", "surface"), ("success", "surface"), ("text", "accent-soft"),
    ("accent-soft-ink", "surface"), ("text", "sunken"),
)
# Control borders and focus rings against what they sit on: need >= 3:1.
UI_PAIRS = (("line2", "surface"), ("line2", "bg"), ("accent", "surface"), ("warn-line", "warn-bg"))

FONT_STACK = '"Segoe UI Variable", "Segoe UI", "Inter", system-ui, sans-serif'


def _linear(channel: int) -> float:
    value = channel / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def luminance(color: str) -> float:
    h = color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


def stylesheet(t: Mapping[str, str] = LIGHT) -> str:
    """Qt style sheet for the window chrome. Pure string building, no Qt import."""
    return f"""
QMainWindow, QDialog {{ background: {t['bg']}; color: {t['text']}; }}
QWidget {{ font-family: {FONT_STACK}; }}
QToolTip {{ background: {t['text']}; color: {t['surface']}; border: 0; padding: 6px 8px; }}

QMenuBar {{ background: {t['surface']}; color: {t['text']}; border-bottom: 1px solid {t['line']}; }}
QMenuBar::item {{ padding: 6px 12px; border-radius: 6px; background: transparent; }}
QMenuBar::item:selected {{ background: {t['accent-soft']}; color: {t['accent-soft-ink']}; }}
QMenu {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['line']}; padding: 6px; }}
QMenu::item {{ padding: 8px 24px 8px 12px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t['accent-soft']}; color: {t['accent-soft-ink']}; }}
QMenu::item:disabled {{ color: {t['text3']}; }}
QMenu::separator {{ height: 1px; background: {t['line']}; margin: 6px 4px; }}

QToolBar {{ background: {t['surface']}; border: 0; border-bottom: 1px solid {t['line']}; spacing: 2px; padding: 1px 8px; }}
QToolBar::separator {{ width: 1px; background: {t['line']}; margin: 6px 6px; }}
QToolBar QToolButton {{ color: {t['text']}; background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 3px 7px; }}
QToolBar QToolButton:hover {{ background: {t['sunken']}; }}
QToolBar QToolButton:pressed {{ background: {t['accent-soft']}; color: {t['accent-soft-ink']}; }}
QToolBar QToolButton:checked {{ background: {t['accent-soft']}; color: {t['accent-soft-ink']}; }}
QToolBar QToolButton:disabled {{ color: {t['text3']}; }}
QToolBar QToolButton:focus {{ border: 2px solid {t['accent']}; }}
QToolBar QToolButton::menu-indicator {{ image: none; width: 0; }}

QToolBar#workspaceRail {{ background: {t['surface']}; border: 0; border-right: 1px solid {t['line']};
    padding: 12px 6px; spacing: 6px; }}
QToolBar#workspaceRail QToolButton {{ color: {t['text2']}; min-width: 64px; padding: 8px 4px 6px 4px;
    border-radius: 14px; font-size: 12px; font-weight: 500; }}
QToolBar#workspaceRail QToolButton:checked {{ background: {t['accent-soft']}; color: {t['accent-soft-ink']}; font-weight: 600; }}
QToolBar#workspaceRail QToolButton:hover:!checked {{ background: {t['sunken']}; color: {t['text']}; }}

QTabWidget::pane {{ border: 0; top: 0; background: {t['bg']}; }}

QSplitter#v2WorkspaceSplitter::handle {{ background: {t['line']}; }}
QSplitter#v2WorkspaceSplitter::handle:hover {{ background: {t['line2']}; }}
QTabWidget#v2WorkspacePane QTabBar {{ background: {t['surface']}; border-bottom: 1px solid {t['line']}; }}
QTabWidget#v2WorkspacePane QTabBar::tab {{ background: transparent; color: {t['text2']}; border: 0;
    border-bottom: 2px solid transparent; padding: 8px 4px 6px 12px; margin-right: 2px; font-weight: 500; }}
QTabWidget#v2WorkspacePane QTabBar::tab:selected {{ color: {t['text']}; border-bottom: 2px solid {t['line2']}; }}
QTabWidget#v2WorkspacePane QTabBar::tab:hover:!selected {{ background: {t['sunken']}; color: {t['text']}; }}
QTabWidget#v2WorkspacePane[active="true"] QTabBar::tab:selected {{ color: {t['accent-soft-ink']};
    border-bottom: 2px solid {t['accent']}; }}
QToolButton#v2TabMenu, QToolButton#v2NewTab {{ color: {t['text2']}; background: transparent; border: 1px solid transparent;
    border-radius: 6px; padding: 0 5px; margin: 4px 2px; }}
QToolButton#v2NewTab {{ font-size: 16px; padding: 0 9px; }}
QToolButton#v2TabMenu:hover, QToolButton#v2NewTab:hover {{ background: {t['sunken']}; color: {t['text']}; }}
QToolButton#v2TabMenu::menu-indicator {{ image: none; width: 0; }}
QWidget#v2ToolPicker {{ background: {t['bg']}; }}
QLabel#v2PickerTitle {{ font-size: 20px; font-weight: 600; color: {t['text']}; }}
QLabel#v2PickerHint {{ color: {t['text2']}; }}
QToolButton#v2ToolTile {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['line2']};
    border-radius: 12px; padding: 14px 10px; font-weight: 500; }}
QToolButton#v2ToolTile:hover {{ background: {t['accent-soft']}; }}
QToolButton#v2ToolTile QLabel {{ background: transparent; }}
QLabel#v2TileName {{ font-weight: 600; color: {t['text']}; }}
QLabel#v2TileNote {{ color: {t['text2']}; font-size: 12px; }}
QToolButton#v2ToolTile:focus {{ border: 2px solid {t['accent']}; }}
QStatusBar {{ background: {t['surface']}; color: {t['text2']}; border-top: 1px solid {t['line']}; }}
QStatusBar::item {{ border: 0; }}

QPushButton {{ background: {t['surface']}; color: {t['text']}; border: 1px solid {t['line2']};
    border-radius: 8px; padding: 8px 14px; min-height: 20px; }}
QPushButton:hover {{ background: {t['sunken']}; }}
QPushButton:pressed {{ background: {t['accent-soft']}; }}
QPushButton:default {{ background: {t['accent']}; color: {t['accent-ink']}; border-color: {t['accent']}; }}
QPushButton:disabled {{ color: {t['text3']}; background: {t['sunken']}; border-color: {t['line']}; }}
QPushButton:focus {{ border: 2px solid {t['accent']}; }}

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDateEdit, QComboBox {{
    background: {t['surface']}; color: {t['text']}; border: 1px solid {t['line2']};
    border-radius: 8px; padding: 6px 10px; selection-background-color: {t['accent-soft']};
    selection-color: {t['accent-soft-ink']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDateEdit:focus, QComboBox:focus {{
    border: 2px solid {t['accent']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled {{ color: {t['text3']}; background: {t['sunken']}; }}
QLabel {{ color: {t['text']}; }}
QCheckBox, QRadioButton {{ color: {t['text']}; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t['line2']}; border-radius: 4px; min-height: 32px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t['line2']}; border-radius: 4px; min-width: 32px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
