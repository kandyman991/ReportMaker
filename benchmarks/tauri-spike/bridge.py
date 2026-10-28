"""Synthetic ReportMaker canonical commands over JSONL stdin/stdout.

A prototype contract test: no TCP listener, file IO, private report, or browser
automation. A packaged Tauri sidecar would need an audited executable wrapper.
"""
from __future__ import annotations
import json
import sys

from fixtures import project
from reportmaker.v2.commands import CommandGateway, CommandIntent
from reportmaker.v2.projections import NodeAddress, project_branch
from reportmaker.v2.session import ReportSession

class Bridge:
    def __init__(self):
        self.session = ReportSession(project(82))
        self.gateway = CommandGateway(self.session)

    def address(self, stable_id):
        report = self.session.report_snapshot()
        row = next((r for r in project_branch(report) if r.stable_id == stable_id), None)
        if row is None:
            raise ValueError("Node does not exist")
        if row.kind in ("module", "root", "conclusion"):
            return NodeAddress(report.id, stable_id)
        return NodeAddress(report.id, row.parent_module_id, stable_id, "text")

    def present(self):
        report = self.session.report_snapshot()
        return [{
            "id":r.stable_id,"kind":r.kind,"parentId":r.parent_module_id,
            "depth":r.depth,"text":r.text,
            "title":r.kind.upper().replace("-", " ")
        } for r in project_branch(report, revision=self.session.revision)]

    def execute(self, request):
        action = request.get("action")
        if action == "hello":
            report = self.session.report_snapshot()
            return {
                "revision":self.session.revision,"generation":self.session.generation,
                "reportId":report.id,"firstModule":report.modules[0].id,
                "secondModule":report.modules[1].id,
                "nodes":len(project_branch(report)), "rows":self.present()
            }
        if action == "snapshot":
            return {"revision":self.session.revision,"generation":self.session.generation,
                    "rows":self.present()}
        if action == "rename":
            target = self.address(request["target"])
            change = self.gateway.execute(CommandIntent(
                "rename_module", target, {"title": request["text"]},
                request["expectedRevision"], request["generation"]))
        elif action == "move":
            target = self.address(request["source"])
            anchor = self.address(request["target"])
            change = self.gateway.execute(CommandIntent(
                "move_node", target, {"anchor":anchor,"position":request["position"]},
                request["expectedRevision"], request["generation"]))
        elif action == "undo":
            change = self.gateway.undo(request["generation"],request["expectedRevision"])
        elif action == "redo":
            change = self.gateway.redo(request["generation"],request["expectedRevision"])
        else:
            raise ValueError("Unsupported action")
        return {"revision":self.session.revision,"changed":change is not None,
                "firstModule":self.session.report_snapshot().modules[0].id}

def main():
    bridge = Bridge()
    for raw in sys.stdin:
        try:
            request = json.loads(raw)
            if not isinstance(request,dict):
                raise ValueError("Command must be an object")
            result = {"id":request.get("id"),"ok":True,"result":bridge.execute(request)}
        except (KeyError, TypeError, ValueError, LookupError, RuntimeError) as exc:
            result = {"id":request.get("id") if isinstance(request,dict) else None,
                      "ok":False,"error":str(exc)}
        sys.stdout.write(json.dumps(result,ensure_ascii=False)+"\n")
        sys.stdout.flush()

if __name__ == "__main__":
    main()
