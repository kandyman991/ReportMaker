"""HTML5/CSS/JS Desktop Shell for ReportMaker V2 via QWebEngineView + QWebChannel.

Wraps V2MainWindow, ReportSession, and CommandGateway so all canonical backend
validation, undo/redo ledgers, .rmproj persistence, DOCX/PDF exports, customer
database, translations, and vector photo annotations work natively in the HTML UI.
"""
from __future__ import annotations

import base64
import json

from PySide6.QtCore import QBuffer, QFile, QIODevice, QMimeData, QObject, QSize, Qt, QUrl, Slot
from PySide6.QtGui import QCloseEvent
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import (
    QFileDialog, QMainWindow, QMessageBox, QSplitter, QVBoxLayout, QWidget,
)

from ..engine import module_outline
from ..media_import import INPUT_SUFFIXES, stage_pictures
from ..model import (
    HeadingBlock, LocalizedText, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, PhotoVisual, TableBlock,
)
from ..photo_gallery import local_picture_paths
from ..rich_text import format_to_dict
from .app import V2MainWindow
from .branch.photo_tools import V2PictureEditorDialog
from .commands import CommandIntent
from .projections import NodeAddress, find_node
from .theme import DARK
from .web_shell import HTML_SHELL
from .web_edits import EDIT_METHODS, field_intent, rich_format_intent, table_shape_intent
from .web_origin import ENTRY, install_studio


def _load_qwebchannel_js() -> str:
    qfile = QFile(":/qtwebchannel/qwebchannel.js")
    if qfile.open(QIODevice.OpenModeFlag.ReadOnly):
        try:
            raw = bytes(qfile.readAll()).decode("utf-8", errors="replace")
            return raw
        finally:
            qfile.close()
    raise RuntimeError("QtWebChannel runtime is missing")


class BackendBridge(QObject):
    """QWebChannel bridge exposing ReportSession and CommandGateway to HTML/JS."""

    def __init__(self, host_window: "V2WebMainWindow", core_window: V2MainWindow):
        super().__init__(host_window)
        self.host = host_window
        self.core = core_window
        self._projection_token = None
        self._projection = None
        self._sent_state = None

    @property
    def session(self):
        return self.core.session

    @property
    def gateway(self):
        return self.core.gateway

    @property
    def report_id(self) -> str:
        return self.session.report_snapshot().id

    def _edit(self, method, args):
        try:
            self.gateway.execute(field_intent(self.session, method, args,
                                             self.session.revision, self.session.generation))
            return self._response()
        except Exception as exc:
            return self._response(error=str(exc))

    @Slot(str, result=str)
    def dispatch(self, request: str) -> str:
        """The only privileged entry point: trusted page + versioned, bounded envelope."""
        try:
            if self.host.webview.url().toString() != ENTRY:
                raise ValueError("Unauthorized studio origin")
            if not isinstance(request, str) or len(request) > 2_000_000:
                raise ValueError("Request exceeds the studio limit")
            data = json.loads(request)
            if not isinstance(data, dict) or set(data) != {"method", "args", "revision", "generation"}:
                raise ValueError("Invalid request envelope")
            method, args = data["method"], data["args"]
            if not isinstance(method, str) or not isinstance(args, list):
                raise ValueError("Invalid method arguments")
            if method == "get_state" and not args:
                return self.get_state()
            if (type(data["revision"]) is not int or data["revision"] != self.session.revision
                    or data["generation"] != self.session.generation):
                raise ValueError("The report changed since editing began; draft preserved. Reopen the current view after resolving edits.")
            if method == "apply_drafts":
                drafts, = args
                if not isinstance(drafts, list) or not 1 <= len(drafts) <= 256:
                    raise ValueError("Apply requires 1–256 field drafts")
                intents = []
                for draft in drafts:
                    if not isinstance(draft, dict) or set(draft) != {"method", "args"}:
                        raise ValueError("Invalid draft")
                    intents.append(field_intent(self.session, draft["method"], draft["args"],
                                                data["revision"], data["generation"]))
                self.gateway.execute(CommandIntent("set_fields_batch", None, {"edits": intents},
                                                   data["revision"], data["generation"]))
                return self._response()
            if method == "close_window" and not args:
                self.host.finish_close()
                return json.dumps({"closed": self.host._close_approved})
            allowed = EDIT_METHODS | {
                "add_module", "add_submodule", "add_block", "edit_photo_annotations",
                "import_photo_to_module", "import_photos_to_gallery", "paste_photo_to_gallery",
                "insert_gallery_photo", "mutate_table_shape", "move_node", "duplicate_node",
                "delete_node", "undo", "redo", "new_project", "open_project", "save_project",
                "save_project_as", "export_document", "export_bundle", "generate_pdf_proof",
                "open_report_info_dialog", "open_customer_manager", "open_translations_dialog",
                "import_word_template", "toggle_ai_drawer", "format_rich_block"}
            if method not in allowed:
                raise ValueError("Unsupported studio action")
            if method == "export_document" and args not in (["docx"], ["pdf"]):
                raise ValueError("Unsupported export format")
            if method == "move_node" and (len(args) != 3 or args[-1] not in ("up", "down")):
                raise ValueError("Unsupported move direction")
            return getattr(self, method)(*args)
        except Exception as exc:
            return json.dumps({"error": str(exc)})

    def _serialize_module(self, mod, number_map: dict[str, str]) -> dict:
        blocks_out = []
        for blk in mod.blocks:
            if isinstance(blk, ParagraphBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "paragraph",
                    "text": blk.text.original,
                    "rich": format_to_dict(blk.rich, blk.text.original),
                })
            elif isinstance(blk, HeadingBlock):
                blocks_out.append({
                    "id": blk.id,
                    "kind": "heading",
                    "text": blk.text.original,
                    "level": blk.level,
                    "rich": format_to_dict(blk.rich, blk.text.original),
                })
            elif isinstance(blk, PhotoBlock):
                raw_bytes = self._assets.get(blk.asset_id, b"")
                blocks_out.append({
                    "id": blk.id,
                    "kind": "photo",
                    "asset_id": blk.asset_id,
                    "asset_name": self._library.get(blk.asset_id, blk.asset_id),
                    "caption": blk.caption.original if blk.caption else "",
                    "width_pct": blk.visual.width_pct,
                    "marks_count": len(blk.visual.marks),
                    "data_url": self.host.resources.image_url(raw_bytes, blk.visual, 720) if raw_bytes else "",
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
        if error:
            return json.dumps({"error": error})
        token = (self.session.generation, self.session.revision)
        if token != self._projection_token:
            if self._projection_token is None or token[0] != self._projection_token[0]:
                self.host.resources.clear_media()
            report = self.session.report_snapshot()
            self._assets, self._library = self.session.assets, self.session.media_library
            self.host.resources.begin_projection()
            outline = module_outline(report)
            number_map = {item.module_id: item.number for item in outline}

            modules_serialized = [
                self._serialize_module(m, number_map) for m in report.modules
            ]
            conclusion_serialized = self._serialize_module(report.conclusion, number_map)

            m_cnt, b_cnt, p_cnt = self._count_tree(modules_serialized + [conclusion_serialized])

            snap = report.customer_snapshot
            gallery_list = []
            for asset_id, raw_bytes in self._assets.items():
                gallery_list.append({
                    "asset_id": asset_id,
                    "name": self._library.get(asset_id, asset_id),
                    "data_url": self.host.resources.image_url(raw_bytes, PhotoVisual(), 360),
                })


            state = {
                "project_name": "",
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
            self._projection = state
            self._projection_token = token
            self.host.resources.end_projection()
        state = dict(self._projection)
        state["project_name"] = self.session.path.name if self.session.path else "Untitled project (.rmproj)"
        state["dirty"] = self.session.dirty
        payload: dict = {"state": state}
        previous = self._sent_state
        if previous and previous["generation"] == state["generation"]:
            old = {m["id"]: m for m in previous["modules"]}
            delta = {k: v for k, v in state.items() if k != "modules" and previous.get(k) != v}
            delta["modules_changed"] = [m for m in state["modules"] if old.get(m["id"]) != m]
            delta["module_order"] = [m["id"] for m in state["modules"]]
            payload = {"patch": delta}
        self._sent_state = state
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

    def get_state(self) -> str:
        self._sent_state = None
        return self._response()

    def add_module(self, title: str) -> str:
        return self._exec("add_module", None, {"title": title or "Intervention module"},
                          toast="Added module")

    def add_submodule(self, parent_module_id: str, title: str) -> str:
        target = NodeAddress(self.report_id, parent_module_id, None, "title")
        return self._exec("add_nested_module", target,
                          {"title": title or "Submodule"},
                          toast="Added submodule")

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

    def rename_module(self, module_id: str, title: str) -> str:
        return self._edit("rename_module", [module_id, title])

    def update_paragraph(self, module_id: str, block_id: str, text: str) -> str:
        return self._edit("update_paragraph", [module_id, block_id, text])

    def update_heading(self, module_id: str, block_id: str, text: str, level: int) -> str:
        return self._edit("update_heading", [module_id, block_id, text, level])

    def format_rich_block(self, module_id: str, block_id: str, op_json: str) -> str:
        try:
            self.gateway.execute(rich_format_intent(
                self.session, module_id, block_id, op_json,
                self.session.revision, self.session.generation,
            ))
            return self._response()
        except Exception as exc:
            return self._response(error=str(exc))

    def update_photo_caption(self, module_id: str, block_id: str, caption: str) -> str:
        return self._edit("update_photo_caption", [module_id, block_id, caption])

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

    def import_photos_to_gallery(self) -> str:
        try:
            ok = self.core.gallery_tab.import_dialog()
            if not ok:
                return self._response()
            return self._response(toast="Imported photos into media library")
        except Exception as exc:
            return self._response(error=str(exc))

    def paste_photo_to_gallery(self) -> str:
        try:
            ok = self.core.gallery_tab.paste_image()
            if not ok:
                return self._response(error=self.core.gallery_tab.hint.text())
            return self._response(toast="Pasted clipboard image into media library")
        except Exception as exc:
            return self._response(error=str(exc))

    def insert_gallery_photo(self, module_id: str, asset_id: str) -> str:
        target = NodeAddress(self.report_id, module_id, None, "title")
        return self._exec("add_photo", target, {"asset_id": asset_id},
                          toast="Inserted photo into module")

    def update_table(self, module_id: str, block_id: str, rows_json: str) -> str:
        return self._edit("update_table", [module_id, block_id, rows_json])

    def mutate_table_shape(self, module_id: str, block_id: str, op: str) -> str:
        try:
            self.gateway.execute(table_shape_intent(self.session, module_id, block_id, op))
            return self._response()
        except Exception as exc:
            return self._response(error=str(exc))

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

    def duplicate_node(self, module_id: str, block_id: str) -> str:
        try:
            report = self.session.report_snapshot()
            addr = self._resolve_structural_address(report, module_id, block_id)
            return self._exec("duplicate_node", addr, {}, toast="Duplicated item")
        except Exception as exc:
            return self._response(error=str(exc))

    def delete_node(self, module_id: str, block_id: str) -> str:
        try:
            report = self.session.report_snapshot()
            addr = self._resolve_structural_address(report, module_id, block_id)
            return self._exec("delete_node", addr, {}, toast="Deleted item")
        except Exception as exc:
            return self._response(error=str(exc))

    def update_report_header(self, payload_json: str) -> str:
        return self._edit("update_report_header", [payload_json])

    def undo(self) -> str:
        try:
            self.gateway.undo(self.session.generation, self.session.revision)
            return self._response(toast="Undid last change")
        except Exception as exc:
            return self._response(error=str(exc))

    def redo(self) -> str:
        try:
            self.gateway.redo(self.session.generation, self.session.revision)
            return self._response(toast="Redid change")
        except Exception as exc:
            return self._response(error=str(exc))

    def new_project(self) -> str:
        if self.core.new_project():
            return self._response(toast="Created new report project")
        return self._response()

    def open_project(self) -> str:
        if self.core.open_project():
            return self._response(toast="Opened project bundle")
        return self._response()

    def save_project(self) -> str:
        if self.core.save_project():
            return self._response(toast="Saved project (.rmproj)")
        return self._response()

    def save_project_as(self) -> str:
        if self.core.save_project_as():
            return self._response(toast="Saved project copy (.rmproj)")
        return self._response()

    def export_document(self, fmt: str) -> str:
        ok = self.core.preview_tab.export_dialog(fmt)
        if ok:
            return self._response(toast=f"Exported {fmt.upper()} document")
        return self._response(error=self.core.preview_tab.notice.text())

    def export_bundle(self) -> str:
        ok = self.core.preview_tab.export_bundle_dialog()
        if ok:
            return self._response(toast="Exported multi-language ZIP package")
        return self._response(error=self.core.preview_tab.notice.text())

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

    def open_report_info_dialog(self) -> str:
        if self.core.edit_report_info():
            return self._response(toast="Updated report information")
        return self._response()

    def open_customer_manager(self) -> str:
        if self.core.open_customer_manager():
            return self._response(toast="Customer database closed")
        return self._response()

    def open_translations_dialog(self) -> str:
        if self.core.edit_translations():
            return self._response(toast="Updated translations")
        return self._response()

    def import_word_template(self) -> str:
        if self.core.import_layout_template():
            return self._response(toast="Imported Word page template")
        return self._response()

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
        self._close_approved = False
        self._close_requested = False
        self._renderer_ready = False

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
        self.resources = install_studio(self.webview, HTML_SHELL)
        self.webview.loadFinished.connect(self._renderer_loaded)
        self.webview.page().renderProcessTerminated.connect(lambda *_: self._renderer_loaded(False))

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

        self.webview.setUrl(QUrl(ENTRY))
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

    def finish_close(self):
        self._close_requested = False
        if self.core._confirm_transition() is None:
            return
        self.core._persist_previous_view(self.core._view())
        self._close_approved = True
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self.close)

    def _renderer_loaded(self, ok):
        self._renderer_ready = False
        if ok:
            self.webview.page().runJavaScript(
                "typeof requestStudioClose === 'function'",
                lambda ready: setattr(self, "_renderer_ready", bool(ready)))

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._close_approved:
            event.accept()
            self.core.deleteLater()
            return
        event.ignore()
        if not self._renderer_ready:
            answer = QMessageBox.warning(
                self, "HTML editor unavailable",
                "The HTML editor is unavailable. Unapplied HTML input cannot be recovered. "
                "Continue closing? Applied report changes can still be saved in the next dialog.",
                QMessageBox.StandardButton.Close | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if answer == QMessageBox.StandardButton.Close:
                self.finish_close()
            return
        # The renderer acknowledges an atomic draft apply (or explicit discard)
        # before the ordinary native unsaved-project confirmation can run.
        self.webview.page().runJavaScript("requestStudioClose()")
