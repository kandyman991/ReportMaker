# M0 — Source dependency inventory and reuse matrix

**Audit date:** 2026-10-28. **Read-only source baseline:** live `main` at `e50557a5a89a20095ea525eafec281894cccd876` (parent is PR #65 merge `01f1e7b1d2558abe409b8f6a60a3f36ab296a678`). **Status:** proposed for review, not authorization to implement M1.

## Method and scope

Read the approved `docs/v2/{ROADMAP,ARCHITECTURE,BRANCH_EDITOR_REQUIREMENTS}.md`, root `ARCHITECTURE.md`, `AGENTS.md`, `CHAT_HANDOFF.md`, `docs/CHECKPOINTS.md`, `handoff/state.json`, report-composition contract, media ADR, all 12 requested Python files and their internal dependencies. Examined the 22+ synthetic test modules, project workflows and `pyproject.toml`. Import relationships below are observed top-level imports; local imports and runtime UI creation are separately noted. This is **static source inspection**, not proof of import isolation at runtime, licensing clearance, or an installed-Windows test.

## Existing dependency graph (arrows mean imports/uses)

```text
reference.py ──stdlib; customer snapshot
rich_text.py ──stdlib; RichFormatting / serialization / validation
model.py ──reference.py, rich_text.py
engine.py ──model.py, rich_text.py
project_io.py ──engine.py, model.py, reference.py, rich_text.py
storage.py ──reference.py; SQLite standard library
media_import.py ──project_io.py; Pillow, optional pillow-heif
photo_editor.py ──model.py; PySide6 QtCore/QtGui/QtWidgets
rich_editor.py ──rich_text.py; PySide6 QtCore/QtGui/QtWidgets
photo_gallery.py ──media_import.py; PySide6 QtCore/QtGui/QtWidgets
page_editor.py ──engine.py, model.py, photo_editor.py, photo_gallery.py,
                 rich_editor.py; PySide6 widgets
export.py ──engine.py, model.py, rich_text.py, project_io.py;
            function-local template_import.py, python-docx, reportlab, Pillow
template_import.py ──stdlib XML/ZIP/JSON; separate local DOCX/DOTX import
template_dialog.py ──template_import.py; PySide6 widgets
visual_editor.py ──engine.py, model.py, project_io.py, export.py,
                   media_import.py, reference.py, photo_editor.py,
                   photo_gallery.py, rich_editor.py, rich_text.py,
                   page_editor.py, template_import.py, template_dialog.py;
                   PySide6 Qt widgets and controllers
ui.py ──PySide6 QtWidgets, QtWebEngineCore/Widgets;
         runtime import visual_editor.py (creates VisualReportEditor)
__main__.py ──runtime command dispatch into desktop/UI and offline probes
```

The **transitive import firewall** is the important result: importing `visual_editor.py` pulls almost the entire UI stack, including galleries, export, templates and page rendering. Importing `ui.MainWindow` and constructing it creates `VisualReportEditor` with hardcoded V1 splitters, ownership and callbacks. Importing `photo_gallery.py` also loads `media_import.py` and project persistence. Conversely, `model → reference/rich_text`, `engine → model/rich_text`, `project_io → engine/model/reference/rich_text`, and `storage → reference` are Qt-free on their top-level import graph; these are the safe initial shared-core boundaries.

**External runtime/build dependencies:** Python >=3.11,<3.16; `python-docx>=1.2,<2`, `reportlab>=4.2,<5`, `Pillow>=10.4,<13`, `pypdf>=5,<7`; `[desktop]` adds pinned `PySide6==6.12.0` and `pillow-heif>=1.8.1,<2`. Win64 PySide6/Qt WebEngine is mandatory. Validate third-party licenses and installer redistribution of Qt WebEngine/heif codecs independently before V2 distribution; no legal clearance is asserted here.

## Per-component inventory, classification and evidence

| Component | Direct internal dependencies; coupling / transitive notes | V2 decision | Boundary and rationale |
| --- | --- | --- | --- |
| `model.py` | `reference`, `rich_text`; stdlib dataclasses. No Qt. | **Reuse** | Authoritative `Report`, `Module`, `NestedModuleBlock`, typed blocks, `LocalizedText`, `PhotoVisual`, frozen snapshots, Conclusions. No V2 parallel model. |
| `engine.py` | `model`, `rich_text`; pure; `MAX_NESTING=256`. | **Adapt** | Keep `ProjectEditor`, `validate_report_tree`, `module_outline`. Add explicit command gateway/change events/draft batching; review mixed-index and ID semantics. `apply` deep-copies entire report; never call on each keystroke. |
| `project_io.py` | `engine`, `model`, `reference`, `rich_text`; stdlib ZIP, hashing, atomic replace. | **Reuse** | `ReportProject`, `save_project`, `load_project`, v1–v4 validation/migration, asset ownership; no Qt. Keep existing Save As version protection. |
| `visual_editor.py` | Imports almost all other report UI/services (see graph), >100 KB/2,200 lines; owns `ModuleTree`, `BlockList`, drafts, reports, export, gallery and Qt callbacks. | **Replace** as V2 UI; **Extract** narrowly if justified | **Never import** into `reportmaker.v2`. Reimplement small documented adapters against shared core, not old three-panel controller. Audit any copied helper independently. |
| `rich_editor.py` | `rich_text`, Qt; `SafeRichTextEdit`, `RichTextRibbon`, `apply_rich`, `capture_rich`; UTF-16 selection handling. | **Adapt** | Reuse Qt text/ribbon operations only behind a per-block editor contract; remove V1 controller assumptions and prevent focus/selection losses. `rich_text.py` itself **Reuse**. |
| `page_editor.py` | `engine`, `model`, `photo_editor`, `photo_gallery`, `rich_editor`, Qt; owns local `fields` and `pending` widgets. | **Adapt** (M6) | Preserve same-ID editability and page presentation; route `commit()` through common draft coordinator; its full `rebuild` must not overwrite active drafts. Not Word-accurate pagination. |
| `photo_gallery.py` | `media_import`, Qt, bounded thumbnails; `PictureGalleryDialog`, `ProjectPictureList`, `PictureDropZone`, copy-only file/clipboard handling. | **Adapt** | Retain safe provenance validation and photo picker/thumbnail helpers; Gallery becomes separate V2 tab and uses shared project media facade, not V1 module list or owning project store. |
| `media_import.py` | `project_io`, Pillow / optional HEIF; conversion, staging, commit, source-copy safety. | **Reuse** | Keep limits for local source, decoded pixels, EXIF, ICC, batch size and asset IDs; wrap in project transaction so failure cannot partially mutate shared state. |
| `photo_editor.py` | `model`, Qt; `PictureCanvas`, `PictureEditorDialog`, `render_photo`. | **Adapt** | Reuse non-destructive visual edit/render semantics and independent annotations; expose callbacks through media facade, not V1 controller. |
| `export.py` | `engine`, `model`, `rich_text`, `project_io`; local template validation, Pillow, python-docx, reportlab. | **Reuse** with explicit known gap | `prepare_export` uses model/outline; `export_project` owns DOCX/PDF output and atomic destination. **Currently raises ExportError for non-default PhotoVisual** rather than silently flattening. M6 integration/gate, not M1 promise. |
| `template_import.py` | stdlib ZIP/XML/JSON; no Qt; bounded, non-executing DOCX/DOTX import. | **Reuse** | Local export/page-template service only, no import-to-report-tree assumption. `template_dialog.py` **Adapt** as Qt facade later. |
| `ui.py` | Qt+QtWebEngine, runtime import of `VisualReportEditor`, `QSplitter` with modules/editor/chat. | **Replace** shell; **Extract/adapt** browser construction | Fresh V2 `QMainWindow` starts in Branch Editor, not three panels. Preserve existing user-controlled `QWebEngineView` profile/Qt behavior, manual paste and external-browser fallback; never introduce automation. |
| `reference.py`, `storage.py` | stdlib, `reference` respectively; `CustomerSnapshot`, SQLite `CustomerStore`. | **Reuse** | Dedicated metadata/customer facade, frozen report-local snapshots; no database access in view components. |

## Observable coupling and corrective boundaries

1. **V1 controller**: `VisualReportEditor(owner,left_layout,center_layout)` is wired to `MainWindow` splitter and `owner.settings`, plus direct `ProjectEditor`, `assets`, `media_library`, template and gallery ownership. Extract behavior via new V2 adapters instead of importing/copying widget graphs.
2. **Split drafts**: `VisualReportEditor` maintains `_block_pending` and `_info_pending` while `EditableDocumentPage` has `pending`; its `_flush_*` methods and same-block conflict detection live inside V1. Introduce one revisioned `EditSessionCoordinator` before mounting a second active editor; no hidden draft discard.
3. **Structural indices**: top-level modules are `report.modules`; nested structural children are `NestedModuleBlock` entries in `module.blocks`, mixed with leaves. A target index must be defined in the **actual mixed children sequence**, not a filtered module list. Root wrapping/unwrapping preserves underlying module ID. Verify nested wrapper ID retention for nested-to-nested moves; decide explicit wrapper preservation rules before M1 commands.
4. **Transactional performance**: `ProjectEditor.apply` uses full `deepcopy` and `validate_report_tree`, holds up to 100 undo reports; `module_outline` validates each call. Event/debounce/batch strategy and bounded visible-widget layout are necessary.
5. **Serialization depth**: `validate_report_tree` iterates with stack and `MAX_NESTING=256`, but `project_io._module_to/_block_to` and `_module_from/_block_from` recurse. Preserve the protective cap while characterizing actual Python/JSON recursion limits, rather than assuming all 256 levels serialize on all Python versions.
6. **Media transactions**: `ReportProject.assets` and `media_library` are separate mutable mappings; `ProjectEditor` snapshots only `Report`. Define a coordinated command boundary for asset import/removal and Undo/Redo so media and canonical photo references never diverge. Continue project-session-token rejection for stale queued drops.
7. **Rendering**: `EditableDocumentPage` is continuous schematic Qt paper and `visual_editor` has its own HTML preview. Neither is canonical nor export-faithful. Share export facade and clearly label fidelity.
8. **Browser**: V1 constructs WebEngine profile inside `ui.py`; reuse the same ordinary website settings/session/external URL behavior in a dedicated non-privileged tab, without `VisualReportEditor`. User-initiated native image import remains separate.
9. **Privacy**: use only synthetic reports/images/tests; no project/customer data, browser cookies/profile, original user photos or machine CAD in repo, CI artifacts or browser automation.

## Audit coverage and existing regressions

- Canonical/migration/undo: `tests/test_model.py`, `test_contract.py`, `test_m2_project.py`, `test_pr9_review_fixes.py`.
- Images/annotations/gallery: `test_m45_media.py`, `test_m45_visual.py`, `test_pr19_review.py`, `test_issue37_photo_gallery.py`, `test_issue48_photo_import.py`.
- Editors/structure/focus: `test_editable_page.py`, `test_rich_editor.py`, `test_rich_pdf_fidelity.py`, `test_issue36_block_labels.py`, `test_issue38_ribbon.py`, `test_issue49_50_ribbon.py`, `test_issues_54_56_modules.py`.
- Export/format/templates: `test_m4_export.py`, `test_m4_branding.py`, `test_template_import.py`, `test_windows_distribution.py`.
- Workflows: `.github/workflows/ci.yml` (Windows compile, Qt offline probes, unittest), `m1-customer-ui.yml` (Windows customer + unittest), `continuity-contract.yml` (Ubuntu `scripts/check_continuity.py`).

M0 acceptance is **source-level boundaries and design**, not a claim of full runtime dependency verification. Before an M1 implementation PR, enforce an import-smoke test that `reportmaker.v2` can import with `reportmaker.visual_editor` absent from `sys.modules`, and a static forbidden-import check.
