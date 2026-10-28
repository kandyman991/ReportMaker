import React, { memo, useCallback, useEffect, useRef, useState } from "react";
import { startNativeBridge } from "./native-bridge.js";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import "./style.css";

const KIND = { root: "REPORT", module: "MODULE", conclusion: "CONCLUSIONS", paragraph: "TEXT", heading: "HEADING", photo: "PHOTO", table: "TABLE" };
const frame = () => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
const api = { set: null, size: 0, async load(size) {
  const start = performance.now();
  const response = await fetch("/data/" + size + ".json");
  if (!response.ok) throw Error("No fixture " + size);
  const nodes = await response.json();
  flushSync(() => api.set(nodes));
  await frame();
  return { ms: performance.now() - start, rows: document.querySelectorAll("[data-rowid]").length };
}, async refresh() {
  const start = performance.now();
  flushSync(() => api.set(old => old.map(item => ({...item}))));
  await frame();
  return performance.now() - start;
}, async edit() {
  const input = document.querySelector('[data-rowkind="module"] input');
  const start = performance.now();
  const original = input.value;
  const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
  descriptor.set.call(input, original + " edited");
  input.dispatchEvent(new Event("input", { bubbles: true }));
  const apply = input.closest("[data-rowid]").querySelector(".apply");
  apply.click();
  await frame();
  return performance.now() - start;
}, async move() {
  const start = performance.now();
  flushSync(() => api.set(old => {
    const next = [...old]; const first = next.findIndex(n => n.kind === "module");
    const second = next.findIndex((n, index) => index > first && n.kind === "module" && n.depth === 1);
    if (second < 0) return next;
    const chunk = next.splice(first, second - first);
    const destination = next.findIndex((n,index) => index >= first && n.kind === "module" && n.depth === 1);
    // Move the complete first subtree AFTER the second top-level module's subtree.
    let end = destination + 1;
    while (end < next.length && next[end].depth > 1) end++;
    next.splice(end, 0, ...chunk);
    return next;
  }));
  await frame();
  return performance.now() - start;
}};
window.__rmBench = api;

const BranchRow = memo(function BranchRow({ row, onApply, onDrop, onPreview, dropMarker }) {
  const [draft, setDraft] = useState(row.text);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { if (!dirty) setDraft(row.text); }, [row.text, dirty]);
  const editable = row.kind === "module" || row.kind === "conclusion" || row.kind === "paragraph";
  function beginDrag(event) {
    event.dataTransfer.setData("text/x-reportmaker-prototype-node", row.id);
    event.dataTransfer.effectAllowed = "move";
  }
  function over(event) {
    if (!event.dataTransfer.types.includes("text/x-reportmaker-prototype-node")) return;
    event.preventDefault();
    const bounds = event.currentTarget.getBoundingClientRect();
    const fraction = (event.clientY - bounds.top) / Math.max(1, bounds.height);
    const location = row.kind === "root" ? "inside" :
      row.kind === "module" || row.kind === "conclusion" ?
      (fraction < .25 ? "before" : fraction > .75 ? "after" : "inside") :
      fraction < .5 ? "before" : "after";
    onPreview(row.id, location);
  }
  const marker = dropMarker?.id === row.id ? dropMarker.position : null;
  return <div className={"branch-row " + (marker ? "hover-" + marker : "")}
       style={{"--depth":row.depth}} data-rowid={row.id} data-rowkind={row.kind}
       onDragOver={over} onDragLeave={() => onPreview(null, null)}
       onDrop={event => { event.preventDefault(); onDrop(event.dataTransfer.getData("text/x-reportmaker-prototype-node"), row.id, dropMarker?.position); }}>
       <div className="gutter" aria-hidden="true"><span className="connector"/></div>
       <section className="branch-card">
         <header><span>{KIND[row.kind] ?? row.kind.toUpperCase()}</span><div className="spacer"/>
           {row.kind !== "root" && row.kind !== "conclusion" &&
             <button className="drag" draggable={true} onDragStart={beginDrag} aria-label="Drag branch node">≡ Drag</button>}
         </header>
         {editable ? <div className="editor">
           {row.kind === "paragraph" ?
             <textarea value={draft} onChange={e=>{setDraft(e.target.value);setDirty(true)}}/> :
             <input value={draft} onChange={e=>{setDraft(e.target.value);setDirty(true)}}/>}
           {dirty && <button className="apply" onClick={()=>{onApply(row.id,draft,row.kind);setDirty(false)}}>Apply</button>}
         </div> : <div className="value">{row.text || "(Empty)"}</div>}
         {marker && <strong className={"indicator "+marker}>{marker.toUpperCase()}</strong>}
       </section>
     </div>;
});

function App() {
  const [nodes, setNodes] = useState([]);
  const [hover, setHover] = useState(null);
  const [notice, setNotice] = useState("Experimental rendering projection — no production report data");
  const activeBridge = useRef(null);
  useEffect(() => {
    if (!window.__TAURI_INTERNALS__) return;
    let closed = false;
    startNativeBridge().then(async transport => {
      const hello = await transport.request({action:"hello"});
      if (closed) { await transport.close(); return; }
      activeBridge.current = {transport, generation:hello.generation, revision:hello.revision};
      setNodes(hello.rows);
      setNotice("Native Tauri Python sidecar connected — all edits use canonical commands.");
    }).catch(error=>setNotice("Native bridge unavailable: "+error.message));
    return () => {closed=true;activeBridge.current?.transport.close();};
  },[]);
  api.set = setNodes;
  api.size = nodes.length;
  const apply = useCallback((id, text, kind) => {
    const bridge = activeBridge.current;
    if (!bridge) {
      setNodes(old => old.map(row => row.id === id ? {...row, text} : row));
      setNotice("Browser-only prototype edit; native Python gateway not connected.");
      return;
    }
    bridge.transport.request({action:kind === "paragraph" ? "set_text" : "rename", target:id, text,
      expectedRevision:bridge.revision, generation:bridge.generation}).then(async result => {
      bridge.revision = result.revision;
      const snapshot = await bridge.transport.request({action:"snapshot"});
      setNodes(snapshot.rows);
      setNotice("Committed to Python canonical report (revision "+bridge.revision+")");
    }).catch(error => setNotice("Canonical command rejected: "+error.message));
  },[]);
  const preview = useCallback((id, position) => setHover(id ? {id,position}:null),[]);
  const drop = useCallback((source, target, position) => {
    setHover(null);
    const bridge = activeBridge.current;
    if (!bridge) {
      setNotice("Browser-only preview. Python plan_drop/move_node required for commit.");
      return;
    }
    bridge.transport.request({action:"move", source, target, position,
      expectedRevision:bridge.revision, generation:bridge.generation}).then(async result => {
      bridge.revision = result.revision;
      const snapshot = await bridge.transport.request({action:"snapshot"});
      setNodes(snapshot.rows);
      setNotice("Canonical move committed (revision "+bridge.revision+") — Undo available.");
    }).catch(error=>setNotice("Move rejected: "+error.message));
  },[]);
  return <main><div className="workspace">
    <div className="toolbar"><div><b>ReportMaker V2</b><span> Branch Editor / Tauri proof of concept</span></div>
      <div className="buttons">{[82,302,802].map(size=><button key={size} onClick={()=>api.load(size)}>{size} nodes</button>)}</div>
    </div>
    <aside className="notice">{notice} · Visible nodes: {nodes.length}</aside>
    <div className="canvas" role="tree" aria-label="Synthetic report branch hierarchy">
      {nodes.map(row => <BranchRow key={row.id} row={row} onApply={apply} onPreview={preview} onDrop={drop} dropMarker={hover}/>)}
    </div>
  </div></main>;
}
createRoot(document.getElementById("root")).render(<App />);
