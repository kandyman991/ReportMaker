"""HTML5/CSS/JS Desktop Shell for ReportMaker V2 via QWebEngineView + QWebChannel.

Wraps V2MainWindow, ReportSession, and CommandGateway so all canonical backend
validation, undo/redo ledgers, .rmproj persistence, DOCX/PDF exports, customer
database, translations, and vector photo annotations work natively in the HTML UI.
"""
from __future__ import annotations

import base64
from dataclasses import replace
from datetime import date
import json

from PySide6.QtCore import QBuffer, QFile, QIODevice, QMimeData, QObject, QSize, Qt, QUrl, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog, QMainWindow, QSplitter, QVBoxLayout, QWidget,
)

from ..engine import module_outline
from ..media_import import INPUT_SUFFIXES, stage_pictures
from ..model import (
    HeadingBlock, LocalizedText, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, PhotoVisual, TableBlock,
)
from ..photo_editor import render_photo
from ..photo_gallery import local_picture_paths
from ..reference import manual_snapshot
from ..rich_text import RichFormatting
from .app import V2MainWindow
from .branch.photo_tools import V2PictureEditorDialog
from .commands import CommandIntent
from .projections import NodeAddress, find_node
from .theme import DARK
from .web_shell import HTML_SHELL


def _load_qwebchannel_js() -> str:
    qfile = QFile(":/qtwebchannel/qwebchannel.js")
    if qfile.open(QIODevice.OpenModeFlag.ReadOnly):
        try:
            raw = bytes(qfile.readAll()).decode("utf-8", errors="replace")
            return f"<script>{raw}</script>"
        finally:
            qfile.close()
    return ""


def _render_photo_data_url(image_bytes: bytes, visual: PhotoVisual | None = None,
                           max_edge: int = 720) -> str:
    try:
        vis = visual if visual is not None else PhotoVisual()
        img = render_photo(image_bytes, vis, max_edge=max_edge)
        if img.isNull():
            return ""
        buf = QBuffer()
        if not buf.open(QIODevice.OpenModeFlag.WriteOnly):
            return ""
        try:
            if not img.save(buf, "PNG"):
                return ""
            b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
            return f"data:image/png;base64,{b64}"
        finally:
            buf.close()
    except Exception:
        return ""


class BackendBridge(QObject):
    """QWebChannel bridge exposing ReportSession and CommandGateway to HTML/JS."""

    def __init__(self, host_window: "V2WebMainWindow", core_window: V2MainWindow):
        super().__init__(host_window)
        self.host = host_window
        self.core = core_window

    @property
    def session(self):
        return self.core.session

    @property
    def gateway(self):
        return self.core.gateway

    @property
    def report_id(self) -> str:
        return self.session.report_snapshot().id

    def _serialize_module(self, mod, number_map: dict[str, str]) -> dict:
        blocks_out = []
        for blk in mod.blocks:
            if isinstance(blk, ParagraphBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "paragraph",
                    "text": blk.text.original,
                })
            elif isinstance(blk, HeadingBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "heading",
                    "text": blk.text.original,
                    "level": blk.level,
                })
            elif isinstance(blk, PhotoBlock):
                raw_bytes = self.session.assets.get(blk.asset_id, b"")
                blocks_out.append({
                    "id": blk.id,
                    "kind": "photo",
                    "asset_id": blk.asset_id,
                    "asset_name": self.session.media_library.get(blk.asset_id, blk.asset_id),
                    "caption": blk.caption.original if blk.caption else "",
                    "width_pct": blk.visual.width_pct,
                    "marks_count": len(blk.visual.marks),
                    "data_url": _render_photo_data_url(raw_bytes, blk.visual) if raw_bytes else "",
                })
            elif isinstance(blk, TableBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "table",
                    "rows": [[cell.original for cell in row] for row in blk.rows],
                })
            elif isinstance(blk, PageBreakBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "page_break",
                })
            elif isinstance(blk, NestedModuleBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "submodule",
                    "module": self._serialize_module(blk.module, number_map),
                })
        return {
            "id": mod.id,
            "number": number_map.get(mod.id, ""),
            "title": mod.title.original,
            "blocks": blocks_out,
        }

    def _count_tree(self, mods: list[dict]) -> tuple[int, int, int]:
        m_cnt, b_cnt, p_cnt = 0, 0, 0
        for m in mods:
            m_cnt += 1
            for b in m.get("blocks", []):
                if b["kind"] == "submodule" and b.get("module"):
                    sm, sb, sp = self._count_tree([b["module"]])
                    m_cnt += sm
                    b_cnt += sb
                    p_cnt += sp
                else:
                    b_cnt += 1
                    if b["kind"] == "photo":
                        p_cnt += 1
        return m_cnt, b_cnt, p_cnt

    def _response(self, *, toast: str | None = None, error: str | None = None) -> str:
        report = self.session.report_snapshot()
        outline = module_outline(report)
        number_map = {item.module_id: item.number for item in outline}

        modules_serialized = [
            self._serialize_module(m, number_map) for m in report.modules
        ]
        conclusion_serialized = self._serialize_module(report.conclusion, number_map)

        m_cnt, b_cnt, p_cnt = self._count_tree(modules_serialized + [conclusion_serialized])

        snap = report.customer_snapshot
        gallery_list = []
        for asset_id, raw_bytes in self.session.assets.items():
            gallery_list.append({
                "asset_id": asset_id,
                "name": self.session.media_library.get(asset_id, asset_id),
                "data_url": _render_photo_data_url(raw_bytes, None, max_edge=360),
            })

        project_name = (
            self.core.session.path.name
            if self.core.session.path is not None
            else "Untitled project (.rmproj)"
        )

        state = {
            "project_name": project_name,
            "dirty": self.session.dirty,
            "revision": self.session.revision,
            "generation": self.session.generation,
            "can_undo": bool(self.session._media_undo),
            "can_redo": bool(self.session._media_redo),
            "report": {
                "title": report.title.original if report.title else "Report of intervention",
                "customer_name": snap.customer_name if snap else (report.customer_id or "Customer"),
                "site_name": snap.site_name if snap else "",
                "machine_name": snap.machine_name if snap else "",
                "ticket": report.ticket,
                "technicians": ", ".join(report.technicians),
                "start_date": report.start_date.isoformat(),
                "end_date": report.end_date.isoformat(),
                "primary_language": report.primary_language,
                "output_languages": list(report.output_languages),
            },
            "modules": modules_serialized,
            "conclusion": conclusion_serialized,
            "gallery": gallery_list,
            "stats": {
                "modules": m_cnt,
                "blocks": b_cnt,
                "photos": max(p_cnt, len(gallery_list)),
            },
        }
        payload: dict = {"state": state}
        if toast:
            payload["toast"] = toast
        if error:
            payload["error"] = error
        self.host.sync_window_title()
        return json.dumps(payload)

    def _exec(self, kind: str, target: NodeAddress | None, args: dict | None = None,
              toast: str | None = None) -> str:
        try:
            self.gateway.execute(CommandIntent(
                kind,
                target,
                args or {},
                self.session.revision,
                self.session.generation,
            ))
            return self._response(toast=toast)
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def get_state(self) -> str:
        return self._response()

    @Slot(str, result=str)
    def add_module(self, title: str) -> str:
        return self._exec("add_module", None, {"title": title or "Intervention module"},
                          toast="Added module")

    @Slot(str, str, result=str)
    def add_submodule(self, parent_module_id: str, title: str) -> str:
        target = NodeAddress(self.report_id, parent_module_id, None, "title")
        return self._exec("add_nested_module", target,
                          {"title": title or "Submodule"},
                          toast="Added submodule")

    @Slot(str, str, result=str)
    def add_block(self, module_id: str, kind: str) -> str:
        target = NodeAddress(self.report_id, module_id, None, "title")
        if kind == "paragraph":
            return self._exec("add_paragraph", target, {"text": ""}, toast="Added paragraph")
        if kind == "heading":
            return self._exec("add_heading", target, {"text": "Section heading", "level": 2},
                              toast="Added heading")
        if kind == "table":
            return self._exec("add_table", target, {}, toast="Added table")
        if kind == "page_break":
            return self._exec("add_page_break", target, {}, toast="Added page break")
        return self._response(error=f"Unsupported block kind: {kind}")

    @Slot(str, str, result=str)
    def rename_module(self, module_id: str, title: str) -> str:
        if not title or not title.strip():
            return self._response(error="Module title cannot be blank")
        target = NodeAddress(self.report_id, module_id, None, "title")
        return self._exec("rename_module", target, {"title": title.strip()})

    @Slot(str, str, str, result=str)
    def update_paragraph(self, module_id: str, block_id: str, text: str) -> str:
        target = NodeAddress(self.report_id, module_id, block_id, "text")
        return self._exec("set_paragraph_rich", target,
                          {"text": text, "rich": RichFormatting()})

    @Slot(str, str, str, int, result=str)
    def update_heading(self, module_id: str, block_id: str, text: str, level: int) -> str:
        target = NodeAddress(self.report_id, module_id, block_id, "text")
        res = self._exec("set_heading_rich", target,
                         {"text": text, "rich": RichFormatting()})
        try:
            lvl = max(1, min(6, int(level)))
            blk = find_node(self.session._editor.report, target)
            if isinstance(blk, HeadingBlock) and blk.level != lvl:
                blk.level = lvl
                return self._response()
        except Exception:
            pass
        return res

    @Slot(str, str, str, result=str)
    def update_photo_caption(self, module_id: str, block_id: str, caption: str) -> str:
        target = NodeAddress(self.report_id, module_id, block_id, "photo")
        return self._exec("set_photo_caption", target, {"text": caption})

    @Slot(str, str, result=str)
    def edit_photo_annotations(self, module_id: str, block_id: str) -> str:
        try:
            report = self.session.report_snapshot()
            target = NodeAddress(report.id, module_id, block_id, "photo")
            block = find_node(report, target)
            if not isinstance(block, PhotoBlock):
                return self._response(error="Selected block is not a photo")
            image_bytes = self.session.assets[block.asset_id]
            rev, gen = self.session.revision, self.session.generation
            dialog = V2PictureEditorDialog(
                self.host, image_bytes, block.visual,
                report.primary_language,
            )
            if not dialog.exec():
                return self._response()
            self.gateway.execute(CommandIntent(
                "set_photo_visual",
                target,
                {"visual": dialog.visual_result()},
                rev,
                gen,
            ))
            return self._response(toast="Updated photo annotations")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, result=str)
    def import_photo_to_module(self, module_id: str) -> str:
        try:
            rev, gen = self.session.revision, self.session.generation
            patterns = " ".join("*" + s for s in sorted(INPUT_SUFFIXES))
            paths, _ = QFileDialog.getOpenFileNames(
                self.host, "Add pictures to module", "",
                f"Supported images ({patterns})",
            )
            if not paths:
                return self._response()
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
            approved, errors = local_picture_paths(mime)
            if errors or not approved:
                return self._response(error="; ".join(errors) or "Invalid image file")
            staged = stage_pictures(approved)
            photos = tuple((item.name, item.photo.data) for item in staged)
            target = NodeAddress(self.report_id, module_id, None, "title")
            self.gateway.execute(CommandIntent(
                "import_photos",
                target,
                {"photos": photos},
                rev,
                gen,
            ))
            return self._response(toast=f"Imported {len(photos)} photo(s)")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def import_photos_to_gallery(self) -> str:
        try:
            ok = self.core.gallery_tab.import_dialog()
            if not ok:
                return self._response()
            return self._response(toast="Imported photos into media library")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def paste_photo_to_gallery(self) -> str:
        try:
            ok = self.core.gallery_tab.paste_image()
            if not ok:
                return self._response(error=self.core.gallery_tab.hint.text())
            return self._response(toast="Pasted clipboard image into media library")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, str, result=str)
    def insert_gallery_photo(self, module_id: str, asset_id: str) -> str:
        target = NodeAddress(self.report_id, module_id, None, "title")
        return self._exec("add_photo", target, {"asset_id": asset_id},
                          toast="Inserted photo into module")

    @Slot(str, str, str, result=str)
    def update_table(self, module_id: str, block_id: str, rows_json: str) -> str:
        try:
            raw_rows = json.loads(rows_json)
            lang = self.session.report_snapshot().primary_language
            loc_rows = [
                [LocalizedText(lang, str(cell)) for cell in row]
                for row in raw_rows
            ]
            target = NodeAddress(self.report_id, module_id, block_id, "table")
            return self._exec("set_table_rows", target, {"rows": loc_rows})
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, str, str, result=str)
    def mutate_table_shape(self, module_id: str, block_id: str, op: str) -> str:
        try:
            report = self.session.report_snapshot()
            target = NodeAddress(report.id, module_id, block_id, "table")
            block = find_node(report, target)
            if not isinstance(block, TableBlock):
                return self._response(error="Target block is not a table")
            lang = report.primary_language
            rows = [[LocalizedText(lang, cell.original) for cell in row] for row in block.rows]
            cols = len(rows[0]) if rows else 1
            if op == "add_row":
                rows.append([LocalizedText(lang, "") for _ in range(cols)])
            elif op == "add_col":
                rows = [r + [LocalizedText(lang, "")] for r in rows]
            elif op == "del_row":
                if len(rows) <= 1:
                    return self._response(error="A table must keep at least 1 row")
                rows.pop()
            elif op == "del_col":
                if cols <= 1:
                    return self._response(error="A table must keep at least 1 column")
                rows = [r[:-1] for r in rows]
            return self._exec("set_table_rows", target, {"rows": rows})
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, str, str, result=str)
    def move_node(self, module_id: str, block_id: str, direction: str) -> str:
        try:
            report = self.session.report_snapshot()
            if block_id:
                owner = find_node(report, NodeAddress(report.id, module_id))
                idx = next(i for i, b in enumerate(owner.blocks) if b.id == block_id)
                target_idx = idx - 1 if direction == "up" else idx + 1
                if not 0 <= target_idx < len(owner.blocks):
                    return self._response()
                sibling = owner.blocks[target_idx]
                if isinstance(sibling, NestedModuleBlock):
                    source_addr = NodeAddress(report.id, sibling.module.id, None) if sibling.id == block_id else NodeAddress(report.id, module_id, block_id)
                    anchor_addr = NodeAddress(report.id, sibling.module.id, None)
                else:
                    source_addr = NodeAddress(report.id, module_id, block_id)
                    anchor_addr = NodeAddress(report.id, module_id, sibling.id)
                owner_blk = owner.blocks[idx]
                if isinstance(owner_blk, NestedModuleBlock):
                    source_addr = NodeAddress(report.id, owner_blk.module.id, None)
                pos = "before" if direction == "up" else "after"
                return self._exec("move_node", source_addr,
                                  {"anchor": anchor_addr, "position": pos})
            else:
                idx = next(i for i, m in enumerate(report.modules) if m.id == module_id)
                target_idx = idx - 1 if direction == "up" else idx + 1
                if not 0 <= target_idx < len(report.modules):
                    return self._response()
                source_addr = NodeAddress(report.id, module_id, None)
                anchor_addr = NodeAddress(report.id, report.modules[target_idx].id, None)
                pos = "before" if direction == "up" else "after"
                return self._exec("move_node", source_addr,
                                  {"anchor": anchor_addr, "position": pos})
        except Exception as exc:
            return self._response(error=str(exc))

    def _resolve_structural_address(self, report, module_id: str, block_id: str) -> NodeAddress:
        if not block_id:
            return NodeAddress(report.id, module_id, None, "title")
        owner = find_node(report, NodeAddress(report.id, module_id))
        for b in owner.blocks:
            if b.id == block_id and isinstance(b, NestedModuleBlock):
                return NodeAddress(report.id, b.module.id, None, "title")
        return NodeAddress(report.id, module_id, block_id, "text")

    @Slot(str, str, result=str)
    def duplicate_node(self, module_id: str, block_id: str) -> str:
        try:
            report = self.session.report_snapshot()
            addr = self._resolve_structural_address(report, module_id, block_id)
            return self._exec("duplicate_node", addr, {}, toast="Duplicated item")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, str, result=str)
    def delete_node(self, module_id: str, block_id: str) -> str:
        try:
            report = self.session.report_snapshot()
            addr = self._resolve_structural_address(report, module_id, block_id)
            return self._exec("delete_node", addr, {}, toast="Deleted item")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, result=str)
    def update_report_header(self, payload_json: str) -> str:
        try:
            data = json.loads(payload_json)
            rep = self.session.report_snapshot()
            snap = rep.customer_snapshot

            customer_name = str(data.get("customer_name", "")).strip() or "Customer"
            site_name = str(data.get("site_name", "")).strip()
            machine_name = str(data.get("machine_name", "")).strip()

            if snap is not None and snap.customer_id:
                new_snap = replace(
                    snap,
                    customer_name=customer_name,
                    site_name=site_name,
                    machine_name=machine_name,
                )
                customer_id = rep.customer_id
            else:
                new_snap = manual_snapshot(
                    customer_name,
                    site_name=site_name,
                    machine_name=machine_name,
                )
                customer_id = None

            tech_raw = str(data.get("technicians", ""))
            techs = [t.strip() for t in tech_raw.split(",") if t.strip()]

            start_d = date.fromisoformat(str(data.get("start_date", rep.start_date.isoformat())).strip())
            end_d = date.fromisoformat(str(data.get("end_date", rep.end_date.isoformat())).strip())

            cmd_payload = {
                "customer_id": customer_id,
                "customer_snapshot": new_snap,
                "created_date": rep.created_date,
                "start_date": start_d,
                "end_date": end_d,
                "primary_language": rep.primary_language,
                "output_languages": list(rep.output_languages),
                "title": str(data.get("title", "")).strip() or "Report of intervention",
                "ticket": str(data.get("ticket", "")).strip(),
                "technicians": techs,
                "intervention_types": list(rep.intervention_types),
                "other_intervention_detail": rep.other_intervention_detail,
            }
            return self._exec("set_report_metadata", None, cmd_payload,
                              toast="Updated report metadata")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def undo(self) -> str:
        try:
            self.gateway.undo(self.session.generation, self.session.revision)
            return self._response(toast="Undid last change")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def redo(self) -> str:
        try:
            self.gateway.redo(self.session.generation, self.session.revision)
            return self._response(toast="Redid change")
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(result=str)
    def new_project(self) -> str:
        if self.core.new_project():
            return self._response(toast="Created new report project")
        return self._response()

    @Slot(result=str)
    def open_project(self) -> str:
        if self.core.open_project():
            return self._response(toast="Opened project bundle")
        return self._response()

    @Slot(result=str)
    def save_project(self) -> str:
        if self.core.save_project():
            return self._response(toast="Saved project (.rmproj)")
        return self._response()

    @Slot(result=str)
    def save_project_as(self) -> str:
        if self.core.save_project_as():
            return self._response(toast="Saved project copy (.rmproj)")
        return self._response()

    @Slot(str, result=str)
    def export_document(self, fmt: str) -> str:
        ok = self.core.preview_tab.export_dialog(fmt)
        if ok:
            return self._response(toast=f"Exported {fmt.upper()} document")
        return self._response(error=self.core.preview_tab.notice.text())

    @Slot(result=str)
    def export_bundle(self) -> str:
        ok = self.core.preview_tab.export_bundle_dialog()
        if ok:
            return self._response(toast="Exported multi-language ZIP package")
        return self._response(error=self.core.preview_tab.notice.text())

    @Slot(result=str)
    def generate_pdf_proof(self) -> str:
        try:
            ok = self.core.preview_tab.show_pdf_proof()
            if not ok:
                return json.dumps({"error": self.core.preview_tab.notice.text()})
            doc = self.core.preview_tab.proof.document
            count = self.core.preview_tab.proof.page_count
            pages_out = []
            for idx in range(count):
                dims = doc.pagePointSize(idx)
                scale = min(1150 / max(1.0, dims.width()), 1500 / max(1.0, dims.height()))
                sz = QSize(max(1, round(dims.width() * scale)),
                           max(1, round(dims.height() * scale)))
                image = doc.render(idx, sz)
                buf = QBuffer()
                if buf.open(QIODevice.OpenModeFlag.WriteOnly):
                    image.save(buf, "PNG")
                    b64 = base64.b64encode(bytes(buf.data())).decode("ascii")
                    pages_out.append(f"data:image/png;base64,{b64}")
                    buf.close()
            return json.dumps({"pages": pages_out})
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    @Slot(result=str)
    def open_report_info_dialog(self) -> str:
        if self.core.edit_report_info():
            return self._response(toast="Updated report information")
        return self._response()

    @Slot(result=str)
    def open_customer_manager(self) -> str:
        if self.core.open_customer_manager():
            return self._response(toast="Customer database closed")
        return self._response()

    @Slot(result=str)
    def open_translations_dialog(self) -> str:
        if self.core.edit_translations():
            return self._response(toast="Updated translations")
        return self._response()

    @Slot(result=str)
    def import_word_template(self) -> str:
        if self.core.import_layout_template():
            return self._response(toast="Imported Word page template")
        return self._response()

    @Slot(result=str)
    def toggle_ai_drawer(self) -> str:
        visible = self.host.toggle_ai_drawer()
        return self._response(
            toast="Opened AI Assistant drawer" if visible else "Closed AI Assistant drawer"
        )


class V2WebMainWindow(QMainWindow):
    """HTML5-powered Desktop Main Window for ReportMaker V2."""

    def __init__(self, *, load_website: bool = True, ephemeral_browser: bool = False) -> None:
        super().__init__()
        self.setObjectName("v2WebMainWindow")
        self.resize(1440, 900)

        # Underlying V2MainWindow owns canonical session, persistence, and native dialogs.
        self.core = V2MainWindow(
            load_website=load_website,
            ephemeral_browser=ephemeral_browser,
            theme=DARK,
        )
        self.core.hide()

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.setCentralWidget(self.splitter)

        self.webview = QWebEngineView(self.splitter)
        self.webview.setObjectName("v2HtmlWorkspaceView")

        # Reparent the isolated ChatGPT assistant panel into a toggleable right drawer
        self.ai_drawer = QWidget(self.splitter)
        self.ai_drawer.setObjectName("v2AiDrawer")
        drawer_layout = QVBoxLayout(self.ai_drawer)
        drawer_layout.setContentsMargins(6, 6, 6, 6)
        drawer_layout.addWidget(self.core.chat_tab)
        self.ai_drawer.hide()

        self.splitter.addWidget(self.webview)
        self.splitter.addWidget(self.ai_drawer)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 1)

        self.channel = QWebChannel(self.webview.page())
        self.bridge = BackendBridge(self, self.core)
        self.channel.registerObject("backend", self.bridge)
        self.webview.page().setWebChannel(self.channel)

        html_doc = HTML_SHELL.replace(
            "<!-- QWEBCHANNEL_SCRIPT_PLACEHOLDER -->",
            _load_qwebchannel_js(),
        )
        self.webview.setHtml(html_doc)
        self.sync_window_title()

    def toggle_ai_drawer(self) -> bool:
        now_visible = not self.ai_drawer.isVisible()
        self.ai_drawer.setVisible(now_visible)
        if now_visible:
            self.splitter.setSizes([980, 440])
        return now_visible

    def sync_window_title(self) -> None:
        self.core._update_caption()
        self.setWindowTitle(self.core.windowTitle())

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.core._confirm_transition() is None:
            event.ignore()
            return
        self.core._persist_previous_view(self.core._view())
        event.accept()
