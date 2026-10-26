# ReportMaker — curated chat handoff
_Last curated: 2026-10-26. This is an intentional checkpoint; it is **not** auto-generated._

## Read first in every development or review chat
1. Read `AGENTS.md`, `ARCHITECTURE.md`, `ROADMAP.md`, this file, `docs/CHECKPOINTS.md`, `docs/ARCHITECTURE_MEMORY.md` and the ADRs.
2. Read `handoff/state.json` on **main** once populated by the automatic workflow.
3. Verify **live** GitHub branches, PR heads/bases, CI conclusions, release commit and outstanding issues. The generated JSON is a snapshot, not proof of current status.
4. State a specific branch, exact SHA, intended change, test plan, merge restriction and next checkpoint.
5. At each milestone or context handoff, update the curated records in a reviewable PR. Automation updates the mechanical snapshot only; it does **not** infer architecture decisions or report validation.

## Repository and current branch situation
- Repository: `kandyman991/ReportMaker` (PUBLIC).
- M0 core foundation **PR #1** is in final integration with main. The original foundation head was `4c6fff52bafd3f755888f46f321efb7b17b3e62e`; use the latest main and PR state for its merged status.
- M0 Windows installer/layout **PR #3 merged into PR #1's feature branch** at `4846e27ed45e2ebb53ca16f51e985883305b9ddd`; its original tested head was `b1cf60870b96f13706437567bad249a278e665b8`.
- The M0 executable is an **unsigned Windows preview**, not a functioning saved report editor.
- Stable, rolling **test prerelease**: https://github.com/kandyman991/ReportMaker/releases/tag/reportmaker-windows-m0 . Installer and SHA256 checksum are GitHub Release assets; no new Actions artifacts.
- Windows packaging and offline layout CI passed at the PR #3 revision listed above. User installed and launched M0 and demonstrated normal ChatGPT conversation in the embedded full-height website from Windows screenshots.
- **Not yet verified:** reinstall/uninstall edge cases, panel width persistence across app restarts, all resize/collapse interactions, login persistence and complete M0 acceptance. Do not confuse visual evidence with exhaustive tests.
- Once branches change, replace these historical SHA pointers with live GitHub evidence, not guesswork.

## Locked product requirements
- Native, self-contained Windows GUI; no Python/Git required on end-user PC.
- Customer → site → machine → serial number/contact/intervention history; report snapshots must not silently change when customer master data changes.
- Reports have unlimited reordered/nested modules with freely interleaved text, photos, tables and submodules. Dedicated Conclusions section always last.
- Local editable canonical project, later genuinely editable DOCX and optionally PDF. Word template import and visual design later.
- Open-ended BCP-47-style languages; original + translations + stale markers; UI locale independent.
- ChatGPT panel is **ordinary user-operated website only**; explicit manual copy/paste into editor. No OpenAI API, other paid AI provider, agents, automation, hidden scripting, web scraping or token extraction. Default-browser fallback.
- **Company CAD, private customer reports, photographs and credentials must never be placed in this PUBLIC repo or uploaded to AI/cloud services.** All tests use synthetic fixtures. CAD Inspector is intentionally **last** milestone, not part of M1.
- Use hosted Windows Actions runners (`windows-latest`), no user-owned self-hosted machine requirement.
- Direct rolling GitHub **prerelease** distribution; no `actions/upload-artifact`, no Actions cache storage. Keep developer/test releases separate from approved main builds in a later reviewable change.

## M1 entry
Start after reading the records and verifying M0 PR #1 and #3 are integrated into main. Design local SQLite customer/site/machine schema/migrations and editable GUI. A report must capture a local immutable customer/site/machine snapshot; support work without a master customer entry. Define backup and privacy boundaries before persistent data. Work on an isolated M1 feature branch/PR from the correct *live* main commit; do not overwrite continuity records. Use fabricated test customers, never production information.

## Completion/checkpoint procedure
Update this file and `docs/CHECKPOINTS.md` whenever work is ready for review or a chat handoff. Record exact commit, PR, CI/run, behavior tested, known gaps, next specific action, and rollback; add an ADR for any architectural deviation. Never merge a PR without user authorization. Review exact commit CI and verify GitHub state before claiming work complete.
