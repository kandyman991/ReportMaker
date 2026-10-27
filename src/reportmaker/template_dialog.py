"""Native, local-only visual controls for a portable Word-derived page template."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QVBoxLayout,
)

from .template_import import DocumentTemplate, TemplateError, validate_template, MAX_LOGO


def edit_template_layout(owner, source: DocumentTemplate,
                         *, warnings: tuple[str, ...] = ()) -> DocumentTemplate | None:
    """Review and edit supported page/header/footer fields; Cancel changes nothing."""
    dialog = QDialog(owner)
    dialog.setObjectName("templateLayoutDialog")
    dialog.setWindowTitle("Word template — local layout editor")
    dialog.resize(600, 660)
    root = QVBoxLayout(dialog)
    if warnings:
        summary = QLabel(
            "Unsupported Word elements are NOT copied. Review before accepting:\n"
            + "\n".join("• " + item for item in warnings[:18])
            + ("\n• Further unsupported items omitted" if len(warnings) > 18 else ""))
        summary.setTextFormat(Qt.TextFormat.PlainText)
        summary.setWordWrap(True)
        summary.setObjectName("templateImportWarnings")
        root.addWidget(summary)
    pane = QHBoxLayout()
    root.addLayout(pane, 1)
    settings = QFormLayout()
    pane.addLayout(settings, 3)
    numeric = {}
    for name, label, bounds in (
        ("page_width_cm", "Page width (cm)", (15, 43)),
        ("page_height_cm", "Page height (cm)", (15, 60)),
        ("left_margin_cm", "Left margin (cm)", (.5, 7)),
        ("right_margin_cm", "Right margin (cm)", (.5, 7)),
        ("top_margin_cm", "Top margin (cm)", (.5, 7)),
        ("bottom_margin_cm", "Bottom margin (cm)", (.5, 7)),
        ("header_distance_cm", "Header position (cm)", (.3, 7)),
        ("footer_distance_cm", "Footer position (cm)", (.3, 7)),
        ("normal_size_pt", "Normal text (pt)", (6, 72)),
        ("heading_size_pt", "Heading 1 text (pt)", (8, 40)),
    ):
        spin = QDoubleSpinBox(dialog)
        spin.setObjectName("template_" + name)
        spin.setRange(*bounds)
        spin.setDecimals(2)
        spin.setSingleStep(.1)
        spin.setValue(getattr(source, name))
        settings.addRow(label, spin)
        numeric[name] = spin
    text_fields = {}
    for name, label in (
        ("header_text", "Header text"),
        ("footer_text", "Footer text"),
        ("normal_font", "Normal Word font"),
        ("heading_font", "Heading 1 Word font"),
    ):
        control = QLineEdit(getattr(source, name))
        control.setObjectName("template_" + name)
        control.setMaxLength(120 if name != "normal_font" else 96)
        settings.addRow(label, control)
        text_fields[name] = control
    logo = [source.logo]
    image_preview = QLabel()
    image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    image_preview.setMinimumSize(100, 40)
    image_preview.setMaximumHeight(85)
    def show_logo():
        image = QImage.fromData(logo[0])
        image_preview.setPixmap(QPixmap.fromImage(image.scaled(
            240, 70, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)) if not image.isNull()
            else QPixmap())
        image_preview.setText("" if logo[0] else "(No logo)")
    show_logo()
    settings.addRow("Header logo", image_preview)
    buttons = QHBoxLayout()
    browse = QPushButton("Choose local logo")
    remove = QPushButton("Remove")
    def select_logo():
        filename, _ = QFileDialog.getOpenFileName(dialog, "Local logo", "",
                                                    "Images (*.png *.jpg *.jpeg *.webp)")
        if filename:
            path = Path(filename)
            try:
                if path.stat().st_size > MAX_LOGO:
                    raise TemplateError("Logo exceeds 2 MiB")
                candidate = path.read_bytes()
                validate_template(replace(source, logo=candidate))
                logo[0] = candidate
                show_logo()
            except (OSError, ValueError) as exc:
                QMessageBox.warning(dialog, "Invalid logo", str(exc))
    browse.clicked.connect(select_logo)
    remove.clicked.connect(lambda: (logo.__setitem__(0, b""), show_logo()))
    buttons.addWidget(browse)
    buttons.addWidget(remove)
    settings.addRow(buttons)

    paper = QFrame()
    paper.setObjectName("templatePaperPreview")
    paper.setStyleSheet("QFrame#templatePaperPreview { background: white; color: #202124; "
                        "border: 1px solid #b6bcc4; } "
                        "QFrame#templatePaperPreview QLabel { color: #202124; }")
    paper.setMinimumWidth(156)
    paper.setMaximumWidth(210)
    paperbox = QVBoxLayout(paper)
    paper_header = QLabel()
    paper_header.setTextFormat(Qt.TextFormat.PlainText)
    paper_header.setWordWrap(True)
    mock_body = QLabel("Report title\n\nReport information\n\nSummary\n\n"
                       "1  Intervention\n\nEditable report content…")
    mock_body.setWordWrap(True)
    mock_body.setStyleSheet("background: #edf1f6; padding: 6px;")
    paper_footer = QLabel()
    paper_footer.setTextFormat(Qt.TextFormat.PlainText)
    paper_footer.setWordWrap(True)
    paperbox.addWidget(paper_header)
    paperbox.addWidget(mock_body, 1)
    paperbox.addWidget(paper_footer)
    pane.addWidget(paper, 2)
    def refresh_preview(*_):
        w, h = numeric["page_width_cm"].value(), numeric["page_height_cm"].value()
        paper.setToolTip(f"{w:g} × {h:g} cm — schematic preview, not Word pagination")
        paper_header.setText(text_fields["header_text"].text() or "(Header)")
        paper_footer.setText(text_fields["footer_text"].text() + "   Page 1")
    for field in numeric.values():
        field.valueChanged.connect(refresh_preview)
    for field in text_fields.values():
        field.textChanged.connect(refresh_preview)
    refresh_preview()
    foot = QLabel("The page is schematic. Word shapes, tables, floating objects and "
                  "exact font metrics are not reproduced. No report content is imported.")
    foot.setWordWrap(True)
    root.addWidget(foot)
    actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                               QDialogButtonBox.StandardButton.Cancel)
    root.addWidget(actions)
    accepted = [None]
    def accept():
        values = {name: widget.value() for name, widget in numeric.items()}
        values.update({name: widget.text() for name, widget in text_fields.items()})
        try:
            proposed = validate_template(DocumentTemplate(**values, logo=logo[0]))
        except TemplateError as exc:
            QMessageBox.warning(dialog, "Unsupported template layout", str(exc))
            return
        accepted[0] = proposed
        dialog.accept()
    actions.accepted.connect(accept)
    actions.rejected.connect(dialog.reject)
    return accepted[0] if dialog.exec() == QDialog.DialogCode.Accepted else None
