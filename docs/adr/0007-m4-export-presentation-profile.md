# ADR-0007 — M4 local export branding and bounded page layout

Status: **Proposed / implemented for review**, 2026-10-27. Applies to M4 completion PR; does not alter the persisted report model.

## Context

M4 entered `main` with editable DOCX and independent locally paginated PDF, but without company branding, repeating Word page numbers or stable image/caption geometry. These were never waived by the architecture. M6 owns arbitrary imported DOCX templates and advanced layout design; M5 owns localization. Native installed-Windows acceptance is separate.

## Decision

1. Branding is **optional, device-local export configuration**: company name, footer note and local company logo selected via a native Qt dialog. Store only textual settings and the path of the explicitly selected logo in the user's QSettings; no logo/image bytes, company styling or personal paths are written into `.rmproj`, the browser profile, GitHub or any project manifest. If the logo is missing, fail safely; do not silently substitute a different logo.
2. DOCX and PDF consume the **same immutable ExportStyle and prepared ExportPlan**, so module hierarchy/Contents, customer snapshot, source text, translations and mandatory Conclusions remain independent of styling. The no-style case stays backward compatible.
3. Output is ISO A4 portrait with 2.1-cm left/right and 3.0-cm top / 2.5-cm bottom body margins, separated from repeatable header/footer areas. Each page can carry an optional scaled company logo/name and a footer note plus current page number. In DOCX, PAGE and PAGEREF are updateable Word fields; page numbering is Word's responsibility after recalculation. In PDF, multipass ReportLab computes the Contents and page numbers locally. These are different pagination engines; identical page breaks are **not** promised.
4. Logos are decoded only from explicit bounded bytes (up to 2 MiB) through the same safe image-normalization pipeline as report media. Paragraph/brand text length and control characters are validated; no remote URL fetching. User assets remain local only.
5. Photos honor EXIF orientation via the existing export normalizer. Display at the natural 96-dpi size or scale down to a **15.6-cm width / 19.5-cm height box**, without upscaling. Word uses explicit image width/height and keep-with-next caption paragraph; PDF uses the same dimensions with KeepTogether where a caption is present. This is controlled inline anchoring rather than arbitrary floating drawing objects.
6. If content cannot fit (oversized nonsplittable table rows, caption, unsupported typography), reject the export with a visible error, preserve existing output atomically and retain the editable source. Future arbitrary Word object positioning remains M6. No legal/official company information is invented.

## Verification and remaining gates

Use entirely synthetic branded DOCX and PDF. Regression tests assert repeated header/footer text, live Word PAGE field, PDF page labels, logo embedding, bounds and aspect ratio, no unwanted image upscaling, no-clobber and source immutability. Hosted Windows Qt export smoke tests settings and missing logo paths. Before calling installed M0–M4 acceptance complete, verify real Word field updates, print/PDF page margins, logo transparency, long Italian text, DPI, and malformed/large real-world layout samples on an approved installed Windows build.

No installer, production customer reports or credentials may be published by this PR. No main merge without explicit approval.
