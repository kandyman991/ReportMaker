# V2 shortcut policy and customer manager

## Shortcut policy
* Never bind **Ctrl+Shift+V** (paste as plain text — how text from an AI assistant is pasted) or **Ctrl+V** to an application action. In every inline editor (module titles, paragraphs, captions and table cells in the Branch Editor, and paragraph text in the page Editor) Ctrl+Shift+V pastes plain text, exactly like Ctrl+V. See `v2/editing_keys.py`.
* Never bind **Ctrl+Shift+Esc**; Windows reserves it for Task Manager, so it never reaches the application.
* **Paste image** is now **Ctrl+Alt+V** (was Ctrl+Shift+V, which silently swallowed text pastes and showed "Image paste rejected"). **Exit focus** is now **Alt+Shift+F** (was Ctrl+Shift+Esc).
* Use Qt's portable key names: **Ctrl+PgUp / Ctrl+PgDown**. `PageUp`/`PageDown` parse as an unknown key in Qt 6, so Previous/Next window previously had no working shortcut.
* `tests/test_v2_shortcuts_customer_manager.py` fails if a V2 shortcut does not parse, is shared by two actions, or uses one of the reserved chords.

## Customers, sites and machines
`reportmaker.v2.customer_manager` (moved from `reportmaker.customer_ui`, which remains as a thin compatibility import until V1 is removed) is opened from **Project ▾ → Customers, sites and machines…**. It works on the same local SQLite database that *Report info → Choose from database* reads (`V2MainWindow(customer_database_path=…)`, default per-user location). Reports keep a frozen snapshot, so editing master data never changes an existing report. The V1 `--customer-self-test` now patches the moved module.

Previously V2 could only *pick* existing records; creating, editing, deleting and backing up customers was reachable only from the V1 shell.
