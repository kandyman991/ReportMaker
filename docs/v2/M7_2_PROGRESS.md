# M7.2 — Legacy project migration and data integrity

**Status:** Initial implementation in independent draft branch `feature/v2-m7-2-migration-acceptance`.
**Parent:** M7 issue #90, M7.2 issue #94.
**Base:** Post-M7.1 `main` `b84c6cb16973b35af8ed7e10ca038812e15a5b80` (includes merged PR #92, `83ef81ab798c100f521a84c745796e895d411206`).

## First implementation
- Use production project writer/reader and one canonical `ReportSession`; no parallel migration model.
- Synthetic fixture matrix covers ZIP schema versions 1–5, their version-specific rich/visual/localization-ledger records, v1–v4 mandatory Save As migration, exact preservation of source bytes, stable nested IDs, customer snapshot, intervention categories, translations/stale provenance, placed photo assets and explicit Gallery library media.
- Malformed/future records, mismatched media metadata and cross-version fields fail closed without replacing an active report. Failed upgrade cannot change a valid existing target or original source.
- Dedicated hosted x64 Windows Python 3.11/3.12 workflow runs these tests plus M2 project, M6.5 localization and V2 lifecycle suites. Existing M0 and V1 Windows CI remain intact.

## Not yet accepted
Exact-head Windows CI, independent security/architecture/migration review and corrections are still required. V1 is preserved as an installed fallback, but an old V1 binary is **not** claimed to open V2 schema v5. Installed-PC acceptance, 33 RM-BE features, Word/browser and release are separate M7 milestones. No installer upload or default promotion. No M7.2 merge without explicit user authorization.
