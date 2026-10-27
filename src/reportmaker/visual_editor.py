"""M3 visual report editor: a desktop view over the M2 canonical project.

No browser bridge, network calls, DOCX export, or separate outline data model.
All mutations are transactional ProjectEditor commands; .rmproj is the source.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import fields
from datetime import date
from html import escape
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QDate, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QImage, QKeySequence, QPainter, QPen, QPixmap, QTextDocument
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDateEdit, QDialog,
    QDialogButtonBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSplitter, QTabWidget, QTableWidget,
    QTableWidgetItem, QTextBrowser, QTreeWidget, QTreeWidgetItem, QVBoxLayout,
    QWidget,
)

from .engine import ProjectEditor, module_outline
from .model import (
    HeadingBlock, LocalizedText, Module, NestedModuleBlock, PageBreakBlock,
    ParagraphBlock, PhotoBlock, PhotoVisual, Report, TableBlock,
)
from .project_io import (LEGACY_VERSION, PREVIOUS_VERSION, VERSION, MAX_ASSET, ReportProject,
                         default_projects_directory, load_project, save_project)
from .export import ExportError, ExportStyle, MAX_BRAND_LOGO_BYTES, export_project
from .media_import import (PictureImportError, stage_pictures, commit_staged_pictures,
                           remove_library_picture)
from .reference import CustomerSnapshot, manual_snapshot
from .photo_editor import PictureEditorDialog, render_photo
from .photo_gallery import PHOTO_MIME, ProjectPictureList, scaled_project_image
from .rich_editor import SafeRichTextEdit, RichTextRibbon, apply_rich, capture_rich
from .rich_text import safe_html
from .page_editor import EditableDocumentPage
from .template_import import (
    DocumentTemplate, TemplateError, import_word_template, load_template, save_template,
)
from .template_dialog import edit_template_layout


def new_report() -> ReportProject:
    today = date.today()
    language = "en"  # Initial preference only; any valid language tag can be entered.
    report = Report(
        customer_id=None, customer_snapshot=manual_snapshot("Customer (edit me)"),
        created_date=today, start_date=today, end_date=today,
        primary_language=language, output_languages=[language],
        title=LocalizedText(language, "Report of intervention"),
        modules=[Module(LocalizedText(language, "Intervention"),
                        [ParagraphBlock(LocalizedText(language, ""))])],
        conclusion=Module(LocalizedText(language, "Conclusions")),
    )
    return ReportProject(report)


def find_module(report: Report, module_id: str) -> Module:
    stack = list(report.ordered_sections())
    while stack:
        module = stack.pop()
        if module.id == module_id:
            return module
        stack.extend(b.module for b in module.blocks if isinstance(b, NestedModuleBlock))
    raise LookupError("Module not found")


def module_insert_index(report: Report, target_id: str, after: bool) -> tuple[str | None, int]:
    """Resolve tree drop to the *mixed block* index, not a child-only index."""
    if target_id == report.conclusion.id:
        return None, len(report.modules)
    for index, module in enumerate(report.modules):
        if module.id == target_id:
            return None, index + int(after)
    stack = list(report.modules)
    while stack:
        module = stack.pop()
        for index, block in enumerate(module.blocks):
            if isinstance(block, NestedModuleBlock):
                if block.module.id == target_id:
                    return module.id, index + int(after)
                stack.append(block.module)
    raise LookupError("Drop target not found")


def revised_manual_snapshot(
    previous: CustomerSnapshot, customer: str, site: str, machine: str,
) -> CustomerSnapshot:
    """Never associate hidden customer/site/machine details with a new identity.

    The form edits visible names only. Keep supplementary snapshot fields when
    their parent identity is unchanged; reset dependent details on a rename.
    """
    customer, site, machine = customer.strip(), site.strip(), machine.strip()
    if customer != previous.customer_name:
        keep_prefixes = ()
    elif site != previous.site_name:
        keep_prefixes = ("customer_",)
    elif machine != previous.machine_name:
        keep_prefixes = ("customer_", "site_")
    else:
        keep_prefixes = ("customer_", "site_", "machine_")
    details = {
        part.name: getattr(previous, part.name)
        for part in fields(previous)
        if part.name not in ("customer_name", "customer_id", "site_name", "site_id",
                            "machine_name", "machine_id", "captured_at", "schema_version")
        and part.name.startswith(keep_prefixes)
    }
    return manual_snapshot(
        customer, site_name=site, machine_name=machine, **details,
    )


class ModuleTree(QTreeWidget):
    moveRequested = Signal(str, object, object)

    def __init__(self):
        super().__init__()
        self.setHeaderHidden(True)
        self.setObjectName("moduleTree")
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    def dropEvent(self, event):
        source = self.currentItem()
        if source is None or not source.data(0, Qt.ItemDataRole.UserRole):
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        position = self.dropIndicatorPosition()
        source_id = source.data(0, Qt.ItemDataRole.UserRole)
        if target is None or position == QAbstractItemView.DropIndicatorPosition.OnViewport:
            self.moveRequested.emit(source_id, None, None)
        elif position == QAbstractItemView.DropIndicatorPosition.OnItem:
            self.moveRequested.emit(source_id,
                                    target.data(0, Qt.ItemDataRole.UserRole), None)
        else:
            self.moveRequested.emit(
                source_id, target.data(0, Qt.ItemDataRole.UserRole),
                position == QAbstractItemView.DropIndicatorPosition.BelowItem,
            )
        # Rebuild from the validated model instead of accepting Qt's local reorder.
        event.acceptProposedAction()


class BlockList(QListWidget):
    moveRequested = Signal(str, int)

    def __init__(self):
        super().__init__()
        self.setObjectName("contentBlocks")
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.photo_drop_resolver = lambda source, mime: None
        self.on_picture_drop = None
        self._photo_drop_index = None

    def _index_at(self, position):
        target = self.itemAt(position)
        if target is None:
            return self.count()
        index = self.row(target)
        if position.y() >= self.visualItemRect(target).center().y():
            index += 1
        return index

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PHOTO_MIME):
            if self.photo_drop_resolver(event.source(), event.mimeData()) is None:
                event.ignore()
                return
            self._photo_drop_index = None
            event.acceptProposedAction()
        elif event.source() is self:
            super().dragEnterEvent(event)
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PHOTO_MIME):
            if self.photo_drop_resolver(event.source(), event.mimeData()) is None:
                self._photo_drop_index = None
                self.viewport().update()
                event.ignore()
                return
            self._photo_drop_index = self._index_at(event.position().toPoint())
            self.viewport().update()
            event.acceptProposedAction()
        elif event.source() is self:
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self._photo_drop_index = None
        self.viewport().update()
        super().dragLeaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._photo_drop_index is None:
            return
        index = self._photo_drop_index
        if index < self.count():
            y = self.visualItemRect(self.item(index)).top()
        elif self.count():
            y = self.visualItemRect(self.item(self.count() - 1)).bottom()
        else:
            y = 3
        painter = QPainter(self.viewport())
        painter.setPen(QPen(QColor("#1474c9"), 3))
        painter.drawLine(3, y, self.viewport().width() - 3, y)
        painter.end()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(PHOTO_MIME):
            key = self.photo_drop_resolver(event.source(), event.mimeData())
            self._photo_drop_index = None
            self.viewport().update()
            if key is None or self.on_picture_drop is None:
                event.ignore()
                return
            index = self._index_at(event.position().toPoint())
            event.acceptProposedAction()
            # Refresh replaces the target list; defer until Qt finishes dropping.
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.on_picture_drop(None, index, key))
            return
        if event.source() is not self:
            event.ignore()
            return
        source = self.currentItem()
        if source is None:
            event.ignore()
            return
        target = self.itemAt(event.position().toPoint())
        pos = self.dropIndicatorPosition()
        index = self.count() if target is None else self.row(target)
        if pos == QAbstractItemView.DropIndicatorPosition.BelowItem:
            index += 1
        self.moveRequested.emit(source.data(Qt.ItemDataRole.UserRole), index)
        event.acceptProposedAction()


class VisualReportEditor:
    """Controller owns the two native editor panes and a single M2 ProjectEditor."""

    def __init__(self, owner, left: QVBoxLayout, center: QVBoxLayout):
        self.owner = owner
        self.path: Path | None = None
        self.assets: dict[str, bytes] = {}
        self.media_library: dict[str, str] = {}
        self.loaded_version = VERSION
        self.loaded_from: Path | None = None
        self.editor = ProjectEditor(new_report().report)
        self.dirty = False
        self._loading = False
        self._block_pending = False
        self._info_pending = False
        self._edit_block_id: str | None = None
        self._module_id: str | None = None
        self._picture_gallery = None
        self._picture_list = None
        self._gallery_populate = None
        self._photo_drag_token = uuid4().hex
        self._build(left, center)
        self.refresh()

    @property
    def report(self):
        return self.editor.report

    def _build(self, left, center):
        self.tree = ModuleTree()
        self.tree.currentItemChanged.connect(self._module_selected)
        self.tree.moveRequested.connect(self._tree_move)
        left.addWidget(self.tree, 5)
        buttons = QHBoxLayout()
        for label, handler in (("Add", self.add_module), ("Submodule", self.add_child),
                               ("Rename", self.rename_module), ("Duplicate", self.duplicate_module),
                               ("Delete", self.delete_module)):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            buttons.addWidget(btn)
        left.addLayout(buttons)
        left.addWidget(QLabel("SUMMARY — generated from the same module hierarchy"))
        self.summary = QTextBrowser()
        self.summary.setObjectName("derivedSummary")
        self.summary.setOpenExternalLinks(False)
        left.addWidget(self.summary, 3)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("reportEditorTabs")
        center.addWidget(self.tabs, 1)

        body = QWidget()
        body_layout = QVBoxLayout(body)
        vertical = QSplitter(Qt.Orientation.Vertical)
        body_layout.addWidget(vertical, 1)
        top = QWidget()
        top_layout = QVBoxLayout(top)
        self.active_label = QLabel()
        top_layout.addWidget(self.active_label)
        content_buttons = QHBoxLayout()
        for label, handler in (("+ Text", self.add_paragraph), ("+ Heading", self.add_heading),
                               ("+ Photo", self.add_photo), ("+ Table", self.add_table),
                               ("+ Page break", self.add_page_break), ("Move block", self.move_block_dialog), ("Remove block", self.remove_block)):
            btn = QPushButton(label)
            btn.clicked.connect(handler)
            content_buttons.addWidget(btn)
        top_layout.addLayout(content_buttons)
        self.blocks = BlockList()
        self.blocks.photo_drop_resolver = self._resolve_project_photo_drag
        self.blocks.on_picture_drop = self._insert_project_photo
        self.blocks.currentItemChanged.connect(self._block_selected)
        self.blocks.moveRequested.connect(self._block_move)
        top_layout.addWidget(self.blocks, 2)
        self.block_hint = QLabel("Select a content block to edit; use drag and drop to reorder.")
        top_layout.addWidget(self.block_hint)
        self.text_edit = SafeRichTextEdit()
        self.text_edit.setObjectName("blockTextEditor")
        self.text_edit.setAcceptRichText(False)
        self.text_edit.setAcceptDrops(False)  # gallery drops are structural, not rich-text edits
        self.text_edit.textChanged.connect(self._set_pending)
        self.rich_ribbon = RichTextRibbon(self.text_edit)
        self.rich_ribbon.setObjectName("reportFontParagraphRibbon")
        for button in self.rich_ribbon.findChildren(QPushButton):
            if button.objectName() != "richShowMarks":
                button.clicked.connect(self._set_pending)
        top_layout.addWidget(self.rich_ribbon)
        top_layout.addWidget(self.text_edit, 1)
        self.photo_caption = QLineEdit()
        self.photo_caption.setAcceptDrops(False)
        self.photo_caption.setPlaceholderText("Photo caption")
        self.photo_caption.textEdited.connect(self._set_pending)
        top_layout.addWidget(self.photo_caption)
        self.picture_edit = QPushButton("Edit selected picture (crop, rotate, annotations…)")
        self.picture_edit.setObjectName("editPictureVisualAction")
        self.picture_edit.clicked.connect(self.edit_picture)
        top_layout.addWidget(self.picture_edit)
        self.table = QTableWidget()
        self.table.setAcceptDrops(False)
        self.table.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.table.cellChanged.connect(self._set_pending)
        top_layout.addWidget(self.table, 1)
        table_controls = QHBoxLayout()
        for label, func in (("+ Row", self._add_row), ("- Row", self._remove_row),
                            ("+ Column", self._add_column), ("- Column", self._remove_column)):
            button = QPushButton(label)
            button.clicked.connect(func)
            table_controls.addWidget(button)
        self.table_buttons = QWidget()
        self.table_buttons.setLayout(table_controls)
        top_layout.addWidget(self.table_buttons)
        apply = QPushButton("Apply block changes")
        apply.setObjectName("applyBlockAction")
        apply.clicked.connect(self.apply_block)
        top_layout.addWidget(apply)
        vertical.addWidget(top)

        preview_box = QWidget()
        preview_layout = QVBoxLayout(preview_box)
        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("EDITABLE DOCUMENT PAGE — source blocks on paper; printed pagination may differ"))
        preview_header.addStretch(1)
        zoom_out = QPushButton("A−")
        zoom_out.setObjectName("previewZoomOut")
        zoom_in = QPushButton("A+")
        zoom_in.setObjectName("previewZoomIn")
        preview_header.addWidget(zoom_out)
        preview_header.addWidget(zoom_in)
        preview_layout.addLayout(preview_header)
        self.page_tabs = QTabWidget()
        self.page_tabs.setObjectName("documentPageTabs")
        self.page = EditableDocumentPage()
        self.page.on_style_request = self._select_page_block
        self.page.photo_drop_resolver = self._resolve_project_photo_drag
        self.page.on_picture_drop = self._insert_project_photo
        page_container = QWidget()
        page_layout = QVBoxLayout(page_container)
        page_controls = QHBoxLayout()
        page_controls.addWidget(QLabel(
            "Edit text, headings, table cells and photo captions on the page. "
            "Module titles and Summary are protected."))
        page_controls.addStretch()
        apply_page = QPushButton("Apply page edits")
        apply_page.setObjectName("applyPageEdits")
        apply_page.clicked.connect(self.commit_page)
        page_controls.addWidget(apply_page)
        page_layout.addLayout(page_controls)
        page_layout.addWidget(self.page, 1)
        self.page_tabs.addTab(page_container, "Editable page")
        self.preview = QTextBrowser()
        self.preview.setObjectName("documentPreview")
        self.preview.setOpenExternalLinks(False)
        # QTextBrowser inherits the app dark palette; HTML had dark text but no
        # background, making the entire report illegible on dark-mode Windows.
        # Make the preview a white paper surface independent of the theme.
        self.preview.setStyleSheet(
            "QTextBrowser#documentPreview { background-color: #ffffff; "
            "color: #202124; border: 1px solid #a9afb7; "
            "selection-background-color: #c2dcff; selection-color: #101820; }")
        self.preview.setMinimumHeight(175)
        zoom_out.clicked.connect(lambda: self.preview.zoomOut(1))
        zoom_in.clicked.connect(lambda: self.preview.zoomIn(1))
        self.page_tabs.addTab(self.preview, "Print preview (read-only)")
        self.page_tabs.currentChanged.connect(self._page_tab_changed)
        preview_layout.addWidget(self.page_tabs, 1)
        vertical.addWidget(preview_box)
        vertical.setSizes([420, 420])
        self.tabs.addTab(body, "Content & Preview")

        info_outer = QScrollArea()
        info_outer.setWidgetResizable(True)
        info_root = QWidget()
        form = QFormLayout(info_root)
        self.info = {}
        for key, label in (
            ("title", "Report title"), ("customer", "Customer"), ("site", "Site"),
            ("machine", "Machine"), ("ticket", "Ticket number"),
            ("technicians", "Personnel (comma separated)"),
            ("language", "Source language tag"), ("outputs", "Output language tags (comma separated)"),
            ("other", "Other intervention details"),
        ):
            control = QLineEdit()
            control.setObjectName("report_" + key)
            self.info[key] = control
            control.textEdited.connect(self._set_info_pending)
            form.addRow(label, control)
        self.dates = {}
        for key, label in (("created", "Creation date"), ("start", "Intervention start"),
                           ("end", "Intervention end")):
            widget = QDateEdit()
            widget.setCalendarPopup(True)
            widget.setDisplayFormat("yyyy-MM-dd")
            self.dates[key] = widget
            widget.dateChanged.connect(self._set_info_pending)
            form.addRow(label, widget)
        self.types = {}
        types_row = QWidget()
        types_layout = QHBoxLayout(types_row)
        for key, label in (("supervision", "Supervision"),
                           ("ordinary_maintenance", "Ordinary maintenance"),
                           ("extraordinary_maintenance", "Extra maintenance"), ("other", "Other")):
            check = QCheckBox(label)
            self.types[key] = check
            check.toggled.connect(self._set_info_pending)
            types_layout.addWidget(check)
        form.addRow("Intervention types", types_row)
        self.origin_label = QLabel()
        form.addRow("Customer source", self.origin_label)
        identity_buttons = QHBoxLayout()
        db_button = QPushButton("Choose from database")
        db_button.clicked.connect(self.choose_customer)
        identity_buttons.addWidget(db_button)
        manual_button = QPushButton("Use manual customer")
        manual_button.clicked.connect(self.detach_customer)
        identity_buttons.addWidget(manual_button)
        form.addRow(identity_buttons)
        commit = QPushButton("Apply report information")
        commit.setObjectName("applyReportInfo")
        commit.clicked.connect(self.apply_info)
        form.addRow(commit)
        info_outer.setWidget(info_root)
        self.tabs.addTab(info_outer, "Report Information")

    def add_toolbar_actions(self, toolbar):
        for title, slot, shortcut in (
            ("New", self.new_document, QKeySequence.StandardKey.New),
            ("Open", self.open_dialog, QKeySequence.StandardKey.Open),
            ("Save", self.save, QKeySequence.StandardKey.Save),
            ("Save As", self.save_as, QKeySequence.StandardKey.SaveAs),
            ("Undo", self.undo, QKeySequence.StandardKey.Undo),
            ("Redo", self.redo, QKeySequence.StandardKey.Redo),
        ):
            action = QAction(title, self.owner)
            action.setObjectName("project" + title.replace(" ", "") + "Action")
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(slot)
            toolbar.addAction(action)
            self.owner.addAction(action)
        pictures_action = QAction("Pictures", self.owner)
        pictures_action.setObjectName("pictureManagerAction")
        pictures_action.triggered.connect(self.manage_pictures)
        toolbar.addAction(pictures_action)
        self.owner.addAction(pictures_action)
        branding_action = QAction("Export branding", self.owner)
        branding_action.setObjectName("exportBrandingAction")
        branding_action.triggered.connect(self.configure_export_branding)
        toolbar.addAction(branding_action)
        self.owner.addAction(branding_action)
        for label, object_name, handler in (
            ("Import Word page template", "importWordTemplateAction", self.import_document_template),
            ("Edit active page template", "editWordTemplateAction", self.edit_document_template),
            ("Clear page template", "clearWordTemplateAction", self.clear_document_template),
        ):
            action = QAction(label, self.owner)
            action.setObjectName(object_name)
            action.triggered.connect(handler)
            toolbar.addAction(action)
            self.owner.addAction(action)
        for fmt in ("docx", "pdf"):
            action = QAction("Export " + fmt.upper(), self.owner)
            action.setObjectName("export" + fmt.upper() + "Action")
            action.triggered.connect(lambda checked=False, kind=fmt: self.export_as(kind))
            toolbar.addAction(action)
            self.owner.addAction(action)

    def _warn(self, title, error):
        QMessageBox.warning(self.owner, title, str(error))

    def _change(self, operation):
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        try:
            operation()
        except (ValueError, LookupError, TypeError) as exc:
            self._warn("Report edit rejected", exc)
            return False
        self.dirty = True
        self.refresh()
        return True

    def _selected_module(self):
        if not self._module_id:
            return None
        return find_module(self.report, self._module_id)

    def _item_for_id(self, identifier):
        def visit(item):
            if item.data(0, Qt.ItemDataRole.UserRole) == identifier:
                return item
            for index in range(item.childCount()):
                found = visit(item.child(index))
                if found:
                    return found
            return None
        for i in range(self.tree.topLevelItemCount()):
            found = visit(self.tree.topLevelItem(i))
            if found:
                return found
        return None

    def refresh(self):
        self._loading = True
        try:
            selected = self._module_id
            self.tree.clear()
            def add(module, parent=None):
                item = QTreeWidgetItem([module.title.original])
                item.setData(0, Qt.ItemDataRole.UserRole, module.id)
                if parent is None:
                    self.tree.addTopLevelItem(item)
                else:
                    parent.addChild(item)
                if module is self.report.conclusion:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled &
                                  ~Qt.ItemFlag.ItemIsDropEnabled)
                for block in module.blocks:
                    if isinstance(block, NestedModuleBlock):
                        add(block.module, item)
            for module in self.report.ordered_sections():
                add(module)
            self.tree.expandAll()
            selected_item = self._item_for_id(selected) if selected else None
            self.tree.setCurrentItem(selected_item or self.tree.topLevelItem(0))
            self._module_id = self.tree.currentItem().data(0, Qt.ItemDataRole.UserRole)
            self._refresh_blocks()
            rows = []
            for entry in module_outline(self.report):
                text = (entry.number + "  " if entry.number else "") + entry.title
                rows.append("<div style='margin-left:%dem'>%s</div>" % (entry.depth, escape(text)))
            self.summary.setHtml("".join(rows))
            self._load_info()
            self._render_preview()
            self.owner.setWindowTitle("ReportMaker — " +
                                      (str(self.path) if self.path else "Untitled project") +
                                      (" *" if self.dirty else ""))
        finally:
            self._loading = False

    def _refresh_blocks(self):
        module = self._selected_module()
        if module is None:
            return
        self.active_label.setText("Editing: " + module.title.original)
        old_id = self._edit_block_id
        self.blocks.clear()
        for block in module.blocks:
            if isinstance(block, NestedModuleBlock):
                name = "Submodule: " + block.module.title.original
            else:
                name = type(block).__name__.replace("Block", "")
                if isinstance(block, (HeadingBlock, ParagraphBlock)):
                    name += ": " + block.text.original[:75].replace("\n", " ")
                elif isinstance(block, PhotoBlock):
                    name += ": " + (block.caption.original if block.caption else block.asset_id)
                elif isinstance(block, TableBlock):
                    name += ": %d rows" % len(block.rows)
            item = QListWidgetItem(name)
            item.setData(Qt.ItemDataRole.UserRole, block.id)
            self.blocks.addItem(item)
        item = next((self.blocks.item(i) for i in range(self.blocks.count())
                     if self.blocks.item(i).data(Qt.ItemDataRole.UserRole) == old_id), None)
        self.blocks.setCurrentItem(item or (self.blocks.item(0) if self.blocks.count() else None))
        self._show_block()

    def _module_selected(self, current, previous):
        if self._loading or current is None:
            return
        if not self._flush_block():
            self._loading = True
            self.tree.setCurrentItem(previous)
            self._loading = False
            return
        self._module_id = current.data(0, Qt.ItemDataRole.UserRole)
        self._loading = True
        self._edit_block_id = None
        self._refresh_blocks()
        self._loading = False

    def _block_selected(self, current, previous):
        if self._loading:
            return
        if not self._flush_block():
            self._loading = True
            self.blocks.setCurrentItem(previous)
            self._loading = False
            return
        self._show_block()

    def _show_block(self):
        self._loading = True
        try:
            module = self._selected_module()
            item = self.blocks.currentItem()
            block = next((b for b in module.blocks if b.id == item.data(Qt.ItemDataRole.UserRole)),
                         None) if item else None
            self._edit_block_id = block.id if block else None
            self._block_pending = False
            is_text = isinstance(block, (ParagraphBlock, HeadingBlock))
            is_photo = isinstance(block, PhotoBlock)
            is_table = isinstance(block, TableBlock)
            self.text_edit.setVisible(is_text)
            self.rich_ribbon.setVisible(is_text)
            self.photo_caption.setVisible(is_photo)
            self.picture_edit.setVisible(is_photo)
            self.table.setVisible(is_table)
            self.table_buttons.setVisible(is_table)
            self.block_hint.setText("Submodules are edited through the module tree." if isinstance(block, NestedModuleBlock)
                                    else "Edit the block below, then Apply." if block else
                                    "Add or select a content block.")
            if is_text:
                apply_rich(self.text_edit, block.text.original, block.rich)
            else:
                self.text_edit.blockSignals(True)
                self.text_edit.clear()
                self.text_edit.blockSignals(False)
            self.photo_caption.setText(block.caption.original if is_photo and block.caption else "")
            if is_table:
                self.table.setRowCount(len(block.rows))
                self.table.setColumnCount(max((len(row) for row in block.rows), default=0))
                for row_index, row in enumerate(block.rows):
                    for col_index, cell in enumerate(row):
                        self.table.setItem(row_index, col_index, QTableWidgetItem(cell.original))
            else:
                self.table.setRowCount(0)
                self.table.setColumnCount(0)
        finally:
            self._loading = False

    def _set_pending(self, *_args):
        if not self._loading:
            self._block_pending = True

    def _set_info_pending(self, *_args):
        if not self._loading:
            self._info_pending = True

    def _flush_info(self):
        return not self._info_pending or self.apply_info()

    def _flush_block(self):
        return not self._block_pending or self.apply_block()

    def _page_conflict_key(self):
        if not self._block_pending or not self._edit_block_id:
            return None
        module = self._selected_module()
        if module is None:
            return None
        block = next((b for b in module.blocks if b.id == self._edit_block_id), None)
        kind = ("text" if isinstance(block, (ParagraphBlock, HeadingBlock)) else
                "caption" if isinstance(block, PhotoBlock) else
                "table" if isinstance(block, TableBlock) else None)
        key = (self._module_id, self._edit_block_id, kind)
        return key if kind and key in self.page.pending else None

    def _flush_page(self):
        if not self.page.pending:
            return True
        try:
            self.page.commit(self.editor)
        except (ValueError, LookupError, TypeError, RuntimeError) as exc:
            self._warn("Invalid page edit", exc)
            return False
        self.dirty = True
        return True

    def commit_page(self):
        if self._page_conflict_key():
            choice = QMessageBox.question(
                self.owner, "Conflicting text drafts",
                "The block editor also has unapplied changes to this field. "
                "Keep the page edits and discard that uncommitted block-editor draft?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if choice != QMessageBox.StandardButton.Yes:
                return False
            # Validate and commit the chosen page source *before* throwing away
            # the other draft; invalid page input must not lose block-editor work.
            if not self._flush_page():
                return False
            self._block_pending = False
            if not self._flush_info():
                return False
            self.refresh()
            return True
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        self.refresh()
        return True

    def _page_tab_changed(self, index):
        if index != 1 or self._loading:
            return
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            self.page_tabs.setCurrentIndex(0)
            return
        self.refresh()  # print preview, ribbon and paper now share one model

    def _select_page_block(self, module_id, block_id):
        # Style controls live in the existing rich ribbon; locate by stable IDs.
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        self._module_id = module_id
        self._edit_block_id = block_id
        self.refresh()
        self.text_edit.setFocus()
        return True

    def apply_block(self):
        if not self._block_pending or not self._edit_block_id:
            return True
        overlap = self._page_conflict_key()
        if overlap:
            choice = QMessageBox.question(
                self.owner, "Conflicting text drafts",
                "The editable page also has unapplied changes to this field. "
                "Keep the block-editor edits and discard that page draft?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel)
            if choice != QMessageBox.StandardButton.Yes:
                return False
            self.page.pending.discard(overlap)
        if not self._flush_page():
            if overlap:
                self.page.pending.add(overlap)  # validation failed: retain page draft
            return False
        identifier = self._edit_block_id
        module_id = self._module_id
        text, rich = capture_rich(self.text_edit)
        caption = self.photo_caption.text()
        cells = [[self.table.item(i, j).text() if self.table.item(i, j) else ""
                  for j in range(self.table.columnCount())]
                 for i in range(self.table.rowCount())]
        def update(report):
            module = find_module(report, module_id)
            block = next(b for b in module.blocks if b.id == identifier)
            if isinstance(block, (ParagraphBlock, HeadingBlock)):
                block.text.update_original(text)
                block.rich = deepcopy(rich)
            elif isinstance(block, PhotoBlock):
                if block.caption is None:
                    block.caption = LocalizedText(report.primary_language, caption)
                else:
                    block.caption.update_original(caption)
            elif isinstance(block, TableBlock):
                new_rows = []
                for i, row in enumerate(cells):
                    new_row = []
                    for j, value in enumerate(row):
                        prior = (deepcopy(block.rows[i][j])
                                 if i < len(block.rows) and j < len(block.rows[i])
                                 else LocalizedText(report.primary_language, ""))
                        prior.update_original(value)
                        new_row.append(prior)
                    new_rows.append(new_row)
                block.rows = new_rows
        try:
            self.editor.apply(update)
        except (ValueError, LookupError, StopIteration) as exc:
            if overlap:
                self.page.pending.add(overlap)
            self._warn("Invalid block", exc)
            return False
        self._block_pending = False
        self.dirty = True
        # Caller may be handling a selection change; avoid rebuilding the list here.
        self._render_preview()
        self.owner.setWindowTitle(self.owner.windowTitle().rstrip(" *") + " *")
        return True

    def _add_row(self):
        self.table.insertRow(self.table.rowCount())
        self._set_pending()

    def _remove_row(self):
        if self.table.rowCount():
            self.table.removeRow(self.table.rowCount() - 1)
            self._set_pending()

    def _add_column(self):
        self.table.insertColumn(self.table.columnCount())
        self._set_pending()

    def _remove_column(self):
        if self.table.columnCount():
            self.table.removeColumn(self.table.columnCount() - 1)
            self._set_pending()

    def _add_block(self, block):
        if self._module_id:
            self._change(lambda: self.editor.add_block(self._module_id, block))
            self._edit_block_id = block.id
            self._refresh_blocks()

    def add_paragraph(self):
        self._add_block(ParagraphBlock(LocalizedText(self.report.primary_language, "")))

    def add_heading(self):
        self._add_block(HeadingBlock(LocalizedText(self.report.primary_language, "New heading")))

    def add_table(self):
        language = self.report.primary_language
        self._add_block(TableBlock([[LocalizedText(language, "") for _ in range(2)]
                                    for _ in range(2)]))

    def add_page_break(self):
        self._add_block(PageBreakBlock())

    def add_photo(self):
        """Open the non-modal project gallery for keyboard or mouse insertion."""
        self.manage_pictures()

    def _resolve_project_photo_drag(self, source, mime):
        """Accept exactly one project-owned asset ID from THIS gallery instance.

        External files, URLs, text, HTML, stale gallery instances and forged
        MIME from another drag source are never interpreted as report content.
        """
        if (source is not self._picture_list or
                getattr(source, "session_token", None) != self._photo_drag_token or
                mime is None or mime.formats() != [PHOTO_MIME]):
            return None
        raw = bytes(mime.data(PHOTO_MIME))
        if not raw or len(raw) > 128:
            return None
        try:
            key = raw.decode("utf-8")
        except UnicodeError:
            return None
        if key not in self.media_library or key not in self.assets:
            return None
        return key

    def _insert_project_photo(self, module_id, index, asset_id):
        """One validated canonical insertion, never a duplicate image asset."""
        if (not isinstance(asset_id, str) or asset_id not in self.media_library
                or asset_id not in self.assets):
            return False
        module_id = module_id or self._module_id
        try:
            module = find_module(self.report, module_id)
        except (LookupError, TypeError):
            return False
        if index is None:
            index = len(module.blocks)
        if type(index) is not int or not 0 <= index <= len(module.blocks):
            return False
        # Respect uncommitted rich block, information and editable-page drafts.
        # Fail without inserting if a conflicting draft cannot be resolved.
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        if asset_id not in self.media_library or asset_id not in self.assets:
            return False
        picture = PhotoBlock(asset_id, LocalizedText(self.report.primary_language, ""))
        try:
            self.editor.add_block(module_id, picture, index=index)
        except (ValueError, LookupError, TypeError) as exc:
            self._warn("Cannot insert project picture", exc)
            return False
        self.dirty = True
        self._module_id = module_id
        self._edit_block_id = picture.id
        self.refresh()
        return True

    def manage_pictures(self):
        """Local project-owned picture container; no external paths persisted."""
        if not self._flush_block() or not self._flush_info():
            return False
        if self._picture_gallery is not None:
            if self._gallery_populate is not None:
                self._gallery_populate()
            self._picture_gallery.show()
            self._picture_gallery.raise_()
            self._picture_gallery.activateWindow()
            return True
        dialog = QDialog(self.owner)
        dialog.setObjectName("projectPictureGallery")
        dialog.setModal(False)
        dialog.setWindowTitle("Project Pictures — drag thumbnails into report")
        dialog.resize(870, 720)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel(
            "All thumbnails are project-owned working copies. Drag onto a blue block-list "
            "insertion marker or a page drop zone; original photos stay unchanged."))
        choices = QHBoxLayout()
        preset = QComboBox()
        preset.setObjectName("pictureImportPreset")
        for value, label in (("balanced", "Balanced · 2500 px / JPEG 88"),
                             ("compact", "Compact · 1600 px / JPEG 75"),
                             ("high", "High quality · 4000 px / JPEG 94")):
            preset.addItem(label, value)
        fmt = QComboBox()
        fmt.setObjectName("pictureImportFormat")
        for value, label in (("auto", "Automatic JPEG / alpha PNG"),
                             ("jpeg", "JPEG"), ("png", "PNG"), ("webp", "WebP")):
            fmt.addItem(label, value)
        choices.addWidget(preset)
        choices.addWidget(fmt)
        layout.addLayout(choices)
        pictures = ProjectPictureList(
            lambda key: key in self.media_library and key in self.assets,
            lambda key: self.assets.get(key, b""),
            self._photo_drag_token, dialog)
        self._picture_list = pictures
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Thumbnail size"))
        zoom = QSlider(Qt.Orientation.Horizontal)
        zoom.setObjectName("pictureThumbnailZoom")
        zoom.setRange(72, 220)
        zoom.setValue(132)
        zoom.valueChanged.connect(pictures.set_thumbnail_size)
        zoom_row.addWidget(zoom)
        layout.addLayout(zoom_row)
        layout.addWidget(pictures, 1)
        empty = QLabel("No project pictures yet. Choose Import pictures… to add some.")
        empty.setObjectName("pictureGalleryEmptyState")
        layout.addWidget(empty)
        thumbnail = QLabel("Select a project picture to inspect it.")
        thumbnail.setObjectName("pictureGalleryInspector")
        thumbnail.setMinimumHeight(180)
        thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(thumbnail)

        def selected_key():
            item = pictures.currentItem()
            return item.data(Qt.ItemDataRole.UserRole) if item else None

        def show_preview():
            key = selected_key()
            image = scaled_project_image(self.assets.get(key, b""), 660, 230) if key else QImage()
            if image.isNull():
                thumbnail.setText("Select a project picture to inspect it.")
                thumbnail.setPixmap(QPixmap())
            else:
                thumbnail.setText("")
                thumbnail.setPixmap(QPixmap.fromImage(image))

        pictures.currentItemChanged.connect(lambda *_: show_preview())

        def populate():
            pictures.populate(self.media_library)
            empty.setVisible(pictures.count() == 0)
            show_preview()

        buttons = QHBoxLayout()
        do_import = QPushButton("Import pictures…")
        do_import.setObjectName("importProjectPicturesAction")
        insert = QPushButton("Insert selected")
        remove = QPushButton("Remove unused")
        close = QPushButton("Close")
        for button in (do_import, insert, remove, close):
            buttons.addWidget(button)
        layout.addLayout(buttons)

        def approve_staged(staged):
            """Review true source/converted previews; approval commits exact bytes."""
            comparison = QDialog(dialog)
            comparison.setObjectName("pictureImportComparisonDialog")
            comparison.setWindowTitle("Compare original and optimized working pictures")
            comparison.resize(780, 475)
            content = QVBoxLayout(comparison)
            selector = QComboBox()
            selector.setObjectName("pictureComparisonSelector")
            for entry in staged:
                selector.addItem(entry.name)
            content.addWidget(selector)
            views = QHBoxLayout()
            source_panel = QVBoxLayout()
            target_panel = QVBoxLayout()
            source_panel.addWidget(QLabel("Original (preview only)"))
            target_panel.addWidget(QLabel("Optimized project copy"))
            source_image = QLabel()
            target_image = QLabel()
            for widget in (source_image, target_image):
                widget.setMinimumSize(300, 210)
                widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
            source_panel.addWidget(source_image)
            target_panel.addWidget(target_image)
            views.addLayout(source_panel)
            views.addLayout(target_panel)
            content.addLayout(views)
            details = QLabel()
            content.addWidget(details)

            def show_comparison(*_):
                entry = staged[selector.currentIndex()]
                photo = entry.photo
                for widget, image_bytes in (
                    (source_image, photo.source_preview), (target_image, photo.data)
                ):
                    image = QImage.fromData(image_bytes)
                    widget.setPixmap(QPixmap.fromImage(image.scaled(
                        330, 240, Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation))
                        if not image.isNull() else QPixmap())
                details.setText(
                    f"{entry.name}: {photo.original_width}×{photo.original_height} "
                    f"({photo.source_bytes / 1048576:.2f} MiB) → "
                    f"{photo.width}×{photo.height} {photo.format.upper()} "
                    f"({len(photo.data) / 1048576:.2f} MiB)")
            selector.currentIndexChanged.connect(show_comparison)
            show_comparison()
            old = sum(entry.photo.source_bytes for entry in staged)
            new = sum(len(entry.photo.data) for entry in staged)
            content.addWidget(QLabel(
                f"Total: {len(staged)} photos; source {old / 1048576:.2f} MiB → "
                f"project {new / 1048576:.2f} MiB. Source files stay unchanged."))
            actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                       QDialogButtonBox.StandardButton.Cancel)
            actions.accepted.connect(comparison.accept)
            actions.rejected.connect(comparison.reject)
            content.addWidget(actions)
            return comparison.exec() == QDialog.DialogCode.Accepted

        def import_selected():
            paths, _ = QFileDialog.getOpenFileNames(
                dialog, "Import independent project copies", "",
                "Images (*.heic *.heif *.jpg *.jpeg *.png *.bmp *.webp)")
            if not paths:
                return
            try:
                # Stage once. The preview and committed working copy use the
                # identical image bytes; source originals are never reopened.
                staged = stage_pictures(paths, preset=preset.currentData(),
                                        output_format=fmt.currentData())
                if not approve_staged(staged):
                    return
                # The non-modal gallery allows ongoing report/page editing.
                # Before a gallery mutation redraws the editor, explicitly
                # commit/resolve drafts or keep both the draft and library intact.
                if not self._flush_block() or not self._flush_info() or not self._flush_page():
                    return
                commit_staged_pictures(
                    ReportProject(self.report, self.assets, self.media_library), staged)
            except (PictureImportError, ValueError, OSError) as exc:
                self._warn("Cannot import pictures", exc)
                return
            self.dirty = True
            populate()
            self.refresh()

        def insert_selected():
            key = selected_key()
            if not key:
                return
            if not self._module_id:
                self._warn("Select a module", "Select a report module before inserting a picture.")
                return
            self._insert_project_photo(self._module_id, None, key)

        def delete_selected():
            key = selected_key()
            if key is None:
                return
            if not self._flush_block() or not self._flush_info() or not self._flush_page():
                return
            try:
                remove_library_picture(ReportProject(self.report, self.assets,
                                                     self.media_library), key)
            except PictureImportError as exc:
                self._warn("Cannot remove picture", exc)
                return
            self.dirty = True
            populate()
            self.refresh()

        do_import.clicked.connect(import_selected)
        insert.clicked.connect(insert_selected)
        remove.clicked.connect(delete_selected)
        close.clicked.connect(dialog.close)
        self._picture_gallery = dialog
        self._gallery_populate = populate
        populate()
        dialog.show()  # non-modal: report remains editable and drop zones active
        return True

    def edit_picture(self):
        """Edit only this PhotoBlock's own visual instructions, never asset bytes."""
        if not self._flush_block() or not self._flush_info():
            return False
        module = self._selected_module()
        block = next((b for b in module.blocks if b.id == self._edit_block_id),
                     None) if module else None
        if not isinstance(block, PhotoBlock):
            return False
        source = self.assets.get(block.asset_id, b"")
        if not source or QImage.fromData(source).isNull():
            self._warn("Cannot edit picture", "The project picture cannot be decoded")
            return False
        dialog = PictureEditorDialog(self.owner, source, block.visual,
                                     self.report.primary_language)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        edited = deepcopy(dialog.visual)
        if edited == block.visual:
            return True
        def update(report):
            destination = find_module(report, module.id)
            image_block = next(b for b in destination.blocks
                               if b.id == block.id)
            image_block.visual = deepcopy(edited)
        return self._change(lambda: self.editor.apply(update))

    def remove_block(self):
        item = self.blocks.currentItem()
        if item and self._module_id:
            block = next(b for b in self._selected_module().blocks if b.id == item.data(Qt.ItemDataRole.UserRole))
            if isinstance(block, NestedModuleBlock):
                self._warn("Use module tree", "Delete a submodule from the module tree.")
                return
            # Flush/validate drafts before deleting. A rejected operation must
            # never clear the selected block's unapplied text or rich formatting.
            if self._change(lambda: self.editor.remove_block(self._module_id, block.id)):
                self._edit_block_id = None
                self.refresh()

    def move_block_dialog(self):
        item = self.blocks.currentItem()
        if item is None or not self._module_id:
            return
        block_id = item.data(Qt.ItemDataRole.UserRole)
        if any(isinstance(b, NestedModuleBlock) and b.id == block_id
               for b in self._selected_module().blocks):
            self._warn("Use module tree", "Move or nest submodules using the module tree.")
            return
        entries = module_outline(self.report)
        labels = [(entry.number + " " if entry.number else "") + entry.title
                  for entry in entries]
        label, ok = QInputDialog.getItem(self.owner, "Move content block",
                                          "Destination module:", labels, 0, False)
        if ok:
            destination = entries[labels.index(label)].module_id
            source = self._module_id
            if self._change(lambda: self.editor.move_block(source, block_id, destination)):
                self._module_id = destination
                self._edit_block_id = block_id
                self.refresh()

    def _block_move(self, block_id, index):
        if self._module_id:
            self._change(lambda: self.editor.move_block(self._module_id, block_id,
                                                        self._module_id, index=index))

    def add_module(self):
        self._add_module_under(None)

    def add_child(self):
        if self._module_id == self.report.conclusion.id:
            self._warn("Invalid parent", "Conclusions must remain the last section.")
            return
        self._add_module_under(self._module_id)

    def _add_module_under(self, parent):
        title, ok = QInputDialog.getText(self.owner, "Add module", "Module title:")
        if ok and title.strip():
            module = Module(LocalizedText(self.report.primary_language, title.strip()))
            if self._change(lambda: self.editor.add_module(module, parent_id=parent)):
                self._module_id = module.id
                self.refresh()

    def rename_module(self):
        module = self._selected_module()
        if module:
            title, ok = QInputDialog.getText(self.owner, "Rename module", "Title:",
                                             text=module.title.original)
            if ok and title.strip():
                self._change(lambda: self.editor.rename_module(module.id, title.strip()))

    def duplicate_module(self):
        if self._module_id:
            result = [None]
            if self._change(lambda: result.__setitem__(0, self.editor.duplicate_module(self._module_id))):
                self._module_id = result[0]
                self.refresh()

    def delete_module(self):
        module = self._selected_module()
        if module and module.id != self.report.conclusion.id:
            if QMessageBox.question(self.owner, "Delete module",
                                    "Delete this module and all nested content?") == QMessageBox.StandardButton.Yes:
                if self._change(lambda: self.editor.remove_module(module.id)):
                    self._module_id = None
                    self.refresh()

    def _tree_move(self, source_id, target_id, after):
        if source_id == self.report.conclusion.id:
            self.refresh()
            return
        try:
            if after is None and target_id is not None:
                parent, index = target_id, None
            elif target_id is None:
                parent, index = None, None
            else:
                parent, index = module_insert_index(self.report, target_id, after)
        except LookupError as exc:
            self._warn("Invalid move", exc)
            return
        self._change(lambda: self.editor.move_module(source_id, parent_id=parent, index=index))
        self._module_id = source_id
        self.refresh()

    def _load_info(self):
        report = self.report
        snapshot = report.customer_snapshot
        values = {
            "title": report.title.original, "ticket": report.ticket,
            "technicians": ", ".join(report.technicians),
            "language": report.primary_language,
            "outputs": ", ".join(report.output_languages),
            "other": report.other_intervention_detail,
            "customer": snapshot.customer_name if snapshot else "",
            "site": snapshot.site_name if snapshot else "",
            "machine": snapshot.machine_name if snapshot else "",
        }
        for key, value in values.items():
            self.info[key].setText(value)
        for key, value in (("created", report.created_date),
                           ("start", report.start_date), ("end", report.end_date)):
            self.dates[key].setDate(QDate(value.year, value.month, value.day))
        for key, checkbox in self.types.items():
            checkbox.setChecked(key in report.intervention_types)
        self._info_pending = False
        linked = report.customer_id is not None
        self.origin_label.setText("Frozen database snapshot" if linked else "Manual report snapshot")
        for key in ("customer", "site", "machine"):
            self.info[key].setReadOnly(linked)

    def apply_info(self):
        if not self._flush_block():
            return False
        values = {key: widget.text() for key, widget in self.info.items()}
        report = self.report
        if report.customer_id is not None:
            customer = report.customer_snapshot
            if (values["customer"] != customer.customer_name or
                values["site"] != customer.site_name or
                values["machine"] != customer.machine_name):
                self._warn("Customer is linked", "Use 'Use manual customer' to detach first.")
                return False
        try:
            output_tags = [part.strip() for part in values["outputs"].split(",") if part.strip()]
            technicians = [part.strip() for part in values["technicians"].split(",") if part.strip()]
            selections = [key for key, checkbox in self.types.items() if checkbox.isChecked()]
            dates = {key: date(widget.date().year(), widget.date().month(), widget.date().day())
                     for key, widget in self.dates.items()}
            def change(target):
                target.title.update_original(values["title"])
                target.ticket = values["ticket"]
                target.technicians = technicians
                target.primary_language = values["language"].strip()
                target.output_languages = output_tags
                target.intervention_types = selections
                target.other_intervention_detail = values["other"]
                target.created_date = dates["created"]
                target.start_date, target.end_date = dates["start"], dates["end"]
                if target.customer_id is None:
                    target.customer_snapshot = revised_manual_snapshot(
                        target.customer_snapshot,
                        values["customer"], values["site"], values["machine"],
                    )
            self.editor.apply(change)
        except (ValueError, TypeError) as exc:
            self._warn("Invalid report information", exc)
            return False
        self.dirty = True
        self._info_pending = False
        self.refresh()
        return True

    def detach_customer(self):
        if self.report.customer_id is None:
            return
        def change(report):
            old = report.customer_snapshot
            details = {f.name: getattr(old, f.name) for f in fields(old)
                       if f.name not in ("customer_name", "customer_id", "site_id",
                                         "machine_id", "captured_at", "schema_version")}
            report.customer_id = None
            report.customer_snapshot = manual_snapshot(old.customer_name, **details)
        self._change(lambda: self.editor.apply(change))

    def choose_customer(self):
        # Selection is explicit and captures a detached immutable snapshot.
        from .storage import CustomerStore
        try:
            with CustomerStore() as store:
                customers = store.list_customers()
                if not customers:
                    self._warn("Customer database", "No customers available. You can enter one manually.")
                    return
                dialog = QDialog(self.owner)
                dialog.setWindowTitle("Select customer, site and machine")
                form = QFormLayout(dialog)
                customer = QComboBox()
                site = QComboBox()
                machine = QComboBox()
                customer.addItem("Choose customer", None)
                for row in customers:
                    customer.addItem(row["name"], row["id"])
                def update_sites():
                    site.clear()
                    site.addItem("(No site)", None)
                    for row in store.list_sites(customer.currentData()) if customer.currentData() else []:
                        site.addItem(row["name"], row["id"])
                    update_machines()
                def update_machines():
                    machine.clear()
                    machine.addItem("(No machine)", None)
                    for row in store.list_machines(site.currentData()) if site.currentData() else []:
                        machine.addItem(row["name"], row["id"])
                customer.currentIndexChanged.connect(update_sites)
                site.currentIndexChanged.connect(update_machines)
                form.addRow("Customer", customer)
                form.addRow("Site", site)
                form.addRow("Machine", machine)
                actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                           QDialogButtonBox.StandardButton.Cancel)
                actions.accepted.connect(dialog.accept)
                actions.rejected.connect(dialog.reject)
                form.addRow(actions)
                if dialog.exec() != QDialog.DialogCode.Accepted or not customer.currentData():
                    return
                snapshot = store.capture_snapshot(
                    customer.currentData(), site_id=site.currentData(),
                    machine_id=machine.currentData())
        except (OSError, ValueError, RuntimeError, LookupError) as exc:
            self._warn("Customer database unavailable", exc)
            return
        def change(report):
            report.customer_id = snapshot.customer_id
            report.customer_snapshot = snapshot
        self._change(lambda: self.editor.apply(change))

    def _render_preview(self):
        report = self.report
        sections = ["<html><body style='font-family:sans-serif; color:#202124; "
                    "background-color:#ffffff; margin:18px'>",
                    "<h1>%s</h1>" % escape(report.title.original)]
        snapshot = report.customer_snapshot
        for label, value in (("Customer", snapshot.customer_name if snapshot else ""),
                             ("Site", snapshot.site_name if snapshot else ""),
                             ("Machine", snapshot.machine_name if snapshot else ""),
                             ("Created", report.created_date.isoformat()),
                             ("Intervention", report.start_date.isoformat() + " – " + report.end_date.isoformat()),
                             ("Ticket", report.ticket),
                             ("Personnel", ", ".join(report.technicians)),
                             ("Types", ", ".join(report.intervention_types)),
                             ("Other intervention details",
                              report.other_intervention_detail
                              if "other" in report.intervention_types else "")):
            if value:
                sections.append("<p><b>%s:</b> %s</p>" % (label, escape(value)))
        sections.append("<h2>Summary</h2>")
        for entry in module_outline(report):
            line = (entry.number + " " if entry.number else "") + entry.title
            sections.append("<p style='margin-left:%dem'>%s</p>" % (entry.depth * 1.3, escape(line)))
        images = {}
        def draw(module, title, level):
            sections.append("<h%d>%s</h%d>" % (min(level, 6), escape(title), min(level, 6)))
            for block in module.blocks:
                if isinstance(block, ParagraphBlock):
                    sections.append(safe_html(block.text.original, block.rich))
                elif isinstance(block, HeadingBlock):
                    sections.append("<div style=\"font-weight:bold\">" + safe_html(block.text.original, block.rich) + "</div>")
                elif isinstance(block, TableBlock):
                    sections.append("<table border='1' cellspacing='0' cellpadding='5'>")
                    for row in block.rows:
                        sections.append("<tr>" + "".join("<td>%s</td>" % escape(cell.original)
                                                        for cell in row) + "</tr>")
                    sections.append("</table>")
                elif isinstance(block, PhotoBlock):
                    data = self.assets.get(block.asset_id, b"")
                    try:
                        image = render_photo(data, block.visual, 800)
                    except ValueError:
                        image = QImage()
                    if not image.isNull():
                        width = min(520, image.width()) * block.visual.width_pct // 100
                        image = image.scaledToWidth(max(1, width),
                                                    Qt.TransformationMode.SmoothTransformation)
                        image_key = (block.asset_id if block.visual == PhotoVisual()
                                     else block.id)
                        images[image_key] = image
                        sections.append('<p style="text-align:%s"><img src="rmasset:%s"/></p>'
                                        % (block.visual.alignment, image_key))
                    else:
                        sections.append("<p>[Photo unavailable]</p>")
                    if block.caption:
                        sections.append("<p><i>%s</i></p>" % escape(block.caption.original))
                elif isinstance(block, PageBreakBlock):
                    sections.append("<hr/><p><i>Page break</i></p>")
                # Keep nested module in its original mixed block position.
                if isinstance(block, NestedModuleBlock):
                    draw(block.module, block.module.title.original, level + 1)
        for entry in report.modules:
            draw(entry, entry.title.original, 2)
        draw(report.conclusion, report.conclusion.title.original, 2)
        sections.append("</body></html>")
        self.preview.setHtml("".join(sections))
        for identifier, image in images.items():
            self.preview.document().addResource(
                QTextDocument.ResourceType.ImageResource,
                QUrl("rmasset:" + identifier), image)
        self.preview.viewport().update()
        # Imported geometry is a view/export concern, not a second report model.
        path = str(self.owner.settings.value("export/page_template", "")).strip()
        try:
            self.page.layout_template = load_template(path) if path else None
            self.page.setToolTip("" if not path else
                "Active local page template: " + Path(path).name)
        except (TemplateError, OSError):
            self.page.layout_template = None
            self.page.setToolTip("Selected page template is invalid: exports will be blocked")
        # Avoid dropping uncommitted direct page edits when the other pane redraws.
        if not self.page.pending:
            self.page.rebuild(report, self.assets)

    def _confirm_discard(self):
        # Discard must remain available even if the pending form is invalid.
        # Only the Save branch validates/commits draft edits.
        if not (self.dirty or self._block_pending or self._info_pending or self.page.pending):
            return True
        choice = QMessageBox.question(
            self.owner, "Unsaved project",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard |
            QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if choice == QMessageBox.StandardButton.Cancel:
            return False
        if choice == QMessageBox.StandardButton.Save:
            return self.save()
        return True

    def new_document(self):
        if self._confirm_discard():
            self._replace(new_report(), None)

    def _replace(self, project, path):
        # A gallery belongs to exactly one open project. Invalidate the drag
        # source and session token BEFORE adopting another project's assets.
        if self._picture_gallery is not None:
            self._picture_gallery.close()
            self._picture_gallery.deleteLater()  # release cached thumbnails on project switch
        self._picture_gallery = None
        self._picture_list = None
        self._gallery_populate = None
        self._photo_drag_token = uuid4().hex
        self.editor = ProjectEditor(project.report)
        self.assets = dict(project.assets)
        self.media_library = dict(project.media_library)
        self.loaded_version = project.loaded_version
        self.loaded_from = project.loaded_from
        self.path = path
        self.dirty = False
        self._module_id = None
        self._edit_block_id = None
        self._block_pending = False
        self._info_pending = False
        self.page.pending.clear()  # deliberate Open/New discards the previous draft
        self.refresh()

    def open_from_path(self, path):
        # Parse and validate first; failed Open must preserve the active document.
        try:
            project = load_project(path)
            replacement = ProjectEditor(project.report)
        except (ValueError, OSError, RuntimeError) as exc:
            self._warn("Cannot open project", exc)
            return False
        self._replace(ReportProject(replacement.report, project.assets,
                                    project.media_library, project.loaded_version,
                                    project.loaded_from), Path(path))
        return True

    def open_dialog(self):
        if not self._confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(
            self.owner, "Open editable project", str(default_projects_directory()),
            "ReportMaker projects (*.rmproj)")
        if path:
            self.open_from_path(path)

    def save_to_path(self, path):
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        if (self.report.customer_id is None and
                self.report.customer_snapshot.customer_name == "Customer (edit me)"):
            self._warn("Customer required", "Enter a customer name or select one from the database.")
            return False
        if (self.loaded_version != VERSION and self.loaded_from is not None
            and Path(path).absolute() == self.loaded_from.absolute()):
            self._warn("Save upgraded project as a copy",
                       "This report uses an older project format. "
                       "Choose Save As and a new filename to preserve your "
                       "original file for rollback.")
            return False
        try:
            saved = save_project(ReportProject(self.editor.report, self.assets,
                                               self.media_library, self.loaded_version,
                                               self.loaded_from), path)
        except (ValueError, OSError, RuntimeError) as exc:
            self._warn("Cannot save project", exc)
            return False
        self.path = saved
        self.loaded_version = VERSION
        self.loaded_from = saved.absolute()
        self.dirty = False
        self.refresh()
        return True

    def save(self):
        if self.path is None:
            return self.save_as()
        return self.save_to_path(self.path)

    def save_as(self):
        suggested = self.path or default_projects_directory() / "Untitled.rmproj"
        path, _ = QFileDialog.getSaveFileName(
            self.owner, "Save editable project", str(suggested),
            "ReportMaker projects (*.rmproj)")
        if not path:
            return False
        target = Path(path)
        if target.suffix.lower() != ".rmproj":
            target = target.with_suffix(".rmproj")
        # Save As is an intentional destination choice, but never silently
        # overwrite a different file if Qt's native file dialog didn't ask.
        if target.exists() and target != self.path:
            if QMessageBox.question(self.owner, "Overwrite project",
                                    "Replace the selected project file?") != QMessageBox.StandardButton.Yes:
                return False
        return self.save_to_path(target)

    def configure_export_branding(self):
        """Local export profile: company text and logo path never enter .rmproj."""
        settings = self.owner.settings
        dialog = QDialog(self.owner)
        dialog.setWindowTitle("Export branding — DOCX and PDF")
        form = QFormLayout(dialog)
        company = QLineEdit(str(settings.value("export/company_name", "")))
        company.setObjectName("exportBrandCompany")
        footer = QLineEdit(str(settings.value("export/footer_note", "")))
        footer.setObjectName("exportBrandFooter")
        logo = QLineEdit(str(settings.value("export/logo_path", "")))
        logo.setObjectName("exportBrandLogoPath")
        form.addRow("Company name", company)
        form.addRow("Footer text", footer)
        form.addRow("Local logo image", logo)
        buttons = QHBoxLayout()
        browse = QPushButton("Browse…")
        clear = QPushButton("Remove logo")
        def choose_logo():
            name, _ = QFileDialog.getOpenFileName(
                dialog, "Choose a local company logo", str(Path.home()),
                "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
            if name:
                logo.setText(name)
        browse.clicked.connect(choose_logo)
        clear.clicked.connect(lambda: logo.setText(""))
        buttons.addWidget(browse)
        buttons.addWidget(clear)
        form.addRow(buttons)
        actions = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        actions.accepted.connect(dialog.accept)
        actions.rejected.connect(dialog.reject)
        form.addRow(actions)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        try:
            # Validate all settings before persisting any of them.
            from .export import _validate_style
            selected = Path(logo.text()) if logo.text().strip() else None
            raw = b""
            if selected is not None:
                if not selected.is_file() or selected.stat().st_size > MAX_BRAND_LOGO_BYTES:
                    raise ExportError("Company logo missing or exceeds the 2 MiB limit")
                raw = selected.read_bytes()
            _validate_style(ExportStyle(company.text(), footer.text(), raw))
        except (OSError, ValueError) as exc:
            self._warn("Invalid export branding", exc)
            return False
        settings.setValue("export/company_name", company.text())
        settings.setValue("export/footer_note", footer.text())
        settings.setValue("export/logo_path", logo.text().strip())
        settings.sync()
        return True

    def import_document_template(self):
        # Always local: never send the DOCX/DOTX or any of its parts to a web view.
        filename, _ = QFileDialog.getOpenFileName(
            self.owner, "Import local Word page format", "",
            "Word documents and templates (*.docx *.dotx)")
        if not filename:
            return False
        try:
            result = import_word_template(filename)
        except (TemplateError, OSError, RuntimeError) as exc:
            self._warn("Cannot import Word template", exc)
            return False
        edited = edit_template_layout(self.owner, result.template, warnings=result.warnings)
        if edited is None:
            return False
        destination, _ = QFileDialog.getSaveFileName(
            self.owner, "Save portable page template", str(Path.home() / "ReportLayout.rmtemplate"),
            "ReportMaker templates (*.rmtemplate)")
        if not destination:
            return False
        target = Path(destination)
        if target.suffix.lower() != ".rmtemplate":
            target = target.with_suffix(".rmtemplate")
        if target.exists() and QMessageBox.question(
            self.owner, "Replace page template", "Replace the selected .rmtemplate?"
        ) != QMessageBox.StandardButton.Yes:
            return False
        try:
            save_template(edited, target)
        except (TemplateError, OSError, ValueError) as exc:
            self._warn("Cannot save page template", exc)
            return False
        self.owner.settings.setValue("export/page_template", str(target.resolve()))
        self.owner.settings.sync()
        if not self.page.pending:
            self.refresh()
        return True

    def edit_document_template(self):
        filename = str(self.owner.settings.value("export/page_template", "")).strip()
        if not filename:
            self._warn("No active page template", "Import a local Word page format first.")
            return False
        try:
            current = load_template(filename)
            edited = edit_template_layout(self.owner, current)
            if edited is None:
                return False
            save_template(edited, filename)
            if not self.page.pending:
                self.refresh()
        except (TemplateError, OSError, ValueError) as exc:
            self._warn("Cannot edit page template", exc)
            return False
        return True

    def clear_document_template(self):
        # A cleared selection never deletes the separately saved portable profile.
        self.owner.settings.remove("export/page_template")
        self.owner.settings.sync()
        if not self.page.pending:
            self.refresh()
        return True

    def _export_style(self):
        settings = self.owner.settings
        template_path = str(settings.value("export/page_template", "")).strip()
        if template_path:
            template = load_template(template_path)  # fail closed if missing/tampered
            return ExportStyle(
                template.header_text, template.footer_text, template.logo,
                template.page_width_cm, template.page_height_cm,
                template.left_margin_cm, template.right_margin_cm,
                template.top_margin_cm, template.bottom_margin_cm,
                template.header_distance_cm, template.footer_distance_cm,
                template.normal_font, template.normal_size_pt,
                template.heading_font, template.heading_size_pt)

        logo_path = str(settings.value("export/logo_path", "")).strip()
        raw = b""
        if logo_path:
            path = Path(logo_path)
            if not path.is_file() or path.stat().st_size > MAX_BRAND_LOGO_BYTES:
                raise ExportError("Configured company logo is missing or exceeds 2 MiB")
            raw = path.read_bytes()
        return ExportStyle(
            str(settings.value("export/company_name", "")),
            str(settings.value("export/footer_note", "")), raw)

    def export_to_path(self, path, format):
        """Export the current validated draft without saving/changing .rmproj."""
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return False
        if (self.report.customer_id is None and
                self.report.customer_snapshot.customer_name == "Customer (edit me)"):
            self._warn("Customer required", "Enter a customer before exporting.")
            return False
        try:
            export_project(ReportProject(self.report, dict(self.assets)), path,
                           format=format, style=self._export_style())
        except (ExportError, ValueError, OSError, RuntimeError) as exc:
            self._warn("Cannot export report", exc)
            return False
        self.refresh()
        return True

    def export_as(self, format):
        if format not in ("docx", "pdf"):
            raise ValueError("Unsupported export")
        ext = "." + format
        suggested = (self.path.with_suffix(ext) if self.path else
                     default_projects_directory() / ("Untitled" + ext))
        destination, _ = QFileDialog.getSaveFileName(
            self.owner, "Export " + format.upper(), str(suggested),
            "Word documents (*.docx)" if format == "docx" else "PDF documents (*.pdf)")
        if not destination:
            return False
        target = Path(destination)
        if target.suffix.lower() != ext:
            target = target.with_suffix(ext)
        if target.exists():
            if QMessageBox.question(
                    self.owner, "Replace exported file",
                    "Replace the selected exported document?"
            ) != QMessageBox.StandardButton.Yes:
                return False
        return self.export_to_path(target, format)

    def ok_to_close(self):
        return self._confirm_discard()

    def undo(self):
        # Preserve pending Report Information before any history navigation.
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return
        if self.editor.undo():
            self.dirty = True
            self.refresh()

    def redo(self):
        if not self._flush_block() or not self._flush_info() or not self._flush_page():
            return
        if self.editor.redo():
            self.dirty = True
            self.refresh()

    def paste_clipboard(self):
        # Explicit manual plain-text transfer only; never inspect browser DOM.
        if not self.text_edit.isVisible():
            self.add_paragraph()
        text = QApplication.clipboard().text()
        if text:
            self.text_edit.insertPlainText(text)
