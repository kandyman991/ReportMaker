"""Run actual QWebEngine/QWebChannel tests in a fresh Qt process."""
import os
from pathlib import Path
import subprocess
import sys
import unittest


class WebRendererTests(unittest.TestCase):
    def test_actual_renderer_and_channel(self):
        root = Path(__file__).resolve().parents[1]
        env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                   QTWEBENGINE_CHROMIUM_FLAGS='--disable-gpu', PYTHONIOENCODING='utf-8')
        result = subprocess.run([sys.executable, str(root/'tests/_web_studio_cases.py')],
                                cwd=root, env=env, capture_output=True, text=True,
                                encoding='utf-8', timeout=240)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
