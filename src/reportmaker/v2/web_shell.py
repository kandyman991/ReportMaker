"""Self-contained HTML5/CSS/JS application shell for ReportMaker V2.

100% offline: no external CDNs, fonts, or network requests.
Communicates exclusively with the local Python BackendBridge over QWebChannel.
"""
from __future__ import annotations

HTML_SHELL = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ReportMaker V2 — Engineering Field Report Studio</title>
<style>
:root, [data-theme="dark"] {
  --bg-app: #0B0F17;
  --bg-header: #111827;
  --bg-rail: #0E1420;
  --bg-toolbar: #0F1522;
  --bg-card: #131B2E;
  --bg-card-header: rgba(24, 34, 56, 0.72);
  --bg-subcard: rgba(13, 20, 34, 0.85);
  --bg-input: #0B0F17;
  --bg-hover: #1E293B;
  --bg-badge: #1E293B;
  --bg-preview-well: #090C12;
  --border-main: #1E293B;
  --border-subtle: rgba(51, 65, 85, 0.55);
  --border-focus: #3B82F6;
  --text-main: #F1F5F9;
  --text-secondary: #CBD5E1;
  --text-muted: #94A3B8;
  --text-dim: #64748B;
  --accent: #2563EB;
  --accent-hover: #1D4ED8;
  --accent-soft: rgba(37, 99, 235, 0.16);
  --accent-border: rgba(59, 130, 246, 0.4);
  --emerald: #10B981;
  --emerald-soft: rgba(16, 185, 129, 0.14);
  --amber: #F59E0B;
  --amber-soft: rgba(245, 158, 11, 0.15);
  --purple: #8B5CF6;
  --purple-soft: rgba(139, 92, 246, 0.15);
  --danger: #EF4444;
  --danger-soft: rgba(239, 68, 68, 0.15);
  --card-shadow: 0 6px 20px -4px rgba(0, 0, 0, 0.45);
}

[data-theme="light"] {
  --bg-app: #F1F5F9;
  --bg-header: #FFFFFF;
  --bg-rail: #F8FAFC;
  --bg-toolbar: #F8FAFC;
  --bg-card: #FFFFFF;
  --bg-card-header: #F8FAFC;
  --bg-subcard: #F1F5F9;
  --bg-input: #FFFFFF;
  --bg-hover: #E2E8F0;
  --bg-badge: #E2E8F0;
  --bg-preview-well: #CBD5E1;
  --border-main: #CBD5E1;
  --border-subtle: #E2E8F0;
  --border-focus: #2563EB;
  --text-main: #0F172A;
  --text-secondary: #1E293B;
  --text-muted: #475569;
  --text-dim: #64748B;
  --accent: #2563EB;
  --accent-hover: #1D4ED8;
  --accent-soft: rgba(37, 99, 235, 0.1);
  --accent-border: rgba(37, 99, 235, 0.35);
  --emerald: #059669;
  --emerald-soft: rgba(5, 150, 105, 0.12);
  --amber: #D97706;
  --amber-soft: rgba(217, 119, 6, 0.12);
  --purple: #7C3AED;
  --purple-soft: rgba(124, 58, 237, 0.12);
  --danger: #DC2626;
  --danger-soft: rgba(220, 38, 38, 0.12);
  --card-shadow: 0 2px 10px -2px rgba(15, 23, 42, 0.08);
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  background: var(--bg-app);
  color: var(--text-main);
  height: 100vh;
  width: 100vw;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  user-select: none;
  font-size: 13px;
}

.mono {
  font-family: "Cascadia Code", Consolas, "Courier New", monospace;
}

/* Scrollbars */
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(100, 116, 139, 0.38); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: rgba(100, 116, 139, 0.65); }

/* TOP COMMAND BAR */
.top-header {
  height: 54px;
  background: var(--bg-header);
  border-bottom: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  flex-shrink: 0;
  gap: 10px;
}

.brand-cluster {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-logo {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: linear-gradient(135deg, #2563EB, #4F46E5);
  display: flex;
  align-items: center;
  justify-content: center;
  color: #fff;
  box-shadow: 0 3px 10px rgba(37, 99, 235, 0.35);
  flex-shrink: 0;
}

.brand-titles {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.brand-name {
  font-weight: 700;
  font-size: 13px;
  color: var(--text-main);
  letter-spacing: -0.01em;
}

.v2-badge {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
}

.project-badge {
  font-size: 11px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--emerald);
  display: inline-block;
}

.status-dot.dirty {
  background: var(--amber);
}

.v-divider {
  width: 1px;
  height: 24px;
  background: var(--border-main);
  margin: 0 4px;
  flex-shrink: 0;
}

.customer-pill {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 7px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}

.customer-pill:hover {
  border-color: var(--accent);
  background: var(--bg-hover);
}

.customer-pill-label {
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 600;
  text-transform: uppercase;
}

.customer-pill-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-main);
  max-width: 240px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Header buttons */
.action-cluster {
  display: flex;
  align-items: center;
  gap: 6px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 11px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  border: 1px solid var(--border-main);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.14s ease;
  white-space: nowrap;
}

.btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-main);
  border-color: var(--text-dim);
}

.btn:disabled {
  opacity: 0.42;
  cursor: not-allowed;
}

.btn-icon {
  padding: 6px 8px;
}

.btn-primary {
  background: var(--accent);
  color: #ffffff;
  border-color: var(--accent);
  box-shadow: 0 2px 8px rgba(37, 99, 235, 0.3);
}

.btn-primary:hover:not(:disabled) {
  background: var(--accent-hover);
  border-color: var(--accent-hover);
  color: #ffffff;
}

.btn-soft {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent-border);
}

.btn-soft:hover:not(:disabled) {
  background: var(--accent);
  color: #ffffff;
}

.btn-active {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent);
}

.airgap-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 9px;
  border-radius: 999px;
  background: var(--emerald-soft);
  border: 1px solid rgba(16, 185, 129, 0.32);
  color: var(--emerald);
  font-size: 11px;
  font-weight: 600;
}

/* MAIN WORKSPACE AREA */
.workspace-body {
  flex: 1;
  display: flex;
  min-height: 0;
  overflow: hidden;
}

/* LEFT NAVIGATION RAIL */
.left-rail {
  width: 58px;
  background: var(--bg-rail);
  border-right: 1px solid var(--border-main);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  justify-content: space-between;
  flex-shrink: 0;
}

.rail-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  width: 100%;
}

.rail-btn {
  width: 40px;
  height: 40px;
  border-radius: 10px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  position: relative;
  transition: all 0.15s ease;
}

.rail-btn:hover {
  background: var(--bg-hover);
  color: var(--text-main);
}

.rail-btn.active {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent-border);
}

.rail-badge {
  position: absolute;
  top: 3px;
  right: 3px;
  background: var(--accent);
  color: #fff;
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 8px;
  line-height: 1.1;
}

.rail-lang-badge {
  position: absolute;
  bottom: 2px;
  right: 2px;
  background: var(--emerald);
  color: #06281E;
  font-size: 8px;
  font-weight: 800;
  padding: 1px 3px;
  border-radius: 4px;
}

/* CENTER BRANCH CANVAS */
.canvas-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 420px;
  background: var(--bg-app);
  overflow: hidden;
}

.context-bar {
  height: 44px;
  background: var(--bg-toolbar);
  border-bottom: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  gap: 8px;
  flex-shrink: 0;
}

.insert-strip {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: nowrap;
  overflow-x: auto;
}

.strip-label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-dim);
  margin-right: 4px;
}

.chip-btn {
  padding: 4px 9px;
  font-size: 11.5px;
  font-weight: 600;
  border-radius: 5px;
  border: 1px solid var(--border-main);
  background: var(--bg-card);
  color: var(--text-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 0.12s;
  white-space: nowrap;
}

.chip-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-main);
  border-color: var(--accent);
}

.chip-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.chip-btn.primary {
  background: var(--accent-soft);
  color: var(--accent);
  border-color: var(--accent-border);
}

.chip-btn.primary:hover:not(:disabled) {
  background: var(--accent);
  color: #fff;
}

.search-box {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--bg-input);
  border: 1px solid var(--border-main);
  border-radius: 6px;
  padding: 4px 9px;
  width: 210px;
}

.search-box:focus-within {
  border-color: var(--border-focus);
}

.search-box input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-main);
  font-size: 12px;
  width: 100%;
}

/* Scrollable Canvas Content */
.canvas-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 22px 26px 60px 26px;
}

.canvas-container {
  max-width: 880px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transform-origin: top center;
}

/* REPORT METADATA HEADER CARD */
.report-meta-card {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  padding: 18px 20px;
  box-shadow: var(--card-shadow);
  position: relative;
  overflow: hidden;
}

.report-meta-card::before {
  content: "";
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 3px;
  background: linear-gradient(90deg, #2563EB, #6366F1, #10B981);
}

.meta-top-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}

.meta-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.tag {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  padding: 2px 7px;
  border-radius: 4px;
  letter-spacing: 0.04em;
}

.tag-blue { background: var(--accent-soft); color: var(--accent); border: 1px solid var(--accent-border); }
.tag-emerald { background: var(--emerald-soft); color: var(--emerald); }
.tag-amber { background: var(--amber-soft); color: var(--amber); }
.tag-purple { background: var(--purple-soft); color: var(--purple); }
.tag-slate { background: var(--bg-badge); color: var(--text-muted); }

.report-title-input {
  width: 100%;
  font-size: 19px;
  font-weight: 700;
  color: var(--text-main);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 6px;
  padding: 4px 6px;
  margin-left: -6px;
  outline: none;
  transition: border-color 0.15s, background 0.15s;
}

.report-title-input:hover {
  border-color: var(--border-subtle);
  background: var(--bg-input);
}

.report-title-input:focus {
  border-color: var(--border-focus);
  background: var(--bg-input);
}

.meta-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.meta-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.meta-field label {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: var(--text-dim);
}

.meta-field input {
  background: var(--bg-input);
  border: 1px solid var(--border-main);
  border-radius: 5px;
  padding: 5px 8px;
  color: var(--text-main);
  font-size: 12px;
  font-weight: 500;
  outline: none;
}

.meta-field input:focus {
  border-color: var(--border-focus);
}

/* MODULE CARDS */
.module-card {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  box-shadow: var(--card-shadow);
  transition: border-color 0.15s, box-shadow 0.15s;
}

.module-card.selected {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent), var(--card-shadow);
}

.module-card.conclusion-card {
  border-color: rgba(16, 185, 129, 0.45);
}

.module-card.drag-over {
  border-color: var(--amber);
  box-shadow: 0 0 0 2px var(--amber);
}

.module-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: var(--bg-card-header);
  border-bottom: 1px solid var(--border-subtle);
  border-top-left-radius: 11px;
  border-top-right-radius: 11px;
  gap: 10px;
  cursor: pointer;
}

.module-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.collapse-btn {
  width: 24px;
  height: 24px;
  border-radius: 5px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}

.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-main);
}

.sec-num-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 5px;
  background: var(--accent-soft);
  color: var(--accent);
  border: 1px solid var(--accent-border);
  flex-shrink: 0;
}

.sec-num-badge.conclusion {
  background: var(--emerald-soft);
  color: var(--emerald);
  border-color: rgba(16, 185, 129, 0.35);
}

.module-title-input {
  flex: 1;
  font-size: 14px;
  font-weight: 700;
  color: var(--text-main);
  background: transparent;
  border: 1px solid transparent;
  border-radius: 5px;
  padding: 4px 8px;
  outline: none;
  min-width: 120px;
}

.module-title-input:hover:not(:disabled) {
  border-color: var(--border-subtle);
  background: var(--bg-input);
}

.module-title-input:focus:not(:disabled) {
  border-color: var(--border-focus);
  background: var(--bg-input);
}

.module-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.icon-act-btn {
  padding: 4px 7px;
  font-size: 11px;
  border-radius: 5px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 3px;
}

.icon-act-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-main);
  border-color: var(--border-main);
}

.icon-act-btn.danger:hover:not(:disabled) {
  background: var(--danger-soft);
  color: var(--danger);
  border-color: rgba(239, 68, 68, 0.35);
}

.icon-act-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.module-body {
  padding: 14px 16px 14px 26px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: relative;
}

/* Tree vertical guide line */
.module-body::before {
  content: "";
  position: absolute;
  left: 14px;
  top: 10px;
  bottom: 14px;
  width: 2px;
  background: var(--border-main);
  border-radius: 2px;
}

/* CONTENT BLOCK CARDS */
.block-node {
  position: relative;
  background: var(--bg-subcard);
  border: 1px solid var(--border-main);
  border-radius: 9px;
  padding: 10px 12px;
  transition: border-color 0.14s;
}

.block-node::before {
  content: "";
  position: absolute;
  left: -12px;
  top: 18px;
  width: 12px;
  height: 2px;
  background: var(--border-main);
}

.block-node:hover {
  border-color: var(--text-dim);
}

.block-node.selected {
  border-color: var(--accent);
}

.block-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 7px;
  gap: 8px;
}

.block-kind-info {
  display: flex;
  align-items: center;
  gap: 7px;
}

.block-textarea {
  width: 100%;
  min-height: 62px;
  background: var(--bg-input);
  border: 1px solid var(--border-main);
  border-radius: 6px;
  padding: 8px 10px;
  color: var(--text-main);
  font-family: inherit;
  font-size: 13px;
  line-height: 1.5;
  resize: vertical;
  outline: none;
}

.block-textarea:focus {
  border-color: var(--border-focus);
}

.heading-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.heading-level-select {
  background: var(--bg-input);
  color: var(--text-main);
  border: 1px solid var(--border-main);
  border-radius: 6px;
  padding: 6px 8px;
  font-size: 12px;
  font-weight: 700;
  outline: none;
}

.heading-input {
  flex: 1;
  background: var(--bg-input);
  color: var(--text-main);
  border: 1px solid var(--border-main);
  border-radius: 6px;
  padding: 6px 10px;
  font-size: 14px;
  font-weight: 700;
  outline: none;
}

.heading-input:focus {
  border-color: var(--border-focus);
}

/* PHOTO BLOCK */
.photo-block-grid {
  display: flex;
  gap: 14px;
  align-items: flex-start;
}

.photo-thumb-box {
  width: 185px;
  height: 128px;
  border-radius: 7px;
  overflow: hidden;
  border: 1px solid var(--border-main);
  background: #000;
  position: relative;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
}

.photo-thumb-box img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.photo-annotate-overlay {
  position: absolute;
  inset: 0;
  background: rgba(11, 15, 23, 0.65);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s;
}

.photo-thumb-box:hover .photo-annotate-overlay {
  opacity: 1;
}

.photo-meta-col {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

/* TABLE BLOCK */
.table-editor-wrap {
  overflow-x: auto;
  border: 1px solid var(--border-main);
  border-radius: 6px;
}

.editor-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.editor-table th, .editor-table td {
  border: 1px solid var(--border-main);
  padding: 0;
}

.editor-table tr:first-child td input {
  font-weight: 700;
  background: rgba(37, 99, 235, 0.08);
}

.editor-table input {
  width: 100%;
  border: none;
  background: var(--bg-input);
  color: var(--text-main);
  padding: 6px 8px;
  font-size: 12px;
  outline: none;
}

.editor-table input:focus {
  background: var(--accent-soft);
}

/* Module quick-insert footer bar */
.module-quick-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding-top: 4px;
  flex-wrap: wrap;
}

/* RIGHT SPLIT PANE: LIVE A4 DOCUMENT PROOF */
.preview-pane {
  width: 46%;
  max-width: 680px;
  min-width: 360px;
  background: var(--bg-preview-well);
  border-left: 1px solid var(--border-main);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.preview-pane.hidden {
  display: none;
}

.preview-header {
  height: 44px;
  background: var(--bg-toolbar);
  border-bottom: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  flex-shrink: 0;
}

.preview-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px 20px 48px 20px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 20px;
}

/* A4 Paper Sheet */
.a4-sheet {
  width: 100%;
  max-width: 560px;
  min-height: 792px;
  background: #FFFFFF;
  color: #0F172A;
  border-radius: 3px;
  padding: 36px 40px;
  box-shadow: 0 20px 45px -10px rgba(0, 0, 0, 0.65), 0 0 1px 1px rgba(15, 23, 42, 0.12);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  font-size: 11px;
  line-height: 1.48;
}

.a4-letterhead {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  border-bottom: 2px solid #0F172A;
  padding-bottom: 12px;
  margin-bottom: 14px;
}

.a4-brand-title {
  font-size: 16px;
  font-weight: 900;
  letter-spacing: -0.02em;
  color: #0F172A;
}

.a4-brand-sub {
  font-size: 8.5px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #2563EB;
}

.a4-meta-box {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 14px;
  background: #F8FAFC;
  border: 1px solid #CBD5E1;
  border-radius: 4px;
  padding: 9px 12px;
  margin-bottom: 16px;
  font-size: 9.5px;
}

.a4-meta-row {
  display: flex;
  gap: 4px;
}

.a4-meta-label {
  color: #64748B;
  font-weight: 700;
  min-width: 66px;
}

.a4-meta-val {
  color: #0F172A;
  font-weight: 600;
}

.a4-doc-title {
  font-size: 14px;
  font-weight: 800;
  color: #0F172A;
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.a4-sec-heading {
  font-size: 11.5px;
  font-weight: 800;
  color: #0F172A;
  border-bottom: 1px solid #E2E8F0;
  padding-bottom: 3px;
  margin-top: 12px;
  margin-bottom: 6px;
  text-transform: uppercase;
}

.a4-subsec-heading {
  font-size: 10.5px;
  font-weight: 700;
  color: #1E293B;
  margin-top: 8px;
  margin-bottom: 4px;
}

.a4-paragraph {
  color: #334155;
  margin-bottom: 7px;
  white-space: pre-wrap;
}

.a4-photo-figure {
  margin: 8px 0;
  border: 1px solid #E2E8F0;
  background: #F8FAFC;
  padding: 6px;
  border-radius: 3px;
  text-align: center;
}

.a4-photo-figure img {
  max-width: 100%;
  max-height: 210px;
  object-fit: contain;
  border-radius: 2px;
}

.a4-photo-caption {
  font-size: 9px;
  color: #475569;
  font-style: italic;
  margin-top: 4px;
}

.a4-table {
  width: 100%;
  border-collapse: collapse;
  margin: 8px 0;
  font-size: 9.5px;
}

.a4-table th, .a4-table td {
  border: 1px solid #CBD5E1;
  padding: 4px 6px;
  text-align: left;
}

.a4-table tr:first-child td {
  background: #F1F5F9;
  font-weight: 700;
}

.a4-page-break {
  border-top: 1px dashed #94A3B8;
  text-align: center;
  font-size: 8.5px;
  color: #64748B;
  margin: 12px 0;
  padding-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.a4-footer {
  margin-top: 24px;
  padding-top: 8px;
  border-top: 1px solid #CBD5E1;
  display: flex;
  justify-content: space-between;
  font-size: 8.5px;
  color: #64748B;
}

/* GALLERY MODAL / DRAWER */
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(5, 8, 15, 0.72);
  display: none;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 24px;
}

.modal-backdrop.open {
  display: flex;
}

.modal-card {
  background: var(--bg-card);
  border: 1px solid var(--border-main);
  border-radius: 12px;
  width: 100%;
  max-width: 760px;
  max-height: 82vh;
  display: flex;
  flex-direction: column;
  box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.65);
  overflow: hidden;
}

.modal-header {
  padding: 14px 18px;
  background: var(--bg-card-header);
  border-bottom: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.modal-body {
  padding: 18px;
  overflow-y: auto;
  flex: 1;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(165px, 1fr));
  gap: 12px;
}

.gallery-item {
  background: var(--bg-subcard);
  border: 1px solid var(--border-main);
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.gallery-item img {
  width: 100%;
  height: 110px;
  object-fit: cover;
  background: #000;
}

.gallery-item-Foot {
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

/* BOTTOM STATUS BAR */
.status-footer {
  height: 28px;
  background: var(--bg-header);
  border-top: 1px solid var(--border-main);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}

.status-cluster {
  display: flex;
  align-items: center;
  gap: 14px;
}

.toast-banner {
  position: fixed;
  bottom: 38px;
  right: 20px;
  background: var(--bg-card);
  border: 1px solid var(--accent);
  color: var(--text-main);
  padding: 9px 14px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  box-shadow: 0 10px 25px rgba(0,0,0,0.45);
  display: none;
  z-index: 200;
}
</style>
<!-- QWEBCHANNEL_SCRIPT_PLACEHOLDER -->
</head>
<body>

<!-- TOP COMMAND BAR -->
<header class="top-header">
  <div class="brand-cluster">
    <div class="brand-logo" title="ReportMaker V2">
      <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
      </svg>
    </div>
    <div class="brand-titles">
      <div class="brand-row">
        <span class="brand-name">ReportMaker</span>
        <span class="v2-badge">V2 STUDIO</span>
      </div>
      <div class="project-badge">
        <span id="dirtyDot" class="status-dot"></span>
        <span id="projectPathLabel" class="mono">Untitled project (.rmproj)</span>
      </div>
    </div>

    <div class="v-divider"></div>

    <!-- Active Customer & Machine Pill -->
    <div class="customer-pill" onclick="callBackend('open_report_info_dialog')" title="Click to configure Customer, Site, Machine, Dates & Languages">
      <div>
        <div class="customer-pill-label">Customer / Machine</div>
        <div id="headerCustomerLabel" class="customer-pill-val">Customer — Site</div>
      </div>
      <svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"/>
      </svg>
    </div>
  </div>

  <!-- Right Action Cluster -->
  <div class="action-cluster">
    <button class="btn btn-icon" id="btnUndo" onclick="callBackend('undo')" title="Undo (Ctrl+Z)">
      <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 10h10a8 8 0 018 8v2M3 10l6 6m-6-6l6-6"/></svg>
    </button>
    <button class="btn btn-icon" id="btnRedo" onclick="callBackend('redo')" title="Redo (Ctrl+Y)">
      <svg width="15" height="15" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 10h-10a8 8 0 00-8 8v2M21 10l-6 6m6-6l-6-6"/></svg>
    </button>

    <div class="v-divider"></div>

    <button class="btn" onclick="callBackend('new_project')" title="New Report Project (Ctrl+N)">New</button>
    <button class="btn" onclick="callBackend('open_project')" title="Open .rmproj Bundle (Ctrl+O)">Open…</button>
    <button class="btn" onclick="callBackend('save_project')" title="Save .rmproj Bundle (Ctrl+S)">Save</button>
    <button class="btn" onclick="callBackend('save_project_as')" title="Save Project As…">Save As…</button>

    <div class="v-divider"></div>

    <button class="btn btn-soft" onclick="callBackend('export_document', 'docx')" title="Export Editable Microsoft Word (.docx)">
      Export DOCX
    </button>
    <button class="btn btn-primary" onclick="callBackend('export_document', 'pdf')" title="Export Paginated A4 PDF">
      Export PDF
    </button>

    <div class="v-divider"></div>

    <!-- Theme Toggle -->
    <button class="btn btn-icon" id="btnThemeToggle" onclick="toggleTheme()" title="Switch Dark Slate / Light Paper Chrome">
      <span id="themeIcon">☀️</span>
    </button>

    <!-- AI Assistant Drawer Toggle -->
    <button class="btn" id="btnAiDrawer" onclick="callBackend('toggle_ai_drawer')" title="Toggle Isolated ChatGPT Assistant Drawer">
      ✨ AI Assistant
    </button>

    <!-- Split Preview Toggle -->
    <button class="btn btn-active" id="btnTogglePreview" onclick="togglePreviewPane()" title="Toggle Live A4 Document Proof (Ctrl+\)">
      Split Proof
    </button>
  </div>
</header>

<!-- MAIN WORKSPACE BODY -->
<div class="workspace-body">

  <!-- LEFT NAVIGATION RAIL -->
  <aside class="left-rail">
    <div class="rail-group">
      <button class="rail-btn active" id="railBranch" onclick="setFocusMode('branch')" title="Branch Canvas Editor">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
      </button>

      <button class="rail-btn" id="railGallery" onclick="openGalleryModal()" title="Project Photo Gallery">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"/></svg>
        <span id="galleryCountBadge" class="rail-badge">0</span>
      </button>

      <button class="rail-btn" onclick="callBackend('open_customer_manager')" title="Customer, Site & Machine Database">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4"/></svg>
      </button>

      <button class="rail-btn" onclick="callBackend('open_translations_dialog')" title="Multilingual Translations & Output Languages">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129"/></svg>
        <span id="langBadge" class="rail-lang-badge">EN</span>
      </button>

      <button class="rail-btn" onclick="callBackend('import_word_template')" title="Import Word (.docx) Page Header/Footer Template">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 13h6m-3-3v6m5 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/></svg>
      </button>
    </div>

    <div class="rail-group">
      <button class="rail-btn" onclick="callBackend('open_report_info_dialog')" title="Report Metadata & Intervention Settings">
        <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/></svg>
      </button>
    </div>
  </aside>

  <!-- CENTER PANE: INTERACTIVE BRANCH CANVAS -->
  <main class="canvas-pane">
    <!-- Contextual Insertion Strip -->
    <div class="context-bar">
      <div class="insert-strip">
        <span class="strip-label">Insert</span>
        <button class="chip-btn primary" onclick="promptAddModule()">+ Module</button>
        <button class="chip-btn" id="btnAddSubmodule" onclick="promptAddSubmodule()">+ Submodule</button>
        <div class="v-divider"></div>
        <button class="chip-btn" onclick="addBlockToSelected('paragraph')">¶ Text</button>
        <button class="chip-btn" onclick="addBlockToSelected('heading')">H Heading</button>
        <button class="chip-btn" onclick="addBlockToSelected('photo')">📷 Photo…</button>
        <button class="chip-btn" onclick="addBlockToSelected('table')">⊞ Table</button>
        <button class="chip-btn" onclick="addBlockToSelected('page_break')">⎯ Page Break</button>
      </div>

      <div style="display:flex; align-items:center; gap:8px;">
        <div class="search-box">
          <svg width="13" height="13" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
          <input type="text" id="searchInput" placeholder="Filter modules or text…" oninput="onSearchFilter(this.value)">
        </div>
        <button class="chip-btn" onclick="adjustZoom(-0.08)" title="Zoom Out">A-</button>
        <span id="zoomLabel" class="mono" style="font-size:11px; color:var(--text-muted); min-width:38px; text-align:center;">100%</span>
        <button class="chip-btn" onclick="adjustZoom(0.08)" title="Zoom In">A+</button>
      </div>
    </div>

    <!-- Scrollable Branch Canvas -->
    <div class="canvas-scroll">
      <div id="canvasContainer" class="canvas-container">
        <!-- Populated dynamically from ReportSession state -->
      </div>
    </div>
  </main>

  <!-- RIGHT PANE: LIVE A4 DOCUMENT PROOF & EXACT PDF PROOF -->
  <section id="previewPane" class="preview-pane">
    <div class="preview-header">
      <div style="display:flex; align-items:center; gap:8px;">
        <span class="status-dot"></span>
        <span style="font-weight:700; font-size:12px;">LIVE A4 DOCUMENT PROOF</span>
        <span id="previewLangLabel" class="tag tag-slate mono">en</span>
      </div>
      <div style="display:flex; align-items:center; gap:6px;">
        <button class="chip-btn" id="btnModeSchematic" onclick="setProofMode('schematic')">Live Sheet</button>
        <button class="chip-btn primary" id="btnModePdf" onclick="requestExactPdfProof()">Paginated PDF Proof</button>
        <button class="chip-btn" onclick="callBackend('export_bundle')" title="Export Multi-Language ZIP Package">ZIP Bundle</button>
      </div>
    </div>

    <div class="preview-scroll" id="previewScroll">
      <!-- Live A4 Paper Sheet or Exact Paginated PDF Proof rendered here -->
    </div>
  </section>

</div>

<!-- GALLERY MODAL -->
<div id="galleryModal" class="modal-backdrop" onclick="if(event.target===this) closeGalleryModal()">
  <div class="modal-card">
    <div class="modal-header">
      <div>
        <div style="font-weight:700; font-size:14px;">Project Media Library</div>
        <div style="font-size:11px; color:var(--text-muted);">Original camera working copies are stored losslessly inside the .rmproj bundle</div>
      </div>
      <div style="display:flex; gap:8px;">
        <button class="btn btn-primary" onclick="callBackend('import_photos_to_gallery')">+ Import Image Files…</button>
        <button class="btn" onclick="callBackend('paste_photo_to_gallery')">📋 Paste Clipboard</button>
        <button class="btn" onclick="closeGalleryModal()">Close</button>
      </div>
    </div>
    <div class="modal-body">
      <div id="galleryGrid" class="gallery-grid"></div>
    </div>
  </div>
</div>

<!-- BOTTOM STATUS FOOTER -->
<footer class="status-footer">
  <div class="status-cluster">
    <span class="airgap-pill" style="padding:1px 8px; font-size:10px;">● Local Airgap Active</span>
    <span id="footerStats">0 Modules · 0 Blocks · 0 Photos</span>
    <span id="footerRevision" class="mono">Rev 0</span>
  </div>
  <div class="status-cluster">
    <span id="footerSelection">Selected: None</span>
    <span class="mono">ReportMaker V2 HTML5 Engine</span>
  </div>
</footer>

<div id="toastBanner" class="toast-banner"></div>

<script>
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

function applyBackendResponse(rawJson) {
  if (!rawJson) return;
  try {
    const res = typeof rawJson === "string" ? JSON.parse(rawJson) : rawJson;
    if (res.error) {
      showToast(res.error, true);
    }
    if (res.toast) {
      showToast(res.toast, false);
    }
    if (res.state) {
      appState = res.state;
      if (!selectedModuleId || !findModuleById(selectedModuleId)) {
        selectedModuleId = (appState.modules && appState.modules.length > 0)
          ? appState.modules[0].id
          : (appState.conclusion ? appState.conclusion.id : null);
        selectedBlockId = null;
      }
      renderAll();
    }
  } catch (err) {
    console.error("Failed to parse backend response:", err);
  }
}

function callBackend(method, ...args) {
  if (!backend || typeof backend[method] !== "function") {
    showToast("Backend channel initializing…", true);
    return;
  }
  backend[method](...args, function(response) {
    applyBackendResponse(response);
  });
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
    title: document.getElementById("metaTitleInput")?.value || appState.report.title,
    customer_name: document.getElementById("metaCustomerInput")?.value || appState.report.customer_name,
    site_name: document.getElementById("metaSiteInput")?.value || appState.report.site_name,
    machine_name: document.getElementById("metaMachineInput")?.value || appState.report.machine_name,
    ticket: document.getElementById("metaTicketInput")?.value || appState.report.ticket,
    technicians: document.getElementById("metaTechInput")?.value || appState.report.technicians,
    start_date: document.getElementById("metaStartInput")?.value || appState.report.start_date,
    end_date: document.getElementById("metaEndInput")?.value || appState.report.end_date,
  };
  callBackend("update_report_header", JSON.stringify(payload));
}

function escapeHtml(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
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
    <div class="module-actions" onclick="event.stopPropagation()">
      <button class="icon-act-btn" onclick="callBackend('move_node', '${modId}', '${b.id}', 'up')" title="Move Up">↑</button>
      <button class="icon-act-btn" onclick="callBackend('move_node', '${modId}', '${b.id}', 'down')" title="Move Down">↓</button>
      <button class="icon-act-btn" onclick="callBackend('duplicate_node', '${modId}', '${b.id}')" title="Duplicate Block">⧉</button>
      <button class="icon-act-btn danger" onclick="callBackend('delete_node', '${modId}', '${b.id}')" title="Delete Block">✕</button>
    </div>
  `;

  if (b.kind === "paragraph") {
    return `
      <div class="block-node ${isSel}" data-block-id="${b.id}" onclick="event.stopPropagation(); selectTarget('${modId}', '${b.id}')">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-slate">¶ Paragraph</span>
          </div>
          ${commonActions}
        </div>
        <textarea class="block-textarea" placeholder="Write field observation or intervention details…"
          onfocus="selectTarget('${modId}', '${b.id}')"
          onchange="callBackend('update_paragraph', '${modId}', '${b.id}', this.value)">${escapeHtml(b.text)}</textarea>
      </div>
    `;
  }

  if (b.kind === "heading") {
    return `
      <div class="block-node ${isSel}" data-block-id="${b.id}" onclick="event.stopPropagation(); selectTarget('${modId}', '${b.id}')">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-blue">H${b.level} Heading</span>
          </div>
          ${commonActions}
        </div>
        <div class="heading-row">
          <select class="heading-level-select" onchange="callBackend('update_heading', '${modId}', '${b.id}', this.nextElementSibling.value, parseInt(this.value, 10))">
            <option value="1" ${b.level === 1 ? "selected" : ""}>H1</option>
            <option value="2" ${b.level === 2 ? "selected" : ""}>H2</option>
            <option value="3" ${b.level === 3 ? "selected" : ""}>H3</option>
          </select>
          <input type="text" class="heading-input" value="${escapeHtml(b.text)}" placeholder="Sub-heading title…"
            onfocus="selectTarget('${modId}', '${b.id}')"
            onchange="callBackend('update_heading', '${modId}', '${b.id}', this.value, ${b.level})">
        </div>
      </div>
    `;
  }

  if (b.kind === "photo") {
    const imgSrc = b.data_url || "";
    return `
      <div class="block-node ${isSel}" data-block-id="${b.id}" onclick="event.stopPropagation(); selectTarget('${modId}', '${b.id}')">
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
            ${imgSrc ? `<img src="${imgSrc}" alt="Photo">` : `<span style="color:#94A3B8;font-size:11px;">No image</span>`}
            <div class="photo-annotate-overlay">
              <button class="btn btn-primary" onclick="event.stopPropagation(); callBackend('edit_photo_annotations', '${modId}', '${b.id}')">
                ✎ Edit Annotations
              </button>
            </div>
          </div>
          <div class="photo-meta-col">
            <label style="font-size:10px; font-weight:700; text-transform:uppercase; color:var(--text-dim);">Figure Caption</label>
            <textarea class="block-textarea" style="min-height:54px;" placeholder="Describe photo evidence or component serial…"
              onfocus="selectTarget('${modId}', '${b.id}')"
              onchange="callBackend('update_photo_caption', '${modId}', '${b.id}', this.value)">${escapeHtml(b.caption)}</textarea>
            <div style="display:flex; gap:6px;">
              <button class="chip-btn primary" onclick="event.stopPropagation(); callBackend('edit_photo_annotations', '${modId}', '${b.id}')">
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
          onchange="commitTableCell('${modId}', '${b.id}', '${tableId}')"></td>`;
      });
      trs += `<tr>${tds}</tr>`;
    });
    return `
      <div class="block-node ${isSel}" data-block-id="${b.id}" onclick="event.stopPropagation(); selectTarget('${modId}', '${b.id}')">
        <div class="block-top-bar">
          <div class="block-kind-info">
            <span class="tag tag-purple">⊞ Structured Table (${rows.length}×${(rows[0] || []).length})</span>
            <button class="chip-btn" onclick="event.stopPropagation(); mutateTableShape('${modId}', '${b.id}', 'add_row')">+ Row</button>
            <button class="chip-btn" onclick="event.stopPropagation(); mutateTableShape('${modId}', '${b.id}', 'add_col')">+ Col</button>
            <button class="chip-btn" onclick="event.stopPropagation(); mutateTableShape('${modId}', '${b.id}', 'del_row')">- Row</button>
            <button class="chip-btn" onclick="event.stopPropagation(); mutateTableShape('${modId}', '${b.id}', 'del_col')">- Col</button>
          </div>
          ${commonActions}
        </div>
        <div class="table-editor-wrap">
          <table class="editor-table" id="${tableId}">
            <tbody>${trs}</tbody>
          </table>
        </div>
      </div>
    `;
  }

  if (b.kind === "page_break") {
    return `
      <div class="block-node ${isSel}" data-block-id="${b.id}" onclick="event.stopPropagation(); selectTarget('${modId}', '${b.id}')"
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
  callBackend("update_table", modId, blockId, JSON.stringify(rows));
}

function mutateTableShape(modId, blockId, op) {
  callBackend("mutate_table_shape", modId, blockId, op);
}

function toggleModuleCollapse(modId, ev) {
  ev.stopPropagation();
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
         data-module-id="${mod.id}"
         onclick="event.stopPropagation(); selectTarget('${mod.id}', null)">
      <div class="module-header">
        <div class="module-header-left">
          <button class="collapse-btn" onclick="toggleModuleCollapse('${mod.id}', event)" title="Collapse / Expand Section">
            ${isCollapsed ? "▸" : "▾"}
          </button>
          <span class="sec-num-badge ${isConclusion ? "conclusion" : ""} mono">
            ${isConclusion ? "FINAL" : escapeHtml(mod.number || "•")}
          </span>
          <input type="text" class="module-title-input"
            value="${escapeHtml(mod.title)}"
            ${isConclusion ? "disabled title='Dedicated Conclusions section title'" : ""}
            onclick="event.stopPropagation(); selectTarget('${mod.id}', null)"
            onchange="callBackend('rename_module', '${mod.id}', this.value)">
        </div>
        <div class="module-actions" onclick="event.stopPropagation()">
          ${!isConclusion ? `
            <button class="icon-act-btn" onclick="callBackend('add_submodule', '${mod.id}', 'Sub-section')" title="Add Nested Submodule">+Sub</button>
            <button class="icon-act-btn" onclick="callBackend('move_node', '${moveTargetMod}', '${moveTargetBlk}', 'up')" title="Move Up">↑</button>
            <button class="icon-act-btn" onclick="callBackend('move_node', '${moveTargetMod}', '${moveTargetBlk}', 'down')" title="Move Down">↓</button>
            <button class="icon-act-btn" onclick="callBackend('duplicate_node', '${moveTargetMod}', '${moveTargetBlk}')" title="Duplicate Module">⧉</button>
            <button class="icon-act-btn danger" onclick="callBackend('delete_node', '${moveTargetMod}', '${moveTargetBlk}')" title="Delete Module">✕</button>
          ` : `<span class="tag tag-emerald">Protected Section</span>`}
        </div>
      </div>

      ${!isCollapsed ? `
        <div class="module-body">
          ${blocksHtml || `<div style="font-size:12px; color:var(--text-dim); font-style:italic; padding:4px 0;">Empty section — use the quick bar below to add paragraphs, photos, or tables.</div>`}
          <div class="module-quick-bar" onclick="event.stopPropagation()">
            <button class="chip-btn" onclick="callBackend('add_block', '${mod.id}', 'paragraph')">+ Text</button>
            <button class="chip-btn" onclick="callBackend('add_block', '${mod.id}', 'heading')">+ Heading</button>
            <button class="chip-btn" onclick="callBackend('import_photo_to_module', '${mod.id}')">+ Photo…</button>
            <button class="chip-btn" onclick="callBackend('add_block', '${mod.id}', 'table')">+ Table</button>
            <button class="chip-btn" onclick="callBackend('add_block', '${mod.id}', 'page_break')">+ Page Break</button>
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
      html += `<div class="a4-paragraph">${escapeHtml(b.text || "")}</div>`;
    } else if (b.kind === "heading") {
      html += `<div class="a4-subsec-heading">${escapeHtml(b.text || "")}</div>`;
    } else if (b.kind === "photo") {
      html += `
        <div class="a4-photo-figure">
          ${b.data_url ? `<img src="${b.data_url}" style="width:${b.width_pct || 100}%;" alt="Figure">` : ""}
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
        <button class="chip-btn" ${currentPdfPage <= 0 ? "disabled" : ""} onclick="stepPdfPage(-1)">‹ Prev</button>
        <span class="mono" style="font-size:12px; font-weight:700;">Exact PDF Page ${currentPdfPage + 1} of ${pdfPages.length}</span>
        <button class="chip-btn" ${currentPdfPage >= pdfPages.length - 1 ? "disabled" : ""} onclick="stepPdfPage(1)">Next ›</button>
      </div>
      <div class="a4-sheet" style="padding:0; overflow:hidden; background:#fff;">
        <img src="${pageImg}" style="width:100%; height:auto; display:block;" alt="Rendered PDF Page">
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

function requestExactPdfProof() {
  if (!backend) return;
  showToast("Rendering exact paginated PDF proof…");
  backend.generate_pdf_proof(function(raw) {
    try {
      const res = JSON.parse(raw);
      if (res.error) {
        showToast(res.error, true);
        return;
      }
      pdfPages = res.pages || [];
      currentPdfPage = 0;
      proofMode = "pdf";
      renderPreviewPane();
      showToast(`Rendered ${pdfPages.length} exact PDF page(s)`);
    } catch (e) {
      showToast("Failed to render PDF proof", true);
    }
  });
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
      <img src="${item.data_url}" alt="${escapeHtml(item.name)}">
      <div class="gallery-item-Foot">
        <div class="mono" style="font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="${escapeHtml(item.name)}">
          ${escapeHtml(item.name)}
        </div>
        <button class="chip-btn primary" style="justify-content:center;"
          onclick="callBackend('insert_gallery_photo', '${targetMod}', '${item.asset_id}'); closeGalleryModal();">
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
            onchange="commitMetadataField()">
        </div>
        <div style="display:flex; gap:6px;">
          <button class="chip-btn" onclick="callBackend('open_report_info_dialog')">⚙ Full Details &amp; Languages…</button>
        </div>
      </div>

      <div class="meta-grid">
        <div class="meta-field">
          <label>Customer Name</label>
          <input type="text" id="metaCustomerInput" value="${escapeHtml(r.customer_name)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>Site / Location</label>
          <input type="text" id="metaSiteInput" value="${escapeHtml(r.site_name)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>Machine / Line</label>
          <input type="text" id="metaMachineInput" value="${escapeHtml(r.machine_name)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>Ticket / Job ID</label>
          <input type="text" id="metaTicketInput" class="mono" value="${escapeHtml(r.ticket)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>Technicians (comma-sep)</label>
          <input type="text" id="metaTechInput" value="${escapeHtml(r.technicians)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>Start Date (YYYY-MM-DD)</label>
          <input type="text" id="metaStartInput" class="mono" value="${escapeHtml(r.start_date)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field">
          <label>End Date (YYYY-MM-DD)</label>
          <input type="text" id="metaEndInput" class="mono" value="${escapeHtml(r.end_date)}" onchange="commitMetadataField()">
        </div>
        <div class="meta-field" style="justify-content:flex-end;">
          <button class="btn" style="height:29px;" onclick="callBackend('open_customer_manager')">Select from Customer DB…</button>
        </div>
      </div>
    </div>
  `;

  const modulesHtml = (appState.modules || []).map(m => renderModuleCardHtml(m, false)).join("");
  const conclusionHtml = appState.conclusion ? renderModuleCardHtml(appState.conclusion, true) : "";

  container.innerHTML = metaCardHtml + modulesHtml + conclusionHtml;

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
  }
});

// Initialize QWebChannel connection
window.addEventListener("DOMContentLoaded", function() {
  if (typeof QWebChannel !== "undefined" && window.qt && window.qt.webChannelTransport) {
    new QWebChannel(window.qt.webChannelTransport, function(channel) {
      backend = channel.objects.backend;
      backend.get_state(function(raw) {
        applyBackendResponse(raw);
      });
    });
  }
});
</script>
</body>
</html>
"""
