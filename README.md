# ReportMaker

Windows-first modular technical report editor and Word document generator.

## Status
M0 foundation prototype — NOT a production report generator. The document, customer database, editing, and export milestones remain unimplemented.

## Product workflow
Select an existing customer/site/machine, choose intervention dates, compose arbitrarily ordered and nested modules containing text/photos/tables, finish with conclusions, and export editable DOCX (with optional PDF). Every translatable text element can carry any BCP-47-style language tag; export may be monolingual or multilingual. Templates may be imported from Word or designed visually.

The optional ChatGPT panel is a normal website, **not** an AI integration. No application API key, paid token service, site automation, credential collection, or automatic conversation access. The user manually copies approved text to an editable report block. Embedded authentication might not work; an external-browser fallback is always available.

## Windows installation (no Python or Git needed)
**Developer preview, not a completed report generator.**
Build artifacts from the Windows packaging workflow produce a downloadable `ReportMaker-M0-Setup.exe` installer. On the corresponding GitHub Actions run, open **Artifacts**, download `ReportMaker-Windows-M0-Setup-<commit>`, extract the ZIP and run the enclosed installer. It creates a Start Menu shortcut and an optional desktop shortcut. Installation is per-user and should not require administrator rights. There is no API/key integration.

The installer is currently **unsigned** and may be flagged by Windows SmartScreen; use only trusted, reviewed builds from this repository and do not disable Windows security protections. A successful CI build does not prove live ChatGPT sign-in or full interactive desktop functionality. Keep the external-browser fallback.

See `docs/WINDOWS_DISTRIBUTION.md` for precise build and validation instructions.

## Developer-only: run the M0 Windows shell
On Windows 11 or supported Windows 10 x64 with Python 3.11+:
1. Create and activate a virtual environment.
2. Run: python -m pip install -e ".[desktop]"
3. Run: python -m reportmaker

The M0 shell contains a mock report module list, a scratchpad editor, clipboard-paste action, ChatGPT web panel and external-browser fallback. It is strictly a browser usability/Windows UI probe; saving report projects and DOCX generation arrive in later milestones.

## Verify the architecture/tests
Run: python -m unittest discover -s tests -v

Consult ARCHITECTURE.md, AGENTS.md, docs/M0_ACCEPTANCE.md and ROADMAP.md before changing functionality.

## Privacy
Repository is PUBLIC. Do not commit real customer information, production photos, private reports, credentials, screenshots of logged-in pages, cookies, or browser profiles. The original reference documents remain outside this repository.
