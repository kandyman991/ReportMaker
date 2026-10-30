
let backend = null;
let appState = null;
let selectedModuleId = null;
let selectedBlockId = null;
let collapsedModules = new Set();
let searchFilter = "";
let canvasZoom = 1.0;
let proofMode = "schematic"; // "schematic" | "pdf"
let pdfPages = [];
let currentPdfPage = 0;
let showFormattingMarks = false;
let activeTextSel = { moduleId: null, blockId: null, start: 0, end: 0 };

function showToast(msg, isError = false) {
  const el = document.getElementById("toastBanner");
  el.textContent = msg;
  el.style.borderColor = isError ? "var(--danger)" : "var(--accent)";
  el.style.display = "block";
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => { el.style.display = "none"; }, 3200);
}

function toggleTheme() {
  const root = document.documentElement;
  const current = root.getAttribute("data-theme") || "dark";
  const next = current === "dark" ? "light" : "dark";
  root.setAttribute("data-theme", next);
  document.getElementById("themeIcon").textContent = next === "dark" ? "☀️" : "🌙";
}

function togglePreviewPane() {
  const pane = document.getElementById("previewPane");
  const btn = document.getElementById("btnTogglePreview");
  pane.classList.toggle("hidden");
  btn.classList.toggle("btn-active", !pane.classList.contains("hidden"));
}

function setFocusMode(mode) {
  const pane = document.getElementById("previewPane");
  if (mode === "branch" && pane.classList.contains("hidden")) {
    togglePreviewPane();
  }
}

function adjustZoom(delta) {
  canvasZoom = Math.min(1.35, Math.max(0.75, +(canvasZoom + delta).toFixed(2)));
  document.getElementById("zoomLabel").textContent = Math.round(canvasZoom * 100) + "%";
  const container = document.getElementById("canvasContainer");
  container.style.transform = `scale(${canvasZoom})`;
}

function onSearchFilter(val) {
  if (pendingDrafts.size) { enqueueStudio(async () => { await flushDrafts(); onSearchFilter(val); }); return; }
  searchFilter = (val || "").trim().toLowerCase();
  renderAll();
}

function selectTarget(moduleId, blockId = null) {
  selectedModuleId = moduleId;
  selectedBlockId = blockId;
  updateSelectionIndicators();
}

function updateSelectionIndicators() {
  document.querySelectorAll(".module-card").forEach(el => {
    el.classList.toggle("selected", el.dataset.moduleId === selectedModuleId && !selectedBlockId);
  });
  document.querySelectorAll(".block-node").forEach(el => {
    el.classList.toggle("selected", el.dataset.blockId === selectedBlockId);
  });
  const selMod = findModuleById(selectedModuleId);
  const isConclusion = appState && appState.conclusion && selectedModuleId === appState.conclusion.id;
  const btnSub = document.getElementById("btnAddSubmodule");
  if (btnSub) btnSub.disabled = !selMod || isConclusion;
  const foot = document.getElementById("footerSelection");
  if (foot) {
    foot.textContent = selMod
      ? `Selected: ${selMod.number ? selMod.number + " " : ""}${selMod.title}${selectedBlockId ? " › Block" : ""}`
      : "Selected: None";
  }
  syncWordRibbonState();
}

function findBlockById(modId, blockId) {
  const mod = findModuleById(modId);
  if (!mod) return null;
  for (const b of mod.blocks || []) {
    if (b.id === blockId) return { mod, block: b };
  }
  return null;
}

function hasRichFormatting(rich) {
  if (!rich) return false;
  return (Array.isArray(rich.runs) && rich.runs.length > 0) ||
         (Array.isArray(rich.paragraphs) && rich.paragraphs.length > 0);
}

function primaryInputStyle(rich) {
  if (!rich) return "";
  const css = [];
  const p0 = (rich.paragraphs || []).find(p => p.start === 0);
  if (p0) {
    if (p0.align && p0.align !== "left") css.push(`text-align:${p0.align}`);
    if (p0.indent > 0) css.push(`padding-left:${10 + p0.indent * 18}px`);
    if (p0.line_height && p0.line_height > 1.0) css.push(`line-height:${p0.line_height}`);
    if (p0.shading) css.push(`background-color:${p0.shading}`);
    if (p0.border) css.push(`border:2px solid var(--accent)`);
  }
  const r0 = (rich.runs || []).find(r => r.start === 0);
  if (r0) {
    if (r0.family) css.push(`font-family:'${escapeHtml(r0.family)}', sans-serif`);
    if (r0.size && r0.size >= 6) css.push(`font-size:${r0.size}pt`);
    if (r0.bold) css.push(`font-weight:700`);
    if (r0.italic) css.push(`font-style:italic`);
    const dec = [];
    if (r0.underline) dec.push("underline");
    if (r0.strike) dec.push("line-through");
    if (dec.length) css.push(`text-decoration:${dec.join(" ")}`);
    if (r0.color) css.push(`color:${r0.color}`);
  }
  return css.join(";");
}

function renderRichHtml(text, rich, isHeading = false) {
  const raw = String(text ?? "");
  const runs = (rich && Array.isArray(rich.runs)) ? rich.runs : [];
  const paras = (rich && Array.isArray(rich.paragraphs)) ? rich.paragraphs : [];
  const paraMap = new Map();
  for (const p of paras) paraMap.set(p.start, p);

  const codepoints = Array.from(raw);
  const lines = [];
  let lineStartCp = 0;
  let curChars = [];
  for (let i = 0; i < codepoints.length; i++) {
    if (codepoints[i] === "\n") {
      lines.push({ start: lineStartCp, end: i, chars: curChars });
      curChars = [];
      lineStartCp = i + 1;
    } else {
      curChars.push(codepoints[i]);
    }
  }
  lines.push({ start: lineStartCp, end: codepoints.length, chars: curChars });

  let listCounter = 0;
  let lastListKind = "none";
  const out = [];

  for (const ln of lines) {
    const spec = paraMap.get(ln.start) || {
      start: ln.start, align: "left", indent: 0, list_kind: "none", line_height: 1.0, shading: "", border: false
    };
    const pStyles = [
      `text-align:${spec.align || "left"}`,
      `margin-left:${(spec.indent || 0) * 1.35}em`,
      `line-height:${spec.line_height || (isHeading ? 1.25 : 1.48)}`,
      "margin-bottom:3px"
    ];
    if (spec.shading) pStyles.push(`background-color:${spec.shading};padding:2px 6px;border-radius:3px`);
    if (spec.border) pStyles.push(`border:1px solid #64748B;padding:3px 7px;border-radius:3px`);

    let prefix = "";
    const lk = spec.list_kind || "none";
    if (lk !== "none") {
      if (lk === lastListKind) listCounter++;
      else { listCounter = 1; lastListKind = lk; }
      if (lk === "bullet") prefix = `<span style="color:#2563EB;font-weight:800;margin-right:6px;">•</span>`;
      else if (lk === "decimal") prefix = `<span style="color:#2563EB;font-weight:700;margin-right:6px;">${listCounter}.</span>`;
      else if (lk === "lower-alpha") {
        const ch = String.fromCharCode(96 + ((listCounter - 1) % 26) + 1);
        prefix = `<span style="color:#2563EB;font-weight:700;margin-right:6px;">${ch}.</span>`;
      } else if (lk === "upper-alpha") {
        const ch = String.fromCharCode(64 + ((listCounter - 1) % 26) + 1);
        prefix = `<span style="color:#2563EB;font-weight:700;margin-right:6px;">${ch}.</span>`;
      }
    } else {
      lastListKind = "none";
      listCounter = 0;
    }

    const edges = new Set([ln.start, ln.end]);
    for (const r of runs) {
      if (r.start < ln.end && r.end > ln.start) {
        edges.add(Math.max(ln.start, r.start));
        edges.add(Math.min(ln.end, r.end));
      }
    }
    const sorted = Array.from(edges).sort((a, b) => a - b);
    let segHtml = "";
    for (let i = 0; i < sorted.length - 1; i++) {
      const s = sorted[i], e = sorted[i + 1];
      if (s >= e) continue;
      let chunk = codepoints.slice(s, e).join("");
      if (showFormattingMarks) chunk = chunk.replace(/ /g, "·");
      const escaped = escapeHtml(chunk);
      const run = runs.find(r => r.start <= s && s < r.end);
      if (!run) {
        segHtml += escaped;
      } else {
        const rStyles = [];
        if (run.family) rStyles.push(`font-family:'${escapeHtml(run.family)}', sans-serif`);
        if (run.size && run.size >= 6) rStyles.push(`font-size:${run.size}pt`);
        if (run.bold) rStyles.push("font-weight:700");
        if (run.italic) rStyles.push("font-style:italic");
        const dec = [];
        if (run.underline) dec.push("underline");
        if (run.strike) dec.push("line-through");
        if (dec.length) rStyles.push(`text-decoration:${dec.join(" ")}`);
        if (run.color) rStyles.push(`color:${run.color}`);
        if (run.highlight) rStyles.push(`background-color:${run.highlight};padding:0 2px;border-radius:2px`);
        if (run.baseline === "sub") rStyles.push("vertical-align:sub;font-size:0.8em");
        else if (run.baseline === "super") rStyles.push("vertical-align:super;font-size:0.8em");
        segHtml += `<span style="${rStyles.join(";")}">${escaped}</span>`;
      }
    }
    const pilcrow = showFormattingMarks ? `<span class="pilcrow-mark">¶</span>` : "";
    out.push(`<div style="${pStyles.join(";")}">${prefix}${segHtml || (showFormattingMarks ? "" : "&nbsp;")}${pilcrow}</div>`);
  }
  return out.join("");
}

function resolveRibbonTargetBlock() {
  if (!appState) return null;
  if (selectedModuleId && selectedBlockId) {
    const found = findBlockById(selectedModuleId, selectedBlockId);
    if (found && (found.block.kind === "paragraph" || found.block.kind === "heading")) {
      return { moduleId: selectedModuleId, blockId: selectedBlockId, block: found.block, mod: found.mod };
    }
  }
  if (activeTextSel.moduleId && activeTextSel.blockId) {
    const found = findBlockById(activeTextSel.moduleId, activeTextSel.blockId);
    if (found && (found.block.kind === "paragraph" || found.block.kind === "heading")) {
      return { moduleId: activeTextSel.moduleId, blockId: activeTextSel.blockId, block: found.block, mod: found.mod };
    }
  }
  const mod = findModuleById(selectedModuleId) || (appState.modules && appState.modules[0]) || appState.conclusion;
  if (mod) {
    const candidate = (mod.blocks || []).find(b => b.kind === "paragraph" || b.kind === "heading");
    if (candidate) return { moduleId: mod.id, blockId: candidate.id, block: candidate, mod };
  }
  return null;
}

function syncWordRibbonState() {
  const showMarksBtn = document.getElementById("wbShowMarks");
  if (showMarksBtn) showMarksBtn.classList.toggle("active", showFormattingMarks);

  const target = resolveRibbonTargetBlock();
  const badgeEl = document.getElementById("wbTargetBadge");
  const hintEl = document.getElementById("wbTargetHint");
  if (!target) {
    if (badgeEl) badgeEl.textContent = "No Text Block";
    if (hintEl) hintEl.textContent = "Add or click a paragraph/heading block";
    return;
  }

  const { block, mod } = target;
  const isSelRange = activeTextSel.blockId === block.id && activeTextSel.end > activeTextSel.start;
  if (badgeEl) {
    badgeEl.textContent = block.kind === "heading" ? `H${block.level} Heading` : "¶ Paragraph";
  }
  if (hintEl) {
    hintEl.textContent = isSelRange
      ? `Selection (${activeTextSel.end - activeTextSel.start} chars) in ${mod.title}`
      : `Whole block in ${mod.title}`;
  }

  const rich = block.rich || { runs: [], paragraphs: [] };
  const probePos = isSelRange ? activeTextSel.start : 0;
  const run = (rich.runs || []).find(r => r.start <= probePos && probePos < r.end) || (rich.runs || [])[0] || null;
  const para = (rich.paragraphs || [])[0] || { align: "left", list_kind: "none", border: false };

  const setBtn = (id, on) => document.getElementById(id)?.classList.toggle("active", !!on);
  setBtn("wbBold", run && run.bold);
  setBtn("wbItalic", run && run.italic);
  setBtn("wbUnderline", run && run.underline);
  setBtn("wbStrike", run && run.strike);
  setBtn("wbSub", run && run.baseline === "sub");
  setBtn("wbSuper", run && run.baseline === "super");

  const famSel = document.getElementById("wbFontFamily");
  if (famSel) famSel.value = (run && run.family) ? run.family : "";
  const szSel = document.getElementById("wbFontSize");
  if (szSel) szSel.value = (run && run.size) ? String(Math.round(run.size)) : "0";

  const align = para.align || "left";
  setBtn("wbAlignLeft", align === "left");
  setBtn("wbAlignCenter", align === "center");
  setBtn("wbAlignRight", align === "right");
  setBtn("wbAlignJustify", align === "justify");

  const lk = para.list_kind || "none";
  setBtn("wbListBullet", lk === "bullet");
  setBtn("wbListDecimal", lk === "decimal");
  setBtn("wbListMulti", lk === "lower-alpha" || lk === "upper-alpha");
  setBtn("wbBorderBtn", !!para.border);
}

function closeAllRibbonPopovers() {
  document.querySelectorAll(".ribbon-popover.open").forEach(el => el.classList.remove("open"));
}

function applyWordRibbon(op, value = null) {
  closeAllRibbonPopovers();
  if (op === "toggle_marks") {
    showFormattingMarks = !showFormattingMarks;
    renderAll();
    return;
  }
  const target = resolveRibbonTargetBlock();
  if (!target) {
    showToast("Select a paragraph or heading block first", true);
    return;
  }
  selectedModuleId = target.moduleId;
  selectedBlockId = target.blockId;

  if (op === "color" && value) {
    const bar = document.getElementById("wbColorBar");
    if (bar) bar.style.background = value;
  } else if (op === "highlight" && value) {
    const bar = document.getElementById("wbHighlightBar");
    if (bar) bar.style.background = value;
  } else if (op === "shading" && value) {
    const bar = document.getElementById("wbShadingBar");
    if (bar) bar.style.background = value;
  }

  let start = 0, end = 0;
  if (activeTextSel.blockId === target.blockId) {
    start = activeTextSel.start || 0;
    end = activeTextSel.end || 0;
  }
  callBackend("format_rich_block", target.moduleId, target.blockId, JSON.stringify({
    op, value, start, end
  }));
}

function findModuleById(id, list = null) {
  if (!appState) return null;
  if (appState.conclusion && appState.conclusion.id === id) return appState.conclusion;
  const mods = list || appState.modules || [];
  for (const m of mods) {
    if (m.id === id) return m;
    for (const b of m.blocks || []) {
      if (b.kind === "submodule" && b.module) {
        const found = findModuleById(id, [b.module]);
        if (found) return found;
      }
    }
  }
  return null;
}

function promptAddModule() {
  callBackend("add_module", "New intervention section");
}

function promptAddSubmodule() {
  if (!selectedModuleId) {
    showToast("Select an intervention module first", true);
    return;
  }
  callBackend("add_submodule", selectedModuleId, "Sub-inspection");
}

function addBlockToSelected(kind) {
  const targetMod = selectedModuleId || (appState && appState.modules[0] ? appState.modules[0].id : (appState && appState.conclusion ? appState.conclusion.id : ""));
  if (!targetMod) return;
  if (kind === "photo") {
    callBackend("import_photo_to_module", targetMod);
  } else {
    callBackend("add_block", targetMod, kind);
  }
}

function commitMetadataField() {
  if (!appState) return;
  const payload = {
    title: document.getElementById("metaTitleInput")?.value ?? appState.report.title,
    customer_name: document.getElementById("metaCustomerInput")?.value ?? appState.report.customer_name,
    site_name: document.getElementById("metaSiteInput")?.value ?? appState.report.site_name,
    machine_name: document.getElementById("metaMachineInput")?.value ?? appState.report.machine_name,
    ticket: document.getElementById("metaTicketInput")?.value ?? appState.report.ticket,
    technicians: document.getElementById("metaTechInput")?.value ?? appState.report.technicians,
    start_date: document.getElementById("metaStartInput")?.value ?? appState.report.start_date,
    end_date: document.getElementById("metaEndInput")?.value ?? appState.report.end_date,
  };
  stageDraft("update_report_header", JSON.stringify(payload));
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function matchesSearch(mod) {
  if (!searchFilter) return true;
  if ((mod.title || "").toLowerCase().includes(searchFilter)) return true;
  for (const b of mod.blocks || []) {
    if (b.kind === "paragraph" && (b.text || "").toLowerCase().includes(searchFilter)) return true;
    if (b.kind === "heading" && (b.text || "").toLowerCase().includes(searchFilter)) return true;
    if (b.kind === "photo" && (b.caption || "").toLowerCase().includes(searchFilter)) return true;
    if (b.kind === "table" && JSON.stringify(b.rows || []).toLowerCase().includes(searchFilter)) return true;
    if (b.kind === "submodule" && b.module && matchesSearch(b.module)) return true;
  }
  return false;
}

function renderBlockHtml(modId, b) {
  const isSel = b.id === selectedBlockId ? "selected" : "";
  const commonActions = `
    <div class="module-actions" data-ev-click="35">
      <button class="icon-act-btn" data-ev-click="36" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}" title="Move Up">↑</button>
      <button class="icon-act-btn" data-ev-click="37" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}" title="Move Down">↓</button>
      <button class="icon-act-btn" data-ev-click="38" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}" title="Duplicate Block">⧉</button>
      <button class="icon-act-btn danger" data-ev-click="39" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}" title="Delete Block">✕</button>
    </div>
  `;

  if (b.kind === "paragraph") {
    const inlineCss = primaryInputStyle(b.rich);
    const hasRich = hasRichFormatting(b.rich);
    const richBanner = (hasRich || showFormattingMarks)
      ? `<div class="rich-preview-strip">${renderRichHtml(b.text || "", b.rich, false)}</div>`
      : "";
    return `
      <div class="block-node ${isSel}" data-block-id="${escapeHtml(b.id)}" data-ev-click="40" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-slate">¶ Paragraph</span>
            ${hasRich ? `<span class="tag tag-blue">Styled</span>` : ""}
          </div>
          ${commonActions}
        </div>
        <textarea class="block-textarea" placeholder="Write field observation or intervention details…"
          ${inlineCss ? `style="${inlineCss}"` : ""}
          data-ev-focus="41" data-args-focus="${escapeHtml(JSON.stringify([modId, b.id]))}"
          data-ev-input="42" data-args-input="${escapeHtml(JSON.stringify([modId, b.id]))}">${escapeHtml(b.text)}</textarea>
        ${richBanner}
      </div>
    `;
  }

  if (b.kind === "heading") {
    const inlineCss = primaryInputStyle(b.rich);
    const hasRich = hasRichFormatting(b.rich);
    const richBanner = (hasRich || showFormattingMarks)
      ? `<div class="rich-preview-strip">${renderRichHtml(b.text || "", b.rich, true)}</div>`
      : "";
    return `
      <div class="block-node ${isSel}" data-block-id="${escapeHtml(b.id)}" data-ev-click="43" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-blue">H${b.level} Heading</span>
            ${hasRich ? `<span class="tag tag-emerald">Styled</span>` : ""}
          </div>
          ${commonActions}
        </div>
        <div class="heading-row">
          <select class="heading-level-select" data-ev-input="44" data-args-input="${escapeHtml(JSON.stringify([modId, b.id]))}">
            <option value="1" ${b.level === 1 ? "selected" : ""}>H1</option>
            <option value="2" ${b.level === 2 ? "selected" : ""}>H2</option>
            <option value="3" ${b.level === 3 ? "selected" : ""}>H3</option>
            <option value="4" ${b.level === 4 ? "selected" : ""}>H4</option>
            <option value="5" ${b.level === 5 ? "selected" : ""}>H5</option>
            <option value="6" ${b.level === 6 ? "selected" : ""}>H6</option>
          </select>
          <input type="text" class="heading-input" value="${escapeHtml(b.text)}" placeholder="Sub-heading title…"
            ${inlineCss ? `style="${inlineCss}"` : ""}
            data-ev-focus="45" data-args-focus="${escapeHtml(JSON.stringify([modId, b.id]))}"
            data-ev-input="46" data-args-input="${escapeHtml(JSON.stringify([modId, b.id, b.level]))}">
        </div>
        ${richBanner}
      </div>
    `;
  }

  if (b.kind === "photo") {
    const imgSrc = b.data_url || "";
    return `
      <div class="block-node ${isSel}" data-block-id="${escapeHtml(b.id)}" data-ev-click="47" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-amber">📷 Annotated Photo</span>
            <span class="mono" style="font-size:11px; color:var(--text-muted);">${escapeHtml(b.asset_name || b.asset_id)}</span>
            <span class="tag tag-slate">${b.marks_count || 0} Callouts · ${b.width_pct || 100}%</span>
          </div>
          ${commonActions}
        </div>
        <div class="photo-block-grid">
          <div class="photo-thumb-box">
            ${imgSrc ? `<img loading="lazy" src="${imgSrc}" alt="Photo">` : `<span style="color:#94A3B8;font-size:11px;">No image</span>`}
            <div class="photo-annotate-overlay">
              <button class="btn btn-primary" data-ev-click="48" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
                ✎ Edit Annotations
              </button>
            </div>
          </div>
          <div class="photo-meta-col">
            <label style="font-size:10px; font-weight:700; text-transform:uppercase; color:var(--text-dim);">Figure Caption</label>
            <textarea class="block-textarea" style="min-height:54px;" placeholder="Describe photo evidence or component serial…"
              data-ev-focus="49" data-args-focus="${escapeHtml(JSON.stringify([modId, b.id]))}"
              data-ev-input="50" data-args-input="${escapeHtml(JSON.stringify([modId, b.id]))}">${escapeHtml(b.caption)}</textarea>
            <div style="display:flex; gap:6px;">
              <button class="chip-btn primary" data-ev-click="51" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
                ✎ Open Vector Annotation Editor…
              </button>
            </div>
          </div>
        </div>
      </div>
    `;
  }

  if (b.kind === "table") {
    const rows = b.rows || [[""]];
    const tableId = `tbl_${b.id}`;
    let trs = "";
    rows.forEach((r, rIdx) => {
      let tds = "";
      r.forEach((cellVal, cIdx) => {
        tds += `<td><input type="text" data-r="${rIdx}" data-c="${cIdx}" value="${escapeHtml(cellVal)}"
          data-ev-input="52" data-args-input="${escapeHtml(JSON.stringify([modId, b.id, tableId]))}"></td>`;
      });
      trs += `<tr>${tds}</tr>`;
    });
    return `
      <div class="block-node ${isSel}" data-block-id="${escapeHtml(b.id)}" data-ev-click="53" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-purple">⊞ Structured Table (${rows.length}×${(rows[0] || []).length})</span>
            <button class="chip-btn" data-ev-click="54" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">+ Row</button>
            <button class="chip-btn" data-ev-click="55" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">+ Col</button>
            <button class="chip-btn" data-ev-click="56" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">- Row</button>
            <button class="chip-btn" data-ev-click="57" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}">- Col</button>
          </div>
          ${commonActions}
        </div>
        <div class="table-editor-wrap">
          <table class="editor-table" id="${escapeHtml(tableId)}">
            <tbody>${trs}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  if (b.kind === "page_break") {
    return `
      <div class="block-node ${isSel}" data-block-id="${escapeHtml(b.id)}" data-ev-click="58" data-args-click="${escapeHtml(JSON.stringify([modId, b.id]))}"
        style="display:flex; align-items:center; justify-content:space-between; padding:7px 12px;">
        <span class="tag tag-slate mono">⎯⎯ EXPLICIT PAGE BREAK ⎯⎯</span>
        ${commonActions}
      </div>
    `;
  }

  if (b.kind === "submodule" && b.module) {
    return `<div class="block-node" style="padding:0; background:transparent; border:none;">
      ${renderModuleCardHtml(b.module, false, modId, b.id)}
    </div>`;
  }

  return "";
}

function commitTableCell(modId, blockId, tableDomId) {
  const tableEl = document.getElementById(tableDomId);
  if (!tableEl) return;
  const rows = [];
  tableEl.querySelectorAll("tr").forEach(tr => {
    const row = [];
    tr.querySelectorAll("input").forEach(inp => row.push(inp.value));
    rows.push(row);
  });
  stageDraft("update_table", modId, blockId, JSON.stringify(rows));
}

function mutateTableShape(modId, blockId, op) {
  callBackend("mutate_table_shape", modId, blockId, op);
}

function toggleModuleCollapse(modId, ev) {
  ev.stopPropagation();
  if (pendingDrafts.size) { enqueueStudio(async () => { await flushDrafts(); toggleModuleCollapse(modId, {stopPropagation() {}}); }); return; }
  if (collapsedModules.has(modId)) collapsedModules.delete(modId);
  else collapsedModules.add(modId);
  renderAll();
}

function renderModuleCardHtml(mod, isConclusion = false, parentModId = null, wrapperBlockId = null) {
  if (!matchesSearch(mod)) return "";
  const isCollapsed = collapsedModules.has(mod.id);
  const isSelected = mod.id === selectedModuleId && !selectedBlockId;
  const blocksHtml = (mod.blocks || []).map(b => renderBlockHtml(mod.id, b)).join("");

  const moveTargetMod = parentModId || mod.id;
  const moveTargetBlk = wrapperBlockId || "";

  return `
    <div class="module-card ${isSelected ? "selected" : ""} ${isConclusion ? "conclusion-card" : ""}"
         data-module-id="${escapeHtml(mod.id)}"
         data-ev-click="59" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">
      <div class="module-header">
        <div class="module-header-left">
          <button class="collapse-btn" data-ev-click="60" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}" title="Collapse / Expand Section">
            ${isCollapsed ? "▸" : "▾"}
          </button>
          <span class="sec-num-badge ${isConclusion ? "conclusion" : ""} mono">
            ${isConclusion ? "FINAL" : escapeHtml(mod.number || "•")}
          </span>
          <input type="text" class="module-title-input"
            value="${escapeHtml(mod.title)}"
            ${isConclusion ? "disabled title='Dedicated Conclusions section title'" : ""}
            data-ev-click="61" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}"
            data-ev-input="62" data-args-input="${escapeHtml(JSON.stringify([mod.id]))}">
        </div>
        <div class="module-actions" data-ev-click="63">
          ${!isConclusion ? `
            <button class="icon-act-btn" data-ev-click="64" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}" title="Add Nested Submodule">+Sub</button>
            <button class="icon-act-btn" data-ev-click="65" data-args-click="${escapeHtml(JSON.stringify([moveTargetMod, moveTargetBlk]))}" title="Move Up">↑</button>
            <button class="icon-act-btn" data-ev-click="66" data-args-click="${escapeHtml(JSON.stringify([moveTargetMod, moveTargetBlk]))}" title="Move Down">↓</button>
            <button class="icon-act-btn" data-ev-click="67" data-args-click="${escapeHtml(JSON.stringify([moveTargetMod, moveTargetBlk]))}" title="Duplicate Module">⧉</button>
            <button class="icon-act-btn danger" data-ev-click="68" data-args-click="${escapeHtml(JSON.stringify([moveTargetMod, moveTargetBlk]))}" title="Delete Module">✕</button>
          ` : `<span class="tag tag-emerald">Protected Section</span>`}
        </div>
      </div>

      ${!isCollapsed ? `
        <div class="module-body">
          ${blocksHtml || `<div style="font-size:12px; color:var(--text-dim); font-style:italic; padding:4px 0;">Empty section — use the quick bar below to add paragraphs, photos, or tables.</div>`}
          <div class="module-quick-bar" data-ev-click="69">
            <button class="chip-btn" data-ev-click="70" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">+ Text</button>
            <button class="chip-btn" data-ev-click="71" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">+ Heading</button>
            <button class="chip-btn" data-ev-click="72" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">+ Photo…</button>
            <button class="chip-btn" data-ev-click="73" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">+ Table</button>
            <button class="chip-btn" data-ev-click="74" data-args-click="${escapeHtml(JSON.stringify([mod.id]))}">+ Page Break</button>
          </div>
        </div>
      ` : ""}
    </div>
  `;
}

function renderA4ModuleNodes(mod, isConclusion = false) {
  const headingLabel = isConclusion
    ? escapeHtml(mod.title)
    : `${escapeHtml(mod.number || "")} ${escapeHtml(mod.title)}`;
  const isNested = (mod.number || "").includes(".");
  let html = `<div class="${isNested ? "a4-subsec-heading" : "a4-sec-heading"}">${headingLabel}</div>`;

  for (const b of mod.blocks || []) {
    if (b.kind === "paragraph") {
      html += `<div class="a4-paragraph">${renderRichHtml(b.text || "", b.rich, false)}</div>`;
    } else if (b.kind === "heading") {
      html += `<div class="a4-subsec-heading">${renderRichHtml(b.text || "", b.rich, true)}</div>`;
    } else if (b.kind === "photo") {
      html += `
        <div class="a4-photo-figure">
          ${b.data_url ? `<img loading="lazy" src="${b.data_url}" style="width:${b.width_pct || 100}%;" alt="Figure">` : ""}
          ${b.caption ? `<div class="a4-photo-caption">${escapeHtml(b.caption)}</div>` : ""}
        </div>
      `;
    } else if (b.kind === "table") {
      const trs = (b.rows || []).map(row =>
        `<tr>${row.map(c => `<td>${escapeHtml(c)}</td>`).join("")}</tr>`
      ).join("");
      html += `<table class="a4-table"><tbody>${trs}</tbody></table>`;
    } else if (b.kind === "page_break") {
      html += `<div class="a4-page-break">— Page Break —</div>`;
    } else if (b.kind === "submodule" && b.module) {
      html += renderA4ModuleNodes(b.module, false);
    }
  }
  return html;
}

function renderPreviewPane() {
  const scroll = document.getElementById("previewScroll");
  if (!scroll || !appState) return;

  document.getElementById("btnModeSchematic").classList.toggle("primary", proofMode === "schematic");
  document.getElementById("btnModePdf").classList.toggle("primary", proofMode === "pdf");

  if (proofMode === "pdf" && pdfPages.length > 0) {
    const pageImg = pdfPages[currentPdfPage] || pdfPages[0];
    scroll.innerHTML = `
      <div style="display:flex; align-items:center; gap:10px; background:var(--bg-card); padding:6px 14px; border-radius:8px; border:1px solid var(--border-main);">
        <button class="chip-btn" ${currentPdfPage <= 0 ? "disabled" : ""} data-ev-click="75">‹ Prev</button>
        <span class="mono" style="font-size:12px; font-weight:700;">Exact PDF Page ${currentPdfPage + 1} of ${pdfPages.length}</span>
        <button class="chip-btn" ${currentPdfPage >= pdfPages.length - 1 ? "disabled" : ""} data-ev-click="76">Next ›</button>
      </div>
      <div class="a4-sheet" style="padding:0; overflow:hidden; background:#fff;">
        <img loading="lazy" src="${pageImg}" style="width:100%; height:auto; display:block;" alt="Rendered PDF Page">
      </div>
    `;
    return;
  }

  const r = appState.report;
  const sectionsHtml = (appState.modules || []).map(m => renderA4ModuleNodes(m, false)).join("")
    + (appState.conclusion ? renderA4ModuleNodes(appState.conclusion, true) : "");

  scroll.innerHTML = `
    <div class="a4-sheet">
      <div>
        <div class="a4-letterhead">
          <div>
            <div class="a4-brand-title">TECHNICAL FIELD REPORT</div>
            <div class="a4-brand-sub">Engineering Service &amp; Commissioning</div>
          </div>
          <div style="text-align:right; font-size:9px; color:#475569;" class="mono">
            <div><strong>Ticket:</strong> ${escapeHtml(r.ticket || "—")}</div>
            <div><strong>Date:</strong> ${escapeHtml(r.start_date)} → ${escapeHtml(r.end_date)}</div>
            <div><strong>Lang:</strong> ${escapeHtml((r.primary_language || "en").toUpperCase())}</div>
          </div>
        </div>

        <div class="a4-doc-title">${escapeHtml(r.title || "Report of intervention")}</div>

        <div class="a4-meta-box">
          <div class="a4-meta-row"><span class="a4-meta-label">Customer:</span><span class="a4-meta-val">${escapeHtml(r.customer_name || "—")}</span></div>
          <div class="a4-meta-row"><span class="a4-meta-label">Site / Plant:</span><span class="a4-meta-val">${escapeHtml(r.site_name || "—")}</span></div>
          <div class="a4-meta-row"><span class="a4-meta-label">Machine:</span><span class="a4-meta-val">${escapeHtml(r.machine_name || "—")}</span></div>
          <div class="a4-meta-row"><span class="a4-meta-label">Technicians:</span><span class="a4-meta-val">${escapeHtml(r.technicians || "—")}</span></div>
        </div>

        <div>${sectionsHtml}</div>
      </div>

      <div class="a4-footer">
        <span>${escapeHtml(r.customer_name || "ReportMaker V2")} · Confidential Technical Record</span>
        <span class="mono">Continuous A4 Live Proof</span>
      </div>
    </div>
  `;
}

function setProofMode(mode) {
  proofMode = mode;
  renderPreviewPane();
}

function stepPdfPage(delta) {
  currentPdfPage = Math.max(0, Math.min(pdfPages.length - 1, currentPdfPage + delta));
  renderPreviewPane();
}

function openGalleryModal() {
  document.getElementById("galleryModal").classList.add("open");
  renderGalleryGrid();
}

function closeGalleryModal() {
  document.getElementById("galleryModal").classList.remove("open");
}

function renderGalleryGrid() {
  const grid = document.getElementById("galleryGrid");
  if (!grid || !appState) return;
  const items = appState.gallery || [];
  if (items.length === 0) {
    grid.innerHTML = `<div style="grid-column:1/-1; text-align:center; padding:32px; color:var(--text-muted);">
      No photos in the project media library yet. Click <strong>+ Import Image Files…</strong> or paste from clipboard.
    </div>`;
    return;
  }
  const targetMod = selectedModuleId || (appState.modules[0] ? appState.modules[0].id : appState.conclusion.id);
  grid.innerHTML = items.map(item => `
    <div class="gallery-item">
      <img loading="lazy" src="${item.data_url}" alt="${escapeHtml(item.name)}">
      <div class="gallery-item-Foot">
        <div class="mono" style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(item.name)}">
          ${escapeHtml(item.name)}
        </div>
        <button class="chip-btn primary" style="justify-content:center;"
          data-ev-click="77" data-args-click="${escapeHtml(JSON.stringify([targetMod, item.asset_id]))}">
          + Insert into Selected Module
        </button>
      </div>
    </div>
  `).join("");
}

function renderAll() {
  if (!appState) return;
  const r = appState.report;

  // Header status
  document.getElementById("dirtyDot").classList.toggle("dirty", !!appState.dirty);
  document.getElementById("projectPathLabel").textContent =
    (appState.project_name || "Untitled project (.rmproj)") + (appState.dirty ? " *" : "");
  document.getElementById("headerCustomerLabel").textContent =
    `${r.customer_name || "Customer"}${r.site_name ? " — " + r.site_name : ""}${r.machine_name ? " (" + r.machine_name + ")" : ""}`;

  document.getElementById("btnUndo").disabled = !appState.can_undo;
  document.getElementById("btnRedo").disabled = !appState.can_redo;
  document.getElementById("galleryCountBadge").textContent = (appState.gallery || []).length;
  document.getElementById("langBadge").textContent = (r.primary_language || "en").toUpperCase();
  document.getElementById("previewLangLabel").textContent =
    `${r.primary_language} → ${(r.output_languages || []).join(", ")}`;

  // Report Header Card + Module Cards
  const container = document.getElementById("canvasContainer");
  const metaCardHtml = `
    <div class="report-meta-card">
      <div class="meta-top-row">
        <div style="flex:1;">
          <div class="meta-tags">
            <span class="tag tag-blue">REPORT METADATA</span>
            <span class="tag tag-emerald mono">PRIMARY: ${escapeHtml((r.primary_language || "en").toUpperCase())}</span>
            <span class="tag tag-slate mono">OUTPUTS: ${escapeHtml((r.output_languages || []).join(", ").toUpperCase())}</span>
          </div>
          <input type="text" id="metaTitleInput" class="report-title-input"
            value="${escapeHtml(r.title)}" placeholder="Report Title…"
            data-ev-input="78">
        </div>
        <div style="display:flex; gap:6px;">
          <button class="chip-btn" data-ev-click="79">⚙ Full Details &amp; Languages…</button>
        </div>
      </div>

      <div class="meta-grid">
        <div class="meta-field">
          <label>Customer Name</label>
          <input type="text" id="metaCustomerInput" value="${escapeHtml(r.customer_name)}" data-ev-input="80">
        </div>
        <div class="meta-field">
          <label>Site / Location</label>
          <input type="text" id="metaSiteInput" value="${escapeHtml(r.site_name)}" data-ev-input="81">
        </div>
        <div class="meta-field">
          <label>Machine / Line</label>
          <input type="text" id="metaMachineInput" value="${escapeHtml(r.machine_name)}" data-ev-input="82">
        </div>
        <div class="meta-field">
          <label>Ticket / Job ID</label>
          <input type="text" id="metaTicketInput" class="mono" value="${escapeHtml(r.ticket)}" data-ev-input="83">
        </div>
        <div class="meta-field">
          <label>Technicians (comma-sep)</label>
          <input type="text" id="metaTechInput" value="${escapeHtml(r.technicians)}" data-ev-input="84">
        </div>
        <div class="meta-field">
          <label>Start Date (YYYY-MM-DD)</label>
          <input type="text" id="metaStartInput" class="mono" value="${escapeHtml(r.start_date)}" data-ev-input="85">
        </div>
        <div class="meta-field">
          <label>End Date (YYYY-MM-DD)</label>
          <input type="text" id="metaEndInput" class="mono" value="${escapeHtml(r.end_date)}" data-ev-input="86">
        </div>
        <div class="meta-field" style="justify-content:flex-end;">
          <button class="btn" style="height:29px;" data-ev-click="87">Select from Customer DB…</button>
        </div>
      </div>
    </div>
  `;

  const modulesHtml = (appState.modules || []).map(m => renderModuleCardHtml(m, false)).join("");
  const conclusionHtml = appState.conclusion ? renderModuleCardHtml(appState.conclusion, true) : "";

  reconcileCanvas(container, metaCardHtml + modulesHtml + conclusionHtml);

  // Footer counts
  document.getElementById("footerStats").textContent =
    `${appState.stats.modules} Modules · ${appState.stats.blocks} Blocks · ${appState.stats.photos} Photos`;
  document.getElementById("footerRevision").textContent = `Rev ${appState.revision}`;

  updateSelectionIndicators();
  renderPreviewPane();
  if (document.getElementById("galleryModal").classList.contains("open")) {
    renderGalleryGrid();
  }
}

// Keyboard Shortcuts
window.addEventListener("keydown", function(e) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
    e.preventDefault();
    if (e.shiftKey) callBackend("save_project_as");
    else callBackend("save_project");
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") {
    e.preventDefault();
    callBackend("open_project");
  } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
    e.preventDefault();
    callBackend("new_project");
  } else if ((e.ctrlKey || e.metaKey) && e.key === "\\") {
    e.preventDefault();
    togglePreviewPane();
  } else if ((e.ctrlKey || e.metaKey) && !e.shiftKey && !e.altKey) {
    const k = e.key.toLowerCase();
    if (k === "b") { e.preventDefault(); applyWordRibbon("bold"); }
    else if (k === "i") { e.preventDefault(); applyWordRibbon("italic"); }
    else if (k === "u") { e.preventDefault(); applyWordRibbon("underline"); }
  }
});

function captureSelectionFromInput(el) {
  if (!el || !el.matches || !el.matches("textarea.block-textarea, input.heading-input")) return;
  const blockNode = el.closest("[data-block-id]");
  const modCard = el.closest("[data-module-id]");
  if (!blockNode || !modCard) return;
  activeTextSel = {
    moduleId: modCard.dataset.moduleId,
    blockId: blockNode.dataset.blockId,
    start: typeof el.selectionStart === "number" ? el.selectionStart : 0,
    end: typeof el.selectionEnd === "number" ? el.selectionEnd : 0,
  };
  syncWordRibbonState();
}

// Initialize QWebChannel connection & Word Ribbon listeners
window.addEventListener("DOMContentLoaded", function() {
  const ribbon = document.getElementById("wordRibbon");
  if (ribbon) {
    // Prevent Ribbon mousedown from stealing focus/selection from textarea/input
    ribbon.addEventListener("mousedown", function(ev) {
      if (ev.target.closest("select")) return;
      ev.preventDefault();
    });

    ribbon.addEventListener("click", function(ev) {
      const popBtn = ev.target.closest("[data-wb-pop]");
      if (popBtn) {
        ev.stopPropagation();
        const popId = popBtn.getAttribute("data-wb-pop");
        const popEl = document.getElementById(popId);
        const wasOpen = popEl && popEl.classList.contains("open");
        closeAllRibbonPopovers();
        if (popEl && !wasOpen) popEl.classList.add("open");
        return;
      }
      const opBtn = ev.target.closest("[data-wb-op]");
      if (opBtn) {
        ev.stopPropagation();
        const op = opBtn.getAttribute("data-wb-op");
        const rawVal = opBtn.hasAttribute("data-wb-val") ? opBtn.getAttribute("data-wb-val") : null;
        let val = rawVal;
        if (op === "step_size" || op === "indent" || op === "line_height" || op === "size") {
          val = parseFloat(rawVal);
        } else if (op === "border" && rawVal === "true") {
          val = true;
        } else if (op === "border" && rawVal === "") {
          val = false;
        }
        applyWordRibbon(op, val);
      }
    });
  }

  document.getElementById("wbFontFamily")?.addEventListener("change", function(ev) {
    applyWordRibbon("family", ev.target.value);
  });

  document.getElementById("wbFontSize")?.addEventListener("change", function(ev) {
    applyWordRibbon("size", parseFloat(ev.target.value || "0"));
  });

  document.addEventListener("click", function(ev) {
    if (!ev.target.closest(".w-pop-wrap")) closeAllRibbonPopovers();
  });

  ["select", "keyup", "mouseup", "focusin"].forEach(evtName => {
    document.addEventListener(evtName, function(ev) {
      if (ev.target && ev.target.matches && ev.target.matches("textarea.block-textarea, input.heading-input")) {
        captureSelectionFromInput(ev.target);
      }
    });
  });

  if (typeof QWebChannel !== "undefined" && window.qt && window.qt.webChannelTransport) {
    new QWebChannel(window.qt.webChannelTransport, function(channel) {
      backend = channel.objects.backend;
      sendStudio('get_state', []).then(applyBackendResponse).catch(e => showToast(e.message, true));
    });
  }
});
