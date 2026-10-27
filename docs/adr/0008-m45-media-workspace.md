# ADR-0008 — M4.5 project-contained media workspace and editable image annotations

Date: 2026-10-27
Status: Proposed for engineering review; product requirements agreed by user
Owners: ReportMaker project
Supersedes: None; extends ADR-0006 (report hierarchy), ADR-0007 (export layout) and M2 project packaging

## Context

Industrial service reports rely on large original photos, often HEIC from phones. The user wants to import **working copies** into a project-specific picture container, keep every original photo entirely outside ReportMaker and untouched, compress/convert HEIC to practical formats, edit photos non-destructively, and distinguish customer-visible technical annotations from private review comments. M4 currently normalizes exported images to PNG and M2 v1 serializes only photos referenced by report blocks, so this is an explicit schema and export architecture change, not a cosmetic UI tweak.

## Decision

1. **External source is sacrosanct.** Import reads selected files and creates **independent project-owned working copies**. Never rename, modify, move or delete external originals. No external path is required to reopen, share locally or export a project. Do not persist absolute original source paths in project metadata. Re-import from external originals is a separate explicit user action, never an automatic dependency.
2. **Project media container.** Add an explicit, visible project media library whose assets can exist before being placed in any module, can be browsed/renamed/removed by the user, and can be reused by multiple PhotoBlocks. Its declared members are first-class reachable project content, not hidden M2 v1 orphan photos. Implement a versioned, validated .rmproj schema migration with backward loading of valid v1 projects, strict validation of hashes/asset bounds, and safe rejection of unsupported future schemas. No silent upgrades that could destroy earlier files; create an explicit migration/rollback test matrix.
3. **HEIC and offline import.** Decode HEIC/HEIF locally through an evaluated Windows-bundled decoder (e.g. Pillow with pillow-heif); also accept supported JPEG/PNG and other explicitly tested types. Fail visibly without damaging the project when a codec, input or color profile is unsupported. Import uses safe size/pixel/decompression limits and avoids arbitrary network or browser handling.
4. **Opt-in format controls, balanced default.** For ordinary photos, default to JPEG at quality 88 and 2,500 pixels maximum long edge (never upscale), with user-selectable Compact (1,600 px, quality 75), High Quality (4,000 px, quality 94), and explicit alternative WebP/PNG as appropriate. Preserve transparency via an alpha-capable format or warn before flattening. Presets are starting points, not fixed output-byte promises. Offer preview/comparison of original and imported dimensions, sizes and visible quality; allow batch import and recompression of working copies without contacting the originals.
5. **Non-destructive composition.** Store immutable imported image bytes separately from editable geometric instructions: crop, rotate, flip, placement size/alignment, and independently addressable visible shapes/arrows/freehand/highlights/text/callouts. Keep positioning in normalized image coordinates so resize does not displace annotations; retain stable IDs and undo/redo. Multiple uses may reference one image asset, while each placement keeps independent layout and annotation state.
6. **Separate review comments.** Store optional internal anchored comment threads, replies and open/resolved state in an isolated project-only layer. Never render them in ordinary customer-facing DOCX/PDF, preview-for-customer, clipboard text or browser transfers. A future review-specific export requires a distinct, explicit opt-in action and conspicuous indication. Clearing/hiding a comment does not delete its retained conversation without explicit user deletion; deletion must remove it from newly saved project media.
7. **Export boundary.** DOCX and PDF render the same approved visual composition (image plus visible annotations), omit internal comments, preserve aspect ratio/fit without unwanted enlargement, and select efficient final encoding when compatible with the format. Do not force JPEG working copies through unconditional PNG conversion. Both exporters must remain local and atomic, keep project content unmodified, and handle unsupported image/layout combinations with a visible failure rather than omission.
8. **Multilingual-ready text.** Visible annotation text and internal comment messages must be modeled for later M5 language variants without collapsing original text, provenance or stale state. No hardcoded language enum. Preserve module-tree order and conclusions-last invariants.
9. **Privacy and portability.** Imported working copies and annotations live only in the locally saved .rmproj, never in the browser profile or GitHub. Strip GPS and nonessential camera-identifying metadata by default while preserving visual orientation and usable color rendering. No private samples in public tests or CI.
10. **Milestone order.** Implement as M4.5 before M5, independently reviewed on a feature branch. M0–M4 installed-Windows acceptance stays pending separately; no installer, release, merge or deployed build follows automatically from this decision.

## Non-goals

- Storing original, full-quality HEIC bytes inside the project by default.
- Lossless HEIC round trip, identical visual color across every device, or a guaranteed file compression ratio.
- Editable native Word drawing objects for each annotation (the customer DOCX initially embeds a composed image).
- Linking a project's availability to the original external photo location.
- Exposing private review notes to customer exports by default.

## Engineering verification

See ../M45_MEDIA_WORKSPACE.md. Test Windows HEIC decoder packaging and import failures, deterministic conversion, extreme dimensions/EXIF/alpha/ICC cases, project-owned unused media persistence (vs orphan rejection), multi-placement independence, undo/redo, v1 migration, save/reopen and missing-source portability, comments excluded from customer exports, source originals unchanged, and atomic failure handling. Synthetic images only.
