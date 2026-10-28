# M2.2 — Native Branch Editor drag-and-drop

**Status:** isolated implementation PR awaiting independent review; not the full M2 exit gate.
**Baseline:** live main dfbdecd7f327c1854f6f925c22999f774e944d07, following PR #71.
**Branch:** feature/v2-m2-2-native-drag-drop.
**Requirements:** RM-BE-001 BE-S01, BE-S02, BE-S04, BE-I01.

## Delivered

- All movable module/submodule and typed content rows expose a dedicated **≡ Drag** handle. Editors retain native mouse text selection; root and mandatory Conclusions cannot be dragged.
- Native Qt drag carries **only an opaque random, in-process MIME token**, not data from the report, customer, photo, or browser. Forged/external MIME is not an edit operation.
- Each row has high-contrast, explicitly labeled **BEFORE / AFTER / INSIDE** hover feedback (red invalid, blue valid). Before/After are visually at the row edges; Inside is a highlighted container. Leaf blocks have no Inside target; root only has Inside; Conclusions only allows module insertion Before.
- Hover preview and commit both use the M2.1 canonical plan_drop planner and unchanged CommandGateway move_node command. The source revision/generation are frozen at drag start. Pending drafts, no-op, stale, self/descendant and invalid Conclusions drops fail without mutation; accepted drops are one undoable canonical transaction preserving media, translations, IDs and ordering.
- Move Up/Down buttons and Alt+Up/Alt+Down continue to provide a nonmouse alternative. No second mutable module tree is added.

## Automated evidence

- tests/test_v2_dragdrop.py: synthetic PySide6 event dispatch for markers and valid/invalid drops, nested mixed-order movement, cross-parent photo, translations, Save/Open, undo/redo, stale changes, pending drafts, forged MIME and Conclusion protection.
- .github/workflows/v2-structure.yml: native PySide6 offscreen validation on hosted Windows Python 3.11 and 3.12, including the new suite and M2.1/M1.2–M1.4 regression gates. Verify all exact PR-head workflows before merge.
- Native installed Windows mouse gesture, OS drag cursor, accessibility, autoscroll, and 100/125/150% DPI physical behavior have NOT been signed off by the hosted tests.

## Installed Windows checklist (pending)

1. Drag A before/after B, Undo/Redo and Save/Open; confirm native cursor, preview and inline text selection are unaffected.
2. Reparent a nested module Inside another and move it Before a paragraph/photo, then back to root/Before Conclusions. Check IDs and content.
3. Move text, table and photo content across parents; verify asset bytes, captions and translations after reopening.
4. Hover self, descendant, invalid Conclusions and leaf nodes; invalid previews must be red and no history created.
5. Keep an unapplied inline draft while attempting to drag, cancel with Escape, check focus, and try scrolling a long branch while dragging.
6. Check Windows 100%, 125% and 150% scaling and screen-reader access to the drag handle.

## Deferred and boundaries

- M2.3: indent/outdent, duplicate/delete. M2.4: collapse persistence, counts, visible numbering/TOC. M4: external Explorer image drops and clipboard import via a separately validated project-media importer. M5: large-branch virtualization/navigation.
- No changes to V1 UI/browser/manual ChatGPT copy-paste, schema, installer, or unrelated draft PR #21. V1 fallback remains intact.
- Independent PR review and explicit user merge authorization remain necessary.
