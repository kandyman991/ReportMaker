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
    HeadingBlock, LocalizedText, NestedModuleBlock, ParagraphBlock,
    PhotoBlock, Report, TableBlock, validate_language_tag,
)
from ..project_io import ReportProject


class TranslationRequiredError(ValueError):
    """A requested language would omit, mix or stale customer-facing text."""


def localized_fields(report: Report):
    """Canonical, iterative fields in export order; no separately stored tree.

    Key components are immutable node IDs plus a field marker and optional
    zero-based cell coordinates or persistent photo-mark IDs.
    """
    yield (report.id, "report_title"), report.title
    stack = list(reversed(report.ordered_sections()))
    while stack:
        module = stack.pop()
        yield (module.id, "module_title"), module.title
        for block in reversed(module.blocks):
            if isinstance(block, NestedModuleBlock):
                stack.append(block.module)
            elif isinstance(block, (ParagraphBlock, HeadingBlock)):
                yield (block.id, "text"), block.text
            elif isinstance(block, PhotoBlock):
                if block.caption is not None:
                    yield (block.id, "caption"), block.caption
                for mark in block.visual.marks:
                    if mark.text is not None:
                        yield (block.id, "photo_mark", mark.id), mark.text
            elif isinstance(block, TableBlock):
                for row_idx, row in enumerate(block.rows):
                    for col_idx, cell in enumerate(row):
                        yield (block.id, "cell", row_idx, col_idx), cell


def _select(value: LocalizedText, language: str, key: tuple) -> str:
    if language.casefold() == value.original_language.casefold():
        return value.original
    if not value.original:
        return ""  # Empty source text is genuinely empty, not fallback.
    matches = [tag for tag in value.translations if tag.casefold() == language.casefold()]
    if len(matches) != 1:
        raise TranslationRequiredError(
            f"Missing {language} translation for {key!r}; no source-text fallback")
    tag = matches[0]
    if tag in value.stale_languages:
        raise TranslationRequiredError(
            f"Outdated {language} translation for {key!r}; review it before export")
    return value.translations[tag]


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
    for (_key, target), value in zip(target_values, translations):
        target.original = value
        # The temporary projection is for output only, not persistence.
        # Clear stale source-language provenance on this detached copy.
        target.translations = {}
        target.stale_languages = set()
        target.original_language = language
    validate_report_tree(result.report)
    return result
