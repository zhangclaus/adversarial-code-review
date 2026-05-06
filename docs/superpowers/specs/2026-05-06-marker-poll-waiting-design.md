# Marker Poll Waiting Design

> Replaces the current "observe once and give up" pattern with a blocking poll loop that waits for the worker's turn marker to appear.

## Problem

`ClaudeCodeTmuxAdapter.watch_turn()` calls `native_session.observe()` exactly once. If the worker hasn't finished yet (marker not in terminal output), the supervisor returns "waiting" immediately without retrying. This makes the supervisor effectively useless for any task that takes more than a few seconds.

## Goal

`watch_turn` should poll the tmux pane in a loop with exponential backoff until either:
1. The marker appears → yield `marker.detected`, return
2. A configurable timeout is reached → yield `runtime.poll_timeout`, return
3. An error occurs → yield `runtime.observe_failed`, return

## Design

### 1. Poll Loop Core

`ClaudeCodeTmuxAdapter.watch_turn` becomes a blocking poll loop:

```
watch_turn(turn):
    # Existing: check filesystem stream first
    yield from _watch_filesystem_stream(turn, worker)

    delay = poll_initial_delay          # 2.0s
    deadline = monotonic() + poll_timeout  # 300s default
    last_text = ""

    while True:
        observation = native_session.observe(pane, lines=200, marker)

        # Incremental output: only yield new text
        current_text = observation.snapshot
        if current_text != last_text:
            new_part = current_text[len(last_text):]
            if new_part.strip():
                yield RuntimeEvent(type="output.chunk", text=new_part)
            last_text = current_text

        # Marker found
        if observation.marker_seen:
            yield RuntimeEvent(type="marker.detected", marker=marker)
            return

        # Timeout
        if monotonic() >= deadline:
            yield RuntimeEvent(type="runtime.poll_timeout",
                             timeout_seconds=poll_timeout)
            return

        # Backoff sleep
        sleep(delay)
        delay = min(delay * 2, poll_max_delay)
```

### 2. Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `poll_initial_delay` | float | 2.0 | First poll interval (seconds) |
| `poll_max_delay` | float | 10.0 | Backoff ceiling (seconds) |
| `poll_timeout` | float | 300.0 | Total timeout (seconds). CLI: repurpose existing `--poll-interval` flag. |

Passed from `V4CrewRunner.supervise()` → adapter constructor.

CLI already has `--poll-interval` (default 5.0s). Repurpose as `poll_timeout` — the semantics change from "sleep between polls" to "total time to wait for marker". Default raised to 300s to align with BUSY worker timeout.

### 3. Event Types

| Event | When | Payload |
|---|---|---|
| `output.chunk` | New text appeared in terminal | `{"text": "..."}` (incremental only) |
| `marker.detected` | Marker string found | `{"marker": "...", "source": "tmux"}` |
| `runtime.poll_timeout` | Timeout reached | `{"timeout_seconds": 300.0}` |
| `runtime.observe_failed` | tmux command error | `{"source": "tmux", "error": "..."}` |

No changes to existing event types. `runtime.poll_timeout` is new.

### 4. Supervisor Impact

**None.** `V4Supervisor.run_worker_turn()` and `CompletionDetector.evaluate()` are unchanged:
- They consume `Iterable[RuntimeEvent]` from `watch_turn`
- `marker.detected` → "turn_completed"
- No `marker.detected` → "waiting"
- The only difference is that "waiting" now means "tried and timed out" instead of "peeked once and didn't see it"

### 5. Incremental Output Diffing

Simple tail-based diff:
- Track `last_text` (full snapshot from previous poll)
- New text = `current_text[len(last_text):]`
- Edge case: if terminal scrolls and old output is lost, `current_text` may be shorter than `last_text`. Fall back to yielding the full `current_text`.

### 6. Error Handling

- `tmux capture-pane` fails → yield `runtime.observe_failed`, return immediately (no retry)
- tmux session gone → same as above
- Worker output > 200 lines (terminal scroll) → `last_text` diff may be inaccurate; degrade to full yield

### 7. Testing

**Unit tests** (`tests/v4/test_tmux_claude_adapter.py`):

1. `test_watch_turn_polls_until_marker_detected` — mock observe returns empty then marker, verify poll loop exits correctly
2. `test_watch_turn_yields_incremental_output` — multiple observe calls with growing text, verify only new parts are yielded
3. `test_watch_turn_timeout_yields_poll_timeout` — mock observe never returns marker, verify timeout event after deadline
4. `test_watch_turn_backoff_increases_delay` — verify sleep intervals: 2s → 4s → 8s → 10s cap
5. `test_watch_turn_observe_failed_returns_immediately` — mock observe throws, verify `runtime.observe_failed` and exit

**Mock strategy:**
- Mock `native_session.observe` with `side_effect` list
- Mock `time.sleep` to avoid real waits
- Use small timeout values (e.g., 5s) for timeout tests

### 8. Files Changed

| File | Change |
|---|---|
| `v4/adapters/tmux_claude.py` | `watch_turn` → poll loop with backoff |
| `v4/adapters/tmux_claude.py` | `__init__` → accept poll params |
| `v4/runtime.py` | Add `runtime.poll_timeout` to event type docs (no code change) |
| `tests/v4/test_tmux_claude_adapter.py` | 5 new tests |

No changes to: `supervisor.py`, `crew_runner.py`, `completion.py`, `runtime.py` interface.
