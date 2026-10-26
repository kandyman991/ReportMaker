# ReportMaker handoff — 2026-10-26

Repository: kandyman991/ReportMaker. Windows-first modular technical service report desktop application.
Architecture agreed from two real intervention reports (not stored in this public repository):
- Customer database, site and machine selection; intervention start/end, ticket, technicians.
- Arbitrary nested/reordered modules; inside each, freely ordered text/photos/tables/submodules.
- Separate always-final Conclusions. Save projects; generate editable Word and optional PDF.
- BCP-47-style addable languages; Italian/English are examples, not limits.
- Visual template designer and existing DOCX template import.
- Optional normal ChatGPT website via resizable browser panel; user signs in, manually copies text. No API, agent, web automation or extra per-token billing attributable to ReportMaker. Authentication within embedded Qt WebEngine is unverified; default-browser fallback required.
- Privacy: customer data stays local, not committed to the public repository.

Current stage: M0. Read AGENTS.md, ARCHITECTURE.md, ROADMAP.md, docs/M0_ACCEPTANCE.md and ADRs. Main began at 05782d4e0f16a21813710eaf490dbe7f488bbb40 (initial README). Foundation changes are proposed in feature/m0-foundation and must be reviewed before merge.

Next: Validate browser shell on a real Windows PC, document whether embedded ChatGPT login works, confirm no APIs/scripts/credential capture, then design M1 storage. Do not claim installer or end-to-end Word export exists.
