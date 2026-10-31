"""Issue #116 Phase 1: prevent accidental V1 GUI imports and frozen packaging.

Source tests are pure; only the subprocess test starts an offline V2 Qt shell.
Windows CI independently inspects the actual PyInstaller EXE archive.
"""
from __future__ import annotations

import ast
import importlib.util
import os
from pathlib import Path
import runpy
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
VERIFY = runpy.run_path(str(ROOT / "scripts/verify_v2_frozen_archive.py"))
BANNED = VERIFY["LEGACY_MODULES"]
NEEDED = VERIFY["REQUIRED_MODULES"]
MODULES = VERIFY["verify_listing"]


def _direct_dependencies(source: Path) -> set[str]:
    """Include resolved relative imports even from lazy methods."""
    package = ".".join(source.relative_to(ROOT / "src").parts[:-1])
    result = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            result.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = ("." * node.level) + (node.module or "")
            name = importlib.util.resolve_name(base, package) if node.level else base
            result.add(name)
            result.update(name + "." + alias.name for alias in node.names)
    return result


class V2RetirementBoundaryTests(unittest.TestCase):
    def test_no_v2_or_shared_engine_has_direct_legacy_gui_imports(self):
        shared = ("engine", "export", "media_import", "model",
                  "photo_editor", "photo_gallery", "project_io", "reference",
                  "rich_text", "storage", "template_import")
        files = list((ROOT / "src/reportmaker/v2").rglob("*.py"))
        files += [ROOT / "src/reportmaker" / (name + ".py") for name in shared]
        self.assertGreaterEqual(len(files), 40)
        for source in files:
            for dependency in _direct_dependencies(source):
                with self.subTest(source=source.name, dep=dependency):
                    self.assertFalse(
                        any(dependency == banned or
                            dependency.startswith(banned + ".") for banned in BANNED),
                        f"V2 runtime depends on V1-only module {dependency}: {source}",
                    )

    def test_runtime_v2_offline_starts_while_v1_imports_are_blocked(self):
        # Isolated child avoids Qt app state leaking into other tests.
        script = """
import builtins, importlib.util, sys
legacy = set({names!r})
original = builtins.__import__
def deny(name, globals=None, locals=None, fromlist=(), level=0):
    module = (importlib.util.resolve_name('.' * level + name,
              (globals or {{}}).get('__package__') or (globals or {{}}).get('__name__') or '')
              if level else name)
    if any(module == forbidden or module.startswith(forbidden + '.') for forbidden in legacy):
        raise RuntimeError('V1 GUI import blocked: ' + module)
    return original(name, globals, locals, fromlist, level)
builtins.__import__ = deny
from reportmaker.v2.__main__ import main
result = main(['--offline-self-test'])
if result:
    raise SystemExit(result)
if legacy.intersection(sys.modules):
    raise RuntimeError('V1 module loaded')
print('STRICT_V2_NO_V1_IMPORT_PASS')
""".format(names=sorted(BANNED))
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen",
                   QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox",
                   PYTHONPATH=str(ROOT / "src"))
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT,
                                capture_output=True, text=True, timeout=60,
                                env=env, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("STRICT_V2_NO_V1_IMPORT_PASS", result.stdout)

    def test_both_packagers_have_explicit_identical_v1_exclusions(self):
        paths = [ROOT / "scripts/build_v2_m73_local.ps1",
                 ROOT / ".github/workflows/v2-m7-packaging.yml"]
        for path in paths:
            source = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("--collect-submodules reportmaker", source)
                for banned in BANNED:
                    self.assertEqual(
                        source.count("--exclude-module " + banned + " "),
                        1, (path, banned))
                self.assertIn("--collect-all pillow_heif", source)
                self.assertIn("--hidden-import PySide6.QtWebEngineWidgets", source)
                self.assertIn("--hidden-import PySide6.QtWebEngineCore", source)
                self.assertIn("--hidden-import PySide6.QtSvg", source)
                self.assertIn("scripts/verify_v2_frozen_archive.py", source)
                self.assertIn("if ($LASTEXITCODE -ne 0)", source)
        workflow = paths[1].read_text(encoding="utf-8")
        self.assertIn("branches: [main, feature/v2-m7-3-native-acceptance]", workflow)
        self.assertLess(workflow.index("python scripts/verify_v2_frozen_archive.py"),
                        workflow.index("Build local-only distinct per-user V2 installer"))
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", workflow)
        self.assertIn("inputs.manual_qa_installer == true", workflow)
        self.assertIn("retention-days: 1", workflow)
        self.assertNotIn("gh release create", workflow)

    def test_archive_inventory_accepts_only_required_v2_and_shared_modules(self):
        fixture = "\n".join("  '" + name + "'" for name in sorted(NEEDED))
        modules, forbidden, missing = MODULES(fixture)
        self.assertEqual(modules, set(NEEDED))
        self.assertFalse(forbidden)
        self.assertFalse(missing)

    def test_archive_inventory_rejects_v1_or_missing_shared_module(self):
        fixture = "\n".join(" '" + name + "'" for name in sorted(NEEDED))
        _, forbidden, missing = MODULES(fixture + "\n 'reportmaker.visual_editor'")
        self.assertIn("reportmaker.visual_editor", forbidden)
        self.assertFalse(missing)
        _, forbidden, missing = MODULES(fixture.replace(
            "'reportmaker.photo_editor'", "'reportmaker.ui'"))
        self.assertIn("reportmaker.ui", forbidden)
        self.assertIn("reportmaker.photo_editor", missing)
        with self.assertRaises(ValueError):
            MODULES("")

    def test_archive_checks_fail_closed_if_viewer_fails_or_invalid(self):
        with TemporaryDirectory() as temp:
            path = Path(temp) / "ReportMakerV2.exe"
            path.write_bytes(b"not a real exe")
            fake = subprocess.CompletedProcess(args=[], returncode=2,
                                               stdout="", stderr="bad archive")
            with patch.dict(VERIFY["inspect_archive"].__globals__,
                            {"subprocess": __import__("subprocess")}):
                with patch.object(subprocess, "run", return_value=fake):
                    with self.assertRaisesRegex(RuntimeError, "viewer failed"):
                        VERIFY["inspect_archive"](path)
            with self.assertRaises(ValueError):
                VERIFY["inspect_archive"](Path(temp) / "missing.exe")


if __name__ == "__main__":
    unittest.main()
