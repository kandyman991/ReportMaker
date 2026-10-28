# M0 → M1 handoff: first functional Branch Editor implementation plan

**Milestone:** M1, contingent on **review/approval of this M0 PR**; M0 itself contains no application code. **Read-only source base:** `main e50557a5a89a20095ea525eafec281894cccd876`. **Product contract:** all 33 `BE-*` requirements remain selected, with phased delivery M1–M7 from `ROADMAP.md`.

## Exact starting point for M1

After M0 approval, re-fetch **live** `main`, verify reviewed CI/PRs, create a **new isolated M1 branch**. First implementation task: add a separate V2 launch path and a **new full-workspace Branch Editor canvas** under `src/reportmaker/v2/`, backed from day one by `model.Report` / `engine.ProjectEditor`, **not** a port of `ui.MainWindow` / `visual_editor.VisualReportEditor`. The very first visible workspace shows a report root, editable first module, its nested editable submodule and a paragraph inside the connector-linked branch. No detached block list or additional module navigation tree.

M1 should be a small sequence of independently reviewed PRs; do not open a monolithic rewrite PR. No proposed PR is authorized to merge automatically; each PR stays open pending explicit user approval.

## M1 PR boundaries (ordered)

| PR | Exclusive responsibility | Code ownership (proposed) | Required isolated proof |
| --- | --- | --- | --- |
| **M1.1 — V2 launch + import firewall** | `python -m reportmaker.v2` launch, a new native `QMainWindow` that defaults to a placeholder/skeleton connected Branch Editor canvas; V1 entry unchanged. Add static and isolated-process runtime tests forbidding transitive imports of both `reportmaker.ui` and `reportmaker.visual_editor`. | `v2/__main__.py`, `app.py`, `branch/canvas.py` minimal, V2 import test | Startup creates fresh V2 app with **no V1 three-panel interface**, and both legacy UI modules absent from the transitive import graph; V1 smoke remains green |
| **M1.2 — Session, adapter, basic safe commands** | Wrap existing `ProjectEditor`, `ReportProject`, `load_project/save_project`; stable-ID resolver/projection and simple `add_module`, `add_nested_module`, `add_paragraph`, `rename_module`, `set_paragraph`, Undo/Redo, revision+generation events | `v2/session.py`, `commands.py`, `projections.py`, `adapters/persistence.py`, tests | Synthetic tree with mixed child index and Conclusions last; valid/invalid transaction atomicity; detached view snapshot cannot mutate canonical report; full report Save/Open; v1–v4 Save As and stable IDs; no Qt in pure adapter |
| **M1.3 — First directly editable branch** | Connected lines; real inline root → module → nested module and text, direct inline title and paragraph editing; contextual editor activation, scroll/selection; no decorative diagram replacing content | `v2/branch/{canvas,module_card,content_card}.py`, `v2/drafts.py`, `v2/adapters/rich_text.py`, targeted Qt tests | From branch view alone: create module + child, edit both titles and Unicode paragraph, undo/redo; focus/selection intact, canonical order matched; no widget mutates report directly |
| **M1.4 — Project lifecycle & checkpoint A acceptance** | Hook New/Open/Save/Save As into session and guard drafts; real V2 offline Qt smoke/Windows-hosted CI, integration with V1 regressions; measured basic performance and Windows manual checklist | `v2/app.py`, `v2/__main__.py`, session/Qt integration tests, CI probe | Fully create, edit, save, close, reopen, undo/redo nested report **entirely in branch workspace**; legacy source unmodified; failed Save As retains identity and drafts; first-Save/Save-As settings identity migration; no V1 UI import; user visual approval of Branch Editor sketch |

**Keep shared-file ownership explicit.** M1.1 owns shell/canvas skeleton; M1.2 owns core gateway; M1.3 owns Qt nodes/drafts/rich helpers; M1.4 integrates. Avoid parallel edits to `engine.py`, `project_io.py`, `rich_editor.py` until M1.2 contract tests pass. Any essential shared-core change gets a narrow earlier PR with regression tests; never fork a second report engine. Existing V1 modules remain unchanged whenever adapters suffice.

## Requirement-to-milestone traceability (all 33 approved BE IDs)

This is the *implementation owner and proof plan*, not a statement that any feature is already implemented. All rows require the common M7 end-to-end/native Windows acceptance gate. Split milestones show first usable subset followed by final completion.

| Requirement | Implement / finish | Dedicated acceptance focus |
| --- | --- | --- |
| BE-L01 | M1 | Full Branch Editor default workspace, editing without separate tree |
| BE-L02 | M1 | Connected root/module/submodule lines after redraw |
| BE-L03 | M2, M5 | Arbitrarily deep conceptual nesting; safe bound and deep round-trips |
| BE-L04 | M1, M3, M4 | Real inline text, then tables and photo previews |
| BE-L05 | M1 | Canvas matches mixed canonical saved/export order |
| BE-L06 | M1 | No duplicated navigation tree or model |
| BE-E01 | M1 basic, M3 complete | Inline Unicode and selection/format/undo fidelity |
| BE-E02 | M1 | Inline title, derived outline, undo |
| BE-E03 | M4 | Project-owned thumbnail, caption and restore |
| BE-E04 | M4, M6 export | Non-destructive placement edits and annotated DOCX/PDF |
| BE-E05 | M3 | Table cell and row/column editing/round-trip |
| BE-E06 | M1 basic, M3 complete | Insert every supported block at exact mixed index |
| BE-E07 | M3 | Active-editor contextual ribbon/focus retention |
| BE-S01 | M2 | Reorder/reparent subtree without identity loss |
| BE-S02 | M2 | BEFORE/AFTER/INSIDE hit-target, invalid-drop rollback |
| BE-S03 | M2 | Collapse hides only, no export omission |
| BE-S04 | M2 | Keyboard and toolbar move-up/down boundaries |
| BE-S05 | M2 | Duplicate IDs, delete confirmation, Outdent, undo |
| BE-S06 | M2 | Expansion persistence across reopen/Save As |
| BE-S07 | M2 | Canonical descendant counts for collapsed branches |
| BE-U01 | M5 | Focus subtree and restore context |
| BE-U02 | M5 | Zoom/pan/fit versus export geometry and DPI |
| BE-U03 | M5 | Canonical search reveals collapsed matches |
| BE-U04 | M5 | Context menus reuse command validation |
| BE-U05 | M3, M5 | Editable display resize; local versus printable semantics |
| BE-U06 | M4 | Explorer file drop CopyAction, safe local import |
| BE-U07 | M4 | Intentional native clipboard image/file import only |
| BE-I01 | M1, M6 | One model and IDs across every tab/summary/export |
| BE-I02 | M2, M6 | Derived numbering/TOC after all structure changes |
| BE-I03 | M6 | Separate Editor shares same data and draft coordinator |
| BE-I04 | M6 | Gallery tab and unchanged user-controlled browser tab |
| BE-I05 | M6 | Refresh guard and accurate supported DOCX/PDF visual output |
| BE-I06 | M6 | Manual plain-text browser copy/paste only; no API/DOM automation |

**Gate accountability:** M1 covers only its named subset. M2–M6 own their listed proof and M7 verifies **all 33** against [RM-BE-001](BRANCH_EDITOR_REQUIREMENTS.md), including real installed Windows acceptance. If an owner milestone slips, update this mapping in a reviewed PR; do not silently drop the requirement.

## M1 minimum command and layout acceptance (Checkpoint A)

1. Start V2 and land on Branch Editor. Root ("Main"/report), module A, nested module A.1 and editable paragraph are visible, with parent/child connectors and vertical canonical order.
2. Enter/rename a module and child inline; enter text directly in a branch content block, preserving Unicode, `RichFormatting` semantics where used and `LocalizedText.update_original` staleness. No separate block editor required.
3. Insert modules and paragraph blocks with precise mixed-list indices; dedicated Conclusions displays last and cannot be mis-parented. No dropped content/IDs.
4. Structural and text changes are validated via one `ProjectEditor` transaction per logical action. Undo then Redo restore the same canonical hierarchy and selected content where feasible.
5. New/Open/Save/Save As `.rmproj` v4 succeed using existing local storage. Open v1–v3 then Save As to a new v4 path only. Failed save/invalid draft does not overwrite source or clear draft.
6. Root Report Information can be created with a synthetic manual customer snapshot and existing metadata types; M1 may display summary metadata read-only, but must not omit fields from persisted `Report`.
7. V1 application still launches and runs existing tests without modifications; V2 import never imports `visual_editor.py`. No browser automation, OpenAI API or project-to-browser transfer.
8. First real Windows acceptance: evaluate root/module/submodule connectors after resize, inline caret/selection/keyboard, save dialog and 100/125/150% DPI. Record actual device/Qt/commit and distinguish runner smoke from installed testing.

M1 is **not** allowed to claim full 33-feature completion. Explicit BEFORE/AFTER/INSIDE drag UI, collapse persistence, advanced table editing, photo placement, search/focus/zoom, separate Editor/Gallery/ChatGPT tabs and export-fidelity checks belong to their respective M2–M7 milestones. M1 data types and layout must not make these later features impossible.

## Work left for M2–M7 (interface-ready, not premature M1 scope)

- **M2**: full drag/drop planner, insert/move/duplicate/remove/outdent, collapse, summaries and derived numbering.
- **M3**: full inline rich formatting, table structure/cells, conflict-safe Branch/Page draft coordinator.
- **M4**: Gallery/media integration, clipboard/Explorer imports, photo visual editing, project-wide media Undo/Redo.
- **M5**: scalable virtualization, focus/search/pan/zoom, accessibility and long-report benchmarks.
- **M6**: Editor/Gallery/ChatGPT tabs, unchanged manual browser integration, report metadata/template/export/preview parity, annotation export supported or explicitly blocked.
- **M7**: complete RM-BE-001 acceptance, legacy V1 interoperability, installed Windows/Word/PDF tests, reviewed V2 release authorization.

## Code-review checklist for every M1 PR

- Base recorded as **live latest main**, exact final head SHA and actual GitHub workflow run links; unrelated open PR #21 not merged by this work.
- Architecture import firewall and pure-core isolation checked.
- Model/outline/Conclusions, translated fields, snapshots, stable IDs and photo references preserved.
- No three-panel UI, extra mutable module tree, website scripting, API or browser profile access added.
- Cross-parent positioning uses canonical mixed `Module.blocks` indices; no implicit merge.
- Pending drafts survive validation failure/selection/Save conflicts; tests demonstrate one-edit-one-undo.
- Tests with fabricated data only, `unittest` + Windows-hosted Qt smoke, no installed Windows acceptance claimed without native interaction evidence.
- Any defect/design change in pure V1 core receives focused tests and an ADR if it changes a locked architecture contract.
- **No PR merged, installer published, release promoted or V1 default replaced without explicit user authorization.**

## Open risks that M1 must disprove with code evidence

- `ProjectEditor` deep-copy/validate on each edit may be too slow on large reports; batch drafts and benchmark before broad text work.
- Existing recursive v4 serialization could fail near allowed nesting depth even when tree validation succeeds; boundary tests are required.
- Reentrant Qt signals and edit focus after branch redraw can lose cursor/selection; use dirty draft coordinator and widget identity reconciliation.
- Native Win32/Qt DPI and drag data paths differ from Linux offscreen tests; reserve installed Windows acceptance.
- Browser-site image-copy bug #64 and export of annotated photos are **outstanding unrelated V1 limitations**, not fixed by M1 architecture work.

## M0 completion / M1 authorization checkpoint

M0 is ready for review once the dependency matrix, blueprint, interface contracts, compatibility/test strategy and this breakdown are present in a documentation-only PR against `main`, with applicable GitHub checks assessed at exact PR head. **Approval of M0 documentation is separate from authorization to merge; M1 code begins only after a deliberate development decision.**
