# GitHub-backed continuity — operating procedure

Two different records are intentionally maintained:
- `CHAT_HANDOFF.md`, `docs/CHECKPOINTS.md`, `ARCHITECTURE.md`, ADRs: human-curated decisions, evidence and constraints. They require a reviewable PR.
- `handoff/state.json`: **automatic mechanical snapshot** of main, open PRs/issues and recent Actions status. It can lag events; inspect live GitHub before acting.

On `main` pushes or manual dispatch, `.github/workflows/update-chat-handoff-state.yml` runs on **GitHub-hosted** Ubuntu and updates `handoff/state.json` via `github-script`, using only the repository-scoped `GITHUB_TOKEN`. Bot pushes do not recursively trigger it. The workflow has read access to PRs, issues and runs and write access only to repository contents; no stored credentials and no artifact uploads.

Before working in a new chat: read project contracts, curated handoff, checkpoints, latest generated state and current PR/release CI. If state.json is absent on a feature branch, read it from main. A merged PR may change exact SHA; never rely on historical pointers alone.

At the end of a development or review chat, propose updates to handoff/checkpoints (exact commit/branch, CI, status, privacy, unresolved issues, next step). Critical requirements require ADR and regression gates. Automatic JSON refresh **does not replace** a curated checkpoint or security review.

If the state refresh fails due to permissions or a branch race, keep human-authored records unchanged, inspect the failed Actions run, then repair/re-dispatch; do not manufacture a successful snapshot.
