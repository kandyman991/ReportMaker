"""Pure M6 mapping from validated local Word templates to export presentation.

Template selection must never write page attributes into the report model.
Unsupported Word objects remain warnings of the existing safe importer.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..export import ExportStyle, _validate_style
from ..template_import import DocumentTemplate, validate_template


def style_from_template(template: DocumentTemplate) -> ExportStyle:
    data = validate_template(template)
    return _validate_style(ExportStyle(
        company_name=data.header_text,
        footer_note=data.footer_text,
        logo=data.logo,
        page_width_cm=data.page_width_cm,
        page_height_cm=data.page_height_cm,
        left_margin_cm=data.left_margin_cm,
        right_margin_cm=data.right_margin_cm,
        top_margin_cm=data.top_margin_cm,
        bottom_margin_cm=data.bottom_margin_cm,
        header_distance_cm=data.header_distance_cm,
        footer_distance_cm=data.footer_distance_cm,
        normal_font=data.normal_font,
        normal_size_pt=data.normal_size_pt,
        heading_font=data.heading_font,
        heading_size_pt=data.heading_size_pt,
    ))
