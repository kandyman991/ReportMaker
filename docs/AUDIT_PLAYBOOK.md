# ReportMaker — repeatable independent audit playbook

**Maintained from:** 2026-10-29. **Audience:** human auditors, Claude/ChatGPT/Codex, CI reviewers and release approvers.

This is the **mandatory audit starting point**, not a passing certificate or a fixed snapshot of current risk. Before each review, fetch live GitHub state and record the **exact SHA** being audited. Follow [AGENTS.md](../AGENTS.md), [ARCHITECTURE.md](../ARCHITECTURE.md), [docs/SECURITY.md](SECURITY.md), active ADRs and V2 contracts. **Do not reuse an earlier test count, coverage percentage, installed-binary hash or audit conclusion as current evidence.** Historical documents may contain superseded milestones.

## 0. Scope, evidence and outcome

At the start, record:

- Date (UTC), reviewer, independent/author relationship, base branch/ref and **40-character commit SHA**; commit dirtiness and any uncommitted changes. Audit `main`, active PR diff **and its exact head** separately as needed. Check open PRs/issues, prior audit findings and releases. Never quietly audit the wrong branch.
- Platform and architecture (Linux distribution/kernel, Windows build, x64), Python and pip versions, resolved `pip freeze` / `pip list`, Pillow / PySide6 / Qt WebEngine / PyInstaller / pillow-heif versions, and dependency-audit tool/database timestamp.
- Exact commands, exit codes, tests passed/failed/skipped, coverage *denominator* and report paths, CI check URLs/run IDs/head SHA, and where evidence is retained. Archive only sanitized, synthetic evidence; never upload customer reports/photos, identifying desktop data, profiles, credentials or proprietary CAD.
- Which checks were **performed**, **not performed**, **blocked**, or **not applicable**. A green workflow is not a substitute for physical UI acceptance; Linux native GUI tests are not Windows installer acceptance, and headless Qt tests are not visual observation.
- Findings with unique ID, severity, impacted file/line and dependency versions, preconditions/attack surface, reproduction using synthetic inputs, expected vs actual result, exploitability **confidence** (confirmed, plausible, not established), and linked GitHub issue/PR. Distinguish scanner advisory count from exploitable paths. Include negative results and verification limits.

**Severity / decision:** Critical or High security, data-loss or release-integrity findings block release until addressed or explicitly risk-accepted by the owner; Medium findings require a tracked owner/issue and a reasoned gate decision; Low/maintenance issues can be scheduled. Never downgrade a failure because tests pass. The review outcome must be `PASS`, `PASS WITH OPEN NONBLOCKERS`, `FAIL/BLOCKED`, or `NOT ASSESSED` **for each tested surface**, not a blanket “all secure”.

## 1. Dependency security and supply-chain integrity (P0/P1)

Audit both declared **constraints** and the **actual installed/frozen dependency graph**, including transitive packages. Re-run on the latest head and on the actual installer used for physical tests.

- Inspect `pyproject.toml`, `packaging/windows/requirements-build.txt`, all `.github/workflows/*.yml`, `packaging/`, Python build metadata and package locks. Check Python-version/platform compatibility, pinning strategy, hashes, stale packages, license constraints, resolution drift and isolation.
- Check vulnerabilities with a current advisory database (for example `python -m pip_audit` after installing `pip-audit` in a disposable virtualenv), and compare with upstream release notes/NVD/GHSA. Report tool version, timestamp, advisory IDs and **affected resolved versions**. `pip-audit` reports findings, not proof of reachability; assess attack paths where feasible.
- **Known investigation, not resolved as of 2026-10-29 baseline:** `Pillow>=10.4,<13` in `pyproject.toml` excludes Pillow 13 security fixes; examine [issue #104](https://github.com/kandyman991/ReportMaker/issues/104). Do not simply assume “39 exploitable vulnerabilities”. Confirm a currently patched major, supported `pillow-heif`, and both Windows/Linux installs and frozen apps before closing.
- Check all `Image.open(...)` and other untrusted decoder paths, especially `src/reportmaker/export.py` (three), `src/reportmaker/project_io.py` (one), `src/reportmaker/media_import.py` (one), plus any newly introduced call sites. **Format checks after `Image.open` do not prevent disallowed parsers being probed.** Require entry-point-specific `formats=[...]` allowlists and safe HEIF plugin registration. Preserve existing source-byte, pixel-count, metadata, decompression and ICC limits. Test JPEG, PNG, WEBP; BMP/HEIF where intentionally supported; unsupported file headers, truncated data, crafted headers, decompression bombs, huge ICC/EXIF, polyglots and malformed multi-frame inputs **with bounded synthetic fixtures**.
- Validate archive safety and import/export: no traversal, duplicate entries, symlink/extraction abuse, ZIP bombs, unsupported compression, stale or unreferenced assets, missing/hash-mismatched assets, oversized media, XML DTD/entity expansion and external resources. Verify fail-closed behavior **without mutating current session, originals or outputs**.
- Inspect GitHub Actions and publisher privileges: least-privilege tokens, guarded release triggers, SHA-pinned actions (not moving tags), source/config SHA, reproducible transitive dependencies, dependency hashes/SBOM, artifact provenance, secrets in logs, tag/asset immutability, unsigned-binary labeling and manual approval. Check embedded Qt WebEngine/Chromium version and **its update policy**; pinning PySide6 alone does not keep Chromium current. See [#105](https://github.com/kandyman991/ReportMaker/issues/105).
- Distinguish **source-pinned**, **dependency-reproducible** and **bit-for-bit reproducible** builds; do not call them equivalent. Compare exact installer/executable/SHA-256 to tests and reports. Rebuild and retest installers after any security dependency upgrade. Historical RC release artifacts remain immutable; existing binaries are not retroactively patched.

## 2. Core architecture, storage and data integrity (P0)

Validate the *current implementation* against the architecture contract and its V2 superseding requirements; record contract mismatches separately from unimplemented future features.

- One canonical ordered module/submodule tree; separate **derived** Editor / branch / Summary / TOC, never dual persisted navigators. Stable IDs, valid parent/child constraints, safe reorder/reparent/duplicate/outdent, cycle rejection, Conclusions last, correctly interleaved text/photos/tables/page breaks, multiple intervention types and manual customer/site/machine entry.
- Unsaved / unapplied rich-text or page edits must be clearly visible; Apply/Discard must be deliberate, lossless and atomic. Verify Save, Save As, close/reopen, undo/redo, cross-tab synchronization, drag/drop under pending drafts, and rollback on validation errors. Check [#98](https://github.com/kandyman991/ReportMaker/issues/98) and active [PR #97](https://github.com/kandyman991/ReportMaker/pull/97); these are **not** automatically closed by synthetic tests.
- `.rmproj` versions v1–v5 and future versions: schema validation, migration direction (V2 reading legacy does not imply V1 reads V2), byte-preserving original files, owned vs orphan media rules, stable translations/localization approvals and source provenance, detached customer snapshots, corrupt archives, failure atomicity, deterministic repeat save/reopen, and stable exports. Cover legacy input *and* new round trips.
- Media import and Gallery: never modify/move/delete the user’s source image; project-owned copies, ID/media ownership, independent non-destructive photo placements, offline re-open, predictable clipboard and Explorer input. No external data fetch or HTML interpretation from pasted content.
- SQLite and customer DB: migrations/idempotence, foreign keys, transaction/rollback, backup/restore integrity, concurrency, path containment, errors without partial writes, and privacy. Reports must keep a frozen customer snapshot independently of changes in the master database.
- DOCX/PDF/Word templates: zip/XML safety, atomic exports, actual editable Word output, valid pagination/TOC, consistent headings/tables/footnotes if supported, template fidelity/unsupported-element warnings, photo transforms, multilingual separation and privacy of internal review comments. Inspect representative files **in native Word/PDF viewers** as separate visual evidence; do not infer visual fidelity from unit tests.

## 3. Desktop GUI, accessibility and actual platform validation (P0/P1)

**Windows x64 remains primary; Linux is a supported secondary native-GUI test environment.** Test real rendered desktop interfaces in addition to unit/offscreen tests.

- Run the actual Linux native application where possible (including connected Lenovo Legion environment) and drive UI operations. Record distribution, Qt/display backend (Wayland/X11), screenshots (sanitized), click/keyboard paths, errors, logs and exact installed package versions. Linux testing does **not** validate Windows installers.
- On physical, **installed Windows x64**, run all **33** V2 RM-BE acceptance scenarios listed in [M7_ACCEPTANCE_MATRIX.json](v2/M7_ACCEPTANCE_MATRIX.json); track each scenario's ID, tested source/build/installer hash, steps, environment, actual behavior, redacted evidence, reviewer, status and linked bugs. **Pending/blocked/failing cannot be marked passed.** Windows-hosted offscreen smoke tests do not satisfy this contract. No V2 default switch or release promotion before the distinct M7.3–M7.6 gates.
- Explicitly verify the failures previously observed on physical Windows: blocking pending drafts ([#98](https://github.com/kandyman991/ReportMaker/issues/98)); pale, barely visible photo/annotation actions in dark mode ([#99](https://github.com/kandyman991/ReportMaker/issues/99)). Test light/dark and checked/disabled/hover/focus states, keyboard accessibility and contrast (target WCAG 4.5:1 for ordinary text where applicable), DPI scaling, resize, scroll/caret retention and long Unicode content.
- Test Modules, Editor, Gallery, photo tools, nested module creation, rich-text toolbar selection indicators, insertion, image import from Explorer, clipboard image/file list, drag/reparent, table editing, save/reopen and DOCX/PDF exports with actual input, not just window launch. Verify that changing text never silently disables unrelated actions.
- Qt WebEngine ChatGPT is an **ordinary user-controlled website** with network access; check privacy boundaries, local profile isolation, external browser fallback and manual copy/paste. No API keys, automated login, DOM scraping, interception, injections or customer data passed to the website. Do not test with real authenticated browser profiles in public CI. Browser functionality may need **manual** validation.
- Windows release chain: clean source, PyInstaller freeze, isolated V2 vs V1 install locations/IDs, install/relaunch/offline smoke/uninstall, no elevation expectation, installer+installed payload hash, rollback/fallback, no accidental publication. Hosted packaging checks ≠ physical user acceptance.

## 4. CI effectiveness, code health and documentation (P1/P2)

- Run the **complete discovered tests**, not only affected tests; record exact command and counts. Recommended starting commands in an isolated environment:

  ```sh
  python -m pip install -e ".[desktop]"
  python -m unittest discover -s tests -v
  python -m compileall -q src
  python -m pip freeze
  ```

  Use `QT_QPA_PLATFORM=offscreen` only for nonvisual Qt smoke tests; use a real display for visual acceptance. In CI, confirm exact PR head and relevant Windows 3.11/3.12 workflows, not just green checks on an earlier SHA. Investigate skipped/path-filtered workflows, flaky tests and missing negative cases. Audit Linux application-test coverage separately from Ubuntu documentation/workflow jobs.
- Run (or explicitly label missing) Ruff lint, type analysis, coverage of the actual `src` modules, dependency checks, installer smoke and performance/resource stress. The external 2026-10-29 Linux audit **reported** 457 tests and ~75% coverage, ~77 unused imports and oversized modules; these figures are historical claims pending independent reproduction. Qt GUI coverage can legitimately be undercounted by unit tests; add native/automation evidence instead of reporting fictitious coverage.
- Check unused imports, complex paths (especially `load_project`, `_write_pdf`), large `visual_editor.py` and V2 canvas modules, shipped `*_probe.py` test code and reliance on `assert` in production guards (Python `-O` removes asserts). Prioritize correctness over cosmetic mass cleanup.
- Ensure Windows and Linux test matrices, dependency audit, Dependabot, SHA-pinned Actions and meaningful coverage/lint gates exist or open issues for omissions. See [#106](https://github.com/kandyman991/ReportMaker/issues/106).
- Check README, roadmap/ADR links, `__version__` vs package version vs published release tags, license status and installer descriptions. No `LICENSE` was present in the 2026-10-29 baseline; **do not choose a license without the repository owner's approval**. Public source code does not itself confer reuse rights. Do not rewrite historic review logs to pretend they were current.

## 5. Audit report template (complete every review)

```text
AUDIT ID / DATE / REVIEWER:
TARGET: repo / branch / exact head SHA / base SHA / working-tree cleanliness:
SCOPE: full repository | PR diff | release binary | native Windows | native Linux:
PLATFORM: OS/build/arch, Python, Qt/WebEngine, Pillow, image plugins, build tools:
DEPENDENCIES: constraints / actual resolved versions / lock/hash state / audit db date:
TOOLS & COMMANDS: commands, versions, exits, observed test counts/coverage:
CI: workflow/run URLs, conclusion and SHA; skipped vs executed checks:
PHYSICAL GUI: platform, exact installer+exe hashes, 33 IDs, evidence storage and results:
ATTACK SURFACES CHECKED: images / archive / DOCX/XML / SQLite / WebEngine / release:
FINDINGS: F-ID | severity | path/line/version | repro | impact | confidence | issue:
KNOWN OPEN FINDINGS: confirm / retest / superseded / blocked / N/A (with evidence):
UNTESTED GAPS / ENVIRONMENT LIMITATIONS:
OVERALL GATE: PASS | PASS WITH OPEN NONBLOCKERS | FAIL/BLOCKED | NOT ASSESSED:
NEXT ACTION: named owner, branch/PR, remediation verification, release restrictions:
```

## 6. Baseline and mandatory revisit list — 2026-10-29

This baseline was assembled from a third-party Linux review **and selective independent GitHub source inspection**, **not** from a freshly executed complete audit. Initial source baseline: `main` at `f3e9e5e661f49ba5d3bacef6202d866aa3bdc621`. Before reporting status, compare with live main, PRs and issues.

| ID | 2026-10-29 observation | Source confidence | Track |
| --- | --- | --- | --- |
| A-01 | `Pillow>=10.4,<13` excludes Pillow 13.0.0 fixes; validate currently installed runtime and advisories | Independently inspected declared cap; reachability/advisory count unverified | [#104](https://github.com/kandyman991/ReportMaker/issues/104) |
| A-02 | Five `Image.open` call sites lack upfront parser format allowlists | Independently inspected source | [#104](https://github.com/kandyman991/ReportMaker/issues/104) |
| A-03 | Source SHA pinning but floating transitive release dependencies; action tags are movable; Qt WebEngine update policy needs evidence | Independently inspected selected workflows | [#105](https://github.com/kandyman991/ReportMaker/issues/105) |
| A-04 | README/version metadata stale; root LICENSE/Dependabot configuration absent; no Linux application test job | Independently inspected root and workflows | [#106](https://github.com/kandyman991/ReportMaker/issues/106) |
| A-05 | Full Linux test suite 457 passed; about 75% coverage; ~77 unused imports; significant oversized functions and probe code | **External audit report only; not independently reproduced** | [#106](https://github.com/kandyman991/ReportMaker/issues/106) |
| A-06 | M7.3 installed Windows 33-case acceptance outstanding; observed draft blocking/contrast findings are not closed by CI | PR/issue records; real physical retests required | [PR #97](https://github.com/kandyman991/ReportMaker/pull/97), [#98](https://github.com/kandyman991/ReportMaker/issues/98), [#99](https://github.com/kandyman991/ReportMaker/issues/99) |

**Next audit instruction:** revisit **every** baseline entry; mark fixed only with an exact corrective SHA, test evidence and, where applicable, rebuilt + physically validated installer. Search for *new* issues too. Evaluate active PRs separately from merged `main`. Keep V1 fallback and V2 release authorization distinct. Update the findings ledger/references through a reviewed documentation PR rather than silently deleting failed items.
