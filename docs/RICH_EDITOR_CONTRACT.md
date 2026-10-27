# Native Word-style Font and Paragraph ribbon — development slice

Status: **not merged, not installed-Windows accepted**, stacked on preview
contrast correction [PR #22](https://github.com/kandyman991/ReportMaker/pull/22).
User reference: Microsoft Word Font+Paragraph ribbon screenshot (private to chat).
No screenshot, corporate Word template, customer photo or company logo was
committed to this public repository.

## Implemented editing architecture

- Native PySide6 `QTextEdit` selected paragraph/heading block editor with
  functional two-row horizontally-scrollable ribbon. Commands: font family,
  point size, grow/shrink, change case, clear formatting, bold, italic,
  underline, strike, super/subscripts, color and highlight; bullets/numbered
  lists, alignment left/center/right/justify, indentation, line spacing,
  paragraph shading/borders, paragraph-mark visibility and selected-line sort.
  Qt owns the *temporary editing selection*, not persisted Word HTML.
- Pasting from the ChatGPT website stays explicitly plain text. No webpage
  DOM, external HTML/URLs/images, fonts or browser cookies reach the report.
- One `LocalizedText.original` string remains canonical for wording and M5
  translation provenance. A sibling `RichFormatting` stores validated Unicode
  code-point ranges and paragraph styles (color/font/size/emphasis/spacing,
  lists). There is no second editable string or imported arbitrary HTML.
- The existing module tree and derived Summary remain driven by the same
  canonical hierarchy. Formatting is one command-engine transaction on
  **Apply block changes**, with report-level Undo/Redo; QTextEdit also has
  local standard text Undo/Redo while editing. Preview uses escaped formatted
  HTML from those same structured ranges, white paper on dark OS theme.
- Project schema **v4** requires rich records on Paragraph and Heading
  blocks. v1/v2/v3 load with default formatting but cannot be silently
  overwritten in place: users must Save As a new v4 copy. ZIP image safety,
  photo annotations and translation provenance are unchanged.
- Editable DOCX generates real Word text runs with applied font/color/size,
  emphasis, baseline and paragraph styling. PDF uses supported ReportLab
  styles with explicitly limited system/embedded font fallback. User should
  visually verify non-Latin and less common fonts in native installed Windows.
- Synthetic tests cover spans crossing Unicode supplementary characters,
  v3→v4 Save As, strict malformed range rejection, project history, Qt
  selection-formatting roundtrip and editable Word runs.

## Deliberate follow-up items (NOT claimed complete)

The ribbon edits the selected **canonical text block**, while the full
document-preview pane is still a projection, **not yet an unconstrained
full-document WYSIWYG contenteditable page**. Such page editing requires
structural regions/commands to avoid corrupting module hierarchy and
translations when dragging/deleting page elements. The user's earlier
page-edit request remains open.

Importing a real DOCX/DOTX letterhead/page template is separate
[issue #24](https://github.com/kandyman991/ReportMaker/issues/24).
Neither the reference Word document nor its identifying contents are placed
in GitHub. This feature PR does not implement page-template import.

The current publicly available RC1 installer is still the old build.
Do not merge the ribbon feature, replace RC1, mark native Windows accepted or
promote stable production without independent review and separate approval.
