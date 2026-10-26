# ADR-0001 — Windows-first, structured modular reports
Status: Accepted | Date: 2026-10-26

Decision: PySide6 Windows-first app; core model not bound to Qt/Word/SQLite. Reports contain ordered nested modules with freely interleaved text, photos, tables, and children. Conclusions are separate and always last. Canonical projects remain editable independently of Word output.

Rationale: Two real intervention-report examples exhibit different workflows and paragraph/photo sequences. A fixed template would force manual Word reformatting.

Consequences: Require stable IDs, order preservation, localization of text/captions, asset ownership, structured storage and output adapters. M0 shell is a compatibility experiment, not the complete editor.
