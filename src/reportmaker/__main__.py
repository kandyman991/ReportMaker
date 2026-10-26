"""ReportMaker Windows application and offline frozen-browser test entry point."""

from __future__ import annotations

import sys


def _frozen_browser_self_test() -> int:
    """Exercise bundled Qt WebEngine without contacting ChatGPT or any service."""
    from PySide6.QtCore import QTimer, QUrl
    from PySide6.QtWidgets import QApplication
    from PySide6.QtWebEngineWidgets import QWebEngineView

    app = QApplication([sys.argv[0]])
    app.setOrganizationName("ReportMaker")
    app.setApplicationName("ReportMaker")
    browser = QWebEngineView()
    timeout = QTimer()
    timeout.setSingleShot(True)
    timeout.timeout.connect(lambda: app.exit(4))
    browser.loadFinished.connect(lambda ok: app.exit(0 if ok else 3))
    timeout.start(20000)
    browser.setUrl(QUrl("about:blank"))
    code = app.exec()
    browser.close()
    return code


def main() -> int:
    if "--self-test" in sys.argv:
        return _frozen_browser_self_test()
    if "--layout-self-test" in sys.argv:
        from .layout_probe import run
        return run()

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
