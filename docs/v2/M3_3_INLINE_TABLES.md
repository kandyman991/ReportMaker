# M3.3 — Inline Table Editing in the Branch Editor

**Started:** 2026-10-28. **Baseline:** live `main` at `76e94b2b3d7a0214e9e20026b9fdde2762a484a6` after merged PR #78 and continuity refresh. **Branch:** `feature/v2-m3-3-inline-tables`. **Contracts:** BE-L04, BE-E05, BE-I01 and BE-I03.

## Delivered scope

- Canonical `TableBlock.rows` and `LocalizedText` remain the only persistent table state. The Branch Editor now projects cells as directly editable Qt `InlineParagraph` widgets inside a layout-managed grid (no `QTableWidget`, extra document model or visible nested scrollbars). Cells wrap and resize by their contents, and keyboard focus can move across cells.
- Source-cell edits and adding/removing rows/columns are staged through a single `TableDraft` keyed to the stable block address in the existing `DraftCoordinator`. The selected cell determines insert-after and delete positions. Row/column controls have `NoFocus` so clicking does not steal the editor's selection. Contextual new-table insertion uses the same module/mixed-index `CommandGateway` path.
- Row and column insertion create language-correct empty `LocalizedText` cells. Existing cells, their translations and stale markers are deep-copied unchanged. Only changed source wording marks that particular cell's translations stale. Transient per-cell origin mappings prevent false staleness if a user types and then returns to the original text, even after inserting rows or columns. A table with one row or column cannot delete its last dimension; non-rectangular imported tables remain editable cell-by-cell but reject ambiguous structure edits rather than silently normalizing data.
- A combined cell+structure draft is committed via one validated `set_table_rows` command and one underlying `ProjectEditor.apply` transaction. Apply/Revert, No-op, Undo/Redo, Save/Open, project switches and other commands reuse the existing draft guards; simultaneous text and table drafts cannot be silently discarded. Table drafts reject obsolete generation/source and retain the user's pending edits.
- The unchanged schema v4 serializer and existing DOCX/PDF exporters consume the committed canonical table rows. Mixed sibling order, stable table ID, translations, mandatory Conclusions and derived outline are unaffected. No V1, browser/ChatGPT, template, release or installer changes.

## Acceptance evidence and remaining gates

- `tests/test_v2_tables.py` covers validated pure cell/grid transforms, mixed-index table insertion, one-step atomic Undo/Redo, no-op/invalid/stale commands, simultaneous text/table drafts, Unicode and translation provenance, project save/reopen, offscreen Qt cell focus, natural height/invisible scrollbars, toolbar row/column operations and Apply/Revert.
- `.github/workflows/v2-inline.yml` runs the new suite on hosted Windows Python 3.11 and 3.12. Require green checks on the **final** review head before merge.
- Physical installed Windows (DPI 100/125/150%, keyboard/focus, long multilingual tables, screen reader and real customer workflow), actual Word/PDF viewing and cross-tab conflict resolution are not claimed by offscreen tests. Cross-tab coordination and remaining block insertion belong to M3.4; full integrated output acceptance belongs to M6/M7.
- M3.3 does not add table-cell rich formatting, merged cells or advanced column width/print controls. No parallel table store or schema migration is introduced.

**Next:** independent PR review and corrections; do not merge without explicit user authorization. Then M3.4 — Remaining Block Insertion and Cross-Tab Draft Coordination.

## Independent review corrections — 2026-10-29

- Reviewed original PR head `618c77ee3ac5b72afc061dc6e93661deb4a63ded`. Reproduced a Qt redraw failure after a pending table draft became stale due to a concurrent canonical table edit. A fresh display-only preview now retains the staged text in read-only cells with a visible conflict warning and usable Revert; editing/Apply remain fail-closed until the draft is resolved. No draft is silently overwritten.
- Reject an insert-row operation on an existing zero-column table: previously it could create a ragged grid by accident. Insert-column remains available to establish a width; an entirely empty table can still start with one row.
- Added a Qt stale-refresh/revert regression and a pure empty-dimension regression. Reverify the dedicated hosted Windows Python 3.11/3.12 workflow on the **corrected final commit**, not the previous successful run; installed physical Windows and M3.4 cross-tab acceptance remain pending.
