"""Local SQLite master data: customer -> sites -> machines and service history.

This module has no Qt/network dependencies. The database is never auto-seeded.
Migrations are versioned and transactional; backup uses SQLite's online backup
API, which includes committed WAL data.
"""
from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

from .reference import CustomerSnapshot


SCHEMA_VERSION = 1

FIELDS = {
    "customers": ("name", "code", "address", "city", "postal_code", "country",
                  "contact_name", "contact_email", "contact_phone", "notes"),
    "sites": ("name", "address", "city", "postal_code", "country",
              "contact_name", "contact_email", "contact_phone", "notes"),
    "machines": ("name", "manufacturer", "model", "serial_number", "asset_tag", "notes"),
}
TABLES = frozenset(FIELDS)

DDL = """
CREATE TABLE customers (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    code TEXT NOT NULL DEFAULT '', address TEXT NOT NULL DEFAULT '',
    city TEXT NOT NULL DEFAULT '', postal_code TEXT NOT NULL DEFAULT '',
    country TEXT NOT NULL DEFAULT '', contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '', contact_phone TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE sites (
    id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    address TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
    postal_code TEXT NOT NULL DEFAULT '', country TEXT NOT NULL DEFAULT '',
    contact_name TEXT NOT NULL DEFAULT '', contact_email TEXT NOT NULL DEFAULT '',
    contact_phone TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX idx_sites_customer ON sites(customer_id);
CREATE TABLE machines (
    id TEXT PRIMARY KEY,
    site_id TEXT NOT NULL REFERENCES sites(id) ON DELETE RESTRICT,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    manufacturer TEXT NOT NULL DEFAULT '', model TEXT NOT NULL DEFAULT '',
    serial_number TEXT NOT NULL DEFAULT '', asset_tag TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_machines_site ON machines(site_id);
CREATE TABLE interventions (
    id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES machines(id) ON DELETE RESTRICT,
    start_date TEXT NOT NULL, end_date TEXT,
    ticket TEXT NOT NULL DEFAULT '', technician TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
    CHECK (end_date IS NULL OR end_date >= start_date)
);
CREATE INDEX idx_interventions_machine_date ON interventions(machine_id, start_date);
CREATE TABLE report_references (
    report_id TEXT PRIMARY KEY,
    snapshot_json TEXT NOT NULL,
    captured_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def default_database_path() -> Path:
    """Per-user storage, independent of browser profile and Git repository."""
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home() / "AppData" / "Local")
        return Path(base) / "ReportMaker" / "records.sqlite3"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "reportmaker" / "records.sqlite3"


def _value(value: str, name: str) -> str:
    if not isinstance(value, str) or len(value) > 10000:
        raise ValueError(f"Invalid {name}")
    cleaned = value.strip()
    if name == "name" and not cleaned:
        raise ValueError("Name cannot be empty")
    return cleaned


class CustomerStore:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_database_path()
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if self.path.is_symlink():
                raise ValueError("Refusing a symlink database")
        self.connection = sqlite3.connect(str(self.path), timeout=10)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA busy_timeout = 10000")
        if str(self.path) != ":memory:":
            self.connection.execute("PRAGMA journal_mode = WAL")
        try:
            self._migrate()
        except BaseException:
            self.connection.close()
            raise

    def __enter__(self) -> "CustomerStore":
        return self

    def __exit__(self, *_args) -> None:
        self.close()

    def close(self) -> None:
        self.connection.close()

    def _migrate(self) -> None:
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Database version is newer than this ReportMaker build")
        if version == 0:
            with self.connection:
                self.connection.executescript("BEGIN IMMEDIATE;\n" + DDL +
                                              f"PRAGMA user_version = {SCHEMA_VERSION};\nCOMMIT;")
        if self.connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise RuntimeError("SQLite foreign-key enforcement unavailable")

    def _insert(self, table: str, parent: str | None = None, **values: str) -> str:
        if table not in TABLES:
            raise ValueError("Invalid table")
        allowed = FIELDS[table]
        if "name" not in values:
            raise ValueError("Name required")
        if set(values) - set(allowed):
            raise ValueError("Unknown fields")
        fields = {key: _value(values.get(key, ""), key) for key in allowed}
        if table != "customers":
            parent_key = "customer_id" if table == "sites" else "site_id"
            if not parent:
                raise ValueError("Parent ID required")
            fields[parent_key] = parent
        identifier, now = uuid4().hex, _now()
        fields.update(id=identifier, created_at=now, updated_at=now)
        keys = tuple(fields)
        placeholders = ", ".join("?" for _ in keys)
        with self.connection:
            self.connection.execute(
                f"INSERT INTO {table} ({', '.join(keys)}) VALUES ({placeholders})",
                tuple(fields[k] for k in keys))
        return identifier

    def create_customer(self, name: str, **fields: str) -> str:
        return self._insert("customers", name=name, **fields)

    def create_site(self, customer_id: str, name: str, **fields: str) -> str:
        return self._insert("sites", parent=customer_id, name=name, **fields)

    def create_machine(self, site_id: str, name: str, **fields: str) -> str:
        return self._insert("machines", parent=site_id, name=name, **fields)

    def update(self, table: str, identifier: str, **values: str) -> None:
        if table not in TABLES or not values or set(values) - set(FIELDS[table]):
            raise ValueError("Invalid update fields/table")
        fields = {key: _value(value, key) for key, value in values.items()}
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{key} = ?" for key in fields)
        with self.connection:
            cursor = self.connection.execute(
                f"UPDATE {table} SET {assignments} WHERE id = ?",
                (*fields.values(), identifier))
            if cursor.rowcount != 1:
                raise LookupError("Record not found")

    def delete(self, table: str, identifier: str) -> None:
        if table not in TABLES:
            raise ValueError("Invalid table")
        # FK RESTRICT intentionally rejects deletion of referenced child records.
        with self.connection:
            cursor = self.connection.execute(
                f"DELETE FROM {table} WHERE id = ?", (identifier,))
            if cursor.rowcount != 1:
                raise LookupError("Record not found")

    def get(self, table: str, identifier: str) -> dict:
        if table not in TABLES:
            raise ValueError("Invalid table")
        row = self.connection.execute(
            f"SELECT * FROM {table} WHERE id = ?", (identifier,)).fetchone()
        if row is None:
            raise LookupError(f"{table} record not found")
        return dict(row)

    def list_customers(self, search: str = "") -> list[dict]:
        term = f"%{search.strip()}%"
        rows = self.connection.execute("""
            SELECT c.* FROM customers AS c WHERE
              c.name LIKE ? OR c.code LIKE ? OR c.city LIKE ?
              OR EXISTS (SELECT 1 FROM sites AS s
                  WHERE s.customer_id = c.id AND
                  (s.name LIKE ? OR s.city LIKE ? OR s.address LIKE ?
                   OR EXISTS (SELECT 1 FROM machines AS m WHERE m.site_id = s.id
                       AND (m.name LIKE ? OR m.model LIKE ? OR m.serial_number LIKE ?))))
            ORDER BY c.name COLLATE NOCASE, c.id
        """, (term,) * 9).fetchall()
        return [dict(row) for row in rows]

    def list_sites(self, customer_id: str) -> list[dict]:
        return [dict(r) for r in self.connection.execute(
            "SELECT * FROM sites WHERE customer_id = ? ORDER BY name COLLATE NOCASE, id",
            (customer_id,))]

    def list_machines(self, site_id: str) -> list[dict]:
        return [dict(r) for r in self.connection.execute(
            "SELECT * FROM machines WHERE site_id = ? ORDER BY name COLLATE NOCASE, id",
            (site_id,))]

    def add_intervention(
        self, machine_id: str, start_date: str, *, end_date: str | None = None,
        ticket: str = "", technician: str = "", description: str = "",
    ) -> str:
        start = date.fromisoformat(start_date)
        if end_date is not None and date.fromisoformat(end_date) < start:
            raise ValueError("End date before start date")
        values = (_value(ticket, "ticket"), _value(technician, "technician"),
                  _value(description, "description"))
        identifier = uuid4().hex
        with self.connection:
            self.connection.execute("""
                INSERT INTO interventions
                (id, machine_id, start_date, end_date, ticket, technician, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (identifier, machine_id, start_date, end_date, *values, _now()))
        return identifier

    def list_interventions(self, machine_id: str) -> list[dict]:
        return [dict(r) for r in self.connection.execute("""
            SELECT * FROM interventions WHERE machine_id = ?
            ORDER BY start_date DESC, created_at DESC, id DESC
        """, (machine_id,))]

    def capture_snapshot(
        self, customer_id: str, *, site_id: str | None = None,
        machine_id: str | None = None,
    ) -> CustomerSnapshot:
        # A single SQLite read transaction avoids combining values captured
        # across concurrent master-data updates by another local process.
        self.connection.execute("SAVEPOINT reference_snapshot")
        try:
            customer = self.get("customers", customer_id)
            site = self.get("sites", site_id) if site_id else None
            machine = self.get("machines", machine_id) if machine_id else None
        finally:
            self.connection.execute("RELEASE SAVEPOINT reference_snapshot")
        if site and site["customer_id"] != customer_id:
            raise ValueError("Selected site does not belong to customer")
        if machine and (site is None or machine["site_id"] != site_id):
            raise ValueError("Selected machine does not belong to site")
        return CustomerSnapshot(
            customer_id=customer_id, customer_name=customer["name"],
            customer_code=customer["code"], customer_address=customer["address"],
            customer_city=customer["city"], customer_country=customer["country"],
            customer_contact=customer["contact_name"],
            customer_email=customer["contact_email"],
            customer_phone=customer["contact_phone"],
            site_id=site_id,
            site_name=site["name"] if site else "",
            site_address=site["address"] if site else "",
            site_city=site["city"] if site else "",
            site_country=site["country"] if site else "",
            site_contact=site["contact_name"] if site else "",
            site_email=site["contact_email"] if site else "",
            site_phone=site["contact_phone"] if site else "",
            machine_id=machine_id,
            machine_name=machine["name"] if machine else "",
            machine_manufacturer=machine["manufacturer"] if machine else "",
            machine_model=machine["model"] if machine else "",
            machine_serial=machine["serial_number"] if machine else "",
            machine_asset_tag=machine["asset_tag"] if machine else "",
        )

    def save_report_reference(self, report_id: str, snapshot: CustomerSnapshot) -> None:
        """Write-once: never mutate a report's captured master-data reference."""
        if not report_id.strip():
            raise ValueError("Report ID required")
        payload = json.dumps(snapshot.to_dict(), ensure_ascii=False, sort_keys=True)
        with self.connection:
            self.connection.execute(
                "INSERT INTO report_references (report_id, snapshot_json, captured_at) "
                "VALUES (?, ?, ?)", (report_id, payload, snapshot.captured_at))

    def load_report_reference(self, report_id: str) -> CustomerSnapshot:
        row = self.connection.execute(
            "SELECT snapshot_json FROM report_references WHERE report_id = ?",
            (report_id,)).fetchone()
        if row is None:
            raise LookupError("No saved report reference")
        return CustomerSnapshot.from_dict(json.loads(row[0]))

    def backup(self, destination: str | Path) -> Path:
        """Explicit local backup. Never overwrite an existing file."""
        target = Path(destination)
        if str(self.path) == ":memory:" and str(target) == ":memory:":
            raise ValueError("Backup must be a file")
        if target.absolute() == self.path.absolute():
            raise ValueError("Backup target cannot be source")
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("xb"):
            pass
        try:
            with closing(sqlite3.connect(str(target))) as destination_db:
                self.connection.backup(destination_db)
                result = destination_db.execute("PRAGMA quick_check").fetchone()[0]
                if result != "ok":
                    raise RuntimeError("SQLite backup integrity check failed")
        except BaseException:
            target.unlink(missing_ok=True)
            raise
        return target
