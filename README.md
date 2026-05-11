# Crew Crucible

Multi-agent coding with adversarial verification. Code through fire.

## The Problem

You ask Claude Code to implement a feature. It writes 500 lines, runs the tests, says "done." You merge it. Two days later you find a subtle race condition it never considered.

**One AI agent reviewing its own work has blind spots.** It optimizes for "make the tests pass," not "find what could go wrong." It won't challenge its own assumptions.

Crew Crucible solves this by pitting multiple Claude CLI instances against each other — one implements, another actively tries to break it. The implementer has to defend its code against a hostile reviewer. Bad code doesn't survive the crucible.

## How It Works

```
You: "Add user registration with email verification"
                    |
                    v
          Supervisor (Claude CLI + MCP)
           /        |        \
          v         v         v
     Explorer   Implementer   Reviewer
     (scout)    (writes code)  (tries to break it)
                    |              |
                    +--- conflict -+
                    |
              Challenge/Repair loop
              (up to 3 rounds)
                    |
                    v
              pytest passes?
                 /    \
               yes     no → fix & retry
                |
                v
           Merge to main
```

The key insight: **the Reviewer is adversarial**. It doesn't just check "do tests pass?" — it looks for edge cases, race conditions, security holes, and architectural problems. When it finds issues, it emits targeted challenges to specific workers. The Implementer must fix them and prove the fix works. This cycle repeats up to 3 rounds.

## Why Multiple Agents?

| Single Claude CLI | Crew Crucible |
|---|---|
| Reviews its own code (blind spots) | Separate reviewer with fresh context |
| One long context window (polluted) | Isolated contexts per role |
| Sequential: write → test → done | Adversarial: write → attack → defend → verify |
| "Tests pass, ship it" | "Tests pass, but what about X?" |

## Features

- **Adversarial Verification** — Reviewer actively attacks code; Implementer defends; up to 3 challenge/repair rounds
- **Long Task Supervisor** — Multi-stage execution with dynamic planning for complex, multi-hour tasks
- **Git Worktree Isolation** — Each worker gets an independent worktree; no file conflicts
- **Event-Sourced Audit Trail** — Every state change recorded in SQLite; full replay capability
- **Blackboard Pattern** — Workers share facts, claims, risks, and patches through typed entries
- **Safety Policy Gate** — Blocks destructive commands, shell injection, sensitive path access
- **MCP Server** — Integrates with Claude Code as native MCP tools
- **Non-blocking Jobs** — `crew_run` returns immediately; delta-status polling minimizes context usage
- **Parallel Subtasks** — Multiple workers execute concurrently with adversarial review

## Requirements

- Python >= 3.11
- [Claude CLI](https://docs.anthropic.com/en/docs/claude-code) (Anthropic's Claude Code)
- tmux

## Installation

```bash
# Clone
git clone https://github.com/zhangclaus/crew-crucible.git
cd crew-crucible

# Install
pip install -e .

# Or with dev dependencies
pip install -e ".[dev]"

# Verify prerequisites
orchestrator doctor
```

## Quick Start

### CLI

```bash
# Run a crew with full supervision loop
orchestrator crew run \
  --repo /path/to/your/project \
  --goal "Add user registration with email verification" \
  --verification-command "pytest" \
  --max-rounds 3

# Check status
orchestrator crew status --repo /path/to/your/project

# Accept results when ready
orchestrator crew accept --repo /path/to/your/project
```

### MCP Server (Claude Code Integration)

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "crew-crucible": {
      "command": "python",
      "args": ["-m", "codex_claude_orchestrator.mcp_server"]
    }
  }
}
```

Then use from Claude Code:

```
crew_run(repo="/path/to/project", goal="Refactor auth module", verification_commands=["pytest"])
crew_job_status(job_id="job-abc123")
crew_accept(crew_id="crew-xyz")
```

## MCP Tools

| Tool | Description |
|------|-------------|
| `crew_run` | Start a non-blocking crew job (returns `job_id`) |
| `crew_job_status` | Poll job status with delta tracking (only returns changes) |
| `crew_cancel` | Cancel a running job |
| `crew_verify` | Run a verification command (pytest, ruff, etc.) |
| `crew_accept` | Accept and finalize crew results |

## CLI Commands

```
orchestrator crew run       # Start a crew with supervision loop
orchestrator crew status    # Show crew status
orchestrator crew accept    # Accept crew results
orchestrator crew stop      # Stop all workers
orchestrator crew verify    # Run verification
orchestrator doctor         # Check prerequisites
```

## How It Works

1. **Dispatch** — `crew_run` spawns workers in tmux panes with role-specific prompts
2. **Execute** — Workers operate in isolated git worktrees, writing code within their assigned scope
3. **Review** — Reviewer reads changes, runs tests, emits a verdict (pass/challenge/replan)
4. **Challenge** — If issues found, specific workers get targeted fix instructions
5. **Verify** — Verification commands (pytest, ruff, etc.) run against the merged result
6. **Accept** — On success, worktrees merge into the main branch

Every step is recorded as an immutable event in the SQLite event store. You can replay the full history with `crew_state_projection`.

## Project Structure

```
src/codex_claude_orchestrator/
├── core/              # Domain models, safety policy gate
├── crew/              # CrewController, worker contracts, merge arbitration
├── v4/                # Event-sourced runtime (primary)
│   ├── event_store.py # SQLite event store
│   ├── crew_runner.py # Main orchestration loop
│   ├── supervisor.py  # V4 supervisor facade
│   ├── parallel_supervisor.py    # Parallel subtask execution
│   ├── long_task_supervisor.py   # Multi-stage long task execution
│   └── adapters/      # tmux Claude adapter
├── mcp_server/        # MCP server (FastMCP, stdio transport)
├── runtime/           # tmux session management
├── workspace/         # Git worktree management
├── messaging/         # Worker-to-worker communication
└── state/             # Blackboard, recorders

skills/
└── orchestration-default.md  # Orchestration protocol (editable)
```

## Configuration

The orchestration protocol is defined in `skills/orchestration-default.md`. Key settings:

- **Worker templates** — `targeted-code-editor`, `repo-context-scout`, `patch-risk-auditor`, etc.
- **Max rounds** — Challenge/repair iterations before escalation (default: 3)
- **Poll interval** — How often to check worker status (adaptive: 5s → 60s)
- **Write scope** — File paths each worker is allowed to modify

Environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `V4_EVENT_STORE_BACKEND` | `sqlite` | Event store backend (`sqlite` or `postgres`) |

## Testing

```bash
# Run all tests
pytest

# Run specific module tests
pytest tests/v4/ -v
pytest tests/mcp_server/ -v

# Run with coverage
pytest --cov=codex_claude_orchestrator
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feat/my-feature`)
3. Write tests first (TDD)
4. Implement the feature
5. Run tests (`pytest`)
6. Commit with conventional commits (`feat:`, `fix:`, `test:`, `docs:`)
7. Open a Pull Request

## License

MIT
