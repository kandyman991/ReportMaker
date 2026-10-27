# M4.5 — Picture Manager, local HEIC conversion and editable image layers

Status: **User-approved feature requirements with a separate M4.5.1 implementation PR under review**. PR #16 records the design; stacked draft PR #17 implements the first media container, offline HEIC conversion and basic Qt Pictures UI. M4.5.2–.4 (annotation layers, private comment editing and composed annotation exports) remain unimplemented. Installed-Windows acceptance and installer approval remain pending. Binding architecture: [ADR-0008](adr/0008-m45-media-workspace.md).

## M4.5.1 implementation checkpoint (draft PR #17)

- New version-2 `.rmproj` metadata stores explicit picture-library members **with byte-verified format and dimensions**, while preserving logical photo reuse and the report hierarchy. Old v1 projects open but **Save As to a different file** is mandatory for conversion; normal in-place Save is blocked, leaving the original v1 archive intact for rollback. Legacy orphan v1 assets continue to be discarded; v2 undeclared hidden assets fail closed.
- Local offline HEIC/HEIF decoding via desktop-packaged `pillow-heif`; standard input image types also convert into independent project JPEG/PNG/WebP working copies with safe bounds, selected image-quality presets and metadata removal. No original external file is overwritten or required when reopening.
- Native **Pictures** dialog allows up to 64 photos per batch, preset/format choice, **per-image original-vs-optimized visual comparison and explicit approval**, library preview, insertion into a module, and removal of unused library images. Staging performs the conversion once, and only approved exact bytes are committed. Per-placement photo annotations, review pins and a crop editor remain future gates.
- DOCX/PDF exporter no longer inflates every JPEG into PNG; it continues to recompress/normalize output locally and atomically. Full annotated-image export remains pending.
- Synthetic unit tests cover v1 migration and rollback, v2 strict image metadata and asset membership, undo restoration without hidden media on disk, source preservation, single-pass approved staging, ICC failure, portable library persistence, reuse, alpha, invalid input and HEIC, plus offline Qt Pictures/comparison smoke regression. The correction is proposed in [PR #18](https://github.com/kandyman991/ReportMaker/pull/18), with detailed ledger at [PR17_REVIEW.md](PR17_REVIEW.md). Hosted Windows CI and independent review must be checked at PR #18's exact final head before any merge.

## User workflow

1. In the native ReportMaker GUI, open **Pictures** to browse the project's own media container, including photos not yet placed in a report.
2. Import one or many pictures from an external folder. Supported types are determined by a verified, installed offline decoder, with **HEIC/HEIF first-class input**. Import **copies and converts** bytes into the project. External originals are **never changed, renamed, moved or deleted**.
3. Choose conversion preset/format, preview source vs optimized copy (dimensions, estimated and actual size, detail and transparency), then accept import. Failure/cancel leaves the project and source files intact. Keep profile defaults device-local and explicit per-import overrides.
4. Organize, rename and delete project media assets; reuse one stored asset across multiple report modules. Pictures remain independently available inside the saved project even when not yet inserted in a module. Report module edits move photo placements with their parent modules.
5. Select/double-click a placed photo to crop, rotate, straighten, flip, scale, align, or annotate. Add moveable arrows, lines, boxes, circles, highlights, freehand drawings, numbered callouts and editable text. Each edit supports undo/redo, cancel/apply and separate object selection.
6. Toggle a **private review comments** layer containing anchored pins/areas, threads, replies and open/resolved state. Keep it separate from exported visible annotations. Internal comments are retained (including resolved threads) until explicitly deleted; hiding is not deleting.
7. Preview the customer output and export DOCX/PDF with the rendered photo plus visible annotations and captions. **Never include internal review pins/threads in ordinary customer exports**. Editing the .rmproj remains canonical; export does not flatten the project's stored layers.
8. Reopen or copy the .rmproj to a different offline PC without its original HEIC/photos. Edit placements, comment threads and annotations and re-export from contained working assets. Reimport a source original only when user explicitly selects a new file.

## Supported formats and defaults

| Preset | Maximum long edge | JPEG encoder quality | Intent |
| --- | ---: | ---: | --- |
| Compact | 1600 px | 75 | Keep many photos in a small project |
| **Balanced (default)** | **2500 px** | **88** | General technical intervention reports |
| High quality | 4000 px | 94 | Small technical detail and print |
| Manual | User-specified within validated limits | User-specified | Select resolution/quality/format explicitly |

- HEIC/HEIF input is decoded locally, then normally stored as **JPEG**, with **WebP** optional when supported by the installed encoder/renderers and **PNG** preferred for transparency, line art and screenshots. JPEG cannot preserve alpha: require a supported alpha-capable destination or explicit informed user choice to flatten.
- Respect EXIF orientation before resizing, preserve colors reasonably via deliberate ICC/color handling or explicit warnings, remove GPS and other nonessential identifying metadata by default. The original's raw metadata stays outside the project.
- Do not enlarge small sources, promise a fixed percentage file-size saving, degrade quality through repeated lossy conversions silently, or auto-fetch photos from websites.
- The working copy can be recompressed from an available higher-quality *project-owned* representation when available, or the user may explicitly reimport an external original. Do not pretend to recover image detail lost on prior lossy conversion.
- Include strict input byte/pixel/decompression/time/memory bounds and controlled errors. HEIC Windows codec licensing, installer inclusion, offline operation and practical performance must be independently checked, not assumed.

## Canonical model and migration

- Separate **MediaAsset** (unique project-owned imported bytes, format and verified metadata), **PhotoPlacement** (existing image block reference, geometry/crop/transforms and per-use visible annotation objects), and **ReviewThread** (private anchored comments, reply/status/history). Do not store an independent copy of the photo for every placement.
- All per-image positions and crop/annotation anchors use stable normalized coordinates relative to the correct, EXIF-oriented image space. Reframing, rotation, duplication and reordering must never silently orphan arrows or review comments.
- This changes M2's legacy **only reachable PhotoBlock assets serialized** rule: a declared media library member is intentionally retained even when unused in report modules. Unknown/unlisted and otherwise unreferenced archive data remain forbidden. Deleting an asset used by placements requires explicit resolution of references, not silent broken links.
- Introduce a new, versioned, validated project manifest/schema with compatibility logic for existing .rmproj v1 projects. Open and migrate valid v1 data without losing photos, captions, translations, module hierarchy or conclusions. Older application binaries may not read the new format; require visible backup/migration notice and safe rollback.
- Project save/load must remain transactional, bounded and verifiable (hashes, lengths, types, allowlisted ZIP members), portable across Windows PCs and independent of source folder paths. The canonical model, media store and export pipeline remain separate from browser profile and device-local export branding.
- Annotation labels and internal comment text must support future arbitrary language tags and M5 translations, preserving the original and review/staleness provenance; UI localization remains independent.
- Ordinary customer exports use only visible annotations; private comments are not serialized into DOCX/PDF document metadata, alt text, captions or incidental rendered resources.

## Development phases and verifiable gates

### M4.5.1 — Project picture container + HEIC import
- Batch import, file filters, local decoder packaging, image bounds and error/cancel behavior.
- Conversion presets with actual comparison, no-upscale, alpha/EXIF/ICC and metadata privacy.
- Explicit media library membership and versioned .rmproj migration/portability, with unit fixtures for v1 and newly packaged projects.

### M4.5.2 — Image formatting and visible annotations
- Crop/rotation/flip/straighten, layout width/height/alignment and previews.
- Arrows, shapes, highlighting, text/callouts and layered non-destructive edits with undo/redo.
- Independent placement state for reused shared assets and stable anchor coordinates on rotate/resize.

### M4.5.3 — Private internal review comments
- Separate pins/threads/replies/status controls, show/hide and explicit deletion.
- Strict proof that comments never enter customer preview, DOCX/PDF, external AI browser or clipboard handoff.

### M4.5.4 — Export integration and regression tests
- Render customer-visible layers into DOCX and PDF from the same composition model; maintain caption pairing, page margins and aspect ratio.
- Avoid mandatory PNG normalization for JPEG photos; preserve reasonable fidelity and bounded export size.
- Word/PDF synthetic content tests, missing/invalid photo failure/no-clobber, persistence/portability, high-DPI/offline Qt smoke and actual installed Windows validation.

## Required synthetic regression matrix

- Original external HEIC/JPEG hashes unchanged after successful import, cancel, edit and project export; originals never copied into .rmproj by default.
- Batch import generates portable project-contained working copies and bounded project size (within declared limits), including source removed after import.
- Valid v1 .rmproj opens, produces identical report structure and photos, migrates safely and preserves original saved file on failure.
- New unplaced library images survive Save/Open, while unknown orphan ZIP assets are rejected/pruned per migration policy.
- Two placements share one image asset but can have different crops, technical arrows and review comments without cross-talk.
- Tiny, large, portrait, panorama, alpha, damaged or oversized sources; EXIF-rotated and ICC-tagged synthetic test images.
- M4 outline and conclusions invariants, user-approved source text, comment visibility separation and M5-ready text structures survive edit/save/undo/export.
- DOCX/PDF show rendered visual annotations and no private comments, including metadata checks and full multi-page layout tests.
- Exact final-head Windows CI is distinct from installed-PC acceptance. No release or user-company data is involved.

## Pre-existing acceptance boundary

M0–M4 code is merged; their **consolidated installed-Windows acceptance is deferred by the user** until they are at their computer. M4.5 planning does not mark that checklist complete or authorize a new installer.
