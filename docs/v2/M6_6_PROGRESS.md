# M6.6 — Precise Page Editor and Word/template fidelity

**Status:** Started in [draft PR #88](https://github.com/kandyman991/ReportMaker/pull/88) on isolated branch `feature/v2-m6-6-page-word-fidelity`; **not independently accepted or merged**. Baseline is post-M6.5 `main` at `e2b19d0a5fea6db6d211d1f306c657969dcc177f`. Follow-up to [issue #86](https://github.com/kandyman991/ReportMaker/issues/86) and the [formal M6 contract](M6_SUBMILESTONES.md).

## Acceptance and non-negotiable contracts

- Keep the report in the one canonical `ReportSession`/ordered hierarchy; no parallel page or TOC model, no schema changes. A Word template is an untrusted **layout profile**, never a second report or imported DOCX body.
- Editor's continuous paper is an **editable schematic** over the same canonical blocks. It must fit narrow app panels, grow to contain text/tables and never show nested scrollbars; paper geometry is not a promise of Word pagination.
- Exported DOCX must be genuinely editable. Word table widths and basic text styles must respect printable margins; the PDF writer and QtPdf proof remain the authority for **PDF** page count, never for Word page count.
- Preserve Word-specific capabilities/limits visibly. Complex Word templates with headers of multiple columns, shapes, floating objects, section-specific styles, text boxes and installed font differences are not copied verbatim. Never silently claim unsupported fidelity.
- Keep multilingual translations, customer snapshots, photos/marks, browser-only ChatGPT, V1 compatibility, atomic overwrite and the private-data boundary intact. No M6.7 checkpoint or installer promotion.

## M6.6-A implemented: paper metrics and fixed Word table layout

1. `NaturalPagePaper` computes the full physical-paper outline and **all four editable-page margins from one cm-to-pixel scale**; it scales at narrow widths without the former hard-coded 500-pixel minimum or independently clamped margins. The outer page remains continuous; only real DOCX/PDF export determines pagination.
2. The Page Editor adopts the selected Word profile's **base normal and heading font families/sizes**, preserving the source rich runs in the canonical model. Advanced inline typography must be controlled in the Branch formatting toolbar until further M6.6 validation.
3. `NaturalPageTable` recomputes its natural height as cell text changes, retaining no inner scrolling.
4. Editable DOCX Report Information and content tables have **fixed, explicit column/grid/cell widths** derived from selected printable width, aligned with the PDF table sizing policy. `w:tblLayout` and `w:tblW` no longer rely on Word autofit to keep data within imported margins. We do **not** assume the first user table row is a header.
5. Added `tests/test_v2_m66_fidelity.py`: Word OOXML grid and margin verification, multi-page PDF with wide/long tables, narrow Qt paper scaling, table growth, canonical text-preservation font checks and a native QWidget-style-method guard. Local isolated **431 tests / 170 subtests passed** on the initial implementation; targeted **5 tests / 2 subtests passed** after the native style-method guard. Hosted Windows Python 3.11/3.12 dedicated `v2-m66-fidelity.yml` plus the broader V2 regression workflow are mandatory checks on this draft.

## M6.6 remaining before milestone acceptance

- Verify richer paragraph-run styling, list/line spacing, text and heading flow, page-break behavior and printable overflow in exported Word on a *native installed Windows + Microsoft Word* environment; document Word field-update/pagination differences. Add reproducible XML checks for supported constructs and fail-closed paths.
- Expand synthetic stress gates for deeper/large reports, embedded photos/marks, oversized table rows, narrowly constrained templates, multilingual fonts, preview/proof invalidation and failure atomicity. Template import intentionally remains allowlisted; unsupported objects require warnings instead of guessed reconstruction.
- Independently review this entire milestone branch for architecture, layout, data integrity and regression impact, fix findings, and verify exact-final-HEAD GitHub-hosted Windows CI before any proposed merge.
- **No release or M6.7 promotion**. The user has authorized starting development, not merging this new PR.

## M6.6-B implemented: explicit list/paragraph pagination semantics (continuing PR #88)

1. Word no longer delegates report lists to the machine's default `List Number` style. `_WordListNumbering` builds **bounded, pure OOXML numbering definitions** for decimal, lower-alpha, upper-alpha and bullets. A new `w:num` starts whenever a plain paragraph, list kind, indent or structural block interrupts a run, while matching lists across adjacent canonical paragraph blocks keep the same sequence. Existing report text stays editable, and numbering is **not** stored separately in the project.
2. `_rich_leading` calculates an explicit, positive point-based line pitch for both DOCX and PDF from supported normal/heading typography and the largest run font size in that line. Word and ReportLab use the same supported line-height ratio instead of mismatched Word-relative vs PDF absolute values. Large styled text cannot silently inherit an insufficient base line pitch.
3. Exported Word module headings and rich heading blocks use `keep_with_next` to reduce orphan headings. Rich heading run size now derives from the selected template's `heading_size_pt`, not the previously hardcoded 16pt. **All nine supported Word Heading levels** now honor the selected template heading font and progressively sized headings, rather than using defaults for nested modules. Pagebreaks, editable tables, photos and captions are preserved.
4. Extended `tests/test_v2_m66_fidelity.py` with **OOXML numbering format and restart/continuity assertions**, line pitch/font/heading flow checks, annotated image and manual-break DOCX/PDF export, 18-level nested multilingual synthetic report stress, and narrow-page oversized-table rollback. The independent PDF list tests and safe Word import regressions also run in dedicated hosted Windows M6.6 CI.

**Local verification of M6.6-B code/tests:** complete isolated offscreen/Linux regression suite **436 tests passed, 170 subtests passed**; targeted M6.6 tests **10 passed, 2 subtests passed**; combined rich-font and PDF lists **20 passed, 19 subtests passed**. GitHub-hosted Windows matrix on the new exact head remains pending until the new PR push is independently checked.

**Fidelity boundary:** We verify explicit OOXML semantics and local PDF pagination, but Word can reflow due to fonts, printer, table-cell splitting, section settings or field updates. The Qt Page Editor remains a continuous, viewport-responsive schematic. Complex Word graphics/layout and native installed-Windows Microsoft Word visual checks remain unverified; do not declare M6.6 accepted or merge this draft without a separate review and authorization.

## M6.6-C: complex Word compatibility warnings, multi-script font OOXML and native Word verification entry point

- Added bounded, deterministic unsupported-layout diagnostics to the safe Word importer, including multi-column sections, page borders, page numbering restart/format, line numbering, mirrored/right-to-left gutters, body/header/footer floating objects, nonreconstructible rich paragraph styles and theme fonts. First-page header variants are now detected across **all** sections, not just the first, preventing false assurances when later sections differ. The first-section-only projection and security checks remain intact.
- Exported Word font faces now set `w:rFonts` `ascii`, `hAnsi`, `eastAsia` and `cs` for explicit Normal, headings and rich runs. This improves source DOCX fidelity for multilingual reports but cannot ensure fonts/glyphs are actually installed in Microsoft Word. PDF proof UI explicitly discloses per-run font-family substitutions.
- New synthetic complex-DOCX tests verify import warnings, section-only behavior, unchanged source bytes, non-leakage of source body/header tables, v1-compatible immutable `.rmtemplate` save/load and malformed untrusted column metadata. Added exported PAGE/PAGEREF/bookmark/updateFields preflight checks and multi-script font XML assertions.
- Added a **Windows-only manual native Microsoft Word pagination verifier** `scripts/verify_word_pagination.ps1`. It opens a generated DOCX in read-only Word COM with macros and automatic links disabled, updates fields in memory, uses native Word repagination/statistics, prints a privacy-preserving JSON summary and never saves. Windows CI checks the script's syntax but **cannot execute Word**. See [M6.6 native Word acceptance procedure](M6_6_WORD_ACCEPTANCE.md) and its separate visual checklist.

**Local verification of M6.6-C:** complete offscreen/Linux suite **440 tests and 179 subtests passed**, 16 inherited deprecation warnings. The scoped M6.6 suite passes **12 tests and 2 subtests**; complex template importer tests pass **17 tests and 13 subtests**. Hosted exact-head Windows CI is pending verification after push.

**Acceptance boundary:** The script has not been run on an installed licensed Windows Microsoft Word instance. Native page count, field updates, font substitution, UI layout and visual fidelity **remain unverified**. Complete full regression testing and exact-new-head hosted Windows checks, independent review and explicit merge approval before declaring M6.6 accepted.
