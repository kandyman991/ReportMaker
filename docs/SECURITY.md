# Security and privacy boundaries

For the **current, mandatory independent audit protocol** (untrusted image decoders, archive/XML, SQLite, browser privacy, dependencies/Qt WebEngine, release provenance and physical platform evidence), follow [AUDIT_PLAYBOOK.md](AUDIT_PLAYBOOK.md) and revisit open issues [#104](https://github.com/kandyman991/ReportMaker/issues/104), [#105](https://github.com/kandyman991/ReportMaker/issues/105), [#106](https://github.com/kandyman991/ReportMaker/issues/106). This page describes privacy boundaries, **not** a claim that all hardening is complete.

This is a public source repository. Never commit real intervention reports, customer/site/machine details, staff personal data, confidential photos, account passwords, API tokens, browser cookies/cache, profile folders or local SQLite data.

Browser panel is an untrusted remote website isolated from ReportMaker's report model. No DOM scraping, injected JavaScript, account/credential capture, browser network interception, automatic prompts, login bypass or hidden ChatGPT tooling. Only explicit user copy/paste; paste plain text and require review before using it in report output.

Any persistent browser session is managed by Qt WebEngine in a user-local profile. The app must not copy it into exported documents or project archives. Site compatibility and login are not guaranteed.

All changes must preserve safe photo and project paths (no traversal or external loads), attachment quotas, backup integrity, database migrations, data-retention boundaries and safe output encoding. Audit current behavior rather than trusting this historically foundational note; report both confirmed controls and any uncovered gaps.
