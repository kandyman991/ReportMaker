"""Independent V2 launcher: python -m reportmaker.v2.

The legacy python -m reportmaker entry point is deliberately unchanged.
"""
from __future__ import annotations

import os
import sys


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    offline = args == ["--offline-self-test"]
    if args and not offline:
        print("Usage: python -m reportmaker.v2 [--offline-self-test]")
        return 2
    if offline:
        # Never open any website or persistent browser profile in CI.
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    try:
        from PySide6.QtWidgets import QApplication, QSplitter, QTreeWidget
        from .app import V2MainWindow
    except ImportError as exc:
        print('ReportMaker V2 requires desktop dependencies: pip install -e ".[desktop]"')
        print(f"Details: {exc}")
        return 2

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setOrganizationName("ReportMaker")
    app.setApplicationName("ReportMaker V2 Preview")
    window = V2MainWindow()

    if offline:
        try:
            window.show()
            app.processEvents()
            kinds = [kind for _, kind, _, _ in window.branch.visible_nodes]
            assert kinds == ["root", "module", "module", "paragraph", "conclusion"]
            assert window.centralWidget() is window.branch
            assert not window.findChildren(QSplitter), "Legacy three-panel UI leaked into V2"
            assert not window.findChildren(QTreeWidget), "Legacy module tree leaked into V2"
            forbidden = {"reportmaker.ui", "reportmaker.visual_editor"}
            assert not forbidden.intersection(sys.modules), "Legacy UI import leaked into V2"
        finally:
            window.close()
            app.processEvents()
        print("V2 Branch Editor M1.1 offline smoke OK")
        return 0

    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
