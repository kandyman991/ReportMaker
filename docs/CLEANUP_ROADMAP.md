# ReportMaker repository consolidation roadmap

**Date:** 2026-10-31  
**Status:** Proposed, implementation started as isolated Phase 1 PR; not release or default-promotion approval.  
**Baseline:** `main` at `8b52776984f6190fa2a0f657af9376f4f1cc5d5f` (PR #121 HTML Studio merged; handoff-only commit at tip).  
**Scope:** Windows-primary, Linux-secondary ReportMaker V1 / native V2 / HTML Studio.  
**Related work:** #116 (safe V1 retirement), #105 (release supply chain), #106 (quality), #96 (physical Windows acceptance), #98/#99 (physical V2 retests), PR #120 (native canvas), PR #21 (historical RC).

## Objective and architectural direction

Consolidate the application without a rewrite. The **HTML Studio is the preferred future primary UI**, conditional on parity and installed-Windows acceptance. Keep native V2 as a functioning fallback until its unique capabilities have been ported or explicitly accepted as specialist tools. Keep V1 rollback until a separately approved release migration. Both frontends must eventually share a framework-neutral application controller using the *existing* canonical model, session, commands, persistence, media and exporters. Do **not** add a second report schema, table of contents, export engine, translation store, or browser-to-report shortcut.

Non-negotiable safeguards: single hierarchy supplies both module tree and TOC; stable IDs, report-local customer/site/machine snapshots, manual references, multi-select intervention types, dedicated conclusions, arbitrary ordered nested blocks, original text plus translatable per-language copies and staleness, atomic `.rmproj` saves/backward compatibility, embedded media/reference integrity, undo/redo and staged draft protections, private photo review comments excluded from customer export. Keep the remote ChatGPT website isolated from the local report bridge. Never ship customer data or browser credentials.

## Phase plan

| Phase | Priority | Delivery | Exit criterion |
| --- | --- | --- | --- |
| **1. Baseline and protection** | P0 | Audited inventory; V1/native V2/HTML capability matrix with **verified, partial, missing, unknown** markings; baseline reproducible commands for tests and sample `.rmproj`, multilingual DOCX/PDF and image round-trips | SHA, environment, test commands/results, fixture plan, data safety matrix, ownership boundaries and untested native Windows gates documented; non-destructive checks added as appropriate |
| **2. Security and CI hygiene** | P0 | #105 transitive build locks/provenance/action pins; #106 supported Linux application CI, security scans and incremental lint | Windows quality/release matrix preserved; dependency update policy and change review in place |
| **3. Branch and PR triage** | P1 | Reconcile #120 against post-#121 main; make an explicit disposition of draft #21; inventory 81 branches by merged/unmerged/unique contributions before archive/delete | No lost distinct work; immutable releases/tags protected; owner approves deletion |
| **4. Shared application controller** | P1 | Extract session/commands/dialog orchestration from `v2/app.py` into neutral services; HTML and native consume same service, not a hidden `V2MainWindow` | Both launch and independently pass project, draft, customer and export tests; no change in `.rmproj` schema |
| **5. Safe V1 retirement** | P1 | Execute #116 parity/compatibility/packaging/entrypoint stages; port or explicitly waive V1-only features (notably template visual editing) | Actual frozen V2 module inventory; native Windows install/upgrade/coexist/uninstall; backups and rollback; 33/33 physical acceptance and release authorization before destructive removal |
| **6. Modularize oversized code** | P2 | Split `v2/branch/canvas.py`, `v2/app.py`, `v2/web_ui.py` and HTML `studio.js` by responsibilities without behavior change | Small independently reviewed changes; focus, accessibility, editor, import, Undo and visual fidelity preserved |
| **7. Consolidate historical infrastructure** | P2 | Reduce duplicated CI, obsolete installer workflows/probes, stale docs and historical branches while keeping evidence and historical immutable assets | No weakened CI/release gates and all retained docs/paths accurate |

**Sequence:** Phase 1 must start first; Phase 2 can proceed after baselines are trustworthy. Phases 3–7 are independently gated; do not merge or delete opportunistically. Pause or split any phase if material user-visible behavior would change.

## Phase 1 work contract

1. Freeze a read-only source baseline, including SHA, file counts, project/package metadata, launchers, CI workflows, active PRs and exact environment.
2. Inventory direct/indirect imports (including dynamic imports and PyInstaller analysis); record proven V2-shared services separately from legacy V1-only UI and probes. Never infer deadness from filenames alone.
3. Prepare a capability-parity matrix across V1, native V2 and HTML Studio with evidence links and explicit **unverified** states. File parity gaps rather than assuming implementation from claims or UI controls.
4. Establish deterministic synthetic golden inputs: legacy and current `.rmproj`, assets/annotations, translations/staleness, customer snapshots, DOCX/PDF, and template examples. Do not commit customer documents or brittle platform-variant full PDF binaries; prefer structural assertions and recorded fingerprints with explained normalization.
5. Execute and log `python -m unittest discover -s tests -v`, `python -m compileall -q src`, native and HTML offline smoke, and focused storage/translation/export tests on Linux. Record real outcomes and any skipped tests; hosted Windows and physical Windows must be separately evidenced.
6. Add only non-destructive regression assertions to protect shared dependency ownership, file/source boundaries, and the snapshot fixtures. Open a reviewable PR from a separate branch. Do not merge without user authorization.

## Review and release gates for each implementation phase

- Independent architecture/security/data-integrity review following `docs/AUDIT_PLAYBOOK.md`; resolve findings and repeat exact-head checks.
- Relevant complete Python tests, Qt Chromium/QWebChannel smoke, native V2 smoke and Linux GUI evidence on the Legion.
- For packaging or behavior changes: Windows frozen archive inventory, full installed-payload SHA check, offline smoke, uninstall, and real installed-Windows acceptance. Hosted CI, Linux offscreen and source-only testing do **not** imply physical acceptance.
- Preserve V1 Windows fallback, all existing user data/DB profiles/templates and a tested rollback plan until *separate* explicit owner approval.
- No releases, branch deletions, schema migration or default UI promotion as a side-effect of documentation/cleanup.

## Phase status

- **Phase 1:** Completed and merged via owner-authorized PR #123 (`066b1b0`), with exact-head independent review and 645 source regressions passed. See `docs/cleanup/PHASE1_BASELINE.md` and `docs/cleanup/FEATURE_PARITY.md`; physical Windows acceptance remains separate.
- **Phase 2:** Started in an independently gated CI/security branch; see `docs/cleanup/PHASE2_SECURITY_CI.md`. Windows dependency locking and release provenance (#105) remain outstanding.
- **Phases 3–7:** Not started under this roadmap. Existing work/issues are prerequisites, not evidence of completion.
