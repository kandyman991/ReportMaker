# Branch canvas layout stress tests

Guards the natural-height card contract in `NATURAL_CARD_LAYOUT.md`: parent
layouts own geometry, cards never overlap, nothing scrolls inside a card, and
nested modules never clip.

Test file: `tests/test_v2_canvas_layout_stress.py` (offscreen Qt, synthetic data,
about 25 seconds). The hosted Windows V2 packaging preflight runs these tests
before freezing; test and workflow changes both trigger the preflight.

**This is not Windows acceptance.** It checks Qt geometry offscreen. Real DPI,
ClearType and font fallback still need the native Windows run (AGENTS.md rule 2).

## What is enforced today

| Test | Guards against |
| --- | --- |
| `test_no_overlap_or_clipping_across_scenarios_widths_and_zoom` | Sibling cards overlapping, a card shorter than its content, clipped paragraph text, tables that scroll inside the card, rows past the canvas edge. Five content scenarios (long text incl. CJK and emoji, wide tables, photos, deep nesting, everything) x 660/1100/1920 px x 55/100/160 % zoom. |
| `test_larger_system_text_does_not_cause_overlap_or_clipping` | Same checks with the application font at 150 %, a stand-in for Windows text scaling. |
| `test_typing_a_long_paragraph_settles_without_overlap_and_keeps_the_caret_visible` | Layout lagging behind typing; caret scrolled out of view. Checked after the layout settles, not on the single frame in which a row may be a few pixels short. |
| `test_resizing_with_an_open_draft_never_overlaps` | Resize while a draft is open. |
| `test_collapsing_and_expanding_repeatedly_keeps_the_layout_clean` | Collapse/expand cycles. |
| `test_preview_never_shows_unapplied_text` | Preview showing text that is still a draft. Inspect **rendered report QLabel content**, assert approved source text is actually present, and reject staged text; checking editable text widgets would pass vacuously. |
| `test_a_field_has_exactly_one_draft_owner` | Two surfaces owning one draft. Explicitly attempts to steal the same field using another editor owner and asserts refusal, retained draft and unchanged canonical report. |
| `test_the_editor_tab_cannot_change_a_draft_owned_by_modules` | The Editor tab silently overwriting a Modules draft. |

## Known defects (expected failures)

These assert the behaviour we want and are marked `expectedFailure`. When one is
fixed the test reports an unexpected success: delete the marker and keep it as a
strict test.

| Test | Current behaviour |
| --- | --- |
| `test_known_defect_deep_nesting_fits_a_660px_window` | Fixed indentation per level pushes the canvas past the window (horizontal scrollbar, 76 px at 14 levels). |
| `test_known_defect_long_module_titles_are_fully_visible` | Module titles are single-line fields; a long title is cut off. |
| `test_known_defect_drop_indicator_never_covers_card_controls` | The drop marker is drawn over the card's own handle, toggle and menu buttons. |
| `test_known_defect_editor_tab_does_not_accept_typing_into_a_field_edited_in_modules` | The Editor tab shows the old text, is not read-only, and keeps typed characters the model then rejects ("Edit rejected; original draft retained"). |

## Deliberately not tested

* The one-frame, up to 8 px short row right after a keystroke. It depends on
  event timing and would be flaky; the settled state is what is asserted.
* Display scale (`QT_SCALE_FACTOR`). It changed devicePixelRatio only and gave
  identical geometry offscreen.
