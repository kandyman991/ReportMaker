"""Run with python -m reportmaker on Windows."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
        from .ui import MainWindow
    except ImportError as exc:
        print("ReportMaker desktop dependencies missing; install: pip install -e \".[desktop]\"")
        print(f"Details: {exc}")
        return 2

    app = QApplication(sys.argv)
    app.setOrganizationName("ReportMaker")
    app.setApplicationName("ReportMaker")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
