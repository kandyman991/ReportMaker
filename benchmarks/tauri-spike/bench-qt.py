"""Measure the real M2.2 Qt Branch Editor with the same synthetic V2 projection."""
from __future__ import annotations
import json
import os
import statistics
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from reportmaker.v2.app import V2MainWindow
from reportmaker.v2.projections import NodeAddress
from fixtures import SIZES, project

def rss_mib():
    with open("/proc/self/status", encoding="utf-8") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return None

def pump(app):
    app.processEvents()
    app.processEvents()

def one(size: int, app):
    synthetic = project(size)
    start = time.perf_counter()
    win = V2MainWindow(project=synthetic)
    win.show()
    pump(app)
    mounted = (time.perf_counter() - start) * 1000
    assert len(win.branch.visible_nodes) == size

    start = time.perf_counter()
    win.branch._refresh()
    pump(app)
    refresh = (time.perf_counter() - start) * 1000

    report = win.session.report_snapshot()
    address = NodeAddress(report.id, report.modules[0].id)
    editor = win.branch.editor_for(address)
    start = time.perf_counter()
    editor.setText("Updated synthetic module")
    editor.textEdited.emit(editor.text())
    assert win.branch.apply_draft(address)
    pump(app)
    edit = (time.perf_counter() - start) * 1000
    assert win.session.report_snapshot().modules[0].title.original == "Updated synthetic module"

    start = time.perf_counter()
    # Move through the V2 UI's canonical Qt adapter (not an in-memory list swap).
    win.branch._selected_module_id = report.modules[0].id
    assert win.branch.move_selected_down()
    pump(app)
    move = (time.perf_counter() - start) * 1000
    assert win.session.report_snapshot().modules[1].id == report.modules[0].id

    mem = rss_mib()
    win._confirm_transition = lambda: False
    win.close()
    pump(app)
    return {"mount_ms": mounted, "refresh_ms": refresh, "edit_ms": edit,
            "move_ms": move, "rss_mib": mem}

def run(reps=3):
    app = QApplication.instance() or QApplication([])
    out = {}
    # The unvirtualized 802-row widget case exceeded the 150s/2GiB
    # experiment resource limit. Opt in deliberately for larger cases.
    max_rows = int(os.getenv("BENCH_MAX_ROWS", "302"))
    for size in (n for n in SIZES if n <= max_rows):
        samples = [one(size, app) for _ in range(reps)]
        out[size] = {key: round(statistics.median(item[key] for item in samples), 2)
                     for key in samples[0] if samples[0][key] is not None}
        print(size, out[size], flush=True)
    return out

if __name__ == "__main__":
    result = run(int(sys.argv[1]) if len(sys.argv)>1 else 3)
    target = Path(__file__).parent / "data" / "qt-results.json"
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
