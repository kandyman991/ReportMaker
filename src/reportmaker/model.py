"""M0 structured report data model. No GUI, storage or web dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from re import fullmatch
from uuid import uuid4

from .reference import CustomerSnapshot


def validate_language_tag(language: str) -> str:
    """Accept extensible BCP-47-style tags; this is syntax checking, not a locale registry."""
    if not isinstance(language, str) or not fullmatch(
        r"[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*", language
    ):
        raise ValueError(f"Invalid language tag: {language!r}")
    return language


@dataclass
class LocalizedText:
    original_language: str
    original: str
    translations: dict[str, str] = field(default_factory=dict)
    stale_languages: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        validate_language_tag(self.original_language)
        seen = {self.original_language.lower()}
        for language in self.translations:
            validate_language_tag(language)
            normalized = language.lower()
            if normalized in seen:
                raise ValueError("Duplicate or source-language translation")
            seen.add(normalized)

    def update_original(self, value: str) -> None:
        if value != self.original:
            self.original = value
            self.stale_languages.update(self.translations)

    def set_translation(self, language: str, text: str) -> None:
        validate_language_tag(language)
        if language.lower() == self.original_language.lower():
            raise ValueError("A translation cannot overwrite the original")
        if any(existing.lower() == language.lower() and existing != language
               for existing in self.translations):
            raise ValueError("Language tag already present with different casing")
        self.translations[language] = text
        self.stale_languages.discard(language)


@dataclass
class ParagraphBlock:
    text: LocalizedText
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class PhotoBlock:
    asset_id: str  # logical ID, not filesystem path or remote URL
    caption: LocalizedText | None = None
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class TableBlock:
    rows: list[list[LocalizedText]]
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class PageBreakBlock:
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class Module:
    title: LocalizedText
    blocks: list[Block] = field(default_factory=list)
    id: str = field(default_factory=lambda: uuid4().hex)


@dataclass
class NestedModuleBlock:
    module: Module
    id: str = field(default_factory=lambda: uuid4().hex)


Block = ParagraphBlock | PhotoBlock | TableBlock | PageBreakBlock | NestedModuleBlock


@dataclass
class Report:
    customer_id: str
    start_date: date
    end_date: date
    primary_language: str
    output_languages: list[str]
    conclusion: Module
    modules: list[Module] = field(default_factory=list)
    ticket: str = ""
    id: str = field(default_factory=lambda: uuid4().hex)
    customer_snapshot: CustomerSnapshot | None = None

    def __post_init__(self) -> None:
        if not self.customer_id.strip() and self.customer_snapshot is None:
            raise ValueError("A customer ID or a manual customer snapshot is required")
        if self.customer_snapshot is not None:
            source_id = self.customer_snapshot.customer_id or ""
            if source_id != self.customer_id:
                raise ValueError("Report customer ID and captured reference disagree")
        if self.start_date > self.end_date:
            raise ValueError("Intervention end date precedes start date")
        validate_language_tag(self.primary_language)
        if not self.output_languages:
            raise ValueError("Select at least one output language")
        for language in self.output_languages:
            validate_language_tag(language)
        normalized = [language.lower() for language in self.output_languages]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate output language")
        # Writing language is independent of export languages. For example,
        # an Italian original may produce only German and French documents.

    def ordered_sections(self) -> tuple[Module, ...]:
        """Conclusion is never interspersed with user-reorderable modules."""
        if any(module.id == self.conclusion.id for module in self.modules):
            raise ValueError("Conclusion cannot also be an intervention module")
        return (*self.modules, self.conclusion)
