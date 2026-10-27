# ReportMaker

Windows-first modular technical report editor and Word document generator.

## Status
M0–M4 and M4.5.1–M4.5.2 are merged into main, including the local SQLite customer database, modular report editor, editable DOCX/PDF exports, HEIC project Picture Manager and non-destructive image annotations. This is a Windows **release candidate for installed acceptance**, not a production acceptance claim. Export of a visually edited PhotoBlock is deliberately blocked until M4.5.4; M4.5.3 internal review comments, M5 languages and M6 templates remain future milestones.

## Product workflow
Select an existing customer/site/machine, choose intervention dates, compose arbitrarily ordered and nested modules containing text/photos/tables, finish with conclusions, and export editable DOCX (with optional PDF). Every translatable text element can carry any BCP-47-style language tag; export may be monolingual or multilingual. Templates may be imported from Word or designed visually.

The optional ChatGPT panel is a normal website, **not** an AI integration. No application API key, paid token service, site automation, credential collection, or automatic conversation access. The user manually copies approved text to an editable report block. Embedded authentication might not work; an external-browser fallback is always available.

## Windows installation (no Python or Git required)

**Current acceptance candidate:** [ReportMaker v0.5.0 RC](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-v0.5.0-rc.1). Download `ReportMaker-0.5.0-Setup.exe` and `SHA256SUMS.txt` **only after the candidate's Windows build has passed and the assets appear**. Verify SHA-256, then install on Windows 10/11 x64. Existing M0 installs upgrade in the same location; back up projects/customer databases to a private location first. The installer is unsigned; do not disable Windows security tools or bypass organizational policy.

**Historical fallback only:** [ReportMaker M0 prototype](https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0). It is not the current report editor, and the old binary cannot open newer `.rmproj` v2/v3 projects.

The release candidate is built from pinned merged source SHA `1e092c175857bfd5969202201b2595604bb27b2f` and must be tested on a real Windows PC before production promotion. GitHub Actions hosted Windows checks do **not** count as interactive installed acceptance. See [native acceptance and release gates](docs/RELEASE_CANDIDATE_ACCEPTANCE.md) and the [M0–M4 checklist](docs/WINDOWS_ACCEPTANCE_M0_M4.md). Production promotion must reuse the tested installer bytes and checksum exactly, with known limitations documented.

## Developer-only: run the Windows desktop application
On Windows 11 or supported Windows 10 x64 with Python 3.11+:
1. Create and activate a virtual environment.
2. Run: python -m pip install -e ".[desktop]"
3. Run: python -m reportmaker

On current merged main, the native editor includes the canonical module hierarchy, report details, project file Open/Save, Picture Manager, DOCX/PDF export for unedited pictures and local browser panel. Use synthetic data for acceptance. Internal picture comments and annotated Word/PDF export are pending; do not misrepresent them as available. See docs/M45_VISUAL_EDITOR.md and docs/M4_EXPORT.md.

## Verify the architecture/tests
Run: python -m unittest discover -s tests -v

Consult ARCHITECTURE.md, AGENTS.md, docs/M0_ACCEPTANCE.md and ROADMAP.md before changing functionality.

## Privacy
Repository is PUBLIC. Do not commit real customer information, production photos, private reports, credentials, screenshots of logged-in pages, cookies, or browser profiles. The original reference documents remain outside this repository.
