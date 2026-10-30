"""Bounded actual-renderer smoke for source, frozen and installed HTML mode."""
import json
import time


def javascript(window, app, expression, timeout=20):
    results = []
    window.webview.page().runJavaScript(expression, results.append)
    deadline = time.monotonic() + timeout
    while not results and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    if not results:
        raise RuntimeError("Studio JavaScript callback timed out")
    return results[0]


def wait_js(window, app, expression, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if javascript(window, app, expression):
            return
        time.sleep(.02)
    raise RuntimeError("Studio condition timed out: " + expression)


def exercise_studio(window, app):
    window.show()
    wait_js(window, app, "typeof appState !== 'undefined' && !!appState && !!document.querySelector('.module-card')")
    initial = window.core.session.revision
    javascript(window, app, "callBackend('add_module', 'Offline HTML smoke'); true")
    wait_js(window, app, f"appState.revision > {initial}")
    modules = window.core.session.report_snapshot().modules
    if modules[-1].title.original != "Offline HTML smoke":
        raise RuntimeError("QWebChannel did not change the canonical report")
    module_id = modules[-1].id
    javascript(window, app, f"callBackend('add_block', {json.dumps(module_id)}, 'paragraph'); true")
    wait_js(window, app, f"appState.revision > {initial + 1}")
    paragraph = window.core.session.report_snapshot().modules[-1].blocks[-1]
    javascript(window, app, """(() => {
      const field = [...document.querySelectorAll('[data-block-id]')]
        .find(el => el.dataset.blockId === %s).querySelector('textarea');
      field.focus(); field.value = 'Focused offline input';
      field.dispatchEvent(new Event('input', {bubbles:true}));
      callBackend('undo'); return true;
    })()""" % json.dumps(paragraph.id))
    wait_js(window, app, f"appState.revision > {initial + 3}")
    # Apply is one command and Undo returns to the empty paragraph.
    if window.core.session.report_snapshot().modules[-1].blocks[-1].text.original:
        raise RuntimeError("Focused draft was not applied before Undo")
    javascript(window, app, "callBackend('redo'); true")
    wait_js(window, app, f"appState.revision > {initial + 4}")
    if window.core.session.report_snapshot().modules[-1].blocks[-1].text.original != "Focused offline input":
        raise RuntimeError("Draft/Redo round trip failed")
