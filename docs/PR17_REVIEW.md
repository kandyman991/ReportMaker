# M4.5.1 PR #17 independent review and isolated corrections (PR #18)

Date: 2026-10-27
Status: **Corrections proposed, not yet independently re-reviewed or merged**.

## Exact review boundary

- Repository: `kandyman991/ReportMaker`
- Parent: [draft PR #17](https://github.com/kandyman991/ReportMaker/pull/17), reviewed exact head `7c31c27e351380135901ad9b3ecbf8dfb04ee420`, targeting the M4.5 architecture branch from draft PR #16.
- Source review: [PR #17 review](https://github.com/kandyman991/ReportMaker/pull/17#pullrequestreview-5663095041) and four inline comments.
- Correction branch: `review/pr17-m45-media-safety-fixes`, [draft PR #18](https://github.com/kandyman991/ReportMaker/pull/18), targeting PR #17's implementation feature branch, **not** `main` or PR #16.
- The reviewer explicitly recommended *not* merging until problems were addressed; hosted Windows CI passed on the reviewed parent, but this did not establish source-level acceptance.

## Findings and correction rationale

### M45-F01 HIGH — deleting undo-reachable photo bytes

When a PhotoBlock was removed from a module and its library member deleted, `remove_library_picture()` also removed `ReportProject.assets` bytes. `ProjectEditor.undo()` then restored the block without the bytes, breaking preview and Save.

**Correction:** Remove explicit media-library membership but retain the bytes in the *current session's* undo cache, matching existing M2 behavior for unreferenced in-memory assets. `save_project` continues to serialize only block-reachable or declared-library media, never a hidden orphan. A fresh reload after deletion does not bring back the deleted photo, while an in-session Undo restores placed photo content safely.

**Regression:** remove placed block, remove library membership, save/reload omission, Undo restoration and valid re-save; explicit deletion/duplicate-use guards retained.

### M45-F02 HIGH — silent in-place v1→v2 upgrade

A formerly valid v1 project could be opened and overwritten on ordinary Save with a v2 archive, leaving no rollback source or warning.

**Correction:** Carry session-only `loaded_version` and `loaded_from` provenance from `load_project` through the Qt editor. Reject `save_project` when it would overwrite the original v1 path, including ordinary Save. Qt explains **Save As** must be used with a *different filename*. The untouched original v1 remains the rollback source; a separate v2 copy becomes the current editable project. Provenance and original source paths are **never serialized** to `.rmproj`.

**Regression:** v1 archive bytes unchanged after rejected in-place save; a new v2 copy loads; GUI offline smoke repeats the refusal and Save As copy. No automatic hidden backups containing sensitive old photographs.

### M45-F03 MEDIUM — double conversion after import approval

Qt converted input before asking for confirmation, then `import_pictures` independently re-read/re-encoded the sources, wasting processing and letting actual stored bytes differ if originals changed in the interim.

**Correction:** `stage_pictures` reads and converts each input once and returns detached immutable working bytes with bounded preview thumbnails. A per-picture Qt comparison dialog shows oriented original preview and **the exact staged output** side-by-side, including dimensions, format and sizes; user can select the picture before approving the batch. `commit_staged_pictures` atomically persists the **same approved bytes**, never reopens source files, and validates archive limits. Batch capped at 64 images to bound temporary previews.

**Regression:** assert conversion invoked once; mutate source between staging and commit, verify stored bytes match the approved output; all-or-nothing batch import and Qt synthetic comparison dialog exercised.

### M45-F04 MEDIUM — unhandled ICC conversion error

Pillow's `ImageCms.profileToProfile` can raise `ImageCms.PyCMSError` for incompatible input profiles. Uncaught errors could escape import handling.

**Correction:** Normalize this exception to `PictureImportError` without touching source files or committing partial media.

**Regression:** synthetic ICC-tagged source plus injected `PyCMSError`, verify controlled failure and unmodified original bytes.

## Additional architecture-gap closure

The v2 library manifest previously stored only photo name/asset ID, despite ADR-0008 requiring validated media format and dimensions. Now `_image_signature` determines format/width/height **from the actual image bytes** at save time and writes those alongside ID/name. Load verifies each declared library image is a supported, bounded JPEG, PNG or WebP and compares the decoded signature with the manifest. No independent editable source-of-truth metadata is maintained; misplaced, forged, corrupted or mismatched signatures are rejected.

The new v2 media-library format is not merged/released, so no deployed v2 bundle migration is required. v1 project loading and explicit v1→v2 Save As continue to be required.

## CI, privacy and next action

Synthetic-only test changes are in `tests/test_m45_media.py`, `tests/test_pr9_review_fixes.py` and the offline Qt `editor_probe.py`. Inspect live exact-head Windows core, customer-UI and continuity checks of PR #18, rather than interpreting intermediate branch runs as final approval. Windows-hosted CI does not replace actual installed desktop Windows, real-world HEIC image testing, Word/print acceptance, or independent review.

No originals, real customer reports, private photos, browser data, external photo paths, installer or release assets were uploaded. Corrections and docs remain in stacked **draft PR #18**, awaiting independent targeted review. **No merge to PR #17/16/main without explicit user authorization.**
