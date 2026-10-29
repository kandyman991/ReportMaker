"""Strict, read-only language projection for V2 customer exports.

No network translation and no fallback to source-language strings. Every
nonempty field, including text/callout image annotations, must be explicitly
translated and current before a requested non-source-language output can be
generated. The original editable project is never modified.
"""
from __future__ import annotations

from copy import deepcopy

from ..engine import validate_report_tree
from ..model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, ParagraphBlock,
    PhotoBlock, Report, TableBlock, validate_language_tag,
)
from ..project_io import ReportProject
from ..rich_text import RichFormatting


class TranslationRequiredError(ValueError):
    """A requested language would omit, mix or stale customer-facing text."""


def localized_fields(report: Report):
    """Yield translatable fields in canonical mixed-block document order.

    Nested-module frames use iterators, avoiding recursive depth limits.
    """
    yield (report.id, "report_title"), report.title
    stack = [iter(report.ordered_sections())]
    while stack:
        try:
            item = next(stack[-1])
        except StopIteration:
            stack.pop()
            continue
        if isinstance(item, NestedModuleBlock):
            stack.append(iter((item.module,)))
        elif isinstance(item, Module):
            yield (item.id, "module_title"), item.title
            stack.append(iter(item.blocks))
        elif isinstance(item, (ParagraphBlock, HeadingBlock)):
            yield (item.id, "text"), item.text
        elif isinstance(item, PhotoBlock):
            if item.caption is not None:
                yield (item.id, "caption"), item.caption
            for mark in item.visual.marks:
                if mark.text is not None:
                    yield (item.id, "photo_mark", mark.id), mark.text
        elif isinstance(item, TableBlock):
            for row_idx, row in enumerate(item.rows):
                for col_idx, cell in enumerate(row):
                    yield (item.id, "cell", row_idx, col_idx), cell


def _select(value: LocalizedText, language: str, key: tuple) -> str:
    if language.casefold() == value.original_language.casefold():
        return value.original
    matches = [tag for tag in value.translations if tag.casefold() == language.casefold()]
    # Empty originals may remain empty; explicit target-only text is retained.
    if not value.original and not matches:
        return ""
    if len(matches) != 1:
        raise TranslationRequiredError(
            f"Missing {language} translation for {key!r}; no source-text fallback")
    tag = matches[0]
    if tag in value.stale_languages:
        raise TranslationRequiredError(
            f"Outdated {language} translation for {key!r}; review it before export")
    translated = value.translations[tag]
    if value.original.strip() and not translated.strip():
        raise TranslationRequiredError(
            f"Blank {language} translation for {key!r}; customer content cannot disappear")
    return translated


def localized_project(project: ReportProject, language: str) -> ReportProject:
    """Build detached export source in selected language, rejecting all gaps."""
    if not isinstance(project, ReportProject):
        raise TranslationRequiredError("A project is required for language export")
    validate_language_tag(language)
    source = project.report
    validate_report_tree(source)
    if not any(item.casefold() == language.casefold()
               for item in source.output_languages):
        raise TranslationRequiredError(
            "Output language is not selected in Report Information")
    # The original project and its localization provenance remain untouched.
    result = deepcopy(project)
    original_values = list(localized_fields(source))
    target_values = list(localized_fields(result.report))
    if [key for key, _ in original_values] != [key for key, _ in target_values]:
        raise TranslationRequiredError("Localized report hierarchy changed unexpectedly")
    # Resolve all strings before writing any detached text; errors are atomic.
    translations = [
        _select(value, language, key) for key, value in original_values
    ]
    translated_rich_ids = {
        key[0] for key, original in original_values
        if key[1] == "text" and
        original.original_language.casefold() != language.casefold()
    }
    for (_key, target), value in zip(target_values, translations):
        target.original = value
        # The temporary projection is for output only, not persistence.
        # Clear stale source-language provenance on this detached copy.
        target.translations = {}
        target.stale_languages = set()
        target.original_language = language
    # Source formatting ranges describe source-language character offsets.
    # Until localized formatting has its own schema, translated paragraphs
    # use plain text; never guess spans or export invalid/misapplied styles.
    # Canonical rich source and translation provenance remain untouched.
    stack = list(result.report.ordered_sections())
    while stack:
        module = stack.pop()
        for block in module.blocks:
            if isinstance(block, NestedModuleBlock):
                stack.append(block.module)
            elif isinstance(block, (ParagraphBlock, HeadingBlock)) and block.id in translated_rich_ids:
                block.rich = RichFormatting()
    validate_report_tree(result.report)
    return result
