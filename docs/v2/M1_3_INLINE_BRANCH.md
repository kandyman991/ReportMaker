# ReportMaker V2 — M1.3 Direct Inline Branch Editing

**Status:** isolated feature branch for review; do not merge or publish a Windows installer without authorization.
**Starting main:** `49abc22934bc18575caadf75ba0113c626fcb70a` (includes merged M1.2 PR #68).
**Feature branch:** `feature/v2-m1-3-inline-branch-editing`.
**Architecture:** M1.3 scope in [M1 implementation plan](M1_IMPLEMENTATION_PLAN.md), [M0 interface contracts](M0_INTERFACE_CONTRACTS.md) and [V2 architecture](ARCHITECTURE.md).

## Behavior

- Actual module/submodule titles and paragraph text appear as inline Qt input widgets inside the existing connected branch. Other block types and report root remain read-only until their approved milestones. V1 UI and Browser/ChatGPT integration are not imported or modified.
- Enter commits a title; Ctrl+Enter commits a paragraph; Escape reverts the active draft. Contextual **Apply**/**Revert** buttons appear for edited fields. Plain Enter inserts a paragraph newline. Plain-text paste is user-directed and stays in that chosen field.
- Unsaved draft text lives in `DraftCoordinator`, not a second editable report. Multiple independent fields can have drafts; rendering preserves their text. Ordinary structural commands, Undo, Redo, Save and project switching are blocked while any draft remains. Applying one draft bypasses the guard only for its validated canonical command. Field-level stale-source comparison prevents overwriting another editor's changes.
- Every successful application is one M1.2 `CommandIntent` and one ProjectEditor history transaction. The new explicit `set_paragraph_rich` command re-maps rich runs for unchanged Unicode characters and retains safely identifiable paragraph styles, never truncating existing formatting with stale offsets. Ambiguously edited paragraph-style delimiters fail and retain the draft for manual resolution. `LocalizedText.update_original` marks translations stale as before.
- Toolbar insertions are `add_module`, `add_nested_module` and `add_paragraph` commands. Title focus selects the parent/target module; mixed-order canvas and derived Conclusions placement remain canonical. Undo/Redo toolbar actions target committed transactions. For editor-local keyboard Undo use native Ctrl+Z, and for **canonical** Undo/Redo use Ctrl+Alt+Z / Ctrl+Alt+Shift+Z or the toolbar.
- View redraws occur after a Qt event turn for command notifications; row selection scroll position and text cursor are restored after the immediate edit. Qt widgets never mutate the underlying Report or bypass typed commands.

## Proof and limitations

- New synthetic `tests/test_v2_inline.py` covers commit/discard, multiple pending drafts, source conflicts, no-op history, Unicode, translations, rich span remapping, invalid styled paragraph delimiters, Qt text editing, creation of nested content and undo/redo.
- New `v2-inline.yml` Windows Python 3.11/3.12 CI runs the new tests and the M1.2 pure session suite. Existing V2 shell and V1 regression gates must continue to pass on the exact PR head.
- M1.3 deliberately does **not** provide New/Open/Save dialogs; full project lifecycle, native installed Windows smoke and Checkpoint A are M1.4. This UI is not complete rich-text formatting (M3), table/photo editing (M3/M4), drag/drop/reorder (M2), large-report virtualization (M5), or tab/browser integration (M6).
- No real customer input, browser profiles, installer artifacts, production deployment, schema changes or legacy UI edits are in scope. No user-owned installed Windows validation is claimed.

## Review instructions

Review draft guard bypass, stale source checks, direct Qt editing callbacks, rich text mapping and all existing V1/V2 regression workflows. Record exact head commit and hosted Windows results on the PR; any new findings must be corrected and rerun before recommending a merge. **Do not merge to main without explicit user approval.**
