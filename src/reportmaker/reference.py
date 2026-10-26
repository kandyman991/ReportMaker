"""Immutable, portable customer/site/machine reference snapshots.

Report snapshots contain copied values, not live database rows. They are also
usable for one-off interventions with no customer registered in the database.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True, slots=True)
class CustomerSnapshot:
    customer_name: str
    customer_id: str | None = None
    customer_code: str = ""
    customer_address: str = ""
    customer_city: str = ""
    customer_country: str = ""
    customer_contact: str = ""
    customer_email: str = ""
    customer_phone: str = ""
    site_id: str | None = None
    site_name: str = ""
    site_address: str = ""
    site_city: str = ""
    site_country: str = ""
    site_contact: str = ""
    site_email: str = ""
    site_phone: str = ""
    machine_id: str | None = None
    machine_name: str = ""
    machine_manufacturer: str = ""
    machine_model: str = ""
    machine_serial: str = ""
    machine_asset_tag: str = ""
    captured_at: str = field(default_factory=_timestamp)
    schema_version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.customer_name, str) or not self.customer_name.strip():
            raise ValueError("A snapshot requires a customer name, even for a one-off report")
        if self.schema_version != 1:
            raise ValueError("Unsupported customer snapshot schema")
        if self.machine_id and not self.site_id:
            raise ValueError("A stored machine reference needs its site reference")
        if self.site_id and not self.customer_id:
            raise ValueError("A stored site reference needs its customer reference")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "CustomerSnapshot":
        if not isinstance(data, dict):
            raise ValueError("Snapshot must be an object")
        # Reject unknown properties to catch incompatible schemas early.
        try:
            return cls(**data)
        except TypeError as exc:
            raise ValueError("Invalid or incompatible snapshot properties") from exc


def manual_snapshot(
    customer_name: str,
    *, site_name: str = "", machine_name: str = "",
    machine_serial: str = "", customer_address: str = "",
    customer_contact: str = "", site_address: str = "",
) -> CustomerSnapshot:
    """Capture an intervention without creating any master customer records."""
    return CustomerSnapshot(
        customer_name=customer_name.strip(), site_name=site_name.strip(),
        machine_name=machine_name.strip(), machine_serial=machine_serial.strip(),
        customer_address=customer_address.strip(), customer_contact=customer_contact.strip(),
        site_address=site_address.strip(),
    )
