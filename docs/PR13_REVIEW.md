# Independent M4 review — PR #13 (2026-10-27)

**Parent:** PR #13 (`feature/m4-editable-docx-pdf-export`), reviewed at `77f12e217c612e03b75db1b66873fce1f55ee5dc`. Stacked corrections target the M4 feature branch, not main. No merge/release authorization.

## Reproduced findings

- **PR13-F01 HIGH:** PDF Summary used raw module text as ReportLab TOC Paragraph markup. `Valve <on> & motor` became `Valve & motor` in the generated PDF contents while the body showed the correct title. Reproduced independently with ReportLab + pypdf. Escape the label at the TOC markup boundary.
- **PR13-F02 MEDIUM:** PDF metadata table used Helvetica rather than the exporter-selected Unicode body font; a Cyrillic customer name appeared as boxes with Helvetica. Reuse the configured normal font for table cells, with synthetic Unicode regression. Font availability and complex-script shaping remain installed-Windows acceptance issues.
- **PR13-F03 MEDIUM:** An oversized single PDF table row causes ReportLab `LayoutError`, which the Qt handler does not catch (`LayoutError` is an `Exception`, not a `RuntimeError`). Convert the layout failure to `ExportError`; preserve previous output atomically.
- **PR13-F04 MEDIUM:** Direct export decoded bytes before enforcing the canonical project's 32 MiB per-photo limit. Check the payload size before opening the image.

Synthetic tests cover escaping, Unicode metadata where Unicode fonts exist, oversized asset bounds, and a tall table cell with no-clobber. All existing M4 Word/PDF/Qt and core tests are still required. Verify exact correction head Windows CI and review fixes independently before integration. M0–M4 installed-Windows acceptance, branded header/footer design and pagination polish remain pending. PR #13 and the correction PR must not be merged without user authorization.
