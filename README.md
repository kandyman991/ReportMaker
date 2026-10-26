# ReportMaker

Windows-first modular technical report editor and Word document generator.

## Status
M0 foundation is merged. M1 customer/site/machine SQLite storage and GUI are under review in [draft PR #5](https://github.com/kandyman991/ReportMaker/pull/5). This is NOT yet a production report generator: full report/project save/reopen, Word output and template editing remain unimplemented.

## Product workflow
Select an existing customer/site/machine, choose intervention dates, compose arbitrarily ordered and nested modules containing text/photos/tables, finish with conclusions, and export editable DOCX (with optional PDF). Every translatable text element can carry any BCP-47-style language tag; export may be monolingual or multilingual. Templates may be imported from Word or designed visually.

The optional ChatGPT panel is a normal website, **not** an AI integration. No application API key, paid token service, site automation, credential collection, or automatic conversation access. The user manually copies approved text to an editable report block. Embedded authentication might not work; an external-browser fallback is always available.

## Windows installation (no Python or Git needed)
**Developer preview, not a completed report generator.**
A successful Windows installer build publishes an unsigned, rolling **GitHub prerelease** (the same scheme as RoadPilot Graph Studio), without consuming GitHub Actions artifact storage. Open [ReportMaker Windows M0 prerelease](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0), download `ReportMaker-M0-Setup.exe` and optionally verify `SHA256SUMS.txt`, then run the installer. It creates a Start Menu shortcut and an optional desktop shortcut. Installation is per-user and should not require administrator rights. There is no API/key integration.

The installer is currently **unsigned** and may be flagged by Windows SmartScreen; use only trusted, reviewed builds from this repository and do not disable Windows security protections. A successful CI build does not prove live ChatGPT sign-in or full interactive desktop functionality. Keep the external-browser fallback.

See `docs/WINDOWS_DISTRIBUTION.md` for precise build and validation instructions.

## Developer-only: run the M0 Windows shell
On Windows 11 or supported Windows 10 x64 with Python 3.11+:
1. Create and activate a virtual environment.
2. Run: python -m pip install -e ".[desktop]"
3. Run: python -m reportmaker

The M0 shell contains a mock report module list, a scratchpad editor, clipboard-paste action, a full-height ChatGPT web panel and external-browser fallback. In the M1 branch, the **Customers / Sites / Machines** toolbar action opens the local SQLite editor (see `docs/M1_CUSTOMER_DATABASE.md`). Drag pane dividers to resize, use the top Modules/Editor/ChatGPT toggles to collapse/reopen, maximize a pane from its header, and use Reset layout to restore defaults. Pane widths and visibility are saved locally between launches; scratchpad text is NOT saved. It is strictly a browser usability/Windows UI probe; saving report projects and DOCX generation arrive in later milestones.

## Verify the architecture/tests
Run: python -m unittest discover -s tests -v

Consult ARCHITECTURE.md, AGENTS.md, docs/M0_ACCEPTANCE.md and ROADMAP.md before changing functionality.

## Privacy
Repository is PUBLIC. Do not commit real customer information, production photos, private reports, credentials, screenshots of logged-in pages, cookies, or browser profiles. The original reference documents remain outside this repository.
