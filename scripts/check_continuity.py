"""Fast, offline, synthetic-only continuity contract checks for ReportMaker."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
required = [
    "AGENTS.md", "ARCHITECTURE.md", "ROADMAP.md", "CHAT_HANDOFF.md",
    "docs/CHECKPOINTS.md", "docs/CONTINUITY.md",
    "docs/ARCHITECTURE_MEMORY.md", "docs/adr/0005-github-continuity.md",
    ".github/workflows/update-chat-handoff-state.yml",
]
for path in required:
    assert (ROOT / path).is_file(), f"Missing continuity file: {path}"
read = lambda p: (ROOT / p).read_text(encoding="utf-8")
agents = read("AGENTS.md")
handoff = read("CHAT_HANDOFF.md")
checkpoints = read("docs/CHECKPOINTS.md")
workflow = read(".github/workflows/update-chat-handoff-state.yml")
assert "handoff/state.json" in agents and "CHAT_HANDOFF.md" in agents
for marker in ("PR #1", "PR #3", "M1 entry", "CAD", "github.com/kandyman991/ReportMaker"):
    assert marker in handoff, f"Handoff omits {marker}"
for marker in ("CP-M0", "CP-M1", "Next", "Not yet"):
    assert marker.lower() in checkpoints.lower(), f"Checkpoints omit {marker}"
assert "github.actor != 'github-actions[bot]'" in workflow
assert "github-script@" in workflow and "workflow_dispatch:" in workflow
assert "branches: [main]" in workflow
assert "handoff/state.json" in workflow
assert "contents: write" in workflow
assert "runs-on: ubuntu-latest" in workflow
assert "actions/upload-artifact" not in workflow
assert "self-hosted" not in workflow
print("ReportMaker curated handoff, GitHub state refresh and privacy contract OK")
