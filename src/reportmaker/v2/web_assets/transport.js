// Presentation drafts only. Canonical validation, rich ranges and translations
// remain in Python. All shortcuts, proof/export and close share this queue.
let pendingDrafts = new Map();
let draftBase = null;
let actionQueue = Promise.resolve();
let draftSerial = 0;
let applying = false;
let queueBusy = false;
let lockedControls = new Map();

function lockStudioControls() {
  if (!queueBusy) return;
  for (const el of document.querySelectorAll('#canvasContainer input, #canvasContainer textarea, #canvasContainer select')) {
    if (!lockedControls.has(el)) lockedControls.set(el, [el.readOnly, el.disabled]);
    if (el.tagName === 'SELECT') el.disabled = true;
    else el.readOnly = true;
  }
}

function draftKey(method, args) {
  return method === 'update_report_header' ? 'metadata' : JSON.stringify([method, ...args.slice(0, method === 'rename_module' ? 1 : 2)]);
}

function stageDraft(method, ...args) {
  if (!appState) return;
  if (!draftBase) draftBase = {revision: appState.revision, generation: appState.generation};
  const key = draftKey(method, args);
  pendingDrafts.set(key, {method, args, serial: ++draftSerial});
  updateDraftStatus();
}

function updateDraftStatus() {
  const count = pendingDrafts.size;
  document.getElementById('draftStatus').textContent = count ? `${count} pending field edit(s)` : 'All edits applied';
  document.getElementById('applyDrafts').disabled = !count || applying;
  document.getElementById('discardDrafts').disabled = !count || applying;
}

function sendStudio(method, args, base = null) {
  return new Promise((resolve, reject) => {
    if (!backend) { reject(new Error('Backend channel initializing…')); return; }
    const version = base || appState || {revision: null, generation: null};
    backend.dispatch(JSON.stringify({method, args, revision: version.revision, generation: version.generation}), raw => {
      try {
        const response = JSON.parse(raw);
        if (response.error) reject(new Error(response.error));
        else resolve(response);
      } catch (error) { reject(error); }
    });
  });
}

function applyBackendResponse(raw) {
  const res = typeof raw === 'string' ? JSON.parse(raw) : raw;
  if (res.error) { showToast(res.error, true); return; }
  const oldToken = appState && `${appState.generation}:${appState.revision}`;
  if (res.state) appState = res.state;
  else if (res.patch && appState) {
    const p = res.patch;
    const modules = new Map(appState.modules.map(m => [m.id, m]));
    for (const m of p.modules_changed || []) modules.set(m.id, m);
    appState = {...appState, ...p, modules: p.module_order.map(id => modules.get(id))};
    delete appState.modules_changed;
    delete appState.module_order;
  }
  if (res.state || res.patch) {
    if (oldToken !== `${appState.generation}:${appState.revision}`) {
      pdfPages = []; proofMode = 'schematic';
    }
    if (!selectedModuleId || !findModuleById(selectedModuleId)) {
      selectedModuleId = appState.modules[0]?.id || appState.conclusion?.id;
      selectedBlockId = null;
    }
    renderAll();
    lockStudioControls();
    updateDraftStatus();
  }
  if (res.toast) showToast(res.toast);
}

async function flushDrafts() {
  if (!pendingDrafts.size) return;
  const submitted = new Map(pendingDrafts);
  applying = true; updateDraftStatus();
  try {
    const edits = [...submitted.values()].map(({method, args}) => ({method, args}));
    const response = await sendStudio('apply_drafts', [edits], draftBase);
    for (const [key, draft] of submitted) {
      if (pendingDrafts.get(key)?.serial === draft.serial) pendingDrafts.delete(key);
    }
    applyBackendResponse(response);
    draftBase = pendingDrafts.size ? {revision: appState.revision, generation: appState.generation} : null;
  } finally {
    applying = false; updateDraftStatus();
  }
  // Input entered while the callback was in flight must also reach Save/Close.
  if (pendingDrafts.size) await flushDrafts();
}

function enqueueStudio(action) {
  actionQueue = actionQueue.then(async () => {
    // Preserve focus, but do not allow a new draft to begin against the old
    // revision while a structural command or native dialog is in flight.
    queueBusy = true;
    lockStudioControls();
    try { return await action(); }
    finally {
      queueBusy = false;
      for (const [el, [readonly, disabled]] of lockedControls) {
        if (el.tagName === 'SELECT') el.disabled = disabled;
        else el.readOnly = readonly;
      }
      lockedControls.clear();
    }
  }).catch(error => {
    showToast(`${error.message} Your pending input is retained. Correct it and Apply, or Discard.`, true);
    return null;
  });
  return actionQueue;
}

function callBackend(method, ...args) {
  return enqueueStudio(async () => {
    await flushDrafts();
    const result = await sendStudio(method, args);
    applyBackendResponse(result);
    return result;
  });
}

function discardStudioDrafts() {
  if (applying || !pendingDrafts.size) return;
  if (!window.confirm('Discard all pending HTML field edits? Applied changes are kept.')) return;
  pendingDrafts.clear(); draftBase = null;
  renderAll(); updateDraftStatus();
}

function requestStudioClose() {
  // Cancel keeps the window and input exactly as it was. Discard is a separate
  // explicit button; closing never implicitly throws away HTML edits.
  if (pendingDrafts.size && !window.confirm('Apply pending edits and continue closing? Cancel keeps editing.')) return;
  callBackend('close_window');
}

function requestExactPdfProof() {
  callBackend('generate_pdf_proof').then(res => {
    if (!res) return;
    pdfPages = res.pages || []; currentPdfPage = 0; proofMode = 'pdf';
    renderPreviewPane();
  });
}

// Patch existing DOM nodes instead of replacing the editing canvas. Inputs with
// pending values are never overwritten by canonical projections. Identity,
// focus, caret and scroll are retained for ordinary acknowledged edits.
function reconcileCanvas(container, markup) {
  const template = document.createElement('template');
  template.innerHTML = markup;
  const key = node => node.nodeType === 1 ? (node.id || node.dataset.moduleId || node.dataset.blockId || '') : '';
  function patch(old, fresh) {
    if (old.nodeType !== fresh.nodeType || old.nodeName !== fresh.nodeName) {
      old.replaceWith(fresh.cloneNode(true)); return;
    }
    if (old.nodeType !== 1) {
      if (old.nodeValue !== fresh.nodeValue) old.nodeValue = fresh.nodeValue;
      return;
    }
    for (const attr of [...old.attributes]) if (!fresh.hasAttribute(attr.name)) old.removeAttribute(attr.name);
    for (const attr of [...fresh.attributes]) if (old.getAttribute(attr.name) !== attr.value) old.setAttribute(attr.name, attr.value);
    if (old.matches('input,textarea,select')) {
      if (!pendingDrafts.size && old.value !== fresh.value) {
        const focused = old === document.activeElement;
        const start = old.selectionStart, end = old.selectionEnd;
        old.value = fresh.value;
        if (focused && start !== null) old.setSelectionRange(Math.min(start, old.value.length), Math.min(end, old.value.length));
      }
      return;
    }
    children(old, fresh);
  }
  function children(old, fresh) {
    const desired = [...fresh.childNodes];
    for (let i = 0; i < desired.length; i++) {
      const next = desired[i];
      let current = old.childNodes[i];
      const wanted = key(next);
      if (wanted && key(current || {}) !== wanted) {
        const match = [...old.childNodes].find(n => key(n) === wanted);
        if (match) { old.insertBefore(match, current || null); current = match; }
        else { old.insertBefore(next.cloneNode(true), current || null); continue; }
      }
      if (!current) old.appendChild(next.cloneNode(true));
      else patch(current, next);
    }
    while (old.childNodes.length > desired.length) old.lastChild.remove();
  }
  children(container, template.content);
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('applyDrafts').addEventListener('click', () => enqueueStudio(flushDrafts));
  document.getElementById('discardDrafts').addEventListener('click', discardStudioDrafts);
  updateDraftStatus();
});

window.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && ['z', 'y'].includes(e.key.toLowerCase())) {
    // Text widgets retain their normal local typing undo until Apply.
    if (pendingDrafts.size && e.target.matches('input,textarea')) return;
    e.preventDefault();
    callBackend(e.key.toLowerCase() === 'y' || e.shiftKey ? 'redo' : 'undo');
  }
});
