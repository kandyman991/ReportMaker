# M2.1 — Structural placement foundation

**Status:** isolated implementation submitted for review; not the full M2 exit gate.
**Base:** live `main` at `9adffa70eb0052dd0b742be25bf33eca6f6d6ff8`.
**Branch:** `feature/v2-m2-1-structural-placement`.
**Requirements addressed in part:** BE-S01, BE-S02, BE-S04, BE-I01, BE-I02; see [RM-BE-001](BRANCH_EDITOR_REQUIREMENTS.md) and the [M2 roadmap](ROADMAP.md).

## Reviewable M2 boundaries

- **M2.1 (this PR):** Pure Before/After/Inside planning from canonical `project_branch` projection, with strict report generation/revision guards and one existing `ProjectEditor` transaction per move. Handles both whole intervention modules/subtrees and individual mixed content blocks, including movement between parents. No hidden merge, no new mutable tree. Keeps existing nested wrapper IDs when a wrapper remains valid. No-op moves preserve redo/history.
- **M2.1 user entry point:** The V2 toolbar adds Up/Down movement for the selected module using adjacent *mixed* siblings, with keyboard Alt+Up/Alt+Down. These controls use the same validated `move_node` command as future drag/drop and are disabled semantically at boundaries (they report no movement and create no history step).
- **M2.2 planned:** Actual drag handles and prominent Before/After/Inside drop target indicators, including cursor, accessibility, mouse and Windows native acceptance. Do not claim BE-S01/S02 complete from the pure planner alone.
- **M2.3 planned:** Indent/outdent, duplicate/delete with confirmation and deep-ID regeneration, undo, mixed-block movement affordances and keyboard paths.
- **M2.4 planned:** Expand/collapse with local identity restoration, canonical descendant counts, visible derived numbering/TOC and Windows/manual responsiveness validation.

## Canonical invariants

1. `Report.modules` and mixed `Module.blocks` are the only authored hierarchy. The planner reads a fresh detached projection; it never stores/persists a secondary structure.
2. An explicit `inside` is accepted only by structural containers, and intervention modules cannot move under Conclusions. The root accepts top-level modules only. Before Conclusions appends among intervention modules; After Conclusions is always invalid.
3. A module cannot move to itself, its descendant, or a destination whose parent is in its subtree. Wrong block owner, stale generation or revision, unsupported position and draft conflicts reject without mutation.
4. In-parent moves calculate pre-removal indices so existing `ProjectEditor` move semantics preserve real mixed ordering; no-op placements do not increment revision or erase redo. Valid moves are a single undoable transaction.
5. Stable module/block IDs, original/translated text, stale markers, rich formatting, photo asset references, photo visuals, and metadata are retained. Serialization remains the existing atomic v4 format. Numbering/TOC continues to derive from `module_outline(report)` and Conclusions stays last.

## Evidence

- `tests/test_v2_structure.py`: synthetic root/nested moves, mixed module/content placement, no-op/redo, undo, cycles, bad destinations, draft/stale guards, cross-parent photo asset and translation preservation, save/reopen, Qt Up/Down toolbar.
- `.github/workflows/v2-structure.yml`: hosted Windows Python 3.11/3.12; real PySide6 offscreen interaction, prior M1.2/M1.3/M1.4 regressions and V2 import firewall.
- Hosted CI is **not** a physically installed Windows machine test. M1 Checkpoint A visual/DPI acceptance remains open.

## Manual Windows review (still outstanding)

On a real Windows x64 installation and 100%, 125% and 150% scaling: select module A/B, use toolbar and Alt+Up/Down, verify line geometry and caret/selection after reordering, use Undo/Redo, reopen and inspect preserved IDs/content. Full mouse drag/drop feedback and collapsed state are *not* implemented by M2.1 and must be accepted in later M2 PRs.

**Next:** review exact PR head and Windows CI; fix any findings. Do not merge without explicit user approval. The V1 fallback and manual ChatGPT copy/paste boundary remain unchanged. No installer, private data, browser automation or unrelated PR #21 changes.
