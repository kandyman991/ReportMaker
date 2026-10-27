"""Independent PR #19 regression gates: geometry, history and version boundaries."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile, ZIP_DEFLATED

from PIL import Image

from reportmaker.model import PhotoMark, PhotoVisual, validate_photo_visual
from reportmaker.project_io import load_project, save_project
from test_m4_export import synthetic_project


def _rewrite_manifest(path: Path, mutate):
    with ZipFile(path) as archive:
        records = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(records['manifest.json'])
    mutate(manifest)
    records['manifest.json'] = json.dumps(manifest).encode('utf-8')
    with ZipFile(path, 'w', ZIP_DEFLATED) as archive:
        for name, data in records.items():
            archive.writestr(name, data)


def _first_photo_json(manifest):
    return manifest['report']['modules'][0]['blocks'][1]['module']['blocks'][1]


class SchemaRegression(unittest.TestCase):
    def test_invalid_unhashable_annotation_kind_fails_closed(self):
        for invalid in ([], {'name': 'line'}):
            visual = PhotoVisual(marks=[PhotoMark(invalid, .2, .2, .8, .8)])
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_photo_visual(visual)
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'project.rmproj'
            save_project(synthetic_project(), path)
            _rewrite_manifest(path, lambda m: _first_photo_json(m)['visual']['marks'].append({
                'id': 'a' * 32, 'kind': [], 'x': .2, 'y': .2, 'x2': .8,
                'y2': .8, 'color': '#ffffff', 'thickness': 3,
                'text': None, 'points': []}))
            with self.assertRaises(ValueError):
                load_project(path)

    def test_v2_cannot_smuggle_v3_visual_layer(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'project.rmproj'
            save_project(synthetic_project(), path)
            _rewrite_manifest(path, lambda m: m.update(version=2))
            with self.assertRaisesRegex(ValueError, 'Legacy photo'):
                load_project(path)


class QtGeometryHistoryRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from PySide6.QtWidgets import QApplication
            from reportmaker.photo_editor import PictureEditorDialog
        except ImportError:
            raise unittest.SkipTest('Qt desktop dependencies unavailable')
        cls.app = QApplication.instance() or QApplication([])

    def _dialog(self, visual):
        from reportmaker.photo_editor import PictureEditorDialog
        buf = BytesIO()
        Image.new('RGB', (600, 350), (43, 91, 111)).save(buf, format='PNG')
        dialog = PictureEditorDialog(None, buf.getvalue(), visual, 'en')
        dialog.show()
        self.app.processEvents()
        self.addCleanup(dialog.close)
        return dialog

    def test_rotated_padding_is_not_an_editable_image_coordinate(self):
        from PySide6.QtCore import QPointF
        dialog = self._dialog(PhotoVisual(straighten=12, crop=(.1,.1,.8,.8)))
        canvas = dialog.canvas
        corner = QPointF(canvas._display_rect.left() + 2,
                          canvas._display_rect.top() + 2)
        self.assertIsNone(canvas._coordinate(corner))
        for visual in (PhotoVisual(rotation=90, straighten=12, flip_h=True,
                                   crop=(.12,.15,.73,.66)),
                       PhotoVisual(rotation=270, straighten=-9, flip_v=True)):
            dialog.visual = deepcopy(visual)
            canvas.update_image()
            self.app.processEvents()
            original = (.45, .4)
            roundtrip = canvas._coordinate(canvas._onscreen(original))
            self.assertIsNotNone(roundtrip)
            self.assertAlmostEqual(roundtrip[0], original[0], places=4)
            self.assertAlmostEqual(roundtrip[1], original[1], places=4)
        # The model allows a one-ppm numerical tolerance on the crop boundary.
        # A mouse hit at that final pixel still must produce valid coordinates.
        dialog.visual = PhotoVisual(crop=(.9900005, 0, .01, 1))
        canvas.update_image()
        self.app.processEvents()
        end = canvas._coordinate(canvas._onscreen((1.0000002, .5)))
        self.assertIsNotNone(end)
        self.assertLessEqual(end[0], 1)

    def test_click_does_not_consume_history_and_move_preserves_shape(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        mark = PhotoMark('rectangle', .2, .2, .8, .8)
        visual = PhotoVisual(marks=[mark])
        dialog = self._dialog(visual)
        dialog.rotate()
        dialog.undo()  # one redo entry must survive selection-only click
        self.assertEqual(len(dialog._redo), 1)
        canvas = dialog.canvas
        center = canvas._onscreen((.5, .5))
        click = QPoint(round(center.x()), round(center.y()))
        QTest.mouseClick(canvas, Qt.MouseButton.LeftButton, pos=click)
        self.assertEqual(len(dialog._redo), 1)
        self.assertEqual(len(dialog._undo), 0)
        target = canvas._onscreen((.9, .5))
        end = QPoint(round(target.x()), round(target.y()))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=click)
        QTest.mouseMove(canvas, end)
        # Returning slightly from an overshot cursor must stay pinned at the
        # image edge until the cursor crosses the actual clamping threshold.
        overshoot_return = canvas._onscreen((.8, .5))
        return_pos = QPoint(round(overshoot_return.x()),
                            round(overshoot_return.y()))
        QTest.mouseMove(canvas, return_pos)
        self.assertAlmostEqual(dialog.visual.marks[0].x2, 1, places=4)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=return_pos)
        moved = dialog.visual.marks[0]
        self.assertAlmostEqual(moved.x2 - moved.x, .6, places=4)
        self.assertAlmostEqual(moved.y2 - moved.y, .6, places=4)
        self.assertAlmostEqual(moved.x2, 1, places=4)
        self.assertEqual(len(dialog._undo), 1)
        self.assertEqual(len(dialog._redo), 0)
        dialog.undo()
        self.assertEqual(dialog.visual.marks, visual.marks)
        dialog.redo()
        self.assertEqual(dialog.visual.marks[0], moved)

    def test_annotation_capacity_is_handled_without_mutating_visual(self):
        from unittest.mock import patch
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        marks = [PhotoMark('line', .2, .2, .8, .8) for _ in range(120)]
        dialog = self._dialog(PhotoVisual(marks=marks))
        dialog.tool_choice.setCurrentIndex(dialog.tool_choice.findData('arrow'))
        canvas = dialog.canvas
        first, last = canvas._onscreen((.1,.1)), canvas._onscreen((.4,.4))
        start = QPoint(round(first.x()),round(first.y()))
        end = QPoint(round(last.x()),round(last.y()))
        with patch('reportmaker.photo_editor.QMessageBox.warning') as warning:
            QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
            QTest.mouseMove(canvas, end)
            QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
            warning.assert_called_once()
        self.assertEqual(dialog.visual.marks, marks)
        self.assertEqual(dialog._undo, [])

    def test_pen_geometry_translates_as_unit_at_boundary(self):
        from PySide6.QtCore import Qt, QPoint
        from PySide6.QtTest import QTest
        mark = PhotoMark('pen', .2, .2, .94, .8,
                         points=[(.2,.2), (.6,.5), (.94,.8)])
        dialog = self._dialog(PhotoVisual(marks=[mark]))
        canvas = dialog.canvas
        origin = canvas._onscreen((.5,.5))
        destination = canvas._onscreen((.8,.5))
        start = QPoint(round(origin.x()),round(origin.y()))
        end = QPoint(round(destination.x()),round(destination.y()))
        QTest.mousePress(canvas, Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(canvas, end)
        QTest.mouseRelease(canvas, Qt.MouseButton.LeftButton, pos=end)
        result = dialog.visual.marks[0]
        self.assertAlmostEqual(result.x2, 1, places=4)
        for original, moved in zip(mark.points, result.points):
            self.assertAlmostEqual(moved[0] - original[0], .06, places=4)
            self.assertAlmostEqual(moved[1], original[1], places=4)
        dialog.undo()
        self.assertEqual(dialog.visual.marks[0], mark)


if __name__ == '__main__':
    unittest.main()
