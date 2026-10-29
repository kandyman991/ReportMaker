"""Explicit, report-local M6.5 translations of customer-visible metadata.

Manual-only approval, guarded drafts, canonical source facts and one gateway
transaction per change. No browser, translation API or parallel report model.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .commands import CommandIntent
from .metadata_locale import (
    ENGLISH_LABELS, MetadataLocale, PERSISTABLE_KEYS, source_digest,
)


class MetadataTranslationDialog(QDialog):
    def __init__(self, session, gateway, parent=None):
        super().__init__(parent)
        self.setObjectName("v2MetadataTranslationDialog")
        self.setWindowTitle("Report metadata and labels · manual translations")
        self.resize(850, 550)
        self.session, self.gateway = session, gateway
        self._key = None
        self._baseline = ""
        self._language = None
        self._source_sha256 = None
        self._revision = session.revision
        self._loading = False
        root = QVBoxLayout(self)
        info = QLabel("Only approved translations are exported. Generated labels have "
                      "English originals; custom intervention details use the report "
                      "writing language. Apply or Revert before switching fields.")
        info.setWordWrap(True)
        root.addWidget(info)
        row = QHBoxLayout()
        row.addWidget(QLabel("Output language"))
        self.language = QComboBox(self)
        self.language.setObjectName("v2MetadataLanguage")
        for language in session.report_snapshot().output_languages:
            self.language.addItem(language, language)
        self.language.currentIndexChanged.connect(self._language_changed)
        row.addWidget(self.language, 1)
        root.addLayout(row)
        self.fields = QListWidget(self)
        self.fields.setObjectName("v2MetadataFields")
        self.fields.currentRowChanged.connect(self._field_changed)
        root.addWidget(self.fields, 2)
        self.source = QLabel(self)
        self.source.setObjectName("v2MetadataSource")
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        root.addWidget(self.source)
        self.translation = QPlainTextEdit(self)
        self.translation.setObjectName("v2MetadataTranslationText")
        self.translation.textChanged.connect(self._changed)
        root.addWidget(self.translation, 1)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("Approve translation", self)
        self.apply_button.setObjectName("v2ApplyMetadataTranslation")
        self.apply_button.clicked.connect(self.apply_field)
        actions.addWidget(self.apply_button)
        revert = QPushButton("Revert draft", self)
        revert.clicked.connect(self.revert_field)
        actions.addWidget(revert)
        close = QPushButton("Close", self)
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        root.addLayout(actions)
        report = session.report_snapshot()
        keys = sorted(PERSISTABLE_KEYS)
        if "other" not in report.intervention_types:
            keys.remove("metadata.other_intervention_detail")
        self._keys = keys
        for key in keys:
            label = ENGLISH_LABELS.get(key, "Custom intervention details")
            item = QListWidgetItem(label + "  [" + key + "]")
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.fields.addItem(item)
        if self.fields.count() and self.language.count():
            self.fields.setCurrentRow(0)
        else:
            self.status.setText("Add output languages in Report Information first.")

    def _has_draft(self):
        return self._key is not None and (
            self.translation.toPlainText() != self._baseline)

    def _changed(self):
        if self._loading:
            return
        self.apply_button.setEnabled(
            not self.translation.isReadOnly() and
            (self._has_draft() or self._is_stale()))

    def _is_stale(self):
        if self._key is None or self._language is None:
            return False
        record = self.session.report_snapshot().localization_ledger.get(
            self._key, {}).get(self._language)
        return record is not None and record["source_sha256"] != self._source_sha256

    def _language_changed(self, _index):
        if self._has_draft():
            self.status.setText("Apply or Revert your draft before switching language.")
            self.language.blockSignals(True)
            self.language.setCurrentIndex(self.language.findData(self._language))
            self.language.blockSignals(False)
            return
        self._load()

    def _field_changed(self, _row):
        if self._has_draft():
            self.status.setText("Apply or Revert your draft before selecting another label.")
            self.fields.blockSignals(True)
            self.fields.setCurrentRow(self._keys.index(self._key))
            self.fields.blockSignals(False)
            return
        self._load()

    def _load(self):
        row = self.fields.currentRow()
        if row < 0 or row >= len(self._keys) or self.language.currentData() is None:
            return
        self._key = self._keys[row]
        self._language = self.language.currentData()
        report = self.session.report_snapshot()
        locale = MetadataLocale(report)
        original, source_language = locale.source(self._key)
        self._source_sha256 = source_digest(self._key, source_language, original)
        self._revision = self.session.revision
        records = report.localization_ledger.get(self._key, {})
        saved_code = next((code for code in records
                           if code.casefold() == self._language.casefold()), None)
        record = records[saved_code] if saved_code else None
        self._baseline = record["text"] if record else ""
        self._loading = True
        try:
            self.source.setText(f"Original [{source_language}]: {original}")
            self.translation.setPlainText(self._baseline)
            self.translation.setReadOnly(
                source_language.casefold() == self._language.casefold())
        finally:
            self._loading = False
        if self.translation.isReadOnly():
            self.status.setText("Canonical original · cannot overwrite this source language.")
        elif record is None:
            self.status.setText("Missing approval — enter a manual translation.")
        elif record["source_sha256"] != self._source_sha256:
            self.status.setText("Outdated approval — review and Apply again.")
        else:
            self.status.setText("Approved · use Save to persist the report.")
        self._changed()

    def apply_field(self):
        if self._key is None or self.translation.isReadOnly() or (
            not self._has_draft() and not self._is_stale()):
            return False
        try:
            self.session.require_clean_drafts()
            self.gateway.execute(CommandIntent(
                "set_metadata_translation", None,
                {"key": self._key, "language": self._language,
                 "text": self.translation.toPlainText(),
                 "expected_source_sha256": self._source_sha256},
                self._revision, self.session.generation))
        except (ValueError, RuntimeError, LookupError) as exc:
            self.status.setText("Approval rejected: " + str(exc))
            return False
        self._load()
        return True

    def revert_field(self):
        if self._key is not None:
            self._loading = True
            self.translation.setPlainText(self._baseline)
            self._loading = False
            self._changed()
            self.status.setText("Unapplied draft discarded.")

    def reject(self):
        if self._has_draft():
            self.status.setText("Apply or Revert before closing.")
            return
        super().reject()
