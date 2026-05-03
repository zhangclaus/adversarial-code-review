# V4 Accept Readiness and Worker Safety Design

Date: 2026-05-03
Status: Approved design direction; implementation plan pending

## Purpose

This design closes the three reopened issues in
`docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md`:

- `crew accept` can currently proceed without proving the crew reached
  `crew.ready_for_accept`.
- source worker fallback can reuse an incompatible implementer when planner
  selection returns no worker.
- tmux transcript cursor initialization happens after `send()`, which can miss
  output written immediately after delivery.

The target is a stable V4 main path where final accept is guarded by replayable
event evidence, worker reuse has one compatibility path, and transcript
evidence cannot be skipped at turn start.

## Context

V4 already has durable runtime evidence, structured outbox completion, message
ack processing, V4-native merge artifacts, guarded merge transactions, repo
intelligence, planner policy, and filesystem runtime event stream support.

The remaining issue is not that these pieces are missing. The issue is that two
final safety boundaries still have escape paths:

- `V4MergeTransaction.accept()` validates patch mechanics and final
  verification, but does not yet require the workflow to have reached an
  accepted ready state.
- `V4CrewRunner._source_worker()` can bypass `PlannerPolicy` by falling back to
  any active implementer.

The transcript cursor issue is smaller but important for evidence completeness:
cursor initialization should mark the transcript size before delivery, not
after delivery.

## Goals

- Make `accept` fail closed unless latest V4 events prove the crew is ready.
- Ensure `accept` only merges patch artifacts associated with the latest ready
  round.
- Prevent open blocking challenges, post-ready verification failures, or
  human-required events from being accepted.
- Remove source worker reuse paths that bypass write-scope compatibility.
- Initialize transcript cursor before sending a turn so immediate output is
  captured.
- Preserve existing V4 merge mechanics: dirty-base protection, integration
  worktree, final verification, and main workspace apply checks.

## Non-Goals

- Do not redesign the entire projection system.
- Do not remove V3 compatibility or legacy patch fallback in this change.
- Do not implement async filesystem subscriptions.
- Do not make learned skills or guardrails active automatically.
- Do not weaken deterministic gates in favor of planner decisions.

## Approach Chosen

Use strict event evidence at the accept boundary.

`V4MergeTransaction.accept()` should call a new readiness gate before loading
patches or checking dirty state. The gate reads the crew's V4 event stream and
returns either a blocked reason or a ready context containing the accepted
`round_id` and evidence ids.

This keeps the final workspace-writing boundary self-contained. It does not rely
on `V4CrewRunner` having taken the happy path, and it does not trust patch
artifacts alone as proof of readiness.

## Alternatives Considered

### Projection-Only Gate

The accept path could ask `CrewProjection` whether a crew is ready. This would
share state interpretation with UI/status, but it would make the final safety
gate depend on a display-oriented model. Projection can later expose the same
summary, but accept should keep its own small gate over raw events.

### Runner-Only Gate

The runner could avoid writing merge artifacts before scope, review, and
verification complete. That reduces accidental accept risk, but it cannot
protect against old artifacts, manual accept calls, partial runs, or replay
after interruption. The accept transaction must still validate readiness.

### Fallback Compatibility Check

Source worker fallback could be kept if it reused planner compatibility logic.
This keeps more reuse behavior, but it creates two selection paths to reason
about. The safer design is to remove fallback and make `PlannerPolicy` the only
reuse selector.

## Component Design

### AcceptReadinessGate

Add `src/codex_claude_orchestrator/v4/accept_readiness.py`.

Responsibilities:

- Read `event_store.list_stream(crew_id)`.
- Find the latest `crew.ready_for_accept` event.
- Validate the latest ready round.
- Return a typed decision object without mutating state.

Suggested models:

```text
AcceptReadinessDecision
  allowed: bool
  reason: str
  round_id: str
  ready_event_id: str
  review_event_id: str
  verification_event_ids: list[str]
  blocking_challenge_event_ids: list[str]
  invalidating_event_ids: list[str]
```

Allowed criteria:

- A latest `crew.ready_for_accept` exists.
- The ready event has a non-empty `round_id`.
- The same `round_id` has at least one `review.completed` event whose status is
  `ok` or `warn` at or before the latest ready event.
- The same `round_id` has at least one `verification.passed` at or before the
  latest ready event.
- There is no same-round blocking `challenge.issued` after the accepted review
  and before or at the latest ready event.
- After the latest ready event, the same round has no invalidating event:
  `challenge.issued` with severity `block`, `verification.failed`,
  `human.required`, `turn.failed`, `turn.timeout`, or `turn.inconclusive`.

When several same-round review events exist, the gate should use the latest
review at or before the ready event. When several verification events exist, at
least one passed verification must exist at or before the ready event, and any
same-round `verification.failed` after the ready event invalidates readiness.

Blocked reasons should be stable strings:

- `missing_ready_for_accept`
- `ready_round_missing`
- `ready_round_missing_review`
- `ready_round_missing_verification`
- `blocking_challenge_open`
- `ready_invalidated_after_ready`

### V4MergeTransaction Integration

`V4MergeTransaction.accept()` should call `AcceptReadinessGate.evaluate()` before
loading worker patches.

If blocked:

- return the existing blocked response shape;
- append `merge.blocked`;
- include readiness details in payload for inspection.

If allowed:

- continue with existing patch loading, conflict detection, dirty-base checks,
  integration worktree verification, and final apply;
- pass the ready `round_id` into patch loading;
- only load V4 `worker.result.recorded` events for that ready round.

Legacy patch fallback remains available only after readiness passes. It must not
be a way to accept a crew that never reached `crew.ready_for_accept`.

Additional blocked reason:

- `no_worker_patches_for_ready_round`

### Ready Round Patch Selection

`_latest_v4_result_events()` should accept an optional `round_id`.

When `round_id` is provided:

- ignore `worker.result.recorded` events from other rounds;
- keep latest event per worker within the ready round;
- return no patches if the ready round has no result event.

This prevents a stale patch from an earlier failed or blocked round from being
merged after a later ready event.

### Source Worker Selection

Change `V4CrewRunner._source_worker()` so it only returns
`PlannerPolicy.select_worker()`.

If planner returns `None`:

- dynamic mode should spawn a fresh source worker through the existing
  `_spawn_source_worker()` path;
- non-dynamic mode should not fallback to an arbitrary implementer;
- decision recording should explain whether the runner spawned a new worker or
  had no compatible worker.

This makes write-scope compatibility a single hard boundary.

### Transcript Cursor Initialization

Change `ClaudeCodeTmuxAdapter.deliver_turn()` ordering:

```text
initialize filesystem stream cursor
native_session.send(...)
return DeliveryResult
```

The cursor initialization records transcript size before delivery. Any transcript
bytes written during or immediately after `send()` are then visible to
`FilesystemRuntimeEventStream.poll_once()`.

Keep the current state-commit rule:

- polling uses `autocommit=False`;
- supervisor appends runtime evidence to EventStore;
- only then adapter `commit_runtime_events()` advances stream sha/cursor state.

## Data Flow

### Accept

```text
crew accept
  -> V4MergeTransaction.accept
  -> AcceptReadinessGate.evaluate(event stream)
  -> blocked if ready evidence is missing or invalidated
  -> load worker.result.recorded for ready round
  -> validate patch artifacts
  -> dirty/base checks
  -> integration worktree
  -> verification commands
  -> final main workspace check
  -> apply patch
  -> crew.accepted
```

### Source Worker

```text
V4CrewRunner._source_worker
  -> PlannerPolicy.select_worker
  -> compatible worker or None
  -> dynamic spawn if None
  -> no arbitrary implementer fallback
```

### Transcript Evidence

```text
deliver_turn
  -> initialize cursor at pre-send transcript size
  -> send turn
watch_turn
  -> poll filesystem stream from pre-send cursor
  -> append evidence to EventStore
  -> commit stream state
```

## Error Handling

- Readiness evaluation should tolerate empty streams and return a blocked
  decision, not raise.
- Malformed or missing event payload fields should block accept with stable
  reasons rather than being treated as ready.
- Merge input errors after readiness passes should keep using existing
  `invalid v4 merge input` style responses.
- `commit_runtime_events()` failure should remain non-fatal to turn completion
  and append `runtime.stream_commit_failed`, as the current supervisor path
  already does.

## Testing

### Accept Readiness

- Missing `crew.ready_for_accept` blocks before patch apply.
- Ready event without `round_id` blocks.
- Ready round without review OK/WARN blocks.
- Ready round without `verification.passed` blocks.
- Blocking `challenge.issued` after ready blocks.
- `verification.failed` after ready blocks.
- Ready round with review OK and verification passed proceeds to merge.
- Accept only loads `worker.result.recorded` for the ready round.
- Legacy patch fallback still requires readiness.

### Source Worker Selection

- Compatible source worker is reused.
- Incompatible active implementer is not reused.
- Dynamic mode spawns a new source worker when no compatible worker exists.
- Non-dynamic mode does not fallback to an arbitrary implementer.

### Transcript Cursor

- Pre-send transcript content is not re-ingested.
- Transcript written during `send()` is captured as `runtime.output.appended`.
- Capture-pane failure does not prevent filesystem transcript evidence.
- Outbox-first behavior remains unchanged.

### Regression

- Existing V4/CLI tests remain green.
- Full `pytest -q` remains green.

## Rollout

This can be implemented in one focused plan:

1. Add `AcceptReadinessGate` with unit tests.
2. Integrate it into `V4MergeTransaction`.
3. Filter V4 merge inputs by ready round.
4. Remove source worker fallback.
5. Move transcript cursor initialization before send.
6. Update current issues documentation and test snapshot after verification.

## Success Criteria

- `crew accept` cannot merge a crew without latest ready evidence.
- scope block, review block, missing ready, open blocking challenge, and
  post-ready verification failure all return blocked.
- stale worker result artifacts from non-ready rounds are ignored.
- source worker reuse cannot bypass planner write-scope checks.
- immediate post-send transcript output is captured.
- The current reopened 2 P1 and 1 P2 issues can be marked closed after tests.
