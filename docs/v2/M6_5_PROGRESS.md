# M6.5 — Metadata and generated-label localization implementation checkpoint

**Date:** 2026-10-29. **PR:** [#84](https://github.com/kandyman991/ReportMaker/pull/84), stacked on frozen M6.1–M6.4 [PR #83](https://github.com/kandyman991/ReportMaker/pull/83).

## What is implemented

- Pure `v2/metadata_locale.py` defines allowlisted, stable semantic keys for every currently generated report heading, report-info label, intervention type and page prefix; two user-authored source keys cover `other_intervention_detail` and branded footer text. All labels are assigned a fixed **English source language**, independently of `Report.primary_language`.
- `LocaleApproval` is a frozen, reviewable entry binding semantic key, target language, text and SHA-256 of key/source-language/source-text. The resolver validates arbitrary language tags and rejects invalid keys, case-variant duplicate language entries, bad digests, overlong text and blank translations. An unchanged entry becomes stale if its source field or catalog text changes.
- `visible_metadata_keys` derives necessary generated labels from canonical report fields, not a second report tree; `resolve_many` supports all-or-nothing validation before customer output.
- 14 synthetic tests in `tests/test_v2_m65_catalog.py` cover English catalog independence, Unicode/arbitrary tags, stale source edits, source-language relabeling, blank/missing/outdated translation refusal, unknown/deduplicated keys, footer prose, source digest identity, canonical preservation and unchanged **v4 project save/load**.
- Added the stacked PR head branch to hosted Windows Python 3.11/3.12 `v2-inline.yml` and included the new suite in compileall and regression steps.

## Explicitly NOT implemented or approved yet

- **No v5 schema changes.** `project_io.VERSION` remains 4, with unchanged v1–v4 loading and V1 compatibility. `LocaleApproval` is not persisted and is not wired into `ReportProject` yet.
- **No changes to production DOCX/PDF, Preview, PDF proof, ZIP output or manual Report Information UI.** They must not be reported as fully localized; existing English/source boilerplate remains a documented limitation.
- The [proposed ADR](ADR_M6_5_METADATA_LOCALIZATION.md) now explicitly closes its v4-rich-text migration, source-English-label and branded-footer review gaps. It **still requires independent architecture approval** before v5 persistence, migration or visible export changes.
- M6.6 page/Word fidelity and M6.7 Checkpoint C remain outside this PR. No merge, release or native installed-Windows acceptance authorized.

## Next acceptance gate

Independently review the proposed ADR and exact v5 wire format, including version thresholds for v3 visual state and v4 rich formatting. Once approved, develop **only M6.5** ledger persistence, validated canonical commands, manual UI and strict DOCX/PDF/Preview/PDF-proof/ZIP integration with full backward migration and Windows CI. Retarget PR #84 onto main only after PR #83 is explicitly approved and merged. No automatic translation or browser integration.
