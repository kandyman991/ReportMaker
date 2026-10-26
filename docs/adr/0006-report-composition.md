# ADR-0006 — Report information and single-source module navigation
Status: Accepted requirements, implementation pending | Date: 2026-10-26

## Context
The user supplied a handwritten layout with a Report Information header (creation date, title, start/end, ticket, intervention type, personnel), followed by a Summary and hierarchical titled Modules. They explicitly clarified that a report may have **multiple intervention types**, that the Summary and editor module tree must never be maintained separately, and that the customer can be selected from the database **or entered manually**.

## Decision
Adopt the report information fields and composition contract documented in `docs/REPORT_COMPOSITION_CONTRACT.md`. Intervention types are a multi-selection collection with an optional "Other" specification. Both the editor tree and automatically generated contents are projections of the one canonical, ordered, arbitrarily nested module structure. Customer/site/machine references permit a missing master key, and saved report snapshots retain the customer facts independent of later master changes. Manual customer details are not added to the master without an explicit operation.

## Rationale
A second, separately editable contents list would drift after moving/renaming modules. A mandatory customer foreign key would block one-off site work. A single-choice intervention category would lose the real meaning of mixed supervision and maintenance activities.

## Consequences and tests
M1 covers optional customer linkage/snapshots; M2–M5 provide metadata persistence, derived views, export pagination and localization. Add regression tests for multiple selected types, manual references, unchanged historical snapshots and identical tree/summary order after deep nest/move/rename. Keep Conclusions last and preserve module media and translations. Neither this ADR nor the contract asserts that these features are already implemented.
