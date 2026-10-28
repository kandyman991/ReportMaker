# ReportMaker V2 — Architecture Contract

**Document status:** Proposed V2 architecture baseline for review  
**Date:** 2026-10-28  
**Scope:** Clean V2 application around selected V1 capabilities; no implementation or replacement of V1 is authorized by this document.  
**Requirements:** [RM-BE-001](BRANCH_EDITOR_REQUIREMENTS.md) · [Roadmap M0–M7](ROADMAP.md)

## 1. Binding design decision

ReportMaker V2 must **start with the Branch Editor as its primary workspace**. It is one connected, hierarchical, ordered, **directly editable** canvas; it is neither a passive flowchart nor an extra navigation pane next to a second unrelated editor.

An expanded branch presents the actual report content—editable titles, text, photo thumbnails/captions, tables and nested modules—in document order. Modules and submodules are structural containers; content blocks are typed leaves. Visible connectors show parent/child relationships. A compact contextual formatting toolbar may appear when editing, not on every idle block.

The separated V1 module tree + block list + detached content editor shall **not** be carried forward as V2's default interaction. A separate Editor tab remains for precise page/document formatting, but uses the *same* canonical data.

**V1 source and release continuity:** Do not rewrite V1 in place, delete it, or copy its monolithic visual-editor UI wholesale. The existing `main` remains the V1 fallback during V2 implementation and acceptance. The initial V2 implementation is isolated; integration to `main` requires review and explicit user authorization.

## 2. Preservation of existing contracts

This document adds a **V2 application-interface** direction without superseding the root [ARCHITECTURE.md](../../ARCHITECTURE.md), [AGENTS.md](../../AGENTS.md), [REPORT_COMPOSITION_CONTRACT.md](../REPORT_COMPOSITION_CONTRACT.md) or existing ADRs. If V2 requires an actual change to one of those locked contracts, create and review an ADR first.

Invariants to retain:

- One structured editable project independent of document rendering.
- One canonical ordered hierarchy of modules, nested submodules and heterogeneously ordered blocks: paragraphs, headings, photos, tables, manual breaks and nested modules.
- Stable persistent node IDs and safe subtree movement, preserving child content, photo associations, source text and translations.
- A dedicated mandatory final Conclusions section, not interleaved with normal intervention modules.
- A single derived summary/table of contents and automatic hierarchy numbering, never another editable/persisted tree.
- Report metadata: title and creation date, intervention date range/ticket/personnel, multiple selected intervention types; database-selected **or manually entered** customer/site/machine with report-local frozen snapshots.
- Unlimited extensible language tags, original text and separate per-language translations with staleness marked when source changes; UI localization independent.
- Project-contained, portable picture working copies; original external files never modified. Asset reuse and non-destructive per-placement transforms/annotations; internal review comments must not enter customer exports.
- True editable DOCX with derived PDF; document page geometry, branding, templates and pagination are export concerns, not Branch Editor canvas geometry.
- Windows x64 native PySide6/Qt application with CI and separate real installed-Windows acceptance gates; Linux optional.

## 3. Selective V1 reuse and dependency firewall

M0 must map actual transitive imports before implementation. Components are classified as follows:

| V1 component | V2 decision | Important boundary |
| --- | --- | --- |
| model.py and rich_text.py | Reuse / minimally adapt | Canonical typed data and translation provenance |
| engine.py | Reuse / extend | Pure validated commands and derived outline; no Qt |
| project_io.py | Reuse / version carefully | Safe portable storage, atomic save, legacy Save As |
| rich_editor.py | Reuse editing functionality | Decouple formatting operations from V1 controller |
| media_import.py, photo_gallery.py, photo_editor.py | Reuse services/tools; adapt UI | One media library, per-placement visuals and safe local import |
| export.py and template_import.py | Reuse / complete necessary integration | Export must consume canonical data, not any UI tree |
| page_editor.py | Preserve useful logic and Editor tab | Shared edit sessions; paper view not a second report model |
| visual_editor.py | Do **not** import as V2 UI | Extract reusable controller logic only if dependency-safe |
| ui.py | New V2 application shell | Keep existing browser behavior; do not keep V1 three-panel navigation |

Copying a source file is **not** sufficient evidence of independent reuse. Review its transitive imports, Qt widget ownership, tests, browser boundaries and assumptions about V1 widget identities. Prefer a common pure core used by both V1 and V2 over two diverging report engines.

## 4. Proposed V2 logical components

These are *architectural responsibilities*, not a fixed file/directory naming mandate. M0 will finalize package paths.

### Pure core and persistence
- **Canonical report model:** report metadata, typed ordered blocks, localized content, stable identities and mandatory conclusions.
- **Command service:** validated insert/rename/change/reorder/reparent/duplicate/remove, table edits, media reference updates, undo/redo; fail atomically.
- **Persistence adapter:** strict serializer/migrations, project-contained assets, durable IDs and safe open/save.
- **Derived projections:** outline/numbering, collapsed counts and TOC created from canonical state.

### Editing coordination
- **Edit-session coordinator:** selected node context, dirty text/table/metadata drafts, commit and cancellation policies, conflict resolution between Branch Editor and Editor tab. No silent discard or overwrite.
- **Presentation-state store:** expanded/collapsed branches, zoom/pan/focus/search/selection and optional remembered positioning. Separate from printable report content; use a versioned local/workspace store or an approved schema extension.
- **Workspace command adapter:** only adapter-approved operations may mutate canonical data. UI must never independently manipulate a second report tree.

### Branch Editor UI
- **Canvas/layout:** a connected, content-sized vertical hierarchy managed by Qt layouts; connector lines are decoration only and order is model-driven. Every expanded card grows/shrinks to the full wrapped content without internal or visible workspace scrollbars. Long reports remain navigable by mouse wheel, touchpad, keyboard and focus/caret tracking, with no nested scrollable editors or arbitrary card-height ceiling; zoom/pan/fit are distinct future controls.
- **Module container:** inline title editing, nested children, collapse/focus, summary and context menu.
- **Content widgets:** rich-text, image/annotation and table renderers/editors, loaded lazily when practical.
- **Drag/drop planner:** compute valid Before/After/Inside preview before commit, reject invalid drops, revalidate after any queued callback; only containers may accept Inside.
- **Search/focus:** query canonical titles, content and captions, reveal results even in collapsed branches, restore prior view state.

### Other application tabs and services
- **Editor:** precise document-oriented formatting of those same stable blocks; not independent HTML data.
- **Photo Gallery:** manages shared project-owned media and its placement links; no extra image store.
- **Preview/export:** generated from validated canonical document and actual export settings; distinguish quick schematic preview from exact pagination claims.
- **ChatGPT:** retain existing embedded user-controlled Qt WebEngine view, session and external-browser fallback; no new integration engine.

## 5. ChatGPT boundary — unchanged and non-negotiable

The user explicitly decided: **ChatGPT integration stays as-is; the interface between ChatGPT and the report is manual copy/paste.**

1. ChatGPT remains an ordinary embedded website operated by the user, with manual login as supported by the site and an external-browser fallback.
2. Users may manually select and copy text from a branch, paste it into ChatGPT, manually copy a response, and paste into a chosen branch block. Text handed into report editors is treated as untrusted plain text. Ordinary user-initiated browser image copy/download is also permitted; any image intentionally added to a report must go through the existing validated Gallery, clipboard-image or local-file importer, never an automatic browser-to-report channel.
3. Users decide whether and where to paste; existing canonical editing/undo behavior applies once they paste.
4. Do **not** implement OpenAI API/SDK calls, hidden prompts, background agents, automated messaging, website scripting/DOM inspection, scraping, browser cookies/tokens export, account automation, automated context synchronization or insertion of website responses.
5. ReportMaker does not transmit project customer/machine/report data to ChatGPT. Only content the user deliberately transfers using normal website/browser controls may reach the site; no background transfer is permitted.
6. No browser profile data in report archives, GitHub, logs or test fixtures.

This replaces the earlier speculative **automatic AI editing of selected branch content** interpretation. RM-BE-001 BE-I06 is fulfilled by **manual, user-directed plain-text copy/paste**; ordinary manual browser image copy/download and separate safe image import do not create an AI integration. Any automated variant would be a separately authorized and reviewed architecture change, not V2 scope.

## 6. Key transaction and interaction rules

- The canonical ordered children sequence is authoritative for both canvas order and exported order; no parallel drag/drop-owned hierarchy may persist.
- Moving a structural module moves its entire subtree. A nested-module wrapper identity must remain stable wherever valid; promotion/demotion must not alter the contained module ID.
- Drop targets are **Before, After and Inside**, shown explicitly. No implicit merge on normal drop; no Inside on text/image/table; no moves into self/descendant or into dedicated Conclusions.
- Outdent/Unmerge means moving a nested module one level outward. Reconstructing a historical merge is not promised without retained history.
- A failed command preserves model, pending drafts, asset references and undo history; a valid compound change must undo in one step.
- Keyboard focus, Qt selection and rich-text formatting survive normal edits; structural drag handles must not conflict with text selection.
- Generate IDs only for genuinely new/duplicated objects; preserve existing IDs through moves, tab transitions, save/load and output.
- Preserve the immutable bytes of each approved **project-owned imported image working copy** and its independent per-placement visual data. Import may explicitly convert/optimize an external original (for example, HEIC to JPEG) under the existing M4.5 media contract; the external original is never modified, need not be stored verbatim and is not required to reopen the report. Clipboard/Explorer ingestion passes through the existing safe local importer and explicit copy semantics.
- Editing transactions may be batched for performance. Never deep-copy/re-render a large hierarchy on every keystroke if this causes lost selection or unresponsive input.

## 7. Persistence and migration

The inspected V1 model and project format **v4** already express nested modules and mixed ordered content. Do not impose a new format solely to render V2's branch lines or editing layout.

If portable block-layout metadata requires a schema extension:
1. Define schema v5 in M0 and the explicit migration; preserve old project structure, IDs, image assets, translations and metadata.
2. Open existing v1–v4 archives safely. Reject malformed/untrusted content and unrecognized future versions.
3. Use **Save As to a new file** for legacy upgrades, with the source project unchanged and restorable.
4. Keep canvas-only settings out of customer-facing exports.
5. Test open/save/reopen, migrations, undo/redo, and a V1 compatibility policy for V2-authored files. Never imply V1 can read future schema versions.

Nesting is conceptually unrestricted in the UI; implementation may enforce documented, security-motivated resource/depth bounds for abusive archives or memory exhaustion. Existing `MAX_NESTING = 256` needs explicit M0 assessment; do not silently remove validation.

## 8. Preview and export boundaries

The Branch Editor represents editable structure, **not a physical Word page**. Canvas zoom and temporary block presentation size do not directly change DOCX/PDF pagination. Persistent layout attributes that should change printable width/flow must have explicit, shared semantics with export.

- TOC and numbering must be derived from the canonical hierarchy on demand.
- All supported photo edits/annotations must be included in previews and customer exports, while private review comments stay excluded. If unsupported, fail explicitly rather than silently discard changes.
- A continuous interactive preview may be approximate, but an **export-faithful preview** must use the actual export/render semantics and identify remaining fidelity limits; do not promise pixel-identical Word/Windows font substitution without native verification.
- The separate Editor tab may edit printable layout and content, but never an independent report body.

## 9. Testing, quality and acceptance gates

All significant changes require testable model-level commands and synthetic tests. Before each PR merge:
- Run architecture invariant tests and affected Qt/unit/serialization/export regressions.
- Test cross-parent moves, IDs, duplicated subtree, undo/redo, invalid drops and concurrency of unsaved text/table/page drafts.
- Test native Windows file drop, keyboard/paste, DPI, fonts, focus, long branches and browser fallback separately from headless CI.
- Verify old project read/Save As, portable images and no private data leaks.
- Record exact tested commit SHA, open findings and proof of native acceptance. PR reviews do not equal merge approval.

The roadmap's M0–M7 gates are binding sequencing/acceptance criteria for V2. This documentation PR alone **does not** begin M0 or authorize a V2 feature branch merge.
