# Tmux Terminal Console Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a tmux-first terminal console that runs Claude and verification commands in visible terminal windows while preserving existing orchestrator records and V2 session behavior.

**Architecture:** Add a focused `tmux_console.py` module that owns tmux layout creation, pane command sending, and a `CompletedProcess`-compatible command runner. Inject that runner into `ClaudeCliAdapter` and `VerificationRunner` through existing builder paths. Add `orchestrator term ...` CLI commands to launch, attach, list, and run tmux-backed sessions.

**Tech Stack:** Python 3.13-compatible stdlib (`argparse`, `dataclasses`, `pathlib`, `shlex`, `subprocess`, `time`, `uuid`), tmux CLI, existing orchestrator modules, pytest.

---

## Files

- Create: `src/codex_claude_orchestrator/tmux_console.py`
- Create: `tests/test_tmux_console.py`
- Modify: `src/codex_claude_orchestrator/verification_runner.py`
- Modify: `src/codex_claude_orchestrator/cli.py`
- Modify: `tests/test_verification_runner.py`
- Modify: `tests/test_cli.py`

## Task 1: tmux Console Core

- [ ] Write failing tests for session layout command construction and command-runner completion behavior in `tests/test_tmux_console.py`.
- [ ] Run `pytest tests/test_tmux_console.py -v` and confirm failures are missing module/API failures.
- [ ] Implement `TmuxConsole`, `TmuxCommandRunner`, and `build_default_term_name` in `tmux_console.py`.
- [ ] Run `pytest tests/test_tmux_console.py -v` and confirm it passes.
- [ ] Commit with `feat: add tmux console core`.

## Task 2: Runner Injection

- [ ] Write failing test showing `VerificationRunner(..., runner=fake_runner)` records stdout/stderr from the injected runner.
- [ ] Run the targeted verification runner test and confirm constructor/API failure.
- [ ] Add optional `runner` to `VerificationRunner` and use it instead of hard-coded `subprocess.run`.
- [ ] Run `pytest tests/test_verification_runner.py -v`.
- [ ] Commit with `feat: allow injected verification runner`.

## Task 3: CLI term Commands

- [ ] Write failing CLI tests for `term` parser exposure, `term session start`, `term attach`, `term list`, and `term run-session` wiring with monkeypatched console/session builders.
- [ ] Run `pytest tests/test_cli.py -v` and confirm `term` command failures.
- [ ] Add CLI parser branches and builders for tmux-backed session launch.
- [ ] Run `pytest tests/test_cli.py -v`.
- [ ] Commit with `feat: add tmux terminal session commands`.

## Task 4: Full Verification

- [ ] Run `pytest -v`.
- [ ] Run `.venv/bin/orchestrator term --help`.
- [ ] Run `.venv/bin/orchestrator term session start --help`.
- [ ] Run `.venv/bin/orchestrator term list` if tmux is available.
- [ ] Report exact commands and outcomes.
