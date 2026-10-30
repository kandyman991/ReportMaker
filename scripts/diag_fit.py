import sys
sys.path[:0] = ["tests", "src"]
import test_v2_canvas_layout_stress as t
from PySide6.QtWidgets import QApplication, QWidget
from PySide6.QtGui import QFont

def say(msg):
    print("::notice::" + str(msg).replace("\n", " | ")[:900], flush=True)

class M(t._QtCase):
    def runTest(self):
        app = self.app
        f = app.font()
        say(f"app font family={f.family()!r} pt={f.pointSizeF()} px={f.pixelSize()} platform={app.platformName()}")
        for depth in (3, 14):
            w = self.make_window(t._project([t._deep(depth)]), width=660)
            self.pump(30)
            c = w.branch
            vp = c.viewport().width()
            say(f"depth={depth} win={w.width()} vp={vp} hscroll={c.horizontalScrollBar().maximum()} "
                f"step={c._gutters[-1].step} side={c._body.contentsMargins().left()} lvl={c._compact_level} "
                f"host_min={c._host.minimumSizeHint().width()} host_w={c._host.width()}")
            rows = sorted(((r.minimumSizeHint().width(), r.property('nodeKind'), r.width()) for r in c._rows), reverse=True)[:3]
            say(f"  widest rows (min,kind,width): {rows}")
            deepest = max(c._rows, key=lambda r: r.minimumSizeHint().width())
            parts = []
            for ch in deepest.findChildren(QWidget):
                if ch.isVisibleTo(deepest):
                    m = ch.minimumSizeHint().width()
                    if m > 120:
                        parts.append((m, type(ch).__name__, ch.objectName() or ch.text()[:20] if hasattr(ch, 'text') and callable(ch.text) and not isinstance(ch.text(), (int,)) else ch.objectName()))
            say(f"  widest children of the widest row: {sorted(parts, reverse=True)[:8]}")
            panel = c.findChild(QWidget, 'v2PendingDraftPanel')
            say(f"  pending panel min={panel.minimumSizeHint().width() if panel else None} visible={panel.isVisible() if panel else None}")
            others = [(ch.minimumSizeHint().width(), type(ch).__name__, ch.objectName()) for ch in c._host.children()
                      if isinstance(ch, QWidget) and ch not in c._rows and ch.isVisibleTo(c._host)]
            say(f"  non-row host children min: {sorted(others, reverse=True)[:5]}")
            self.close_window(w)

import unittest
unittest.TextTestRunner(verbosity=0).run(unittest.TestSuite([M()]))
