# M3 visual report editor — draft implementation

Status: M3 implementation under review in PR #11. Windows-hosted Qt acceptance is separate from installed-PC acceptance. This is an editable .rmproj project editor, **not** DOCX/PDF export.

## Interface
- Native three-pane layout remains: Module Tree + derived Summary on the left; report information, ordered content editor and live document preview in the center; optional user-operated ChatGPT website on the right. Pane dividers, show/hide and maximize are still supported.
- Module tree and Summary both use M2's single canonical hierarchy (`module_outline`); all module add/rename/delete/duplicate/nest/reorder commands use `ProjectEditor`. Conclusions cannot be nested, removed or moved out of the last section.
- Drag tree items onto a module to nest, or above/below an item to reorder. The content-block list supports drag/drop reordering of paragraphs, headings, photos, tables, page breaks and submodule wrappers within the active module. Preview follows the original mixed ordering.
- Select and edit text/headings, photo captions or table cells. Use **Apply block changes** or switch selection to commit the edit. Add photos from local image files only; project bundles embed logical assets.
- Report Information includes creation and intervention dates, title, ticket, personnel, language tags, multi-select intervention types and optional manual customer/site/machine. Database selection explicitly captures an immutable snapshot; detaching it to manual entry is an explicit action.

## Graphical project operations
- Toolbar New / Open / Save / Save As / Undo / Redo are native Qt actions; no terminal needed. Save and Open use the existing M2 `.rmproj` format with strict validation and atomic replacement. Invalid opens preserve the active document. Unsupported schema files are not silently migrated.
- Switching projects or closing with unsaved changes asks to Save, Discard or Cancel. Unsaved block/metadata fields are applied and validated before saving or discarding. Invalid forms block saving instead of silently dropping information.
- Preview is an **on-device HTML/Qt visual representation** of the canonical report including block content and images. It is *not* Word pagination, a print proof, or DOCX/PDF.
- Clipboard transfer from ChatGPT remains user-initiated **plain text**, with no browser DOM access, AI API, injected scripts, telemetry or profile export.

## Verification and acceptance
1. `python -m unittest discover -s tests -v` checks model, persistence, architecture and regressions.
2. `python -m reportmaker --visual-editor-self-test` runs a synthetic offline Qt smoke test: tree and Summary projection, nested preview, block edits, save/reopen, two intervention types, invalid file and failed metadata save.
3. CI on PR #11 runs the hosted Windows smoke gate; review its exact head and log before merge.
4. Native **installed Windows** acceptance is outstanding: mouse drag/drop (including nested/mixed lists), layout/DPI and scroll resizing, image rendering, unsaved edit prompts, keyboard focus/shortcuts, customer DB selection, .rmproj file dialogs, backup/private report policy and actual WebEngine sign-in. An automated hosted runner cannot prove these.
5. M4 must implement DOCX/PDF output. M5 translation editing and richer document layout remain separate milestones.

## Local privacy and data safety
Only synthetic data belongs in GitHub or CI. Customer projects/photos are never sent to the web panel and are saved only to paths the user chooses. Do not add private projects to logs or release assets. No production installer is built or published from this draft PR.
