"""M1.1 V2 launcher, pure-core projection and legacy-UI isolation tests.

All data is synthetic. The desktop smoke never loads a website or browser
profile, opens a customer database, or saves a project.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
V2 = ROOT / "src" / "reportmaker" / "v2"
FORBIDDEN = {"reportmaker.ui", "reportmaker.visual_editor"}


def _module_name(path: Path) -> tuple[str, str]:
    relative = path.relative_to(ROOT / "src").with_suffix("")
    parts = list(relative.parts)
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    full = ".".join(parts)
    return full, (full if is_package else full.rpartition(".")[0])


class V2ImportContractTests(unittest.TestCase):
    def test_v2_has_no_static_import_path_to_legacy_ui(self):
        files = sorted(V2.rglob("*.py"))
        self.assertTrue(files, "V2 source files not found")
        for path in files:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(path))
            _module, package = _module_name(path)
            for entry in ast.walk(tree):
                if isinstance(entry, ast.Import):
                    names = [alias.name for alias in entry.names]
                elif isinstance(entry, ast.ImportFrom):
                    name = entry.module or ""
                    base = importlib.util.resolve_name("." * entry.level + name, package) if entry.level else name
                    names = [base] + [base + "." + alias.name for alias in entry.names]
                else:
                    continue
                for name in names:
                    self.assertFalse(
                        any(name == forbidden or name.startswith(forbidden + ".")
                            for forbidden in FORBIDDEN),
                        f"Legacy UI dependency in {path}: {name}",
                    )

    def test_offline_smoke_is_not_disabled_by_python_optimization(self):
        tree = ast.parse((V2 / "__main__.py").read_text(encoding="utf-8"))
        self.assertFalse(any(isinstance(node, ast.Assert) for node in ast.walk(tree)))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        outcome = subprocess.run(
            [sys.executable, "-O", "-m", "reportmaker.v2", "--offline-self-test"],
            env=env, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("V2 Branch Editor M1.1 offline smoke OK", outcome.stdout)

    def test_shell_ci_tracks_transitive_shared_core_changes(self):
        workflow = (ROOT / ".github/workflows/v2-branch-shell.yml").read_text(encoding="utf-8")
        for path in ("src/reportmaker/model.py", "src/reportmaker/engine.py",
                     "src/reportmaker/reference.py", "src/reportmaker/rich_text.py",
                     "pyproject.toml"):
            with self.subTest(path=path):
                self.assertIn(f'      - "{path}"', workflow)

    def test_isolated_launch_never_imports_legacy_ui(self):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        outcome = subprocess.run(
            [sys.executable, "-m", "reportmaker.v2", "--offline-self-test"],
            env=env, capture_output=True, text=True, timeout=60, check=False,
        )
        self.assertEqual(outcome.returncode, 0, outcome.stdout + outcome.stderr)
        self.assertIn("V2 Branch Editor M1.1 offline smoke OK", outcome.stdout)


class V2BranchCanvasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_default_canvas_has_connected_model_order_not_v1_panels(self):
        from PySide6.QtWidgets import QSplitter, QTreeWidget
        from reportmaker.v2.app import V2MainWindow
        window = V2MainWindow()
        try:
            window.show()
            self.app.processEvents()
            self.assertIs(window.centralWidget(), window.branch)
            self.assertEqual(
                [kind for _, kind, _, _ in window.branch.visible_nodes],
                ["root", "module", "module", "paragraph", "conclusion"],
            )
            self.assertEqual(
                [depth for _, _, depth, _ in window.branch.visible_nodes],
                [0, 1, 2, 3, 1],
            )
            self.assertFalse(window.findChildren(QTreeWidget))
            self.assertFalse(window.findChildren(QSplitter))
            self.assertGreater(window.branch.viewport().width(), 500)
        finally:
            window.close()
            self.app.processEvents()

    def test_mixed_order_and_conclusions_are_derived_from_report(self):
        from reportmaker.model import (
            HeadingBlock, LocalizedText, PageBreakBlock, ParagraphBlock, TableBlock,
        )
        from reportmaker.v2.app import V2MainWindow, example_report
        report = example_report()
        parent = report.modules[0]
        parent.blocks.insert(0, ParagraphBlock(LocalizedText("en", "Before nested")))
        parent.blocks.extend([
            HeadingBlock(LocalizedText("en", "After nested")),
            TableBlock([[LocalizedText("en", "Cell A")]]),
            PageBreakBlock(),
        ])
        window = V2MainWindow(report)
        try:
            nodes = window.branch.visible_nodes
            self.assertEqual(
                [kind for _, kind, _, _ in nodes],
                ["root", "module", "paragraph", "module", "paragraph",
                 "heading", "table", "page-break", "conclusion"],
            )
            self.assertEqual(nodes[2][3], "Before nested")
            self.assertEqual(nodes[6][3], "Cell A")
            self.assertEqual(nodes[-1][0], report.conclusion.id)
        finally:
            window.close()
            self.app.processEvents()

    def test_deep_connectors_retain_true_model_depth_beyond_32(self):
        from reportmaker.model import LocalizedText, Module, NestedModuleBlock
        from reportmaker.v2.app import V2MainWindow, example_report
        from reportmaker.v2.branch.canvas import ConnectorGutter
        report = example_report()
        top = report.modules[0]
        for number in range(35):
            top = Module(LocalizedText("en", f"Outer {number}"),
                         blocks=[NestedModuleBlock(top)])
        report.modules = [top]
        window = V2MainWindow(report)
        try:
            deepest = max(depth for _, _, depth, _ in window.branch.visible_nodes)
            self.assertGreater(deepest, 32)
            matching = [g for g in window.branch.findChildren(ConnectorGutter)
                        if g._depth == deepest]
            self.assertEqual(len(matching), 1)
            self.assertEqual(matching[0].width(), 18 + 25 * deepest)
            self.assertEqual(len(matching[0]._ancestors), deepest - 1)
        finally:
            window.close()
            self.app.processEvents()

    def test_projection_is_detached_and_validation_failure_is_atomic(self):
        from reportmaker.v2.app import V2MainWindow, example_report
        report = example_report()
        window = V2MainWindow(report)
        try:
            first = window.branch.visible_nodes
            report.modules[0].title.update_original("External mutable reference")
            self.assertEqual(window.branch.visible_nodes, first)
            invalid = example_report()
            invalid.modules.append(invalid.conclusion)
            with self.assertRaises(ValueError):
                window.branch.set_report(invalid)
            self.assertEqual(window.branch.visible_nodes, first)
        finally:
            window.close()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
