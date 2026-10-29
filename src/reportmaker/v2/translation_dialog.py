"""User-controlled V2 translation editor, using canonical stable IDs.

One field at a time: no hidden machine translation, no silent draft discard,
and every accepted change goes through the existing transactional gateway.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QVBoxLayout,
)

from .commands import CommandIntent
from .localized_export import localized_fields


class TranslationDialog(QDialog):
    def __init__(self, session, gateway, parent=None):
        super().__init__(parent)
        self.setObjectName("v2TranslationDialog")
        self.setWindowTitle("Report translations · manual editing")
        self.resize(900, 560)
        self.session, self.gateway = session, gateway
        self._key = None
        self._baseline = ""
        self._fields = []
        self._updating = False
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Edit translations locally. Missing or outdated fields block exports "
            "in that language; original text is never replaced."))
        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel("Translation language"))
        self.language = QComboBox(self)
        self.language.setObjectName("v2TranslationLanguage")
        report = session.report_snapshot()
        for code in report.output_languages:
            if code.casefold() != report.primary_language.casefold():
                self.language.addItem(code, code)
        self.language.currentIndexChanged.connect(self._language_changed)
        lang_row.addWidget(self.language, 1)
        layout.addLayout(lang_row)
        self.fields = QListWidget(self)
        self.fields.setObjectName("v2TranslatableFields")
        self.fields.currentRowChanged.connect(self._field_changed)
        layout.addWidget(self.fields, 2)
        self.source = QLabel(self)
        self.source.setObjectName("v2TranslationSource")
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.translation = QPlainTextEdit(self)
        self.translation.setObjectName("v2TranslationText")
        self.translation.textChanged.connect(self._dirty_changed)
        layout.addWidget(self.translation, 1)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        actions = QHBoxLayout()
        self.apply_button = QPushButton("Apply this field", self)
        self.apply_button.setObjectName("v2ApplyTranslation")
        self.apply_button.clicked.connect(self.apply_field)
        actions.addWidget(self.apply_button)
        revert = QPushButton("Revert draft", self)
        revert.clicked.connect(self.revert_field)
        actions.addWidget(revert)
        close = QPushButton("Close", self)
        close.clicked.connect(self.reject)
        actions.addWidget(close)
        layout.addLayout(actions)
        self._rebuild()

    def _has_draft(self):
        return (self._key is not None
                and self.translation.toPlainText() != self._baseline)

    def _dirty_changed(self):
        if not self._updating:
            stale = False
        if self._key is not None and self.language.currentData() is not None:
            selected = dict(localized_fields(self.session.report_snapshot())).get(self._key)
            if selected is not None:
                stale = any(tag.casefold() == self.language.currentData().casefold()
                            for tag in selected.stale_languages)
        self.apply_button.setEnabled(self._has_draft() or stale)

    def _rebuild(self):
        report = self.session.report_snapshot()
        self._fields = list(localized_fields(report))
        self._updating = True
        try:
            self.fields.clear()
            for key, text in self._fields:
                title = f"{key[1]} · {text.original[:85]}"
                item = QListWidgetItem(title)
                item.setData(Qt.ItemDataRole.UserRole, key)
                self.fields.addItem(item)
        finally:
            self._updating = False
        if self.language.count() == 0:
            self.status.setText("Add an output language in Report Information first.")
            self.translation.setReadOnly(True)
            self.apply_button.setEnabled(False)
        elif self.fields.count():
            self.fields.setCurrentRow(0)

    def _language_changed(self, _idx):
        if self._has_draft():
            self.status.setText("Apply or Revert the current field before switching language.")
            # Preserve the currently edited language.
            self.language.blockSignals(True)
            try:
                self.language.setCurrentIndex(self.language.findData(self._active_language))
            finally:
                self.language.blockSignals(False)
            return
        self._load_field(self._key)

    def _field_changed(self, row):
        if self._updating or row < 0 or row >= len(self._fields):
            return
        key = self._fields[row][0]
        if self._has_draft():
            self.status.setText("Apply or Revert the current field before navigating.")
            self.fields.blockSignals(True)
            try:
                previous = next(
                    (i for i, (k, _) in enumerate(self._fields) if k == self._key), -1)
                self.fields.setCurrentRow(previous)
            finally:
                self.fields.blockSignals(False)
            return
        self._load_field(key)

    def _load_field(self, key):
        if key is None or self.language.currentIndex() < 0:
            return
        report = self.session.report_snapshot()
        fields = dict(localized_fields(report))
        text = fields.get(key)
        if text is None:
            self.status.setText("Field no longer exists. Reopen translations.")
            return
        lang = self.language.currentData()
        self._active_language = lang
        stored = next((code for code in text.translations
                       if code.casefold() == lang.casefold()), lang)
        self._key = key
        self._baseline = text.translations.get(stored, "")
        self._updating = True
        try:
            self.source.setText(f"Original [{text.original_language}]: {text.original}")
            self.translation.setPlainText(self._baseline)
            self.translation.setReadOnly(
                text.original_language.casefold() == lang.casefold())
        finally:
            self._updating = False
        if stored in text.stale_languages:
            self.status.setText("Outdated translation — review and Apply to mark current.")
        elif not self._baseline and text.original:
            self.status.setText("Missing translation — fill and Apply before export.")
        else:
            self.status.setText("Translation current · project changes are saved with Save.")
        self._dirty_changed()

    def apply_field(self):
        if not self._has_draft():
            # Reconfirm an unchanged but stale translation explicitly.
            report = self.session.report_snapshot()
            value = dict(localized_fields(report)).get(self._key)
            language = self.language.currentData()
            stale = value is not None and any(
                code.casefold() == language.casefold()
                for code in value.stale_languages)
            if not stale:
                return False
        try:
            self.session.require_clean_drafts()
            self.gateway.execute(CommandIntent(
                "set_translation", None,
                {"key": self._key, "language": self.language.currentData(),
                 "text": self.translation.toPlainText()},
                self.session.revision, self.session.generation))
        except (LookupError, ValueError, RuntimeError) as exc:
            self.status.setText("Translation not applied: " + str(exc))
            return False
        self._baseline = self.translation.toPlainText()
        self._load_field(self._key)
        return True

    def revert_field(self):
        if self._key is None:
            return
        self._updating = True
        try:
            self.translation.setPlainText(self._baseline)
        finally:
            self._updating = False
        self._dirty_changed()
        self.status.setText("Unapplied translation draft discarded.")

    def reject(self):
        if self._has_draft():
            self.status.setText("Apply or Revert your draft before closing.")
            return
        super().reject()
