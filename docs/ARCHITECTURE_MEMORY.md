# Architecture memory / anti-regression log

2026-10-26 — Initial decisions:
- Chose modular, hierarchical report content instead of fixed form fields after comparing supervision and spiral-maintenance reports.
- Flexible blocks INSIDE each module; photos belong to their module and must move with it.
- Customer-first workflow and conclusion-last invariant.
- Open-ended report languages and independent UI localization.
- Windows is a mandatory runtime.
- Rejected paid AI API/agent integration in favor of user-driven normal website with manual copy/paste.
- Real sample reports are sensitive and must not be placed in this public repository.
- Existing Word templates and custom visual templates must coexist without promising lossless arbitrary DOCX-to-editor conversion.

Rejected architecture patterns:
- Fixed Title -> Description -> Photo Gallery module.
- Hardcoded {Italian, English} language enum.
- DOCX as the only editable canonical project representation.
- Programmatic ChatGPT login, scraping or automated use.
- Claiming embedded login or Windows installer compatibility without Windows testing.

For future changes add a dated entry with evidence, failed alternatives, ADR reference and regression test link.

2026-10-26 — Windows installer decision (ADR-0004): production users must not install Python, Git or use PowerShell. M0 distribution uses an unsigned, per-user Inno Setup installer wrapping an onedir PyInstaller build; GitHub Actions performs an offline Qt WebEngine smoke test. Actual ChatGPT login and installer acceptance remain human Windows tests.

2026-10-26 — M0 layout correction: Windows field test proved that QtWebEngineView loaded ChatGPT but only consumed a narrow portion of the right panel. Require explicit vertical stretch for browser, compact status, resizable/collapsible/maximizable panels, persistent layout preferences, and offline UI geometry regression checks. No browser automation or sensitive site data in tests.
