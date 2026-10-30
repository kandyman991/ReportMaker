# ReportMaker

Windows-first modular technical report editor and document generator; Linux is a supported secondary native-GUI testing platform.

## Current development status

The older M0–M6 implementation and M7.1/M7.2 source milestones are integrated into `main`; **V2's 33-case native installed-Windows M7.3 acceptance is still pending**, with work in [PR #97](https://github.com/kandyman991/ReportMaker/pull/97). M7.4–M7.6 and any V2 default/release promotion have distinct gates. The Windows **V1 fallback remains separate**. Check live PR/issue/CI state before relying on this dated description (2026-10-29). Green hosted CI or successful install/launch is **not** proof of interactive acceptance.

**Auditors and AI reviewers: start with [the independent audit playbook](docs/AUDIT_PLAYBOOK.md), then [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [security boundaries](docs/SECURITY.md), [V2 acceptance matrix](docs/v2/M7_ACCEPTANCE_MATRIX.json) and the live GitHub PR/issues.** The playbook specifies security, dependency and release supply-chain checks, data-integrity regressions, physical Windows / native Linux tests, and the evidence required to call a finding fixed. Open security follow-ups: [#104](https://github.com/kandyman991/ReportMaker/issues/104), [#105](https://github.com/kandyman991/ReportMaker/issues/105), [#106](https://github.com/kandyman991/ReportMaker/issues/106).

## Product workflow

Select a customer/site/machine from local data or supply a manual reference; build reports from independently editable, arbitrarily nested and reordered modules containing text, images, tables and submodules; finish with Conclusions. The module tree and Summary/TOC derive from one canonical hierarchy. Reports preserve source text and per-language translation records. `.rmproj` is the editable local project; DOCX/PDF are derived exports. Template import and design have feature and fidelity limits, so review the relevant acceptance documents before promising full Word compatibility.

The optional ChatGPT panel is an ordinary **user-controlled website**, **not** an API or automated agent integration. Users manually copy approved text between the website and report editor. Embedded authentication may fail; an external-browser fallback is available. The site can use the network; report data and browser profiles must remain isolated.

## Windows builds and acceptance

The [historical M0 Windows prerelease](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0) is a **legacy reference**, not the current V2 release. V1 release candidates and V2 test-only builds have independent channels, installer identities and acceptance criteria. Do not download a historical M0 build expecting today's editor, and do not assume an unsigned QA installer is an approved release.

A reviewed V2 test installer must pass hosted freeze/install/offline/uninstall gates **and then** separate native installed-Windows x64 manual tests, including all 33 cases in `docs/v2/M7_ACCEPTANCE_MATRIX.json`. Installer/build SHA-256, review outcome and real observations are required. Never publish or promote V2 solely because a CI workflow succeeded. See [Windows distribution](docs/WINDOWS_DISTRIBUTION.md), [V2 requirements](docs/v2/BRANCH_EDITOR_REQUIREMENTS.md), and the [audit playbook](docs/AUDIT_PLAYBOOK.md).

## Developer setup and tests

Supported Python range and dependencies are declared in `pyproject.toml`. Use a disposable virtual environment for development and verification:

```sh
python -m pip install -e ".[desktop]"
python -m unittest discover -s tests -v
python -m compileall -q src
```

Run `python -m reportmaker` for the legacy V1 GUI, or **`python -m reportmaker.v2` for the V2 Branch Editor GUI**. `python -m reportmaker.v2 --offline-self-test` provides a synthetic nonvisual startup check; it does **not** replace inspecting and interacting with the actual window. V1 and V2 remain separate installation/packaging tracks. For Linux, record the actual distribution, Qt display backend and installed dependencies; GUI observations must be made on a real rendered display, not inferred from offscreen tests. **Windows** packaging/real-PC acceptance cannot be completed on Linux.

A security scanner or third-party test count does not certify the installed application. Follow `docs/AUDIT_PLAYBOOK.md` for a repeatable evidence-based audit.

## Project privacy and governance

This repository is **PUBLIC**. Never commit real customer data, production photos/reports, proprietary CAD, credentials, screenshots of authenticated sessions, cookies or browser profiles. Use synthetic fixtures. Follow `AGENTS.md`, architecture contracts and review gates; changes must be reviewed and pass exact-head checks. There is no owner-approved `LICENSE` file in the 2026-10-29 baseline; do not assume public code is open-source licensed.

### HTML studio candidate (PR #121)

Launch with `python -m reportmaker.v2 --html`. The existing native V2 workspace remains the default and is explicitly selectable with `--native`; V1 still uses `python -m reportmaker`. HTML promotion requires installed Windows acceptance. See [validation and rollback](docs/v2/PR121_HTML_VALIDATION.md).
