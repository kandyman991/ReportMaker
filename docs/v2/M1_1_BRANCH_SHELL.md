# ReportMaker V2 — M1.1 Branch Editor shell checkpoint

**Status:** implementation proposed for review; **not** merged, accepted on an installed Windows PC, or approved for release.
**Baseline:** live `main` `5e2b87da72f4871ea4b2bc16c16738486aec016f` (after approved M0 PR #66).
**Branch:** `feature/v2-m1-1-branch-shell`.
**Contract:** [M1 breakdown](M1_IMPLEMENTATION_PLAN.md), [M0 blueprint](M0_ARCHITECTURE_BLUEPRINT.md), [33 Branch Editor requirements](BRANCH_EDITOR_REQUIREMENTS.md).

## Implemented in this isolated M1.1 PR

- A new `python -m reportmaker.v2` launcher under `src/reportmaker/v2/__main__.py`. The legacy `python -m reportmaker` entry point remains unchanged.
- A fresh `V2MainWindow` whose **only central editor** is `BranchCanvas`; no V1 three-panel splitter, detached block list or independent navigation tree.
- A scrollable canonical report-root → module → nested submodule → actual text → dedicated Conclusions branch, with visible connector gutters and cards. The renderer iterates over the ordered `Report.modules` and heterogeneous `Module.blocks` directly, preserving mixed order and original IDs, while using existing `validate_report_tree`. The projection does **not** create or persist an alternative report hierarchy.
- All displayed values use Qt plain-text labels, including rich/paragraph source text and table cell content as a read-only preview; no HTML rendering of report input.
- The startup hierarchy is **explicit synthetic in-memory example data** with a manual customer snapshot. This M1.1 stage does not read private customer files, save projects, or navigate the ChatGPT website.
- An offline `python -m reportmaker.v2 --offline-self-test` and `tests/test_v2_shell.py` enforcing no `reportmaker.ui` or `reportmaker.visual_editor` transitive runtime imports and no direct imports, no QTreeWidget/QSplitter, correct canonical order, stable Conclusions, projection detach and validation-failure atomicity.
- A standalone, targeted hosted-Windows workflow `.github/workflows/v2-branch-shell.yml`, in addition to existing V1/M0/M1 workflows. It creates no Actions artifacts or installer and performs no network/browser interaction in its test steps.

## Scope intentionally NOT implemented in M1.1

This is a **read-only connected scaffold**, not yet the fully editable Branch Editor or M1 checkpoint A. It deliberately has no fake editing, active draft coordinator, command engine UI wiring, Save/Open dialog, image/photo editor, drag-and-drop, template or ChatGPT tab. Its status bar labels the functionality as a read-only architecture preview so users do not mistake synthetic content for a saved report.

M1.2 must first provide `ReportSession`, revision-scoped detached read projections, `CommandGateway`, stable node addresses and safe `ProjectEditor` transactions plus `.rmproj` v4 persistence; then M1.3 replaces read-only cards with actual inline module titles and paragraph editors using guarded drafts. The short M1.1 iterative projection is not a promised scalable 5000-block renderer; M5 addresses virtualization.

## M1.1 tests and acceptance

| Gate | Required evidence |
| --- | --- |
| Compile/launcher | `python -m compileall -q src/reportmaker/v2 tests/test_v2_shell.py`; `python -m reportmaker.v2 --offline-self-test` exits 0 |
| Import firewall | Static + fresh-process runtime checks that V2 does not import `reportmaker.ui` or `reportmaker.visual_editor` |
| Canonical branch | Root/module/child/paragraph/Conclusions order and depths are model-derived; mixed block order and stable IDs intact |
| Qt layout | BranchCanvas is the sole central widget; no V1 splitter, QTreeWidget or detached editor; connector widgets instantiated for descendants |
| Source immutability | External `Report` mutation after projection does not alter visible text; invalid report replacement leaves displayed state unchanged |
| V1 regression | Existing Windows M0 architecture/model and M1 customer UI workflows remain successful on the exact PR head |
| Native PC | User-installed Windows x64, high-DPI and connector/resize visual confirmation **pending**, not established by hosted smoke |

## Known issues and boundaries

- Cards and text are read-only until M1.3; a usable New/Open/Save/Undo flow is an M1.2–M1.4 gate.
- The scaffold eagerly creates one widget per visible canonical node. Large-report viewport virtualization and sophisticated focus/selection are future M5 concerns.
- The initial connector drawing has only a synthetic/offline Qt smoke test, not native installed-Windows visual acceptance.
- Browser interface and manual-only ChatGPT contract are unchanged; this stage does not touch profiles or attempt to fix V1 browser issue #64.
- Current v4 schema and all V1 code paths are unchanged. No automatic migration, schema v5, release/installer publication or default-executable switch.

## Next exact step

**M1.2 — canonical session + command gateway + persistence** as documented in [M1_IMPLEMENTATION_PLAN.md](M1_IMPLEMENTATION_PLAN.md); start only after an independent review and user-authorized merge (or separate approval to develop stacked work). No M1.1 automatic merge.
