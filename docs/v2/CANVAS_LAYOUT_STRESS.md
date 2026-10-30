# Branch canvas layout stress tests

Guards the natural-height card contract in `NATURAL_CARD_LAYOUT.md`: parent
layouts own geometry, cards never overlap, nothing scrolls inside a card, and
nested modules never clip.

Test file: `tests/test_v2_canvas_layout_stress.py` (offscreen Qt, synthetic data,
about 35 seconds). The hosted Windows V2 packaging preflight runs these tests before
freezing; changes to these tests and workflow retrigger that gate.

**This is not Windows acceptance.** It checks Qt geometry offscreen. Real DPI,
ClearType and font fallback still need the native Windows run (AGENTS.md rule 2).

## What is enforced

| Test | Guards against |
| --- | --- |
| `test_no_overlap_or_clipping_across_scenarios_widths_and_zoom` | Sibling cards overlapping, a card shorter than its content, clipped text (paragraphs and titles), tables that scroll inside the card, rows past the canvas edge. Five content scenarios (long text incl. CJK and emoji, wide tables, photos, deep nesting, everything) x 660/1100/1920 px x 55/100/160 % zoom. |
| `test_larger_system_text_does_not_cause_overlap_or_clipping` | Same checks with the application font at 150 %, a stand-in for Windows text scaling. |
| `test_typing_a_long_paragraph_settles_without_overlap_and_keeps_the_caret_visible` | Layout lagging behind typing; caret scrolled out of view. Checked after the layout settles, not on the single frame in which a row may be a few pixels short. |
| `test_resizing_with_an_open_draft_never_overlaps`, `test_collapsing_and_expanding_repeatedly_keeps_the_layout_clean` | Resize with a draft open; collapse/expand cycles. |
| `test_preview_never_shows_unapplied_text` | Inspects actual rendered report `QLabel` content: approved report text must be present, unapplied draft text must be absent. |
| `test_a_field_has_exactly_one_draft_owner` | Explicitly rejects another editor taking over an owned draft, preserving source report, owner, and staged text. |

### Fixed after the 2026-10-29 review

| Problem | Fix | Tests |
| --- | --- | --- |
| Deep nesting pushed cards past the right edge of a narrow window. The canvas has no horizontal scrollbar, so the card's buttons were unreachable (76 px off at 14 levels in 660 px). A later run on another machine still saw 3 px at 20 levels because the fit used a card width cached when the rows were built. | `_apply_indent()` measures each row's **live** minimum width (and again after the style sheet is polished) and uses four stages, each only if the last was not enough: the indentation per level shrinks (never below 6 px); the side margin shrinks (20 to 8 px); the cards' inner padding shrinks (15 to 8 px); the drag handle shows only its glyph (same tooltip and accessible name). Every row uses the same step so levels still line up, and everything is restored when there is room. Past the last stage it can still overflow: at 160 % zoom in a half-width pane (about 450 px) 20 levels are still about 9 px too wide (it was 77 px before), because the minimum step scales with zoom. Very wide fonts at roughly 25+ levels at 660 px can also still overflow. | `AdaptiveLayoutTests`: `test_deep_nesting_*`, `test_indentation_only_shrinks_when_it_has_to`, `test_connector_lines_stay_distinct_at_the_narrowest_step`, `test_the_fit_follows_the_real_widths_not_a_cached_estimate` (11 px over on the old fit), `test_larger_application_fonts_*`, and the side-margin and compact-stage tests |
| Module titles were single-line `QLineEdit`s, so a long title was silently cut off. | `InlineTitle` is now a wrapping editor that reuses the paragraph's natural-height logic. It keeps the `QLineEdit` calls the canvas uses (`text`, `setText`, `textEdited`, `returnPressed`, selection), always stays one logical line (Enter commits, pasted line breaks become spaces) and has no bold/italic/underline. | `test_a_long_title_wraps_instead_of_being_cut_off`, `test_an_unbroken_title_also_wraps`, `test_a_title_stays_one_logical_line` |
| The drop indicator label was drawn over the card's own drag handle, collapse toggle and menu button. | The label slides left past any button it would cover (or below the header). The coloured edge line is unchanged. | `test_the_drop_indicator_never_covers_card_controls` |
| The Editor tab kept showing the old text, editable, for a field being edited in Modules; typed characters were rejected by the draft coordinator but stayed on screen. A later review saw the lock arrive late in a full run because it waited for a debounced timer. | `DraftCoordinator.subscribe_changes` reports which field changed owner (never text). A field another editor owns is made read-only, showing that draft, **synchronously inside the notification**, when a canvas is shown, and after a rejected keystroke (so a missed notification is repaired by the first rejected key). It unlocks the same way. The debounced redraw only adds the "belongs to the other editor" notice, so no lock depends on a timer or on how long a redraw takes. | `LiveInterferenceTests`: asserts the lock right after the keystroke, with timers and redraws disabled, after a missed notification, and after every step of a 4-round back-and-forth. Waits use the real event loop until a condition holds, never a fixed sleep |

## Deliberately not tested

* The one-frame, up to 8 px short row right after a keystroke. It depends on
  event timing and would be flaky; the settled state is what is asserted.
* Display scale (`QT_SCALE_FACTOR`). It changed devicePixelRatio only and gave
  identical geometry offscreen.
