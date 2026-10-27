"""Native, offline PySide6 picture composition and non-destructive editor.

All annotation coordinates are normalized to the oriented project working image.
The image asset is read only. Customer export support follows in M4.5.4.
"""
from __future__ import annotations

from copy import deepcopy
from math import hypot
from uuid import uuid4

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPolygonF, QPixmap, QTransform
from PySide6.QtWidgets import (
    QColorDialog, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
    QHBoxLayout, QInputDialog, QLabel, QListWidget, QPushButton, QSlider,
    QSpinBox, QVBoxLayout, QWidget,
)

from .model import LocalizedText, PhotoMark, PhotoVisual, validate_photo_visual

TOOLS = ("select", "crop", "arrow", "line", "rectangle", "ellipse",
         "highlight", "text", "callout", "pen")


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _source_rectangle(image: QImage, visual: PhotoVisual) -> QRectF:
    x, y, w, h = visual.crop
    return QRectF(x * image.width(), y * image.height(),
                  w * image.width(), h * image.height())


def _transformation(visual: PhotoVisual) -> QTransform:
    transform = QTransform()
    transform.rotate(visual.rotation + visual.straighten)
    transform.scale(-1 if visual.flip_h else 1,
                    -1 if visual.flip_v else 1)
    return transform


def _draw_mark(painter: QPainter, mark: PhotoMark, visual: PhotoVisual,
               width: int, height: int) -> None:
    crop_x, crop_y, crop_w, crop_h = visual.crop
    def pt(x, y):
        return QPointF((x - crop_x) / crop_w * width,
                       (y - crop_y) / crop_h * height)
    a, b = pt(mark.x, mark.y), pt(mark.x2, mark.y2)
    scale = max(width, height) / 720
    pen = QPen(QColor(mark.color), max(1.0, mark.thickness * scale))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    if mark.kind == "highlight":
        color = QColor(mark.color)
        color.setAlpha(68)
        painter.setBrush(color)
        painter.drawRect(QRectF(a, b).normalized())
        painter.setBrush(Qt.BrushStyle.NoBrush)
    elif mark.kind == "rectangle":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(a, b).normalized())
    elif mark.kind == "ellipse":
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(a, b).normalized())
    elif mark.kind == "pen":
        if len(mark.points) >= 2:
            path = QPainterPath(pt(*mark.points[0]))
            for xy in mark.points[1:]:
                path.lineTo(pt(*xy))
            painter.drawPath(path)
    elif mark.kind in ("arrow", "line", "callout"):
        painter.drawLine(a, b)
        if mark.kind != "line":
            dx, dy = b.x() - a.x(), b.y() - a.y()
            size = hypot(dx, dy)
            if size > 0.01:
                ux, uy = dx / size, dy / size
                side = max(7.0, 11 * scale)
                wing = max(4.0, 5 * scale)
                triangle = QPolygonF([
                    b, QPointF(b.x() - ux * side - uy * wing,
                               b.y() - uy * side + ux * wing),
                    QPointF(b.x() - ux * side + uy * wing,
                            b.y() - uy * side - ux * wing)])
                painter.setBrush(QColor(mark.color))
                painter.drawPolygon(triangle)
                painter.setBrush(Qt.BrushStyle.NoBrush)
    if mark.kind in ("text", "callout") and mark.text is not None:
        pos = a if mark.kind == "text" else b
        font = painter.font()
        font.setPixelSize(max(10, int(17 * scale)))
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(pos.x(), pos.y() - 50 * scale,
                                max(90, width - pos.x()), 100 * scale),
                         Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                         mark.text.original)


def render_photo(data: bytes, visual: PhotoVisual, max_edge: int = 1000) -> QImage:
    """Compose a bounded temporary view; never mutate or re-encode source bytes."""
    validate_photo_visual(visual)
    if not isinstance(max_edge, int) or not 32 <= max_edge <= 2400:
        raise ValueError("Invalid rendered photo size")
    source = QImage.fromData(data)
    if source.isNull():
        raise ValueError("Invalid project photograph")
    region = _source_rectangle(source, visual)
    factor = min(1.0, max_edge / max(region.width(), region.height()))
    w, h = max(1, int(region.width() * factor)), max(1, int(region.height() * factor))
    layer = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    layer.fill(Qt.GlobalColor.transparent)
    painter = QPainter(layer)
    try:
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawImage(QRectF(0, 0, w, h), source, region)
        painter.setClipRect(QRectF(0, 0, w, h))
        for mark in visual.marks:
            _draw_mark(painter, mark, visual, w, h)
    finally:
        painter.end()
    return layer.transformed(_transformation(visual),
                             Qt.TransformationMode.SmoothTransformation)


class PictureCanvas(QWidget):
    """Mouse-driven creation, selection and movement in stable source coordinates."""

    def __init__(self, owner, image_bytes: bytes):
        super().__init__(owner)
        self.owner = owner
        self.image_bytes = image_bytes
        self.preview = QImage()
        self.base_size = (1, 1)
        self.rect = QRectF()
        self.selected: str | None = None
        self.tool = "select"
        self.start = None
        self.current = None
        self.trace = []
        self.dragging_id = None
        self.setMinimumSize(470, 330)
        self.setMouseTracking(True)
        self.update_image()

    def update_image(self):
        visual = self.owner.visual
        self.preview = render_photo(self.image_bytes, visual, 900)
        source = QImage.fromData(self.image_bytes)
        region = _source_rectangle(source, visual)
        factor = min(1.0, 900 / max(region.width(), region.height()))
        self.base_size = (max(1, int(region.width() * factor)),
                          max(1, int(region.height() * factor)))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect if False else self.contentsRect(), QColor("#24282c"))
        if self.preview.isNull():
            return
        scale = min((self.width() - 16) / self.preview.width(),
                    (self.height() - 16) / self.preview.height())
        w, h = self.preview.width() * scale, self.preview.height() * scale
        self.rect = QRectF((self.width() - w) / 2, (self.height() - h) / 2, w, h)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(self.rect, self.preview)
        if self.start and self.current and self.tool != "select":
            a, b = self._onscreen(self.start), self._onscreen(self.current)
            painter.setPen(QPen(QColor("#00d4ff"), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            if self.tool in ("crop", "rectangle", "highlight", "ellipse"):
                painter.drawRect(QRectF(a, b).normalized())
            else:
                painter.drawLine(a, b)
        painter.end()

    def _coordinate(self, pos):
        if self.rect.isNull() or not self.rect.contains(QPointF(pos)):
            return None
        rendered = QPointF((pos.x() - self.rect.x()) / self.rect.width() *
                           self.preview.width(),
                           (pos.y() - self.rect.y()) / self.rect.height() *
                           self.preview.height())
        matrix = QImage.trueMatrix(_transformation(self.owner.visual), *self.base_size)
        inverse, ok = matrix.inverted()
        if not ok:
            return None
        original = inverse.map(rendered)
        x0, y0, cw, ch = self.owner.visual.crop
        return (round(_clamp(x0 + original.x() / self.base_size[0] * cw), 6),
                round(_clamp(y0 + original.y() / self.base_size[1] * ch), 6))

    def _onscreen(self, value):
        # Preview overlay is approximate for drag feedback; final render is canonical.
        x0, y0, cw, ch = self.owner.visual.crop
        pos = QPointF((value[0] - x0) / cw * self.base_size[0],
                      (value[1] - y0) / ch * self.base_size[1])
        matrix = QImage.trueMatrix(_transformation(self.owner.visual), *self.base_size)
        out = matrix.map(pos)
        return QPointF(self.rect.left() + out.x() / self.preview.width() * self.rect.width(),
                       self.rect.top() + out.y() / self.preview.height() * self.rect.height())

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        value = self._coordinate(event.position())
        if value is None:
            return
        self.start = value
        self.current = value
        self.trace = [value]
        self.dragging_id = None
        if self.tool == "select":
            marks = list(reversed(self.owner.visual.marks))
            hit = next((mark for mark in marks
                        if min(mark.x, mark.x2)-0.025 <= value[0] <= max(mark.x, mark.x2)+0.025
                        and min(mark.y, mark.y2)-0.025 <= value[1] <= max(mark.y, mark.y2)+0.025),
                       None)
            self.selected = hit.id if hit else None
            self.owner.sync_marks(self.selected)
            if hit:
                self.dragging_id = hit.id
                self.owner.checkpoint()

    def mouseMoveEvent(self, event):
        if self.start is None:
            return
        value = self._coordinate(event.position())
        if value is None:
            return
        if self.tool == "select" and self.dragging_id:
            mark = next((x for x in self.owner.visual.marks if x.id == self.dragging_id), None)
            if mark:
                dx, dy = value[0] - self.current[0], value[1] - self.current[1]
                mark.x, mark.x2 = _clamp(mark.x + dx), _clamp(mark.x2 + dx)
                mark.y, mark.y2 = _clamp(mark.y + dy), _clamp(mark.y2 + dy)
                mark.points = [(_clamp(x + dx), _clamp(y + dy))
                               for x, y in mark.points]
                self.update_image()
        elif self.tool == "pen" and len(self.trace) < 500:
            self.trace.append(value)
        self.current = value
        self.update()

    def mouseReleaseEvent(self, event):
        if self.start is None:
            return
        finish = self._coordinate(event.position()) or self.current or self.start
        start = self.start
        self.start = None
        self.current = None
        if self.tool == "select":
            self.dragging_id = None
            self.update_image()
            return
        if self.tool == "crop":
            x, y = min(start[0], finish[0]), min(start[1], finish[1])
            w, h = abs(finish[0] - start[0]), abs(finish[1] - start[1])
            if w >= 0.01 and h >= 0.01:
                self.owner.checkpoint()
                self.owner.visual.crop = (x, y, min(w, 1-x), min(h, 1-y))
        else:
            if self.tool not in ("text", "callout") and hypot(
                finish[0] - start[0], finish[1] - start[1]) < 0.006:
                self.update_image()
                return
            text = None
            if self.tool in ("text", "callout"):
                value, ok = QInputDialog.getMultiLineText(
                    self, "Photo label", "Visible technical label:")
                if not ok or len(value) > 500:
                    self.update_image()
                    return
                text = LocalizedText(self.owner.language, value)
            points = list(self.trace) if self.tool == "pen" else []
            if self.tool == "pen" and len(points) < 2:
                self.update_image()
                return
            self.owner.checkpoint()
            mark = PhotoMark(self.tool, *start, *finish,
                             color=self.owner.current_color,
                             thickness=self.owner.current_thickness,
                             text=text, points=points)
            self.owner.visual.marks.append(mark)
            self.selected = mark.id
            self.owner.sync_marks(mark.id)
        self.owner.changed()
        self.update_image()


class PictureEditorDialog(QDialog):
    def __init__(self, parent, image_bytes: bytes, visual: PhotoVisual,
                 language: str):
        super().__init__(parent)
        validate_photo_visual(visual)
        self.setWindowTitle("Picture editor — editable layers / original preserved")
        self.setObjectName("pictureEditorDialog")
        self.resize(950, 720)
        self.visual = deepcopy(visual)
        self.language = language
        self.current_color = "#e02020"
        self.current_thickness = 3
        self._undo = []
        self._redo = []
        root = QVBoxLayout(self)
        self.canvas = PictureCanvas(self, image_bytes)
        self.canvas.setObjectName("pictureEditorCanvas")
        tools = QHBoxLayout()
        self.tool_choice = QComboBox()
        self.tool_choice.setObjectName("pictureAnnotationTool")
        for kind in TOOLS:
            self.tool_choice.addItem(kind.capitalize(), kind)
        self.tool_choice.currentIndexChanged.connect(
            lambda *_: setattr(self.canvas, "tool", self.tool_choice.currentData()))
        tools.addWidget(self.tool_choice)
        color = QPushButton("Color")
        color.clicked.connect(self.choose_color)
        tools.addWidget(color)
        weight = QSpinBox()
        weight.setRange(1, 16)
        weight.setValue(3)
        weight.valueChanged.connect(lambda val: setattr(self, "current_thickness", val))
        tools.addWidget(QLabel("Line"))
        tools.addWidget(weight)
        edit = QPushButton("Edit label")
        edit.clicked.connect(self.edit_selected_text)
        tools.addWidget(edit)
        delete = QPushButton("Delete mark")
        delete.clicked.connect(self.delete_selected)
        tools.addWidget(delete)
        undo = QPushButton("Undo")
        undo.clicked.connect(self.undo)
        tools.addWidget(undo)
        redo = QPushButton("Redo")
        redo.clicked.connect(self.redo)
        tools.addWidget(redo)
        root.addLayout(tools)
        root.addWidget(self.canvas, 1)

        props = QHBoxLayout()
        self.width = QSpinBox()
        self.width.setObjectName("pictureLayoutWidthPercent")
        self.width.setRange(20, 100)
        self.width.setSuffix("% report width")
        self.width.setValue(self.visual.width_pct)
        self.width.valueChanged.connect(lambda v: self.change_property("width_pct", v))
        props.addWidget(self.width)
        self.align = QComboBox()
        for value in ("left", "center", "right"):
            self.align.addItem(value.capitalize(), value)
        self.align.setCurrentIndex(("left", "center", "right").index(self.visual.alignment))
        self.align.currentIndexChanged.connect(
            lambda *_: self.change_property("alignment", self.align.currentData()))
        props.addWidget(self.align)
        self.straighten = QSlider(Qt.Orientation.Horizontal)
        self.straighten.setObjectName("pictureStraightenDegrees")
        self.straighten.setRange(-15, 15)
        self.straighten.setValue(self.visual.straighten)
        self.straighten.sliderReleased.connect(
            lambda: self.change_property("straighten", self.straighten.value()))
        props.addWidget(QLabel("Straighten"))
        props.addWidget(self.straighten)
        for text, callback in (
            ("Rotate 90°", self.rotate), ("Flip H", lambda: self.flip("flip_h")),
            ("Flip V", lambda: self.flip("flip_v")), ("Reset crop", self.reset_crop)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            props.addWidget(button)
        root.addLayout(props)
        self.marks = QListWidget()
        self.marks.setObjectName("pictureMarkList")
        self.marks.setMaximumHeight(92)
        self.marks.currentRowChanged.connect(self.mark_selected)
        root.addWidget(self.marks)
        root.addWidget(QLabel("Annotations remain editable in .rmproj. DOCX/PDF "
                              "export of edited pictures requires M4.5.4."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.sync_marks()

    def checkpoint(self):
        self._undo.append(deepcopy(self.visual))
        del self._undo[:-80]
        self._redo.clear()

    def changed(self):
        validate_photo_visual(self.visual)
        self.canvas.update_image()

    def undo(self):
        if self._undo:
            self._redo.append(deepcopy(self.visual))
            self.visual = self._undo.pop()
            self._refresh_controls()

    def redo(self):
        if self._redo:
            self._undo.append(deepcopy(self.visual))
            self.visual = self._redo.pop()
            self._refresh_controls()

    def _refresh_controls(self):
        self.width.blockSignals(True)
        self.width.setValue(self.visual.width_pct)
        self.width.blockSignals(False)
        self.align.blockSignals(True)
        self.align.setCurrentIndex(("left", "center", "right").index(self.visual.alignment))
        self.align.blockSignals(False)
        self.straighten.setValue(self.visual.straighten)
        self.sync_marks()
        self.changed()

    def sync_marks(self, selected=None):
        self.marks.blockSignals(True)
        self.marks.clear()
        for mark in self.visual.marks:
            summary = mark.text.original[:35] if mark.text else mark.kind
            self.marks.addItem(f"{mark.kind}: {summary}")
        index = next((i for i, mark in enumerate(self.visual.marks)
                      if mark.id == selected), -1)
        self.marks.setCurrentRow(index)
        self.marks.blockSignals(False)

    def mark_selected(self, index):
        self.canvas.selected = (self.visual.marks[index].id
                                if 0 <= index < len(self.visual.marks) else None)

    def choose_color(self):
        color = QColorDialog.getColor(QColor(self.current_color), self)
        if color.isValid():
            self.current_color = color.name()

    def delete_selected(self):
        key = self.canvas.selected
        if key:
            self.checkpoint()
            self.visual.marks = [m for m in self.visual.marks if m.id != key]
            self.canvas.selected = None
            self.sync_marks()
            self.changed()

    def edit_selected_text(self):
        mark = next((m for m in self.visual.marks
                     if m.id == self.canvas.selected), None)
        if mark is None or mark.text is None:
            return
        new, ok = QInputDialog.getMultiLineText(self, "Edit label",
                                                "Visible technical text:",
                                                mark.text.original)
        if ok and len(new) <= 500:
            self.checkpoint()
            mark.text.update_original(new)  # M5 marks translations stale
            self.changed()
            self.sync_marks(mark.id)

    def change_property(self, key, value):
        if getattr(self.visual, key) != value:
            self.checkpoint()
            setattr(self.visual, key, value)
            self.changed()

    def rotate(self):
        self.change_property("rotation", (self.visual.rotation + 90) % 360)

    def flip(self, key):
        self.change_property(key, not getattr(self.visual, key))

    def reset_crop(self):
        self.change_property("crop", (0.0, 0.0, 1.0, 1.0))

    def accept(self):
        validate_photo_visual(self.visual)
        super().accept()
