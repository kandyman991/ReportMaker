# GitHub Actions superseded-run cancellation

Status: proposed on an isolated PR. No automatic merge or release is authorized.

## Scope

Workflow-level concurrency is enabled for the three **read-only validation** workflows:

- `.github/workflows/ci.yml` — M0 architecture, editor and model checks
- `.github/workflows/m1-customer-ui.yml` — M1 Windows customer UI checks
- `.github/workflows/continuity-contract.yml` — curated handoff contract checks

Group key (identical policy in each workflow):

```yaml
concurrency:
  group: ${{ github.workflow }}-${{ github.event_name }}-${{ github.event_name == 'workflow_dispatch' && github.run_id || github.event.pull_request.number || github.ref }}
  cancel-in-progress: ${{ github.event_name != 'workflow_dispatch' }}
```

This uses supported GitHub Actions contexts and expressions. The workflow name
separates M0, M1 and continuity checks; the event name separates push, PR and
manual checks; a PR number separates independent PRs; a pushed ref separates
branches. The newest matching validation cancels the older running or pending
validation only **within the same group**.

A manual `workflow_dispatch` uses its own `github.run_id`, and cancellation
is disabled for manual dispatch. User-requested test runs are never superseded
by another run under this policy.

| Events | Result |
| --- | --- |
| PR #25 updated twice during development | Earlier #25 run of the *same* workflow is cancelled, latest runs |
| PR #25 and PR #26, even if stacked | Neither cancels the other |
| Two pushes to one branch | Latest push supersedes previous push of the same workflow |
| Push and PR checks originating from the same branch | Kept separate to preserve required PR validation |
| M0 and M1 jobs on the same PR | Kept separate to preserve both test families |
| Two manually triggered runs | Both retained under independent run IDs |

## Intentional exclusions

The `windows-installer.yml` workflow publishes a rolling Windows release and
already serializes with `reportmaker-windows-rolling-release`. The
`update-chat-handoff-state.yml` workflow writes a shared `handoff/state.json`
file and already serializes under `reportmaker-chat-handoff-state`. Neither
workflow is modified by this change: cancelling/overlapping a publisher or
shared-state writer requires a separate safety review.

## Verification and limitations

`tests/test_workflow_concurrency.py` checks that all three validators retain
their triggers, have workflow-scoped groups, isolate manual runs and leave the
two writer/publisher groups intact. All application and Windows GUI checks
remain unchanged. Confirm exact-head GitHub-hosted Windows CI before merging;
an installed Windows PC test is not needed for this CI-only change.

GitHub still displays historical failed and cancelled runs: this reduces future
redundant work, but does not erase old failures. GitHub concurrency controls
execution/queueing, not which historic entries GitHub keeps. PR and push runs
are deliberately separate, so a commit can still cause more than one type of
validation. No secrets, photos, customer reports, installer assets or external
runtime services are involved.
