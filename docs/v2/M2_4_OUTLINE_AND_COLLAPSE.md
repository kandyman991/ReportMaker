# M2.4 — Branch Collapse, Local View State and Single-Source Outline

**Date:** 2026-10-28. **Base:** `main` at `a4a8821988009cfc38569917d8623442f835a4c3` (PR #74 merged). **Branch:** `feature/v2-m2-4-outline-state`. **Requirements:** BE-S03, BE-S06, BE-S07, BE-I02; M2 exit criteria. **Scope:** isolated V2 UI, read projections, local settings, synthetic tests; V1 and project schema v4 unchanged.

## Interaction

- Each module and Conclusions has a compact ▾/▸ toggle in the Branch Editor card header. Collapsing hides only descendants, never removes or reorders them; opening expands exactly that module, preserving independent collapse choices of descendants.
- Collapsed cards show *read-only, derived* counts: descendant modules/submodules, text/heading blocks, photos, tables and page breaks across all nested levels. These count data from the canonical mixed ordered blocks regardless of which branches are currently hidden.
- Labels show `MODULE 1`, `MODULE 1.1`, etc., derived exclusively from `engine.module_outline(report)`. A compact toolbar Contents menu displays the complete up-to-date outline, including hidden descendants and dedicated final Conclusions; selecting an entry reveals its ancestors and scrolls to the stable module ID. There is no persistent editable TOC, duplicated module tree, detached editor or printable-layout geometry on the canvas.
- Collapse/expand, reveal, and settings changes do not modify report data, revision, Undo/Redo, exports, translation provenance or image associations. Existing draft guards prevent redrawing away uncommitted text. A collapse containing the current selection moves that selection to the newly collapsed ancestor.
- Cards retain PR #75's natural content height, no visible/internal scrollbars, wheel/caret navigation and canonical order.

## Local persistence / migration

- Use the existing versioned Qt `QSettings` `presentation/v1` namespace and report-ID + normalized project-path identity; extend records with a sorted list of collapsed module IDs. There is **no `.rmproj` schema migration** and no portable collapse state.
- Legacy M1.4 records containing only `selected` and `scroll` remain readable. Invalid/corrupt data is ignored, and missing/deleted module IDs are pruned on load. Unknown IDs and report content are not recorded in local settings.
- Changes to visibility are written locally when made and at normal lifecycle checkpoints. On first Save / successful Save As, the view is copied under the new path identity **only after** the archive write succeeds; old path state remains independent. Cancelled/failed Save As does not change the active path, archive or destination view state.

## Verification and remaining gates

- `tests/test_v2_outline.py`: pure canonical descendant counts and reparent/duplicate/delete/Undo; Qt hidden/visible rows, numbering, summaries and connector geometry; TOC jump into collapsed ancestors; pending draft protection; legacy/stale settings; first Save and Save As, reopen, failed Save As; long-paragraph natural height and scrollbar preservation.
- `.github/workflows/v2-structure.yml` gates M2.4 on hosted Windows Python 3.11/3.12, alongside M2.1–M2.3 and M1 compatibility. Run all affected suites and offline launcher on the **exact PR head** before requesting merge.
- **Still required:** hands-on installed Windows x64 at 100%/125%/150% DPI, keyboard/screen-reader and long nested reports. Performance virtualization remains M5; M3 table, M4 photo editing, and M6 preview/export parity are not claimed complete. No V1, installer, browser, ChatGPT integration, customer media or release changes.
