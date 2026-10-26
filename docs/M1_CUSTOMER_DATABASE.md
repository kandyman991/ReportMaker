# M1 — Local customer records (development preview)

## Boundaries
- Schema v1 consists of customers, sites, machines, interventions, and immutable report_references.
- Child records belong to exactly one parent; database foreign keys are enabled and deleting a parent with children/history is refused. No cascading data loss.
- Master records are mutable. A customer reference snapshot copies customer/site/machine fields by value; saving a report reference is *write-once*. Report modules/assets are handled in M2.
- One-off reports may create an unlinked manual snapshot without creating master data. M1 has a snapshot preview, not a saved report editor.
- No auto-seeded demo data. Every synthetic fixture exists only in temporary tests.

## Data location / privacy
- Windows: per-user `%LOCALAPPDATA%\ReportMaker\records.sqlite3`.
- Linux development: `$XDG_DATA_HOME/reportmaker/records.sqlite3` (fallback `~/.local/share/reportmaker/`).
- SQLite may maintain `-wal` and `-shm` next to the database. Do not copy only the DB file while it is in use.
- Qt WebEngine browser profile is separate. No customer fields are sent to browser, network, ChatGPT, CI, repository or release assets.
- This GitHub repository is public: **never add real customer database, reports, names, addresses, serial numbers, photos, or backup files.**

## Backup, recovery and migration policy
- Backups are explicitly initiated in the Customer Manager. They use SQLite's consistent online backup API and a quick integrity check, and **refuse to overwrite** an existing file.
- Choose a destination on a local, user-controlled drive and protect it like the original customer data. Backups are not automatically uploaded anywhere.
- To restore: close ReportMaker; keep a copy of the active DB and any WAL/SHM alongside it; validate the backup independently (SQLite `PRAGMA quick_check`), then replace the inactive database with the backup and relaunch. Never restore while the application is running. Recovery UI and versioned encrypted archival backups are deferred.
- Newer database schema versions refuse to open on an older application. Schema migrations run inside transactions; future migrations must be additive/tested against a copied database. Migration downgrade is unsupported. Before an app upgrade, take a verified local backup.
- JSON/CSV import and export are **not yet available**; format and merge/deduplication policy require design/review so imported private records cannot silently overwrite masters. Manual record entry is supported.

## Development verification
```text
python -m unittest discover -s tests -v
python -m reportmaker --customer-self-test
```
Run the second command on an actual Windows runner with PySide6. It uses a temporary synthetic SQLite database and an offline Qt UI; it does not browse ChatGPT.

## Manual Windows acceptance still required
1. Launch installed preview, open Customers / Sites / Machines.
2. Create and edit a customer, multiple sites, multiple machines with serials.
3. Search by customer, site, serial number. Add dated intervention history and restart; check persistence.
4. Attempt to delete a customer with a site and a machine with history; verify deletion is refused.
5. Preview a reference, update its live master data and verify a **saved** reference captured by storage remains unchanged; confirm manual one-off references do not create masters.
6. Create a local backup; inspect it separately after app shutdown; verify original browser pane and login fallback still work. No upload to cloud.
7. Check DPI/resize/keyboard accessibility and fresh install/uninstall behavior on a normal Windows account.

M1 is **not** the report editor, Word exporter, completed installer acceptance, or a guarantee of production readiness.
