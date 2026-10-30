"""Compatibility import: the customer manager moved to ``reportmaker.v2.customer_manager``.

Kept only so the legacy V1 shell and its self-test keep working; delete this
file together with V1.
"""
from .v2.customer_manager import (  # noqa: F401
    LABELS, CustomerManagerDialog, HistoryDialog, ManualReferenceForm, RecordForm,
)
