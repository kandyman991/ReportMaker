# ReportMaker architecture contract — v1 (2026-10-26)

## User-facing workflow (binding requirements)
1. Search/select customer from a local customer database. Customer may own multiple sites and each site multiple machines. Record an immutable snapshot of customer/site/machine details in each saved report.
2. Enter intervention start/end dates, optional ticket, technician(s) and report language configuration.
3. Add, delete, duplicate, nest and reorder any number of intervention modules.
4. Each module has a localized title and arbitrary ordered content blocks: paragraphs, headings, photos with local asset references and optional captions, tables, manual page breaks, and nested modules. Blocks can alternate freely; no mandatory photo gallery position.
5. A dedicated, final Conclusions section supports free text and optional recommendations. It must appear after all intervention modules in export.
6. Save/edit/reopen reports as structured local projects independently from exported documents.
7. Export genuine editable DOCX; PDF is an optional derived output. Page layout, automatic numbering, headers, footers, tables of contents and company branding are export/template concerns. Blocks need not correspond to pages.
8. Import existing DOCX templates in a high-fidelity fillable mode. Visual editing of supported elements must be separate; arbitrary Word drawing objects need not be losslessly converted to editable blocks.
9. User can add any language identifier and choose output languages and presentation (separate files / text pairs / language sections). Each editable translatable element has separate original and translations; update of source flags outdated translations for review; no silent overwrites. UI localization is independent.

## Browser-only AI writing workflow (binding requirements)
User-controlled ordinary website at https://chatgpt.com inside a resizable Qt WebEngine panel, subject to site compatibility. Users manually log in; site account/plan determines its limits. Manual copy-and-paste is the only planned transfer mechanism. No AI SDK, cloud AI API, provider tokens, hidden agents, DOM injection, credential processing, automated messaging, scraping or account automation. If blocked by authentication/browser compatibility, provide external default browser fallback and keep report editor fully usable. No bypass attempts.

## Architecture layers
- Pure core: typed report/project structure, validation, migration/versioning, serialization.
- Storage: local SQLite for customer/report indexes; content and photo assets in controlled per-project storage; backup/migration semantics specified before persistence.
- UI: native Windows PySide6 editor, module tree, arbitrary block editor, properties, preview, independent embedded browser panel.
- Rendering: document-layout-independent export abstraction; DOCX writer, PDF converter, Word template adapter.
- Browser: isolated, non-privileged profile and Qt WebEngine view; no report/customer data injected into website.
- Testing: pure-model invariant tests in cross-platform CI; Windows packaging and interactive browser/login compatibility tested separately on a real machine.

## Initial implementation boundaries
M0 provides model types and a Windows shell/browser compatibility probe; it is not a production customer database, final editor or document exporter. Architecture remains binding across later milestones.

## Data model invariants
- Report contains customer_id plus intervention date range with start <= end; reference snapshot planned for M1.
- Primary writing language and requested language codes are validated as nonempty tags; never fixed to Italian/English.
- Modules contain ordered block arrays, with optional nested module blocks and localized text/captions. IDs are stable.
- Conclusions are stored separately and are last in logical and export order.
- Asset references must not become absolute public URLs or leak into browser profiles.
- Translation provenance/stale state must survive round trips once persistence is implemented.

See docs/adr and docs/ARCHITECTURE_MEMORY.md for decisions and rationale.
