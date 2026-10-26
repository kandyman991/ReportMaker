# ADR-0005 — GitHub-backed human and automatic continuity
Status: Accepted for continuity bootstrap | Date: 2026-10-26

## Decision
Use `CHAT_HANDOFF.md`, `docs/CHECKPOINTS.md`, `docs/ARCHITECTURE_MEMORY.md` and prior ADRs as curated architecture/milestone truth. Run a hosted GitHub Actions workflow on pushes to `main` and manual dispatch to snapshot current default-branch SHA, latest commit, open PRs/issues and recent workflow runs in `handoff/state.json`.

Always re-check live GitHub refs/CI before relying on a snapshot. Update curated files at milestones and chat handoffs. Add simple CI gates that the continuity documents and approved wording exist, and reject repository Actions artifact uploads.

## Why not just ChatGPT conversation context?
Chats can be separated, truncated or misleading about branch status. GitHub records are inspectable across chats. Auto-generated state cannot document user decisions; curated records cannot keep job statuses current.

## Safety
No self-hosted runners, no customer/CAD/report screenshots, credential copying, package downloads or artifact storage. Only repository metadata goes into the PUBLIC state JSON (public PR titles/issues may already be public). Use minimal GitHub permissions. Do not merge unrelated M0 PRs as part of continuity.

## Alternatives
Manual-only handoff: rejected for stale CI/branch status. Auto-generated architecture decisions: rejected as ungrounded. Triggering on PR branches: rejected to avoid writes by untrusted contributions.

## Acceptance
Workflow exists on main and produces parseable state.json; contract CI passes; new chat can recover M0 exact PR topology and explicit M1 entry requirements. Workflow refresh itself is not a green light to merge PRs.
