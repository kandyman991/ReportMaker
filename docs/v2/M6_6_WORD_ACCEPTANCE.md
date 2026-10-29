# M6.6 — Word template and native pagination acceptance contract

**Status (2026-10-29):** A synthetic desktop Microsoft Word 16.0 pagination/field-update check **passed**, and the user reports that its exported A4 DOCX and matching PDF looked OK. This is an M6.6 **single-fixture native acceptance result**, not a claim of pixel-identical rendering, all-layout visual certification, a Windows installed-app acceptance, or permission for V2 release/installer promotion. The user separately authorized merging PR #88 after review and findings were corrected.

## Explicit template compatibility

`.docx` / `.dotx` input is validated, bounded and projected into an independent `.rmtemplate` layout profile. It is **not** opened as an editable report or reproduced pixel-for-pixel. The following supported properties are copied from the first section only: page width/height, four margins, header/footer distances, static header/footer text, the first safe inline header logo, and Normal/Heading 1 base font names/sizes. The generated report uses these with canonical report content, the derived module summary, Word PAGE/PAGEREF fields and fixed printable-width tables.

Unsupported Word features are either rejected for package safety or disclosed as import warnings. Warnings now explicitly cover multiple sections, different first-page and odd/even headers, header/footer tables/artwork, extra header logos, text boxes and floating artwork, multi-column layouts, page borders, mirrored/right-to-left gutters, page-number restart/format, source line numbering, paragraph spacing/tabs/colors and theme-dependent fonts. A warning **does not** mean a Word source element has been reconstructed. The report's body content, underlying OOXML style graph, rich templates, mail-merge data, external relationships, macros, and active content are never imported.

**Typography limitations:** Word DOCX retains editable formatting and explicit Latin/East Asian/complex-script face attributes for a named font, but actual glyph coverage and font substitutions depend on installed Microsoft Word fonts. PDF is rendered separately using an available local Unicode font; per-run Word font families may be substituted in PDF. Lists, line pitch, page geometry and table widths have supported shared semantics, not pixel-identical cross-renderer metrics. Content can reflow differently in Word and PDF.

## Native Word synthetic sample result — 2026-10-29

The user downloaded the **synthetic-only** QA report `pr88-synthetic-a4.docx`
and comparison `pr88-synthetic-a4.pdf` from isolated
`qa/pr88-word-acceptance`, generated from reviewed PR #88 code commit
`3e4127518e8befe75fecea45cd41b972efdbb066`.
The test sample contains fictional report text and programmatically drawn
media; **no customer content** is present in the evidence.

The user reports that the DOCX/PDF **visual comparison looked OK**.
They then executed the reviewed, read-only Windows PowerShell verifier on
the synthetic DOCX and supplied the following machine-independent result:

```json
{
  "check": "native_microsoft_word_read_only_pagination",
  "word_version": "16.0",
  "pages_before_field_update": 3,
  "pages_after_field_update": 3,
  "page_reference_fields": 4,
  "unresolved_page_references": 0,
  "expected_word_pages": 0,
  "pdf_pages_for_information_only": 0,
  "word_pdf_pages_equal": null
}
```

**Result: PASS** for native field update and page-reference resolution on
this synthetic 3-page A4 fixture (4 PAGEREF fields; none unresolved).
Word version `16.0` was recorded; Word build, Windows edition, fonts and
DPI were not supplied. `expected_word_pages: 0` explicitly indicates
that a saved Word baseline was **not** enforced; the script verified the
actual page count and field resolutions but did not independently assert
an expected page count. `word_pdf_pages_equal: null` is informational,
**not** evidence that the two formats have the same pagination.
Additional narrow-page, large-table, complex-template, deep multilingual
and installed V2 UI/manual printer testing remain outside this sample.
Do not label those release/Checkpoint C gates complete.

## Native installed-Windows + Microsoft Word pagination gate

Use **only a synthetic ReportMaker-generated DOCX** in a trusted local development environment with desktop Microsoft Word installed. No source/customer documents or reports need to leave the user's computer. The verifier itself does not call a network service, but Office installation, licensing and telemetry have separate network behavior; use a trusted controlled environment. GitHub-hosted CI typically does **not** include licensed Microsoft Word and cannot certify this gate.

From an ordinary PowerShell shell at the repository root:

```powershell
powershell.exe -NoProfile -File .\scripts\verify_word_pagination.ps1 -DocxPath "C:\SyntheticReports\sample.docx"
```

For a reproducible Word-to-Word baseline after approving a particular Word version and template:

```powershell
powershell.exe -NoProfile -File .\scripts\verify_word_pagination.ps1 -DocxPath "C:\SyntheticReports\sample.docx" -ExpectedWordPages 5 -PdfPagesForComparison 4
```

The optional `-ExpectedWordPages` means an **approved Microsoft Word baseline**, never the PDF page count. `-PdfPagesForComparison` is informational; a difference does not fail the check. The verifier opens DOCX **read-only**, disables macros and automatic link updates, updates body/header/footer fields **in memory only**, repaginates using the installed Word engine, reports Word version/pages and unresolved PAGEREF fields, and closes without saving. The JSON result deliberately omits customer content, source paths and document titles. The script fails explicitly if Word COM is unavailable, pages are invalid, page references stay unresolved or the optional Word baseline mismatches. **It must not be mistaken for evidence of execution until an actual installed-Windows result is supplied.**

The dedicated Windows M6.6 GitHub workflow parses the PowerShell script for syntax errors; it does **not** execute Microsoft Word COM.

### Visual checklist after native script succeeds

1. Visually inspect page margins/headers/logo and the first, middle and last pages in Word Print Layout (including page breaks and the Conclusions section).
2. Refresh fields and confirm all Word TOC PAGEREF entries resolve to the expected body headings; no `?` placeholders or incorrect page labels remain.
3. Compare a synthetic A4 report, a narrow custom-page layout, a long multilevel report with large tables and image captions, and a multilingual/font-substitution report against the PDF proof **without expecting identical page counts**. Record both page counts and explain differences.
4. Inspect 9-level heading typography, decimal/Latin-alphabetic list restart/continuity, rich span sizing, color/highlight, line pitch, fixed table widths, row splitting and photo/caption flow. Word's glyph substitutions, printing margins and table-cell expansion are native acceptance questions.
5. Test import of a **synthetic** complex source template and confirm unsupported features produce clear warnings, that source bytes remain unchanged, and that its private body/table data never appears in the generated report.
6. Record Word version/build, Windows edition, DPI/zoom, installed fonts, PR commit SHA, the synthetic template profile and pass/fail observations in a **private/local** acceptance log. Do not commit customer documents, screenshots or machine-identifying paths to the public repository.

**Merge boundary:** Local OOXML/PDF tests and hosted CI can establish bounded structural fidelity; they cannot establish the above native Word acceptance. Independent PR review and explicit merge authorization remain separate. M6.7 Checkpoint C, V2-default promotion and installer release are not covered here.
