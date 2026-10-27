# Direct editable document-page surface — Step 2

Status: staged implementation for independent review. This is **not** a native
installed-Windows acceptance, production installer, or merge into main.

## User interaction

The lower document pane opens on **Editable page**, a white paper-like,
scrollable Qt surface containing the full report in canonical module/block
order. User changes text, heading wording, table cells, and multiline photo
captions directly on that page. Press **Apply page edits**, use Save/Export/
Undo/Redo, or switch to **Print preview** to commit a validated transaction.
The original read-only rendered HTML **Print preview** remains available for
comparison. Actual Word/PDF page breaks and font substitutions may differ.

The existing Font/Paragraph ribbon remains available for editing rich run and
paragraph formatting. Each text/heading has **Style in ribbon…**, which commits
page edits and selects exactly that canonical block for ribbon formatting.
The page uses SafeRichTextEdit with plain-text-only clipboard input and blocks
all drag/drop; it never imports arbitrary HTML, URLs or remote images.

Protected display-only elements: report metadata, derived Summary, module/
submodule titles, page breaks, and photo working images. Structural edits use
the module tree, block controls and picture editor, not edits to arbitrary
rendered HTML or removal of structural boundaries. The page deliberately does
not promise arbitrary Word document-object editing, live print pagination or
fillable imported DOCX letterhead. The user can always access existing editor
controls for photo placement, module reordering and report metadata.

## Canonical model and save

- Widgets are transient views keyed by **stable module ID + block ID + field**.
  No parallel project text/HTML, index-based mapping or second Summary exists.
- Only changed widgets are captured; one ProjectEditor.apply() transaction
  validates the full candidate and provides report-level Undo/Redo.
- Changed LocalizedText.original uses update_original(), marking every existing
  translation stale. Unchanged cells/fields retain translations and styles.
- Text typography is re-captured as RichFormatting with Unicode code-point
  offsets. The .rmproj schema remains **v4**, preserving legacy Save As rules.
- Table edits modify existing cells only; table dimensions stay structural.
  Original photo asset bytes and placement transforms remain untouched.
- Save/Open and DOCX/PDF export operate solely on the validated canonical
  report, not the page view; invalid edits cannot partially commit. Pending
  page edits are never silently dropped by a preview redraw.

## Verification and limitations

Synthetic GUI regressions cover stable field mapping, mixed/nested block
ordering, page text/heading/table/caption changes, translation staleness,
single-step Undo/Redo, fail-closed validation, untrusted clipboard,
Save/Open and DOCX/PDF export. An offline Qt smoke checks page editing and
the read-only preview's light background. Hosted Windows CI and real installed
Windows UI, high-DPI, font faces, clipboard, drag/drop, multi-page layout and
actual Word/PDF visual output are separate acceptance gates.

The currently implemented continuous editable page is **not a pixel-accurate
Word layout**: it is a white page-styled native editing view. Real pagination,
headers/footers and full template editing belong to the subsequent template
and native Windows acceptance steps.
