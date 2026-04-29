# Codex-in-the-loop Claude Bridge Supervision Design

- Date: 2026-04-29
- Status: Approved direction, awaiting written spec review
- Scope: Connect V2 evaluator, verification, and challenge records to the Claude bridge without replacing the current Codex App as the thinking supervisor

## Goal

Turn the Claude bridge from "long dialogue only" into "long dialogue plus Codex-supervised adversarial control".

The core workflow is:

```text
Codex thinks
→ Codex sends an instruction through the bridge
→ Claude Code executes and replies
→ Codex reads the reply and evidence
→ Codex runs or requests verification
→ Codex records a challenge when needed
→ Codex sends the next repair or continuation instruction through the same Claude session
```

The bridge should make this loop durable, inspectable, and easy for the current Codex App agent to operate from shell commands. It should not pretend that a local Python rules class is the main Codex evaluator.

## Current Context

The project already has two useful but separate pieces.

`ClaudeBridge` provides a recoverable Claude Code conversation:

- `claude bridge start` starts a `claude --print` turn.
- `claude bridge send` resumes the stored Claude session with `--resume`.
- bridge state is written under `.orchestrator/claude-bridge/`.
- `bridge.log` and `turns.jsonl` preserve a human-readable and machine-readable transcript.

V2 adversarial sessions provide durable supervision records:

- `SessionRecord`
- `TurnRecord`
- `OutputTrace`
- `VerificationRecord`
- `ChallengeRecord`
- `LearningNote`
- `SessionRecorder`
- `VerificationRunner`
- `ResultEvaluator`

The missing connection is not just a local auto-loop. The user requirement is specifically that Codex remains the demand-side thinker while Claude Code acts as the coding worker.

## Chosen Direction

Use a Codex-in-the-loop bridge.

`ClaudeBridge` remains responsible for the long Claude Code session. A supervised bridge additionally creates or links a V2 `SessionRecord` and exposes commands that let the current Codex App agent record verification and challenge decisions as it thinks.

`ResultEvaluator` is demoted to an auxiliary safety net. It can classify basic mechanical failures such as non-zero exits, parse errors, or empty output, but it is not the primary supervisor. The primary evaluator is Codex in this conversation, using bridge commands to inspect Claude's output and record decisions.

This keeps the design honest:

- no unstable automation of the current Codex App UI input box
- no fake "Codex thinking" implemented as a small deterministic Python class
- no loss of the Claude `--resume` long-dialogue context
- no replacement of V2 session records

## Product Behavior

A supervised bridge starts like a normal bridge but records a linked V2 session id in `record.json`.

```bash
orchestrator claude bridge start \
  --repo /path/to/repo \
  --goal "..." \
  --workspace-mode shared \
  --supervised \
  --visual log
```

Codex can then operate the loop with shell commands:

```bash
orchestrator claude bridge status --repo /path/to/repo
orchestrator claude bridge tail --repo /path/to/repo --limit 3
orchestrator claude bridge verify --repo /path/to/repo --command "pytest -q"
orchestrator claude bridge challenge --repo /path/to/repo --summary "..." --repair-goal "..." --send
orchestrator claude bridge send --repo /path/to/repo --message "..."
orchestrator claude bridge accept --repo /path/to/repo --summary "..."
orchestrator claude bridge needs-human --repo /path/to/repo --summary "..."
```

The existing unsupervised bridge behavior remains available. If `--supervised` is not used, `start/send/tail/list` keep their current lightweight behavior.

## Data Model

`record.json` gains optional supervision fields:

- `supervised`: boolean
- `session_id`: linked V2 session id or null
- `latest_turn_id`: latest bridge turn id
- `latest_verification_status`: `passed`, `failed`, `blocked`, or null
- `latest_challenge_id`: most recent unresolved challenge id or null
- `status`: existing bridge status plus `needs_human` when Codex marks the loop blocked

`turns.jsonl` remains the bridge-local transcript and continues storing Claude command details, stdout, stderr, parsed result text, parse errors, and Claude session id.

For supervised bridges, each Claude turn is also mirrored into the V2 session as:

- a `TurnRecord` with phase `execute` for Claude output
- an `OutputTrace` containing command, stdout/stderr summary, parse status, and result text

Codex-authored challenge commands append:

- a `ChallengeRecord`
- a `TurnRecord` with phase `challenge`
- a bridge log section that makes the challenge visible in the watcher

Verification commands append:

- a `VerificationRecord`
- a `TurnRecord` with phase `final_verify` or `light_verify`
- stdout/stderr artifacts through `SessionRecorder`
- a bridge log section with pass/fail summary

## Command Semantics

### `start --supervised`

Creates the bridge and a linked V2 session. The initial Claude turn is still sent through the bridge so the same Claude conversation can be resumed later.

If the Claude start turn fails mechanically, the bridge records the failed turn and marks the supervised session as needing human review.

### `status`

Returns a compact JSON object for Codex:

- bridge record
- linked session summary when present
- latest Claude turn
- latest verification result
- latest challenge
- suggested next action fields such as `needs_codex_review`, `verification_failed`, or `challenge_pending`

This command exists so Codex can quickly decide what to do next without manually reading every JSONL file.

### `verify`

Runs a guarded verification command through the existing `VerificationRunner`.

The command is associated with the latest bridge turn unless `--turn-id` is supplied. A failed verification does not automatically send anything to Claude. It records evidence so Codex can decide the next instruction.

### `challenge`

Records a Codex-authored adversarial challenge. Required inputs are:

- `--summary`
- `--repair-goal`

With `--send`, the repair goal is immediately sent to the same Claude `--resume` session as a normal bridge turn. Without `--send`, the challenge is recorded but left pending for Codex to edit or send later.

### `send`

Continues to send arbitrary Codex instructions to Claude. In a supervised bridge, each send is mirrored into the linked V2 session.

### `accept`

Marks the supervised bridge and linked V2 session as accepted with a Codex-authored summary. This is an explicit Codex decision, usually after reviewing Claude's output and passing verification evidence.

### `needs-human`

Marks the supervised bridge and linked V2 session as needing human review with a Codex-authored summary. This is used when Claude is blocked, verification remains unsafe, or Codex decides the requirement cannot be accepted without user input.

## Evaluator Boundary

`ResultEvaluator` should not be treated as the real demand-side Codex.

Its role in the bridge is limited to auxiliary classification:

- Claude command failed
- Claude output could not be parsed
- result text was empty
- structured output is absent when a structured mode is requested

Human-level requirement judgment, adversarial counterexamples, repair strategy, and final acceptance remain Codex-in-the-loop decisions. Those decisions are persisted by explicit `verify`, `challenge`, `accept`, and `needs-human` commands.

## Safety

The design does not automate the current Codex App UI. The current Codex App agent operates the bridge by running CLI commands, which is stable and auditable.

Verification commands go through `PolicyGate` before execution.

`readonly` bridges preserve the current allowed tool restriction for Claude: `Read,Glob,Grep,LS`.

`shared` bridges still rely on Claude permissions and explicit prompts to preserve unrelated user work. Codex remains responsible for reviewing changes before final acceptance.

## Non-Goals

- No UI automation of the current Codex App input box.
- No claim that a deterministic Python class is equivalent to Codex reasoning.
- No fully autonomous background Codex controller in this step.
- No replacement of `SessionEngine`.
- No new hosted service or external control plane.

## Testing

Add tests for:

- `bridge start --supervised` creates a linked V2 session.
- supervised `send` mirrors Claude output into session turns and output traces.
- `bridge verify` records passing and failing `VerificationRecord` entries.
- `bridge challenge --send` records a `ChallengeRecord` and sends the repair goal through the existing Claude session.
- `bridge status` returns the latest turn, verification, challenge, and linked session summary.
- `bridge accept` and `bridge needs-human` finalize the linked supervised session state.
- existing unsupervised bridge tests continue to pass unchanged.
- CLI tests cover new `--supervised`, `status`, `verify`, `challenge`, `accept`, and `needs-human` routes.

## Implementation Boundary

This spec should produce a bridge that the current Codex App can operate manually and repeatedly in one conversation.

If a future fully automatic Codex controller is needed, it should be added as a separate adapter that calls a stable model or agent API. It should not be built by trying to type into the current Codex App UI.
