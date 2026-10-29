# M7.2 — Legacy project migration and data integrity

**Status:** Independent review corrections prepared on the M7.2 branch; fresh exact-head Windows CI and final merge are still gated.
**Parent:** M7 issue #90, M7.2 issue #94.
**Base:** Post-M7.1 `main` `b84c6cb16973b35af8ed7e10ca038812e15a5b80` (includes merged PR #92, `83ef81ab798c100f521a84c745796e895d411206`).

## First implementation
- Use production project writer/reader and one canonical `ReportSession`; no parallel migration model.
- Synthetic fixture matrix covers ZIP schema versions 1–5, their version-specific rich/visual/localization-ledger records, v1–v4 mandatory Save As migration, exact preservation of source bytes, stable nested IDs, customer snapshot, intervention categories, translations/stale provenance, placed photo assets and explicit Gallery library media.
- Malformed/future records, mismatched media metadata and cross-version fields fail closed without replacing an active report. Failed upgrade cannot change a valid existing target or original source.
- Dedicated hosted x64 Windows Python 3.11/3.12 workflow runs these tests plus M2 project, M6.5 localization and V2 lifecycle suites. Existing M0 and V1 Windows CI remain intact.

## Not yet accepted
Exact-head Windows CI, independent security/architecture/migration review and corrections are still required. V1 is preserved as an installed fallback, but an old V1 binary is **not** claimed to open V2 schema v5. Installed-PC acceptance, 33 RM-BE features, Word/browser and release are separate M7 milestones. No installer upload or default promotion. No M7.2 merge without explicit user authorization.

## Independent review findings and corrective coverage (2026-10-29)
- **F01 — migration integrity:** the initial v1–v5 matrix only exercised empty/default rich formatting. Fixtures now include non-default rich spans and paragraph alignment and verify v1–v3 defaults vs v4–v5 preservation.
- **F02 — localization integrity:** the initial test only checked whether a v5 ledger existed. It now checks the actual approved translation and source SHA-256 provenance.
- **F03 — archive/session security:** initial tests did not explicitly cover duplicate ZIP members, traversal entries, unsupported compression or direct rejection by a live session. Added negative cases with byte-for-byte source preservation and no session replacement.
- **Initial head `3e2ac2d071a2f3869ad6f4beaba6957f831203e1` CI:** M0, M1, continuity, M7.2 hosted Windows Python 3.11/3.12, and M7.1 frozen/installed/uninstalled Windows preflight passed (workflow runs 40902786794, 40902786639, 40902786784, 40902787315, 40902786864). M6.5/M6.6 conditional checks skipped by their path rules.
- **Next gate:** verify all applicable workflows on the corrected PR head, record that exact head in PR review, then merge using the user's 2026-10-29 M7.2 authorization only if checks remain green. Hosted CI is not physical installed-Windows acceptance.
