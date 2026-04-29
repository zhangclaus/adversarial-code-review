# Tmux Terminal Console Design

## Goal

Replace the browser UI as the primary live observation surface with a tmux-first terminal console. Codex remains the demand-side orchestrator, while Claude and verification commands execute in visible tmux windows and continue to write durable `.orchestrator` records.

## Requirement Lineage

- Original: Codex supervises Claude Code tasks.
- Midpoint: Claude/Codex output must be visible and inspectable.
- Current: adversarial sessions should show live execution, verification, challenge loops, and skill evolution without hiding behind a browser dashboard.

## Recommended Interaction Model

The terminal console is the live control plane. It creates one tmux session per orchestrator run with these windows:

- `control`: Codex orchestration command and final JSON summary.
- `claude`: Claude worker command execution.
- `verify`: final verification command execution.
- `records`: auto-refreshing `sessions list` and `runs list`.
- `skills`: auto-refreshing pending skills.

The browser UI may remain as a passive record viewer, but it is not the primary workflow.

## Execution Model

`orchestrator term session start ...` creates the tmux layout and starts an internal orchestrator process in the `control` window. That internal process builds the normal V2 `SessionEngine`, but injects tmux-backed command runners:

- Claude command runner targets the `claude` window.
- Verification command runner targets the `verify` window.

Each tmux-backed command runner sends the command to its target pane, writes stdout/stderr/exit code to files under `.orchestrator/term/<name>/`, waits for completion, and returns a `CompletedProcess`-compatible object to the existing adapter/evaluator path.

## CLI

Public commands:

```bash
orchestrator term session start --repo /path/to/repo --goal "..." --assigned-agent claude
orchestrator term attach --name orchestrator-...
orchestrator term list
```

The internal command is intentionally available for tmux to call, but not intended as the normal human entrypoint:

```bash
orchestrator term run-session --tmux-name orchestrator-... ...
```

## Safety

- Keep existing policy gates before worker and verification execution.
- Keep existing workspace modes and shared-write approval.
- Do not use tmux to bypass command policy.
- Do not require interactive Claude mode for the first version.

## Testing

- Unit-test tmux command construction with a fake runner.
- Unit-test tmux command runner with a fake tmux runner and fake completion files.
- Unit-test CLI parsing and command wiring.
- Unit-test verification runner injection so tmux and subprocess runners share the same contract.
