# ReportMaker V2 — Development Roadmap

**Status:** Approved architecture baseline; V2 implementation in progress at M6 (submilestone status below)  
**Date:** 2026-10-29  
**Requirements baseline:** [RM-BE-001 — Branch Editor requirements](BRANCH_EDITOR_REQUIREMENTS.md), 33 selected features  
**Architecture baseline:** [V2 architecture](ARCHITECTURE.md)  
**V1 reference:** [existing roadmap](../../ROADMAP.md) (unchanged)

## Product direction

Build **ReportMaker V2** as a clean native Windows application whose **Branch Editor is the primary editing workspace from the first usable prototype**. Reuse validated V1 core capabilities selectively; do not reproduce V1's permanent module tree + detached central workspace or import its monolithic UI. V1 on `main` remains usable as the fallback until separate V2 acceptance and release authorization.

Modules, nested submodules and ordered rich text, photographs, headings, tables and page breaks are visible in the connected branch canvas and editable at their location. The same canonical report data powers editing, numbering, summary/table of contents, saved projects and exports.

**ChatGPT scope is frozen:** retain the existing user-controlled embedded ChatGPT browser and external-browser fallback. **AI writing text** moves only through manual, user-initiated plain-text copy/paste. Ordinary user-initiated browser image copy/download remains permitted, but adding such images to a report requires a separate, explicit Gallery/clipboard/local-file import through the validated project-media workflow. No APIs, automated synchronization, website scripting, scraping, DOM access, automatic proposal injection, automatic image transfer or automatic insertion. The selected-content AI requirement in RM-BE-001 is satisfied by manually copying the selected text to ChatGPT, reviewing a response and explicitly pasting it into a chosen block.

## Project boundaries

- Preserve V1's original `ROADMAP.md`, application implementation, and release fallback while V2 is built on its own reviewed feature branches.
- Plan and execute V2 in this repository using reviewed, milestone-sized PRs. M6.1–M6.4 implementation currently resides in draft PR #83, which is now frozen for new features.
- Before copying a V1 module into V2, inventory its runtime and transitive imports, identify UI coupling, licensing, test coverage and migration assumptions. Prefer shared, independently testable services over a forked second report engine.
- Never silently alter the binding project invariants in the root `ARCHITECTURE.md`, `AGENTS.md` or related ADRs. Any unavoidable contract change requires a reviewed ADR.
- Avoid modifying shared V1 files from concurrent workstreams without an explicitly coordinated PR boundary.
- Use synthetic test fixtures only; no customer reports, company images, browser profiles or real machine data in GitHub or CI.

## Milestones and exit gates

### M0 — Architecture foundation and dependency audit

**Goal:** Define the implementation boundaries before writing V2 application code.

Deliverables:
- Inspect `model.py`, `engine.py`, `project_io.py`, `visual_editor.py`, `rich_editor.py`, `page_editor.py`, `photo_gallery.py`, `media_import.py`, `photo_editor.py`, `export.py`, `ui.py` and test suites.
- Record a dependency inventory (including transitive imports), reuse/adapt/replace matrix and ownership of every shared interface.
- Define the canonical report adapter, transactional command interface, edit-session/draft coordinator, V2 presentation-state store, media service, rendering/export facade and ChatGPT browser boundary.
- Decide whether existing schema v4 suffices; if persistent layout metadata necessitates v5, document strict backward-compatible migration, Save As behavior and rollback.
- Define the safe deep-nesting and large-report policies, performance benchmarks, failure behavior and regression test matrix.
- Agree on testable PR boundaries, architecture validation and an M1 interaction prototype checklist.

**Exit:** Reviewed design/dependency artifacts; no second report model, hidden old-UI dependency or unresolved persistence/ChatGPT boundary. No UI implementation is required to complete M0.

### M1 — First working Branch Editor

**Goal:** Deliver the defining V2 interaction immediately, not a recreation of V1.

Deliverables:
- Fresh PySide6 V2 application shell with Modules/Branch Editor as primary full-workspace tab.
- Root → module → submodule connected, vertically ordered editable containers.
- Inline title and rich-text entry for a basic report; insert basic modules and text blocks.
- Reuse canonical model and command engine; New, Save, Open, Save As and Undo/Redo work.
- Preserve dedicated Conclusions and report metadata in data and saved projects.
- Keep the V1 executable and its files unaffected.

**Exit / Checkpoint A:** User can construct, edit, save and reopen a nested report entirely in the branch workspace; visual and interaction review confirms fidelity to the agreed sketch.

### M2 — Complete structural editing

Deliverables:
- Arbitrarily nested modules with ordered mixed child blocks and valid placement.
- Drag/drop with unambiguous **Before / After / Inside** target feedback; Inside only on a container, never an implicit merge.
- Move up/down, indent/outdent ("Unmerge" as moving out one level), duplicate, delete and undo/redo.
- Expand/collapse; restore expansion state after reopening; collapsed descendant counts.
- Deterministic derived numbering and single-source TOC; Conclusions remain last.
- Safe cycle prevention, invalid-drop rollback and preserved IDs/content/assets/translations.

**Exit:** Model and Qt tests demonstrate no accidental nesting, data loss, duplicate IDs or independent structure.

### M3 — Complete inline text and table editing

Deliverables:
- Edit paragraphs, headings and module titles in place.
- Contextual rich-text ribbon displayed when text is being edited, with correct selection/focus handling and existing formatting semantics.
- Inline table cell editing and row/column operations.
- Contextual insertion of every supported block type.
- Block-width/height presentation behavior defined and controlled; persistence only where appropriate.
- Shared edit-session coordinator prevents losing unsaved drafts between the Branch Editor and page Editor.

**Exit / Checkpoint B:** Format and edit actual content without leaving the branch; mixed text/table edits survive save/reload, translation-stale rules, cross-tab conflicts and undo/redo.

### M4 — Photo integration

Deliverables:
- Show original or transformed image thumbnails and editable captions in their branch positions.
- Reuse project-owned asset storage, Photo Gallery, conversion, crop, rotation, scale and annotations; no duplicate photo model.
- Explicit image replacement and in-branch editing affordances.
- Windows Explorer drop and clipboard image paste at a selected valid insertion location, using safe native image import; external originals are never modified, and approved project-owned working-copy bytes are retained unchanged through non-destructive edits.
- Asset reuse with per-placement non-destructive visual edits; compatibility, invalid input, stale drag and undo tests.

**Exit:** Photos can be imported, displayed, edited, moved and reopened directly within the branch without broken references or external-file dependencies.

### M5 — Navigation and scalability

Deliverables:
- Focus mode for a selected module/subtree; restore context on exit.
- Zoom, pan and fit-to-screen without modifying print dimensions.
- Search titles, text and image captions, revealing matches in collapsed branches.
- Right-click context menus, keyboard accessibility and movement alternatives.
- Lazy rendering/virtualization or comparable bounded-widget approach for large reports; meaningful collapsed summaries and safe deep nesting.

**Exit:** Large synthetic reports remain responsive on Windows, with no cursor/selection drift, dropped edits or loss of structural data.

### M6 — Full application integration

Deliverables:
- Keep separate Editor tab for precise document/page formatting.
- Make Photo Gallery and ChatGPT accessible as tabs without any independent report data.
- Retain the existing user-controlled ChatGPT browser and manual plain-text copy/paste writing workflow; normal manual browser image copy/download uses the separate validated Gallery/clipboard/file importer, never a new AI engine or direct browser integration.
- Preserve customer/site/machine snapshots, multiple intervention types, open-ended languages, mandatory Conclusions, template and project workflows.
- Synchronize automatic numbering and TOC from the canonical hierarchy.
- Live printable preview with clearly stated fidelity and refresh rules, and accurate DOCX/PDF export of ordered text/tables/photos, including supported photo annotations. Do not silently export an unedited photo when edits exist.

**M6 implementation decomposition (2026-10-29):** [Seven formally tracked submilestones, evidence and PR ownership](M6_SUBMILESTONES.md). The approved M6 deliverables and Checkpoint C definition above/below are unchanged.

1. **M6.1 — Canonical shared workspaces:** reviewed and merged in PR #83.
2. **M6.2 — Photos/Gallery and basic faithful exports:** reviewed and merged in PR #83.
3. **M6.3 — Report Info and references:** reviewed and merged in PR #83.
4. **M6.4 — Explicit content translations and language delivery:** reviewed and merged in PR #83.
5. **M6.5 — Metadata and boilerplate localization:** reviewed and merged in PR #84, including strict schema-v5 provenance and export approvals.
6. **M6.6 — Precise page Editor and Word/template fidelity:** independently reviewed, corrected and merged in PR #88. Synthetic native Word 16.0 verification and visual comparison passed; broader release testing is M7. See [M6.6 progress](M6_6_PROGRESS.md).
7. **M6.7 — End-to-end Checkpoint C:** ACTIVE on isolated branch after PR #88; see [M6.7 progress](M6_7_PROGRESS.md). Not yet independently accepted or merged.

**PR boundary:** PR #83, #84 and #88 are merged. M6.7 is a separate integration/checkpoint draft with dedicated synthetic Windows-hosted gates; independent review and explicit merge authorization still apply. Physical installed-Windows/release acceptance remains M7, beyond the narrowly recorded synthetic Word check.

**Exit / Checkpoint C:** End-to-end synthetic technical report edits in Branch Editor, previews, saves and exports correctly; all tabs reference the same stable content IDs and no unsaved edits vanish.

### M7 — Validation, migration acceptance and Windows release

Deliverables:
- Complete the 33-feature RM-BE-001 acceptance matrix, including the manual ChatGPT-only interpretation of BE-I06.
- Test v1–v4 project reading, any approved new schema and non-destructive Save As migration.
- Run model/Qt/Windows-hosted CI, plus native installed Windows keyboard, DPI, drag/drop, clipboard, browser sign-in/fallback, long reports and real Word/PDF visual acceptance.
- Verify legacy V1 project reopening, existing export/branding/template workflows, security and privacy requirements.
- Fix blockers and prepare an independently approved Windows V2 release candidate; preserve V1 fallback until user acceptance.

**Exit / Checkpoint D:** Installed Windows acceptance passed, blocking regressions resolved and explicit approval obtained before merging V2 as the default or publishing a production release.

## PR and integration approach

1. The initial roadmap/architecture documentation baseline was reviewed and merged separately (PR #65); later implementation PRs must honor that contract. **PR #83 (M6.1–M6.4) and PR #84 (M6.5) are merged.**
2. From M6.6 onward, use **one milestone-sized feature PR at a time**, from the reviewed `main` baseline. New PRs remain narrow, testable, independently reviewable and unmerged without explicit authorization.
3. Prefer model/command and editing-session foundations before concurrent widget work. Parallel photo/preview changes are permissible only after their interfaces are stable and shared-file ownership is coordinated.
4. Every PR must state baseline/head commit SHAs, exact tests run, unverified Windows steps, acceptance evidence and how it respects the architecture contract.
5. Protect `main` and the V1 release path. CI success alone is not permission to merge.

## Known prerequisites and risks

- Existing `engine.py` has `MAX_NESTING = 256`; V2 must remove arbitrary user-facing nesting limits *without disabling resource/safety protection*.
- Existing `ProjectEditor.apply()` deep-copies and validates the report. Inline typing needs deliberate batching and UI draft management.
- Current editable page is a continuous schematic, not exact Word/PDF pagination; preview fidelity is a separate acceptance gate.
- In the assessed V1 source, exporting visually edited photos may fail closed until annotated-output integration is ready.
- Existing V1 Ctrl+drop/Unmerge behavior is a safe starting point, not the final Branch Editor gesture design.
- Multiple editors must share explicit transaction/draft-conflict handling; never silently overwrite one another.

## Documentation and status

- Scope: [RM-BE-001](BRANCH_EDITOR_REQUIREMENTS.md)
- Invariants and module/service boundaries: [V2 architecture](ARCHITECTURE.md)
- V1 source of truth stays [root architecture contract](../../ARCHITECTURE.md), [report composition](../REPORT_COMPOSITION_CONTRACT.md) and [existing roadmap](../../ROADMAP.md).

**Current next action (2026-10-29):** M6.7 [PR #89](https://github.com/kandyman991/ReportMaker/pull/89) is independently reviewed and merged (commit `6cd9565a1514e84c1ee2a21543174dafef4c911e`), completing synthetic Checkpoint C. Begin [M7.1](M7_PLAN.md) on an isolated draft branch: build a **V2-specific** Windows installer with distinct V1 identity and safe installed-offline CI smoke, then separately review. All 33 physical Windows acceptance cases remain pending; do not release V2 or change the default without separate user authorization.
