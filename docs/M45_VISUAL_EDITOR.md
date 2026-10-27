# M4.5.2 — Non-destructive photo editing and annotations

Status: **Feature branch implementation pending independent review; not merged**. Derived from ADR-0008. Tests use only synthetic image assets.

## Native PySide6 visual editor

Select a PhotoBlock and click **Edit selected picture** in Content & Preview. The offline dialog supports source-relative rectangular crop and reset, 90° rotation, ±15° straightening, horizontal/vertical flips, report width from 20–100%, left/center/right alignment, and individually editable technical arrows, lines, rectangles, ellipses, highlights, freehand pen, text and callouts. Tool choice, color/thickness, mark selection/movement, edit label, delete, and dialog undo/redo are available; Cancel discards all changes. Apply writes one ProjectEditor history transaction for report-level undo/redo.

Image assets are immutable imported working bytes. Per-photo placements own their own geometric state, which is moved and duplicated along with blocks. Shape coordinates are normalized to the oriented input image before crop and rotation. Preview composition uses bounded temporary Qt QImages; report preview uses distinct resources for separately edited placements.

## Project v3 compatibility

- Format version is **3**; project manifest and hashed asset boundaries remain ZIP allowlisted and local/atomic.
- Each PhotoBlock has a typed non-destructive visual object, with validated crop coordinates, rotation, straightening, layout, and a bounded array of typed shape records (stable IDs).
- Text labels are LocalizedText objects with original/source language, separate translations and stale markers; these retain M5 provenance.
- Valid version 1 and version 2 archives load with default empty photo visuals. Save As to a **different filename** is mandatory before writing version 3; originals remain unchanged for rollback.
- Newly saved v3 files reject absent/malformed visual objects, invalid attributes, duplicate IDs, impossible crop, nonfinite coordinates, unsupported kinds and excessive freehand points.

## Export compatibility

**M4.5.2 is an editor and report-preview milestone, not annotated DOCX/PDF export**. Until M4.5.4, an export containing a visually edited PhotoBlock is deliberately rejected rather than silently omitting the saved annotations or cropping. Normal unchanged-photo M4 Word/PDF export remains supported. M4.5.4 will compose consistent Word/PDF images and layout while excluding any future internal review comments.

## Tests, limits and status

Synthetic tests cover v3 save/reopen, per-placement independence and localization, undo/redo, v2/v1 migration, tampered manifest rejection, original byte preservation, Qt rendered composition and the DOCX/PDF fail-closed boundary. Native offline Qt editor interaction is added to editor_probe. Hosted Windows CI does not constitute installed-Windows acceptance.

M4.5.3 private review comments, M4.5.4 composed-image exports, native installed-Windows checks and the user-deferred M0–M4 acceptance remain pending. Do not merge or publish an installer without explicit user authorization.
