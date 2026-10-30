"""Isolated real Chromium integration cases, invoked by test_v2_web.py."""
import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

# Register the private scheme before QApplication, independent of test discovery order.
from reportmaker.v2.web_ui import V2WebMainWindow
from reportmaker.v2.web_origin import ENTRY, StudioPage, trusted_url
from reportmaker.v2.web_smoke import javascript, wait_js
from reportmaker.v2.commands import CommandIntent
from reportmaker.v2.projections import NodeAddress
from reportmaker.v2.adapters.persistence import ProjectPersistence
from reportmaker.project_io import load_project
from reportmaker.model import LocalizedText, Module, ParagraphBlock, PhotoBlock, PhotoVisual
from PySide6.QtCore import QUrl, QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication
from PySide6.QtWidgets import QMessageBox
from PySide6.QtTest import QTest
from PIL import Image
from test_v2_web_commands import sample


class StudioTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.window = V2WebMainWindow(load_website=False, ephemeral_browser=True)
        self.window.core.session.replace_project(sample(), discard_unsaved=True)
        self.window.show()
        wait_js(self.window, self.app, "typeof appState !== 'undefined' && !!appState")

    def tearDown(self):
        self.window._close_approved = True
        self.window.close()
        self.window.deleteLater()
        self.app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.window = None
        self.temp.cleanup()

    def js(self, code):
        return javascript(self.window, self.app, code)

    def wait(self, code):
        wait_js(self.window, self.app, code)

    def action(self, method, *args):
        self.js("window.testDone=false; callBackend(%s, ...%s).then(r => {window.testResult=r;window.testDone=true;}); true" % (json.dumps(method), json.dumps(args)))
        self.wait('window.testDone')
        return self.js('JSON.stringify(window.testResult)')

    def input(self, selector, value):
        self.js("""(() => {const el=document.querySelector(%s); el.focus();
            el.value=%s; el.dispatchEvent(new Event('input',{bubbles:true})); return true;})()""" % (json.dumps(selector), json.dumps(value)))

    def refresh(self):
        self.js("window.testDone=false;sendStudio('get_state',[]).then(r=>{applyBackendResponse(r);window.testDone=true;});true")
        self.wait('window.testDone')

    def test_focused_ctrl_s_saves_and_preserves_caret(self):
        path = Path(self.temp.name) / 'focused.rmproj'
        save = lambda: bool(ProjectPersistence().save(self.window.core.session, path))
        self.input('textarea.block-textarea', '🙂ABCDE!')
        self.js("document.activeElement.setSelectionRange(3,3);window.originalField=document.activeElement;true")
        with patch.object(self.window.core, 'save_project', save):
            self.js("window.dispatchEvent(new KeyboardEvent('keydown',{key:'s',ctrlKey:true,cancelable:true}));true")
            self.wait('pendingDrafts.size===0 && appState.dirty===false')
        report = load_project(path).report
        self.assertEqual(report.modules[0].blocks[1].text.original, '🙂ABCDE!')
        self.assertTrue(report.modules[0].blocks[1].rich.runs[0].bold)
        self.assertEqual(report.modules[0].blocks[1].rich.runs[0].start, 1)
        self.assertTrue(self.js('document.activeElement===window.originalField && document.activeElement.selectionStart===3'))

    def test_validation_keeps_all_drafts_and_prevents_save_then_recovers(self):
        self.input('#metaStartInput', 'not-a-date')
        self.input('textarea.block-textarea', 'ABCDE pending')
        with patch.object(self.window.core, 'save_project') as save:
            self.action('save_project')
            save.assert_not_called()
        self.assertEqual(self.window.core.session.revision, 0)
        self.assertEqual(self.js('pendingDrafts.size'), 2)
        self.assertEqual(self.js("document.querySelector('textarea.block-textarea').value"), 'ABCDE pending')
        self.input('#metaStartInput', '2026-10-30')
        self.action('get_state')
        self.assertEqual(self.js('pendingDrafts.size'), 0)
        self.assertEqual(self.window.core.session.revision, 1)

    def test_discard_and_undo_refresh_live_value(self):
        self.input('textarea.block-textarea', 'Unapplied')
        self.js('window.confirm=()=>true;discardStudioDrafts();true')
        self.assertEqual(self.js("document.querySelector('textarea.block-textarea').value"), 'ABCDE')
        self.input('textarea.block-textarea', 'ABCDEF')
        self.action('undo')
        self.assertEqual(self.js("document.querySelector('textarea.block-textarea').value"), 'ABCDE')
        self.action('redo')
        self.assertEqual(self.js("document.querySelector('textarea.block-textarea').value"), 'ABCDEF')

    def test_heading_six_text_edit_and_table_shape_translation(self):
        module = self.window.core.session.report_snapshot().modules[0]
        self.action('update_heading', module.id, module.blocks[0].id, 'ABCDE', 6)
        self.assertEqual(self.js("document.querySelector('.heading-level-select').value"), '6')
        self.input('.heading-input', 'ABCDEF')
        self.action('mutate_table_shape', module.id, module.blocks[2].id, 'add_row')
        report = self.window.core.session.report_snapshot()
        self.assertEqual(report.modules[0].blocks[0].level, 6)
        self.assertEqual(report.modules[0].blocks[2].rows[0][0].translations['it'], 'Cella')

    def test_structure_preview_and_project_roundtrip(self):
        module = self.window.core.session.report_snapshot().modules[0]
        self.action('add_submodule', module.id, 'Nested synthetic')
        self.action('add_module', 'Second')
        second = self.window.core.session.report_snapshot().modules[-1]
        self.action('move_node', second.id, '', 'up')
        self.action('duplicate_node', module.id, '')
        report = self.window.core.session.report_snapshot()
        self.assertEqual(report.modules[0].id, second.id)
        self.assertEqual(len(report.modules), 3)
        self.assertIn('Nested synthetic', self.js("document.getElementById('previewContent').textContent") or self.js('document.body.textContent'))
        path = Path(self.temp.name) / 'tree.rmproj'
        ProjectPersistence().save(self.window.core.session, path)
        self.assertEqual(load_project(path).report, report)

    def test_hostile_text_and_ids_never_execute_markup(self):
        project = sample()
        hostile = '\"><img src=x onerror="window.compromised=1">\'\\'
        project.report.modules[0].id = hostile
        project.report.modules[0].title.original = hostile
        project.report.modules[0].blocks[1].text.original = 'ABCDE' + hostile
        self.window.core.session.replace_project(project, discard_unsaved=True)
        self.refresh()
        self.assertFalse(self.js('!!window.compromised'))
        self.assertEqual(self.js('document.querySelectorAll("img[src=x]").length'), 0)
        self.input('.module-title-input', 'Safe title')
        self.action('get_state')
        self.assertEqual(self.window.core.session.report_snapshot().modules[0].title.original, 'Safe title')

    def test_navigation_resources_inline_scripts_and_bridge_restricted(self):
        page = self.window.webview.page()
        for url in ('https://example.com', 'file:///etc/passwd', 'data:text/html,hostile', 'rmstudio://evil/index.html'):
            self.assertFalse(page.acceptNavigationRequest(QUrl(url), StudioPage.NavigationType.NavigationTypeLinkClicked, True))
        self.assertFalse(page.acceptNavigationRequest(QUrl(ENTRY), StudioPage.NavigationType.NavigationTypeTyped, False))
        self.assertTrue(self.window.webview.studio_profile.isOffTheRecord())
        self.assertIsNone(self.window.core.chat_tab.browser)
        self.assertTrue(self.js("typeof backend.dispatch==='function' && typeof backend.save_project==='undefined'"))
        self.js("const s=document.createElement('script');s.textContent='window.compromised=1';document.body.appendChild(s);true")
        self.assertFalse(self.js('!!window.compromised'))
        revision = self.window.core.session.revision
        self.js("window.blocked=false;sendStudio('_exec',[]).catch(()=>window.blocked=true);true")
        self.wait('window.blocked')
        self.js("window.blocked=false;sendStudio('add_module',['Wrong'],{revision:-1,generation:appState.generation}).catch(()=>window.blocked=true);true")
        self.wait('window.blocked')
        self.assertEqual(self.window.core.session.revision, revision)
        self.js("window.networkBlocked=false;fetch('https://example.com').catch(()=>window.networkBlocked=true);true")
        self.wait('window.networkBlocked')

    def test_close_cancel_does_not_apply_or_discard(self):
        self.input('textarea.block-textarea', 'ABCDEF')
        self.js('window.confirm=()=>false;requestStudioClose();true')
        self.assertFalse(self.window._close_approved)
        self.assertEqual(self.window.core.session.revision, 0)
        self.assertEqual(self.js('pendingDrafts.size'), 1)

    def test_renderer_failure_has_native_cancel_recovery(self):
        self.window._renderer_loaded(False)
        with patch.object(QMessageBox, 'warning', return_value=QMessageBox.StandardButton.Cancel) as warning:
            self.window.close()
            warning.assert_called_once()
        self.assertTrue(self.window.isVisible())
        self.assertFalse(self.window._close_approved)

    def test_pending_flush_then_delayed_action_keeps_controls_locked(self):
        self.input('#metaTitleInput', 'Synthetic first edit')
        self.js("""window.originalSend=sendStudio;
          sendStudio=(method,args,base)=>window.originalSend(method,args,base).then(r=>
            method==='add_module' ? new Promise(resolve=>setTimeout(()=>resolve(r),800)) : r);
          window.testDone=false;callBackend('add_module','Delayed').then(()=>window.testDone=true);true""")
        self.wait('pendingDrafts.size===0 && queueBusy')
        self.assertTrue(self.js("document.getElementById('metaTitleInput').readOnly"))
        QTest.keyClicks(self.window.webview.focusProxy(), 'X')
        self.wait('window.testDone')
        self.assertEqual(self.js("document.getElementById('metaTitleInput').value"), 'Synthetic first edit')
        self.assertEqual(self.js('pendingDrafts.size'), 0)

    def test_new_and_open_resolve_focused_input(self):
        path = Path(self.temp.name) / 'open.rmproj'
        ProjectPersistence().save(self.window.core.session, path)
        self.input('textarea.block-textarea', 'ABCDE before open')
        observed = []
        def open_existing():
            observed.append(self.window.core.session.report_snapshot().modules[0].blocks[1].text.original)
            ProjectPersistence().open_into(self.window.core.session, path, discard_unsaved=True)
            return True
        with patch.object(self.window.core, 'open_project', open_existing):
            self.action('open_project')
        self.assertEqual(observed, ['ABCDE before open'])
        self.assertEqual(self.js("document.querySelector('textarea.block-textarea').value"), 'ABCDE')
        self.input('textarea.block-textarea', 'ABCDE before new')
        def new_report():
            observed.append(self.window.core.session.report_snapshot().modules[0].blocks[1].text.original)
            self.window.core.session.replace_project(sample(), discard_unsaved=True)
            return True
        with patch.object(self.window.core, 'new_project', new_report):
            self.action('new_project')
        self.assertEqual(observed[-1], 'ABCDE before new')
        self.assertEqual(self.js('pendingDrafts.size'), 0)

    def test_many_cards_patch_payload_lazy_images_and_bounded_cache(self):
        project = sample()
        buf = io.BytesIO(); Image.new('RGB', (24,24), 'blue').save(buf, format='PNG')
        project.assets['synthetic'] = buf.getvalue()
        project.media_library['synthetic'] = 'Synthetic photo'
        for i in range(100):
            project.report.modules.append(Module(LocalizedText('en', f'Module {i}'), [
                ParagraphBlock(LocalizedText('en', 'Synthetic long report')), PhotoBlock('synthetic')]))
        self.window.core.session.replace_project(project, discard_unsaved=True)
        start = time.monotonic()
        self.refresh()
        self.assertLess(time.monotonic() - start, 20)
        self.js("window.retainedCard=document.querySelectorAll('.module-card')[1];true")
        module = self.window.core.session.report_snapshot().modules[0]
        response = json.loads(self.action('rename_module', module.id, 'Changed'))
        self.assertNotIn('state', response)
        self.assertEqual(len(response['patch']['modules_changed']), 1)
        self.assertLess(len(json.dumps(response)), 5000)
        self.assertTrue(self.js("window.retainedCard===document.querySelectorAll('.module-card')[1]"))
        resources = self.window.resources
        key = resources.image_url(buf.getvalue(), PhotoVisual(), 360).rsplit('/',1)[1]
        resources.image_bytes(key)
        count = resources.renders
        resources.image_bytes(key)
        self.assertEqual(resources.renders, count)
        self.assertLessEqual(resources.cache_bytes, resources.CACHE_LIMIT)
        hashed = resources.digest_computations
        self.action('rename_module', module.id, 'Changed again')
        self.assertEqual(resources.digest_computations, hashed)


if __name__ == '__main__':
    unittest.main(verbosity=2)
