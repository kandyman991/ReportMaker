# Phase 2 — security and CI hygiene (incremental work)

**Baseline:** `main@d77102e9abc6b88bc6a21ba4ef604a62b0a8a996` after PR #123's approved merge `066b1b0a70f40d813edc32f247b107b1aedc13fa`. Issue #122 tracks the roadmap; [#105](https://github.com/kandyman991/ReportMaker/issues/105) and [#106](https://github.com/kandyman991/ReportMaker/issues/106) are **not closed by this initial PR**.

## First independently gated increment (this branch)

- New `.github/workflows/linux-application.yml` runs **real application tests** on Ubuntu 24.04, Python 3.12 and 3.14: Qt offscreen dependencies; source compile; native V2 smoke; **actual HTML QtWebEngine/QWebChannel smoke**; complete `unittest discover` with a non-thresholded coverage report. This is intentionally additional to Windows M0/M1, frozen Windows package checks and physical acceptance; it does **not** replace them.
- New checks use full action commit SHAs for checkout and Python setup (recorded tag resolution on 2026-10-31). The image label and pip ranges are **not immutable provenance**.
- Incremental Ruff enforcement targets only likely parser/undefined-name failures on all modules; stricter E4 applies to V2 and new tests. Broader pre-existing E7/E4 style warnings are not used to block the branch before triage.
- `pip-audit` examines the actual installed Linux Python 3.12 dependency environment. Findings are surfaced as a warning, **not a successful security clearance** or Windows lock. No vulnerability is waived merely because the workflow is green.
- Weekly Dependabot checks Python and GitHub Actions; update PRs still require independent review, test evidence, and release-control assessment. Dependabot is not a replacement for reviewing Qt WebEngine security advisories.

## Completion gates still outstanding (#105 / #106)

1. **Windows release builds:** pin supported runner image + Python x64 interpreter; generate and review a **complete transitive hash-verified platform lock** including desktop, pillow-heif, Qt/PySide6, PyInstaller and their dependencies. Add a lock-verification check before using it for release builds. Pin publication-critical action revisions in a dedicated release-safety change and review trigger conditions carefully: editing `windows-rc3.yml` may itself trigger a source-pinned release path. Do not touch immutable RC history.
2. **Release provenance:** record source/config commit SHAs, lock digest, OS/tool versions, Qt WebEngine/Chromium version, resolved manifest/SBOM, frozen inventory and installer SHA-256. Verify clean builds; **same locked dependencies are not a claim of bit-identical installers**.
3. **Qt security cadence:** review official PySide6/Qt security advisories and newer releases at least weekly alongside Dependabot. Record the installed Qt WebEngine runtime version and assess each update against HTML/local-origin isolation, smoke, and frozen install tests; do not silently change the Qt pin.
4. **Further maintainability:** assess version/README metadata, probes and asserts, stronger incremental lint/coverage metrics, license **only after owner approval**, and the separate non-destructive workflow consolidation. Windows 33-case physical acceptance (#96) remains separate.
5. **Review/CI:** exact-head Linux and Windows CI, security and data-integrity review, and explicit owner approval for each merge. No default UI switch, V1 deletion, release, history rewrite or branch deletion is part of this first increment.

## Local Phase 2 implementation verification (before hosted CI)

At the Legion isolated branch source with Python 3.14.4 / PySide6 6.12.0 and `QT_QPA_PLATFORM=offscreen`: compileall, native smoke and HTML Chromium/QWebChannel smoke passed. **649 tests passed in 181.075 s** under coverage; local report showed **74.8% aggregate Python source coverage**. This is *not* a trustworthy end-to-end GUI coverage percentage: out-of-process browser work and other subprocess imports can be missed (e.g. `v2/web_ui.py` showed zero coverage in this run). All four new Phase 2 contract tests and the selected Ruff checks passed. A separate local `pip-audit` of the Legion's installed environment reported no known vulnerabilities; the editable `reportmaker` package itself was skipped because it is not a PyPI package. Hosted Ubuntu 3.12/3.14 and Windows CI are separate gates.

## Local verification

Using an isolated virtual environment with desktop dependencies (not customer data):

```sh
export PYTHONPATH="$PWD/src" QT_QPA_PLATFORM=offscreen
export QTWEBENGINE_CHROMIUM_FLAGS="--disable-gpu"
python -m compileall -q src
python -m reportmaker.v2 --offline-self-test
python -m reportmaker.v2 --html --offline-self-test
python -m coverage run --source=reportmaker -m unittest discover -s tests -v
python -m coverage report --precision=1
ruff check --select E9,F63,F7,F82 src tests scripts
ruff check --select E4,E9,F63,F7,F82 src/reportmaker/v2 tests/test_cleanup_phase1_golden.py tests/test_phase2_ci_contract.py
```

Headless tests provide source/Chromium contract evidence, **not** an installed physical Windows GUI signoff.
