# PR #31 independent technical and security review (2026-10-27)

Target: [PR #31](https://github.com/kandyman991/ReportMaker/pull/31)
Initial exact reviewed head: `f98936f3a5b31f0ab68d758725afd119830ec20c`.
Base: PR #25 `feature/word-style-rich-editor` at `6f233cc8eff40de97c2bbeaa50439078c783c824`.

## Findings and independent corrections

- **F01 — Medium / security: OOXML remote-reference validation could be bypassed at inspection.** The relationships filter rejected `TargetMode="External"` but did not reject absolute URI targets declared with missing or spoofed `TargetMode`; it also accepted unknown modes. A malformed relationship could pass the intended local-only preflight (even if later rejected by python-docx). Reject non-Internal target modes, URI schemes, protocol-relative and backslash paths; require a nonempty target. Add regression variants for missing, Internal and invalid modes. No assertion is made that the earlier implementation actually fetched a URL.
- **F02 — Medium / confidentiality: untrusted header logo bytes were carried into the portable sidecar unchanged.** A valid image can retain EXIF descriptors, private comments or trailing content. Re-encode the imported logo at ingestion and the stored logo on sidecar save, keeping source Word bytes untouched. Add synthetic private EXIF marker regression. The user's real Word file has not been accessed.
- **F03 — Medium / UX and cross-report provenance: active profile was global app configuration yet the editable page did not render the imported header, logo or footer.** Users could inspect a report without realizing a different report's selected letterhead would be used during export. Show a protected active-template label, logo, header and schematic footer on the editable page; continue to disclose global local-export setting behavior and prevent these labels from entering report facts.
- **F04 — Low / validation mismatch:** Heading 1 font edit control accepted 120 characters while schema allows 96. Align UI bound.

## Security, feature and release boundaries

These are narrowly scoped corrections; there is no new network code, new report schema, customer metadata persistence, module tree, or export format. The Word source is not extracted to disk or uploaded. The overall importer remains a *partial* OOXML reader, not a full Word renderer or sandbox; installed Windows and original-template print fidelity remain untested. The profile is a shared local selection, **not bound to an individual project**. UI visibility mitigates, but does not remove, the need to verify the correct customer template on each export.

Review corrections and the exact post-correction Windows M0/M1 checks before merging corrections into PR #31. Then re-evaluate PR #31 for integration into PR #25 only. Do not merge directly to main, install or publish a release without a separate authorization.
