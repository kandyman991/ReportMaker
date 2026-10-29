"""Pure, validated table draft transformations. No Qt, no parallel document."""
from __future__ import annotations

from copy import deepcopy

from ...model import LocalizedText, validate_language_tag, validate_localized_text


def checked_rows(rows: object) -> list[list[LocalizedText]]:
    if not isinstance(rows, list) or any(not isinstance(row, list) for row in rows):
        raise ValueError("Table rows must be a list of cell lists")
    for row in rows:
        for cell in row:
            validate_localized_text(cell)
    return deepcopy(rows)


def edit_cell(rows: list[list[LocalizedText]], row: int, column: int,
              value: str) -> list[list[LocalizedText]]:
    copy = checked_rows(rows)
    if (type(row) is not int or type(column) is not int
            or row < 0 or row >= len(copy)
            or column < 0 or column >= len(copy[row])):
        raise ValueError("Cell is outside the table")
    if not isinstance(value, str):
        raise ValueError("Cell source must be text")
    copy[row][column].update_original(value)
    return copy


def change_grid(rows: list[list[LocalizedText]], operation: str, index: int,
                language: str) -> list[list[LocalizedText]]:
    copy = checked_rows(rows)
    validate_language_tag(language)
    if type(index) is not int or index < 0:
        raise ValueError("Table position must be a non-negative integer")
    widths = {len(row) for row in copy}
    if len(widths) > 1:
        raise ValueError("Resize a ragged table explicitly before changing its structure")
    width = next(iter(widths), 1)
    if operation == "insert_row":
        if index > len(copy):
            raise ValueError("Row position exceeds the table")
        if copy and width == 0:
            raise ValueError("Add a column before inserting rows into a zero-column table")
        copy.insert(index, [LocalizedText(language, "") for _ in range(max(1, width))])
    elif operation == "delete_row":
        if not 0 <= index < len(copy) or len(copy) <= 1:
            raise ValueError("Cannot delete the final row or a missing row")
        copy.pop(index)
    elif operation == "insert_column":
        if not copy or index > width:
            raise ValueError("Column position exceeds the table")
        for row in copy:
            row.insert(index, LocalizedText(language, ""))
    elif operation == "delete_column":
        if not copy or not 0 <= index < width or width <= 1:
            raise ValueError("Cannot delete the final column or a missing column")
        for row in copy:
            row.pop(index)
    else:
        raise ValueError("Unsupported table operation")
    return copy
