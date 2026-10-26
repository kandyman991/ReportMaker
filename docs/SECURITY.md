# Security and privacy boundaries

This is a public source repository. Never commit real intervention reports, customer/site/machine details, staff personal data, confidential photos, account passwords, API tokens, browser cookies/cache, profile folders or local SQLite data.

Browser panel is an untrusted remote website isolated from ReportMaker's report model. No DOM scraping, injected JavaScript, account/credential capture, browser network interception, automatic prompts, login bypass or hidden ChatGPT tooling. Only explicit user copy/paste; paste plain text and require review before using it in report output.

Any persistent browser session is managed by Qt WebEngine in a user-local profile. The app must not copy it into exported documents or project archives. Site compatibility and login are not guaranteed.

Later stages must address safe photo paths (no traversal or external loads), attachment quotas, backup integrity, database migration, data retention and output encoding. This foundational skeleton is not yet hardened for production data.
