# Phase 1 — code and dependency ownership inventory

**Evidence:** 2026-10-31; exact source `main@8b52776984f6190fa2a0f657af9376f4f1cc5d5f`. Python `ast` traversal of `src/reportmaker/**/*.py` on the Legion isolated Phase 1 worktree. Inspects direct `import` and `from ... import` references (including function-local imports), resolves relative imports and follows the resulting internal module closure. **Static analysis is not a complete proof of runtime reachability**; the independently enforced runtime import fence and frozen Windows archive inventory remain required (#116).

## Summary

- `src/reportmaker` has **67 Python modules** (23 root package files and 44 `v2/` Python files), plus five `v2/web_assets/` HTML/CSS/JS files.
- Treating **all 44 V2 Python files** as potential entry points, static import traversal reaches **55 Python modules total**: 44 V2 plus **exactly 11 shared root engines/services** below.
- The remaining **11 root Python modules**, including the old default `__main__`, comprise the legacy V1 shell/probes/compatibility surface; this is a **deletion candidate set only**, not deletion authorization. It is not a full runtime dynamic-import or frozen-package guarantee.
- Shared package `reportmaker/__init__.py` must remain as the Python package initializer; don't confuse it with V1 `reportmaker/__main__.py`.

## Proven direct imports from V2 to shared root modules

| Retain root module | Direct V2 importers (count) | Representative importers |
| --- | ---: | --- |
| `engine.py` | 8 | `v2/app.py`, `v2/commands.py`, `v2/session.py`, `v2/web_ui.py` |
| `export.py` | 6 | `v2/app.py`, `v2/language_bundle.py`, `v2/pdf_proof.py` |
| `media_import.py` | 4 | `v2/branch/canvas.py`, `v2/gallery_tab.py`, `v2/web_ui.py` |
| `model.py` | 15 | `v2/commands.py`, `v2/session.py`, `v2/web_ui.py`, `v2/drafts.py` |
| `photo_editor.py` | 5 | `v2/branch/photo_tools.py`, `v2/web_origin.py`, `v2/editor_tab.py` |
| `photo_gallery.py` | 3 | `v2/gallery_tab.py`, `v2/branch/canvas.py`, `v2/web_ui.py` |
| `project_io.py` | 7 | `v2/adapters/persistence.py`, `v2/session.py`, `v2/app.py` |
| `reference.py` | 5 | `v2/report_info.py`, `v2/web_edits.py`, `v2/customer_manager.py` |
| `rich_text.py` | 9 | `v2/adapters/rich_text.py`, `v2/web_edits.py`, `v2/drafts.py` |
| `storage.py` | 4 | `v2/app.py`, `v2/customer_manager.py`, `v2/report_info.py` |
| `template_import.py` | 2 | `v2/app.py`, `v2/layout_template.py` |

The import dependencies confirm that **shared media/photo-editor files are not unused V1 code**. In particular, `V2PictureEditorDialog` subclasses the shared `PictureEditorDialog` and the HTML project page renders media through `v2/web_origin.py` and shared `photo_editor.render_photo`.

## V1-only candidate set — keep for now

`reportmaker.__main__`, `reportmaker.ui`, `reportmaker.visual_editor`, `reportmaker.page_editor`, `reportmaker.rich_editor`, `reportmaker.template_dialog`, `reportmaker.customer_ui`, `reportmaker.customer_probe`, `reportmaker.editor_probe`, `reportmaker.export_probe`, `reportmaker.layout_probe`.

Retire only after V1 feature inventory, migration/rollback, relevant tests and installer channels have been accepted. Legacy `visual_editor` / `template_dialog` expose template visual editing still absent from the V2/HTML UI. Probes may include useful regression coverage, which must be relocated before removal.

## Dynamic, packaging and source-of-truth qualifications

- `v2/web_shell.py` and `v2/web_origin.py` load **packaged, non-Python web assets** using `importlib.resources.files`. The Python AST import graph cannot establish that the HTML/CSS/JS resources are present in the frozen EXE; `scripts/verify_v2_frozen_archive.py`, the PyInstaller resource inventory and Windows frozen/installed smoke tests enforce that.
- `v2/web_ui.py` creates a hidden `V2MainWindow` for application logic and native dialogs: this is **current dependency**, not the long-term desired Phase 4 architecture.
- `tests/test_v2_retirement_boundary.py` already enforces a static/runtime V1 import fence; `v2-m7-packaging.yml` and `scripts/build_v2_m73_local.ps1` exclude V1-only modules and check the frozen archive. Do not weaken any gate during Phase 5.
- External runtime dependency set and build pins appear in `docs/cleanup/PHASE1_BASELINE.md`; transitive lock and SBOM remediation is Phase 2 (#105).
- The required long-term direction is a single canonical service/controller imported by HTML and native UIs, **not** importing the entire native GUI into the HTML host. No refactor or change in import paths is carried out by this Phase 1 audit.
