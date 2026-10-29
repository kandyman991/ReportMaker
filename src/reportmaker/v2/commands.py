"""Typed V2 command gateway around the existing, transactional ProjectEditor.

No view widget receives ProjectEditor or its mutable Report. Each successful
intent is one logical undo step; stale/malformed intents never reach apply().
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Mapping
from uuid import uuid4

from ..model import (HeadingBlock, LocalizedText, Module, PageBreakBlock,
                     ParagraphBlock, PhotoBlock, PhotoVisual, TableBlock,
                     validate_photo_visual)
from ..media_import import ImportedPicture, StagedPicture, commit_staged_pictures
from ..engine import validate_report_tree
from ..project_io import ASSET_ID
from ..rich_text import RichFormatting, validate_rich
from .adapters.tables import checked_rows
from .projections import NodeAddress, find_node
from .session import ReportSession, StaleIntentError
from .structure import plan_drop, structural_node


@dataclass(frozen=True)
class CommandIntent:
    kind: str
    target: NodeAddress | None
    args: Mapping[str, object]
    expected_revision: int
    project_generation: str


@dataclass(frozen=True)
class ChangeSet:
    revision: int
    changed_ids: frozenset[str]
    structure_changed: bool = False
    assets_changed: bool = False
    outline_invalidated: bool = False


_KINDS = {
    "add_module": ({"title"}, {"index"}),
    "add_nested_module": ({"title"}, {"index"}),
    "add_paragraph": ({"text"}, {"index"}),
    "add_heading": ({"text", "level"}, {"index"}),
    "add_table": (set(), {"index"}),
    "add_page_break": (set(), {"index"}),
    "add_photo": ({"asset_id"}, {"index"}),
    "import_photo": ({"image_bytes", "name"}, {"index"}),
    "import_photos": ({"photos"}, {"index"}),
    "import_library_photos": ({"photos"}, set()),
    "set_translation": ({"language", "key", "text"}, set()),
    "set_metadata_translation": (
        {"language", "key", "text", "expected_source_sha256"}, set()),
    "set_fields_batch": ({"edits"}, set()),
    "set_report_metadata": ({"title", "created_date", "start_date", "end_date",
                             "ticket", "technicians", "intervention_types",
                             "other_intervention_detail", "customer_snapshot",
                             "primary_language", "output_languages"}, {"customer_id", "relabel_source_language"}),
    "replace_photo_import": ({"image_bytes", "name"}, set()),
    "replace_photo": ({"asset_id"}, set()),
    "set_photo_caption": ({"text"}, set()),
    "set_photo_visual": ({"visual"}, set()),
    "set_table_rows": ({"rows"}, set()),
    "rename_module": ({"title"}, set()),
    "set_paragraph": ({"text"}, set()),
    "set_paragraph_rich": ({"text", "rich"}, set()),
    "set_heading_rich": ({"text", "rich"}, set()),
    "move_node": ({"anchor", "position"}, set()),
    "duplicate_node": (set(), set()),
    "delete_node": (set(), set()),
}


def _apply_report_metadata(report, args):
    """Validate by replaying the exact same one-report transaction."""
    snapshot = args["customer_snapshot"]
    # A selected database reference and its report key are one atomic pair.
    # Legacy clients may omit customer_id, but may never override the snapshot.
    customer_id = snapshot.customer_id if snapshot is not None else None
    if "customer_id" in args and args["customer_id"] != customer_id:
        raise ValueError("Customer ID does not match detached reference")
    # The primary language labels existing source text. A language change
    # therefore requires explicit user confirmation and a safe provenance
    # migration, never a metadata-only relabel with mismatched field tags.
    new_language = args["primary_language"]
    from ..model import validate_language_tag
    validate_language_tag(new_language)
    if new_language.casefold() != report.primary_language.casefold():
        from .localized_export import localized_fields
        if args.get("relabel_source_language") is not True:
            raise ValueError("Changing source language requires explicit confirmation that existing original text is already in that language")
        fields = list(localized_fields(report))
        for _key, value in fields:
            if value.original_language.casefold() != report.primary_language.casefold():
                raise ValueError("Mixed source languages need a separate migration")
            if any(code.casefold() == new_language.casefold() for code in value.translations):
                raise ValueError("A translation already exists for the requested source language; preserve it before migrating")
        # Metadata translations must not become new canonical source text
        # after a language relabel. Reject rather than silently discard them.
        for code in report.localization_ledger.get(
                "metadata.other_intervention_detail", {}):
            if code.casefold() == new_language.casefold():
                raise ValueError("Existing metadata translation conflicts with new source language")
        for _key, value in fields:
            value.original_language = new_language
            value.stale_languages.update(value.translations)
    elif "relabel_source_language" in args and args["relabel_source_language"] is not False:
        raise ValueError("Relabel confirmation is only valid for a source-language change")
    report.customer_id = customer_id
    report.title.update_original(args["title"])
    for field in ("created_date", "start_date", "end_date", "ticket",
                  "technicians", "intervention_types", "other_intervention_detail",
                  "customer_snapshot", "primary_language", "output_languages"):
        setattr(report, field, deepcopy(args[field]))


class CommandGateway:
    def __init__(self, session: ReportSession) -> None:
        self._session = session

    def _check_generation(self, generation: str) -> None:
        if generation != self._session.generation:
            raise StaleIntentError("Action belongs to a previous report session")

    def validate(self, intent: CommandIntent) -> None:
        if not isinstance(intent, CommandIntent) or intent.kind not in _KINDS:
            raise ValueError("Unsupported V2 command")
        self._check_generation(intent.project_generation)
        if type(intent.expected_revision) is not int or intent.expected_revision != self._session.revision:
            raise StaleIntentError("Action was based on an outdated report revision")
        if not isinstance(intent.args, Mapping):
            raise ValueError("Command arguments must be a mapping")
        required, optional = _KINDS[intent.kind]
        if set(intent.args) - required - optional or not required <= set(intent.args):
            raise ValueError("Unsupported command arguments")
        if intent.kind == "set_fields_batch":
            edits = intent.args["edits"]
            allowed = {"rename_module", "set_paragraph_rich", "set_heading_rich",
                       "set_photo_caption", "set_table_rows"}
            if (not isinstance(edits, (list, tuple)) or not 1 <= len(edits) <= 256
                    or any(not isinstance(edit, CommandIntent) or edit.kind not in allowed
                           for edit in edits)):
                raise ValueError("Editor batch requires 1–256 validated field intents")
            addresses = [edit.target for edit in edits]
            if any(not isinstance(address, NodeAddress) for address in addresses):
                raise ValueError("Invalid document editor field address")
            if len(set(addresses)) != len(addresses):
                raise ValueError("Duplicate field in document editor batch")
            for edit in edits:
                if (edit.expected_revision != intent.expected_revision or
                        edit.project_generation != intent.project_generation):
                    raise StaleIntentError("Batch field is based on a different revision")
                self.validate(edit)
            return
        if intent.kind == "move_node":
            plan_drop(self._session.report_snapshot(), intent.target,
                      intent.args["anchor"], intent.args["position"])
            return
        if intent.kind in ("duplicate_node", "delete_node"):
            structural_node(self._session.report_snapshot(), intent.target)
            return
        if intent.kind == "set_table_rows":
            report = self._session.report_snapshot()
            addr = intent.target
            if (not isinstance(addr, NodeAddress) or addr.report_id != report.id
                    or addr.block_id is None or addr.field != "table"
                    or addr.row is not None or addr.column is not None
                    or not isinstance(find_node(report, addr), TableBlock)):
                raise ValueError("Table edit requires an owning table address")
            checked_rows(intent.args["rows"])
            return
        if intent.kind in ("add_photo", "replace_photo"):
            asset_id = intent.args["asset_id"]
            if (not isinstance(asset_id, str) or ASSET_ID.fullmatch(asset_id) is None
                    or asset_id not in self._session.assets):
                raise ValueError("Photo must reference an existing project-owned asset")
        if intent.kind in ("import_photo", "replace_photo_import"):
            if (not isinstance(intent.args["image_bytes"], bytes)
                    or not isinstance(intent.args["name"], str)):
                raise ValueError("Import requires detached image bytes and a label")
        if intent.kind in ("import_photos", "import_library_photos"):
            from ..media_import import MAX_IMPORT_BATCH
            photos = intent.args["photos"]
            if (not isinstance(photos, (list, tuple))
                    or not 1 <= len(photos) <= MAX_IMPORT_BATCH
                    or any(not isinstance(photo, tuple) or len(photo) != 2
                           or not isinstance(photo[0], str)
                           or not isinstance(photo[1], bytes) for photo in photos)):
                raise ValueError("Import batch must contain validated (name, bytes) pairs")
        if intent.kind == "import_library_photos":
            if intent.target is not None:
                raise ValueError("Library import cannot carry a report placement")
            return
        if intent.kind == "set_translation":
            from .localized_export import localized_fields
            from ..model import validate_language_tag
            language, key, text = (intent.args[name]
                                   for name in ("language", "key", "text"))
            validate_language_tag(language)
            report = self._session.report_snapshot()
            if not any(code.casefold() == language.casefold()
                       for code in report.output_languages):
                raise ValueError("Select the translation language in Report Information first")
            if not isinstance(key, tuple) or not isinstance(text, str):
                raise ValueError("Translation requires a stable field key and plain text")
            matches = [value for candidate_key, value in localized_fields(report)
                       if candidate_key == key]
            if len(matches) != 1:
                raise LookupError("Translation field no longer belongs to this report")
            if matches[0].original_language.casefold() == language.casefold():
                raise ValueError("Cannot overwrite original-language content")
            if len(text) > 100000:
                raise ValueError("Translation exceeds the safe text size")
            if matches[0].original.strip() and not text.strip():
                raise ValueError("Nonempty original content needs a nonblank translation")
            return
        if intent.kind == "set_metadata_translation":
            from .metadata_locale import MetadataLocale, PERSISTABLE_KEYS, source_digest
            from ..model import validate_language_tag
            if intent.target is not None:
                raise ValueError("Metadata translation must target the whole report")
            key, language, text, expected = (intent.args[name] for name in
                ("key", "language", "text", "expected_source_sha256"))
            if not isinstance(key, str) or key not in PERSISTABLE_KEYS:
                raise ValueError("Unknown or transient metadata translation key")
            validate_language_tag(language)
            report = self._session.report_snapshot()
            if not any(code.casefold() == language.casefold()
                       for code in report.output_languages):
                raise ValueError("Select metadata output language in Report Information")
            resolver = MetadataLocale(report)
            original, source_language = resolver.source(key)
            if expected != source_digest(key, source_language, original):
                raise StaleIntentError("Metadata source changed since translation draft")
            resolver.approve(key, language, text)
            return
        if intent.kind == "set_report_metadata":
            if intent.target is not None:
                raise ValueError("Report information must target the whole report")
            candidate = self._session.report_snapshot()
            _apply_report_metadata(candidate, intent.args)
            validate_report_tree(candidate)
            return
        if intent.kind == "set_photo_visual":
            validate_photo_visual(intent.args["visual"])
        value_key = "text" if intent.kind in ("add_paragraph", "add_heading", "set_paragraph", "set_paragraph_rich", "set_heading_rich", "set_photo_caption") else "title"
        if intent.kind not in ("add_table", "add_page_break", "add_photo", "replace_photo", "import_photo", "import_photos", "replace_photo_import", "set_photo_visual") and not isinstance(intent.args[value_key], str):
            raise ValueError("Title and text must be strings")
        if intent.kind == "add_heading" and (type(intent.args["level"]) is not int
                                             or not 1 <= intent.args["level"] <= 6):
            raise ValueError("Heading level must be 1..6")
        if intent.kind in ("set_paragraph_rich", "set_heading_rich"):
            if not isinstance(intent.args["rich"], RichFormatting):
                raise ValueError("An explicit rich formatting value is required")
            validate_rich(intent.args["rich"], intent.args["text"])
        if "index" in intent.args and (type(intent.args["index"]) is not int or intent.args["index"] < 0):
            raise ValueError("Mixed insertion index must be a non-negative integer")
        report = self._session.report_snapshot()
        if intent.kind == "add_module":
            if intent.target is not None:
                raise ValueError("Top-level module insertion has no target")
            size = len(report.modules)
        else:
            addr = intent.target
            if not isinstance(addr, NodeAddress) or addr.report_id != report.id:
                raise ValueError("Action must address the active report")
            if intent.kind in ("set_photo_caption", "set_photo_visual",
                               "replace_photo", "replace_photo_import"):
                if (addr.block_id is None or addr.field != "photo"
                        or addr.row is not None or addr.column is not None
                        or not isinstance(find_node(report, addr), PhotoBlock)):
                    raise ValueError("Photo edit requires a stable photo block address")
            elif intent.kind in ("set_paragraph", "set_paragraph_rich", "set_heading_rich"):
                if addr.field != "text" or addr.block_id is None:
                    raise ValueError("Text edit requires a block text address")
                block = find_node(report, addr)
                expected = HeadingBlock if intent.kind == "set_heading_rich" else ParagraphBlock
                if not isinstance(block, expected):
                    raise ValueError("Wrong block kind for text edit")
            else:
                if addr.block_id is not None or addr.field != "title":
                    raise ValueError("Command requires a module address")
                module = find_node(report, addr)
                if not isinstance(module, Module):
                    raise ValueError("Target is not a module")
                if intent.kind == "add_nested_module" and module.id == report.conclusion.id:
                    raise ValueError("Conclusions cannot have intervention submodules")
                size = len(module.blocks)
        if intent.kind in ("add_module", "add_nested_module", "add_paragraph", "add_heading", "add_table", "add_page_break", "add_photo", "import_photo", "import_photos"):
            if "index" in intent.args and intent.args["index"] > size:
                raise ValueError("Mixed insertion index exceeds parent length")

    def execute(self, intent: CommandIntent) -> ChangeSet | None:
        self.validate(intent)
        self._session.require_clean_drafts()
        # Freeze inputs before mutating the canonical data; arbitrary UI-provided
        # callables/fields never enter the transaction.
        kind, args, address = intent.kind, dict(intent.args), intent.target
        editor = self._session._editor
        if kind == "set_fields_batch":
            edits = args["edits"]
            def apply_batch(report):
                for field in edits:
                    node = find_node(report, field.target)
                    payload = field.args
                    if field.kind == "rename_module":
                        node.title.update_original(payload["title"])
                    elif field.kind in ("set_paragraph_rich", "set_heading_rich"):
                        node.text.update_original(payload["text"])
                        node.rich = deepcopy(payload["rich"])
                        validate_rich(node.rich, node.text.original)
                    elif field.kind == "set_photo_caption":
                        if node.caption is None:
                            node.caption = LocalizedText(report.primary_language, payload["text"])
                        else:
                            node.caption.update_original(payload["text"])
                    elif field.kind == "set_table_rows":
                        node.rows = checked_rows(payload["rows"])
            # One validated report transaction, one history entry; no prefix
            # of successful field writes can leak out on a later failure.
            editor.apply(apply_batch)
            ids = frozenset(
                field.target.block_id or field.target.module_id for field in edits)
            renamed = any(field.kind == "rename_module" for field in edits)
            change = ChangeSet(self._session.revision + 1, ids, False, False, renamed)
            self._session._publish(change)
            return change
        if kind == "set_translation":
            from .localized_export import localized_fields
            from ..model import validate_language_tag
            language = args["language"]
            key = args["key"]
            text = args["text"]
            report = self._session.report_snapshot()
            target = next(value for field_key, value in localized_fields(report)
                          if field_key == key)
            existing = next((code for code in target.translations
                             if code.casefold() == language.casefold()), language)
            if (target.translations.get(existing) == text
                    and existing not in target.stale_languages):
                return None
            def apply_translation(report):
                candidate = next(value for field_key, value in localized_fields(report)
                                 if field_key == key)
                candidate.set_translation(existing, text)
            editor.apply(apply_translation)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({str(key[0])}), False, False, True)
            self._session._publish(change)
            return change
        if kind == "set_metadata_translation":
            from .metadata_locale import MetadataLocale
            key, language, text = (args[name] for name in ("key", "language", "text"))
            candidate = self._session.report_snapshot()
            approved = MetadataLocale(candidate).approve(key, language, text)
            current = candidate.localization_ledger.get(key, {})
            code = next((tag for tag in current if tag.casefold() == language.casefold()),
                        language)
            record = {"text": approved.text, "source_sha256": approved.source_sha256}
            if current.get(code) == record:
                return None
            def set_approved_metadata(report):
                report.localization_ledger.setdefault(key, {})[code] = record
            editor.apply(set_approved_metadata)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({editor.report.id}), False, False, True)
            self._session._publish(change)
            return change
        if kind == "set_report_metadata":
            candidate = deepcopy(editor.report)
            _apply_report_metadata(candidate, args)
            if candidate == editor.report:
                return None
            editor.apply(lambda report: _apply_report_metadata(report, args))
            change = ChangeSet(self._session.revision + 1,
                               frozenset({editor.report.id}), False, False, True)
            self._session._publish(change)
            return change
        if kind == "move_node":
            plan = plan_drop(editor.report, address, args["anchor"], args["position"])
            if plan.noop:
                return None  # Preserve redo, revision and listeners on a no-op.
            if plan.source_kind == "module":
                editor.move_module(plan.source_id, parent_id=plan.destination_parent_id,
                                   index=plan.destination_index)
            else:
                if plan.source_parent_id is None or plan.destination_parent_id is None:
                    raise ValueError("Content needs an owning module")
                editor.move_block(plan.source_parent_id, plan.source_id,
                                  plan.destination_parent_id,
                                  index=plan.destination_index)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({plan.source_id}), True, False, True)
            self._session._publish(change)
            return change
        if kind in ("duplicate_node", "delete_node"):
            node = structural_node(editor.report, address)
            if kind == "delete_node":
                if node.kind == "module":
                    editor.remove_module(node.stable_id)
                else:
                    editor.remove_block(node.parent_module_id, node.stable_id)
                changed_id = node.stable_id
            elif node.kind == "module":
                changed_id = editor.duplicate_module(node.stable_id)
            else:
                changed_id = uuid4().hex

                def duplicate_block(report):
                    owner = find_node(report, NodeAddress(report.id, node.parent_module_id))
                    at = next(i for i, block in enumerate(owner.blocks)
                              if block.id == node.stable_id)
                    copy = deepcopy(owner.blocks[at])
                    copy.id = changed_id
                    owner.blocks.insert(at + 1, copy)

                editor.apply(duplicate_block)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({changed_id}), True, False, True)
            self._session._publish(change)
            return change
        # An unchanged inline commit must not add a history step, invalidate
        # queued edits, or erase the redo stack after an Undo.
        if kind == "rename_module" and find_node(editor.report, address).title.original == args["title"]:
            return None
        if kind == "set_table_rows":
            current = find_node(editor.report, address)
            rows = checked_rows(args["rows"])
            if current.rows == rows:
                return None
            def edit_table(report):
                find_node(report, address).rows = rows
            editor.apply(edit_table)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({address.block_id}))
            self._session._publish(change)
            return change
        if kind in ("import_photo", "import_photos", "import_library_photos", "replace_photo_import"):
            from ..project_io import ReportProject, _assets_checked
            staged = ReportProject(deepcopy(editor.report),
                                   dict(self._session.assets), dict(self._session.media_library))
            photos = (args["photos"] if kind in ("import_photos", "import_library_photos")
                      else [(args["name"], args["image_bytes"])])
            imports = [
                StagedPicture(name, ImportedPicture(
                    blob, "approved", 1, 1, 1, 1, len(blob)))
                for name, blob in photos
            ]
            asset_ids = commit_staged_pictures(staged, imports)
            new_blocks = [
                PhotoBlock(asset_id, LocalizedText(editor.report.primary_language, ""))
                for asset_id in asset_ids
            ]
            if kind == "import_library_photos":
                def edit(report):
                    # A single canonical editor history step keeps asset-only
                    # transactions aligned with session media undo/redo.
                    return None
                changed_ids = frozenset(asset_ids)
                structure = False
            elif kind in ("import_photo", "import_photos"):
                def edit(report):
                    module = find_node(report, address)
                    at = args.get("index", len(module.blocks))
                    for offset, block in enumerate(new_blocks):
                        module.blocks.insert(at + offset, deepcopy(block))
                changed_ids = frozenset(block.id for block in new_blocks)
                structure = True
            else:
                def edit(report):
                    block = find_node(report, address)
                    block.asset_id = new_blocks[0].asset_id
                    block.visual = PhotoVisual()
                changed_ids = frozenset({address.block_id})
                structure = False
            # Validate prospective report and owned media before touching live
            # editor, undo history or session; a bad batch commits NOTHING.
            preview = deepcopy(editor.report)
            edit(preview)
            _assets_checked(ReportProject(preview, staged.assets, staged.media_library))
            editor.apply(edit)
            self._session._assets = staged.assets
            self._session._library = staged.media_library
            change = ChangeSet(self._session.revision + 1, changed_ids,
                               structure, True, structure)
            self._session._publish(change)
            return change
        if kind in ("set_photo_caption", "set_photo_visual", "replace_photo"):
            current = find_node(editor.report, address)
            if kind == "set_photo_caption" and current.caption is not None and current.caption.original == args["text"]:
                return None
            if kind == "set_photo_visual" and current.visual == args["visual"]:
                return None
            if (kind == "replace_photo" and current.asset_id == args["asset_id"]
                    and current.visual == PhotoVisual()):
                return None
            def edit_photo(report):
                block = find_node(report, address)
                if kind == "set_photo_caption":
                    if block.caption is None:
                        block.caption = LocalizedText(report.primary_language, args["text"])
                    else:
                        block.caption.update_original(args["text"])
                elif kind == "set_photo_visual":
                    block.visual = deepcopy(args["visual"])
                else:
                    block.asset_id = args["asset_id"]
                    block.visual = PhotoVisual()
            editor.apply(edit_photo)
            change = ChangeSet(self._session.revision + 1,
                               frozenset({address.block_id}),
                               False, kind == "replace_photo")
            self._session._publish(change)
            return change
        if kind == "set_paragraph":
            current = find_node(editor.report, address)
            if current.text.original == args["text"]:
                return None
            # The legacy plain-text command has no formatting remap data.
            # Reject edits to formatted sources even when the new text has
            # the same length: otherwise old offsets can style wrong letters.
            # Inline editors must use the atomic set_paragraph_rich command.
            if current.rich.runs or current.rich.paragraphs:
                raise ValueError("Formatted paragraphs require set_paragraph_rich")
        if kind in ("set_paragraph_rich", "set_heading_rich"):
            current = find_node(editor.report, address)
            if current.text.original == args["text"] and current.rich == args["rich"]:
                return None
        language = editor.report.primary_language
        changed_id: str
        structure = kind in ("add_module", "add_nested_module", "add_paragraph", "add_heading", "add_table", "add_page_break", "add_photo")
        if kind in ("add_module", "add_nested_module"):
            module = Module(LocalizedText(language, args["title"]))
            if kind == "add_module":
                editor.add_module(module, index=args.get("index"))
            else:
                editor.add_module(module, parent_id=address.module_id, index=args.get("index"))
            changed_id = module.id
        elif kind == "add_paragraph":
            paragraph = ParagraphBlock(LocalizedText(language, args["text"]))
            editor.add_block(address.module_id, paragraph, index=args.get("index"))
            changed_id = paragraph.id
        elif kind == "add_page_break":
            page_break = PageBreakBlock()
            editor.add_block(address.module_id, page_break, index=args.get("index"))
            changed_id = page_break.id
        elif kind == "add_photo":
            # Reference existing validated project-owned media; never construct
            # fake assets or import arbitrary local paths from a command.
            photo = PhotoBlock(args["asset_id"], LocalizedText(language, ""))
            editor.add_block(address.module_id, photo, index=args.get("index"))
            changed_id = photo.id
        elif kind == "add_table":
            table = TableBlock([[LocalizedText(language, "") for _ in range(2)]
                                for _ in range(2)])
            editor.add_block(address.module_id, table, index=args.get("index"))
            changed_id = table.id
        elif kind == "add_heading":
            heading = HeadingBlock(LocalizedText(language, args["text"]), level=args["level"])
            editor.add_block(address.module_id, heading, index=args.get("index"))
            changed_id = heading.id
        elif kind == "rename_module":
            editor.rename_module(address.module_id, args["title"])
            changed_id = address.module_id
        elif kind in ("set_paragraph_rich", "set_heading_rich"):
            # Native text widgets supply a detached rich record; one transaction
            # updates wording, provenance, and offsets without a shadow model.
            rich = deepcopy(args["rich"])
            def edit(report):
                block = find_node(report, address)
                block.text.update_original(args["text"])
                block.rich = rich
                validate_rich(block.rich, block.text.original)
            editor.apply(edit)
            changed_id = address.block_id
        elif kind == "set_paragraph":
            def edit(report):
                paragraph = find_node(report, address)
                # Never silently discard existing rich typography. The M1.3
                # text adapter will supply a coherent text+rich transaction.
                paragraph.text.update_original(args["text"])
                validate_rich(paragraph.rich, paragraph.text.original)
            editor.apply(edit)
            changed_id = address.block_id
        else:
            raise ValueError("Unsupported V2 command")
        change = ChangeSet(
            self._session.revision + 1, frozenset({changed_id}), structure,
            False, structure or kind == "rename_module",
        )
        self._session._publish(change)
        return change

    def undo(self, expected_generation: str, expected_revision: int) -> ChangeSet | None:
        self._check_generation(expected_generation)
        if type(expected_revision) is not int or expected_revision != self._session.revision:
            raise StaleIntentError("Undo was based on an outdated report revision")
        self._session.require_clean_drafts()
        if not self._session._editor.undo():
            return None
        change = ChangeSet(self._session.revision + 1,
                           frozenset({self._session._editor.report.id}),
                           True, False, True)
        self._session._publish(change, history="undo")
        return change

    def redo(self, expected_generation: str, expected_revision: int) -> ChangeSet | None:
        self._check_generation(expected_generation)
        if type(expected_revision) is not int or expected_revision != self._session.revision:
            raise StaleIntentError("Redo was based on an outdated report revision")
        self._session.require_clean_drafts()
        if not self._session._editor.redo():
            return None
        change = ChangeSet(self._session.revision + 1,
                           frozenset({self._session._editor.report.id}),
                           True, False, True)
        self._session._publish(change, history="redo")
        return change
