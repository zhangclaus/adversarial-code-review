# V4 Accept Readiness Worker Safety Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the reopened V4 accept readiness, source worker fallback, and transcript cursor initialization issues.

**Architecture:** Add a small `AcceptReadinessGate` over raw V4 events, invoke it at the start of `V4MergeTransaction.accept()`, and filter merge inputs to the ready round. Remove the unsafe source worker fallback so `PlannerPolicy` is the only reuse selector, and initialize tmux transcript cursor before `send()` so immediate output is captured.

**Tech Stack:** Python, dataclasses, pytest, existing V4 `EventStore`, `SQLiteEventStore`, `V4MergeTransaction`, `V4CrewRunner`, `ClaudeCodeTmuxAdapter`.

---

## File Structure

- Create `src/codex_claude_orchestrator/v4/accept_readiness.py`
  - Owns replay-only accept readiness decisions.
  - Does not mutate EventStore.
  - Produces typed decision payloads for merge blocked events.
- Create `tests/v4/test_accept_readiness.py`
  - Unit tests for missing ready, missing review, missing verification, blocking challenge, post-ready invalidation, and allowed ready state.
- Modify `src/codex_claude_orchestrator/v4/workflow.py`
  - Set `round_id` on `crew.ready_for_accept` events in addition to payload.
- Modify `src/codex_claude_orchestrator/v4/merge_transaction.py`
  - Call `AcceptReadinessGate` before loading patches or touching git.
  - Load V4 result events only from the ready round.
  - Keep legacy fallback only after readiness passes.
- Modify `tests/v4/test_merge_transaction.py`
  - Add ready evidence helpers.
  - Update existing merge tests that verify post-readiness behavior to seed ready evidence.
  - Add regression tests for missing ready and stale round patches.
- Modify `src/codex_claude_orchestrator/v4/crew_runner.py`
  - Remove arbitrary active implementer fallback from `_source_worker()`.
- Modify `tests/v4/test_crew_runner.py`
  - Add regression test that incompatible implementer is not reused and dynamic mode spawns a source worker.
- Modify `src/codex_claude_orchestrator/v4/adapters/tmux_claude.py`
  - Move `_initialize_filesystem_stream()` before `native_session.send()`.
- Modify `tests/v4/test_tmux_claude_adapter.py`
  - Add regression test for transcript written during `send()`.
- Modify `docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md`
  - After all tests pass, mark the 2 P1 and 1 P2 as closed and refresh test count.

---

### Task 1: Add AcceptReadinessGate

**Files:**
- Create: `src/codex_claude_orchestrator/v4/accept_readiness.py`
- Create: `tests/v4/test_accept_readiness.py`

- [ ] **Step 1: Write failing tests for readiness decisions**

Create `tests/v4/test_accept_readiness.py`:

```python
from __future__ import annotations

from codex_claude_orchestrator.v4.accept_readiness import AcceptReadinessGate
from codex_claude_orchestrator.v4.event_store import SQLiteEventStore


def test_accept_readiness_blocks_missing_ready_event(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "missing_ready_for_accept"
    assert decision.round_id == ""


def test_accept_readiness_blocks_ready_without_round_id(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    store.append(stream_id="crew-1", type="crew.ready_for_accept", crew_id="crew-1")

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing"


def test_accept_readiness_blocks_ready_round_without_review(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing_review"


def test_accept_readiness_blocks_ready_round_without_verification(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing_verification"


def test_accept_readiness_blocks_challenge_before_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    review = _review_completed(store, status="ok")
    _challenge(store, severity="block")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "blocking_challenge_open"
    assert review.event_id
    assert len(decision.blocking_challenge_event_ids) == 1


def test_accept_readiness_blocks_invalidating_event_after_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="warn")
    _verification_passed(store)
    _ready(store)
    failed = store.append(
        stream_id="crew-1",
        type="verification.failed",
        crew_id="crew-1",
        round_id="round-1",
        payload={"command": "pytest -q"},
    )

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_invalidated_after_ready"
    assert decision.invalidating_event_ids == [failed.event_id]


def test_accept_readiness_allows_latest_ready_round(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    review = _review_completed(store, status="ok")
    verification = _verification_passed(store)
    ready = _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is True
    assert decision.reason == "ready"
    assert decision.round_id == "round-1"
    assert decision.ready_event_id == ready.event_id
    assert decision.review_event_id == review.event_id
    assert decision.verification_event_ids == [verification.event_id]
    assert decision.to_payload()["round_id"] == "round-1"


def test_accept_readiness_uses_latest_ready_round(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, round_id="round-1", status="ok")
    _verification_passed(store, round_id="round-1")
    _ready(store, round_id="round-1")
    _ready(store, round_id="round-2")

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.round_id == "round-2"
    assert decision.reason == "ready_round_missing_review"


def _ready(store, *, round_id="round-1"):
    return store.append(
        stream_id="crew-1",
        type="crew.ready_for_accept",
        crew_id="crew-1",
        round_id=round_id,
        payload={"round_id": round_id},
    )


def _review_completed(store, *, round_id="round-1", status="ok"):
    return store.append(
        stream_id="crew-1",
        type="review.completed",
        crew_id="crew-1",
        worker_id="worker-review",
        turn_id=f"{round_id}-worker-review-review",
        round_id=round_id,
        payload={"status": status, "summary": "reviewed"},
    )


def _verification_passed(store, *, round_id="round-1"):
    return store.append(
        stream_id="crew-1",
        type="verification.passed",
        crew_id="crew-1",
        worker_id="worker-source",
        round_id=round_id,
        payload={"command": "pytest -q"},
    )


def _challenge(store, *, round_id="round-1", severity="block"):
    return store.append(
        stream_id="crew-1",
        type="challenge.issued",
        crew_id="crew-1",
        worker_id="worker-source",
        round_id=round_id,
        payload={"severity": severity, "finding": "review block"},
    )
```

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_accept_readiness.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'codex_claude_orchestrator.v4.accept_readiness'`.

- [ ] **Step 3: Implement AcceptReadinessGate**

Create `src/codex_claude_orchestrator/v4/accept_readiness.py`:

```python
"""Accept readiness checks for V4 merge transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from codex_claude_orchestrator.v4.event_store_protocol import EventStore
from codex_claude_orchestrator.v4.events import AgentEvent, normalize


_INVALIDATING_AFTER_READY = {
    "human.required",
    "turn.failed",
    "turn.timeout",
    "turn.inconclusive",
    "verification.failed",
}


@dataclass(frozen=True, slots=True)
class AcceptReadinessDecision:
    allowed: bool
    reason: str
    round_id: str = ""
    ready_event_id: str = ""
    review_event_id: str = ""
    verification_event_ids: list[str] = field(default_factory=list)
    blocking_challenge_event_ids: list[str] = field(default_factory=list)
    invalidating_event_ids: list[str] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return normalize(self)


class AcceptReadinessGate:
    def __init__(self, *, event_store: EventStore) -> None:
        self._events = event_store

    def evaluate(self, crew_id: str) -> AcceptReadinessDecision:
        events = self._events.list_stream(crew_id)
        ready_event = _latest_event(events, event_type="crew.ready_for_accept")
        if ready_event is None:
            return AcceptReadinessDecision(
                allowed=False,
                reason="missing_ready_for_accept",
            )

        round_id = _event_round_id(ready_event)
        if not round_id:
            return AcceptReadinessDecision(
                allowed=False,
                reason="ready_round_missing",
                ready_event_id=ready_event.event_id,
            )

        same_round = [event for event in events if _event_round_id(event) == round_id]
        before_ready = [event for event in same_round if event.sequence <= ready_event.sequence]
        after_ready = [event for event in same_round if event.sequence > ready_event.sequence]

        review = _latest_acceptable_review(before_ready)
        if review is None:
            return AcceptReadinessDecision(
                allowed=False,
                reason="ready_round_missing_review",
                round_id=round_id,
                ready_event_id=ready_event.event_id,
            )

        verification_events = [
            event.event_id for event in before_ready if event.type == "verification.passed"
        ]
        if not verification_events:
            return AcceptReadinessDecision(
                allowed=False,
                reason="ready_round_missing_verification",
                round_id=round_id,
                ready_event_id=ready_event.event_id,
                review_event_id=review.event_id,
            )

        blocking_challenges = [
            event.event_id
            for event in before_ready
            if event.sequence > review.sequence and _is_blocking_challenge(event)
        ]
        if blocking_challenges:
            return AcceptReadinessDecision(
                allowed=False,
                reason="blocking_challenge_open",
                round_id=round_id,
                ready_event_id=ready_event.event_id,
                review_event_id=review.event_id,
                verification_event_ids=verification_events,
                blocking_challenge_event_ids=blocking_challenges,
            )

        invalidating_events = [
            event.event_id
            for event in after_ready
            if event.type in _INVALIDATING_AFTER_READY or _is_blocking_challenge(event)
        ]
        if invalidating_events:
            return AcceptReadinessDecision(
                allowed=False,
                reason="ready_invalidated_after_ready",
                round_id=round_id,
                ready_event_id=ready_event.event_id,
                review_event_id=review.event_id,
                verification_event_ids=verification_events,
                invalidating_event_ids=invalidating_events,
            )

        return AcceptReadinessDecision(
            allowed=True,
            reason="ready",
            round_id=round_id,
            ready_event_id=ready_event.event_id,
            review_event_id=review.event_id,
            verification_event_ids=verification_events,
        )


def _latest_event(events: list[AgentEvent], *, event_type: str) -> AgentEvent | None:
    for event in reversed(events):
        if event.type == event_type:
            return event
    return None


def _latest_acceptable_review(events: list[AgentEvent]) -> AgentEvent | None:
    for event in reversed(events):
        if event.type != "review.completed":
            continue
        status = str(event.payload.get("status", "")).strip().lower()
        if status in {"ok", "warn"}:
            return event
    return None


def _event_round_id(event: AgentEvent) -> str:
    return event.round_id or str(event.payload.get("round_id", ""))


def _is_blocking_challenge(event: AgentEvent) -> bool:
    if event.type != "challenge.issued":
        return False
    return str(event.payload.get("severity", "block")).strip().lower() == "block"


__all__ = ["AcceptReadinessDecision", "AcceptReadinessGate"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_accept_readiness.py -q
```

Expected: `8 passed`.

- [ ] **Step 5: Commit Task 1**

```bash
git add src/codex_claude_orchestrator/v4/accept_readiness.py tests/v4/test_accept_readiness.py
git commit -m "feat: add v4 accept readiness gate"
```

---

### Task 2: Enforce AcceptReadinessGate in V4MergeTransaction

**Files:**
- Modify: `src/codex_claude_orchestrator/v4/workflow.py`
- Modify: `src/codex_claude_orchestrator/v4/merge_transaction.py`
- Modify: `tests/v4/test_merge_transaction.py`

- [ ] **Step 1: Write failing merge transaction readiness tests**

Add these tests near the top of `tests/v4/test_merge_transaction.py` after imports:

```python
def test_merge_transaction_blocks_without_ready_event_before_git(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    recorder = _crew_with_patch(repo_root, tmp_path, base_ref="base-sha")
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    git = FakeGitRunner(heads=["base-sha"])

    result = V4MergeTransaction(
        repo_root=repo_root,
        recorder=recorder,
        event_store=store,
        git_runner=git,
        command_runner=FakeCommandRunner([0]),
    ).accept(
        crew_id="crew-1",
        summary="accepted",
        verification_commands=["python -c 'print(123)'"],
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "missing_ready_for_accept"
    assert not git.calls


def test_merge_transaction_blocks_ready_round_without_any_patch(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    recorder = _crew_without_patch(repo_root, tmp_path)
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _record_ready_events(store, round_id="round-1")

    result = V4MergeTransaction(
        repo_root=repo_root,
        recorder=recorder,
        event_store=store,
        git_runner=FakeGitRunner(heads=["base-sha"]),
        command_runner=FakeCommandRunner([0]),
    ).accept(
        crew_id="crew-1",
        summary="accepted",
        verification_commands=["python -c 'print(123)'"],
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "no_worker_patches_for_ready_round"
```

Add this stale-round test after `test_merge_transaction_prefers_v4_merge_inputs_over_legacy_changes`:

```python
def test_merge_transaction_ignores_v4_patch_from_non_ready_round(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    recorder = _crew_with_patch(repo_root, tmp_path, base_ref="base-sha")
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    paths = V4Paths(repo_root=repo_root, crew_id="crew-1")
    legacy_root = paths.crew_root / "artifacts"
    legacy_patch = legacy_root / "workers/worker-1/diff.patch"
    legacy_patch.parent.mkdir(parents=True, exist_ok=True)
    legacy_patch.write_text(_patch_for("src/app.py"), encoding="utf-8")
    V4MergeInputRecorder(event_store=store, paths=paths).record_from_changes(
        changes={
            "worker_id": "worker-1",
            "base_ref": "base-sha",
            "changed_files": ["src/app.py"],
            "artifact": "workers/worker-1/changes.json",
            "diff_artifact": "workers/worker-1/diff.patch",
        },
        turn_id="round-1-worker-1-source",
        round_id="round-1",
        contract_id="source_write",
    )
    _record_ready_events(store, round_id="round-2")

    result = V4MergeTransaction(
        repo_root=repo_root,
        recorder=recorder,
        event_store=store,
        git_runner=FakeGitRunner(heads=["base-sha", "base-sha"]),
        command_runner=FakeCommandRunner([0]),
    ).accept(
        crew_id="crew-1",
        summary="accepted",
        verification_commands=["python -c 'print(123)'"],
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "no_worker_patches_for_ready_round"
```

Add helper functions before `FakeGitRunner`:

```python
def _crew_without_patch(repo_root: Path, tmp_path: Path) -> CrewRecorder:
    recorder = CrewRecorder(tmp_path / ".orchestrator")
    recorder.start_crew(
        CrewRecord(
            crew_id="crew-1",
            root_goal="goal",
            repo=repo_root,
            active_worker_ids=["worker-1"],
        )
    )
    return recorder


def _record_ready_events(store: SQLiteEventStore, *, round_id: str = "round-1") -> None:
    store.append(
        stream_id="crew-1",
        type="review.completed",
        crew_id="crew-1",
        worker_id="worker-review",
        round_id=round_id,
        payload={"status": "ok", "summary": "review passed"},
    )
    store.append(
        stream_id="crew-1",
        type="verification.passed",
        crew_id="crew-1",
        worker_id="worker-1",
        round_id=round_id,
        payload={"command": "pytest -q"},
    )
    store.append(
        stream_id="crew-1",
        type="crew.ready_for_accept",
        crew_id="crew-1",
        round_id=round_id,
        payload={"round_id": round_id},
    )
```

- [ ] **Step 2: Update existing merge tests to seed readiness**

For each existing `tests/v4/test_merge_transaction.py` test that expects merge to reach patch validation, dirty checks, verification, or accepted state, change the local store setup from inline `SQLiteEventStore(...)` to a variable and call `_record_ready_events(store)`.

Example replacement in `test_merge_transaction_applies_verified_patch_and_accepts_crew`:

```python
store = SQLiteEventStore(tmp_path / "events.sqlite3")
_record_ready_events(store)

result = V4MergeTransaction(
    repo_root=repo_root,
    recorder=recorder,
    event_store=store,
    git_runner=git,
    command_runner=verifier,
    stop_workers=lambda **kwargs: stopped.append(kwargs) or {"stopped": True},
).accept(
    crew_id="crew-1",
    summary="accepted",
    verification_commands=["python -c 'print(123)'"],
)
```

Apply the same pattern in these tests:

- `test_merge_transaction_applies_verified_patch_and_accepts_crew`
- `test_merge_transaction_prefers_v4_merge_inputs_over_legacy_changes`
- `test_merge_transaction_falls_back_to_legacy_changes_and_records_evidence`
- `test_merge_transaction_blocks_v4_merge_input_with_bad_patch_sha`
- `test_merge_transaction_applies_patch_in_real_git_repo`
- `test_merge_transaction_ignores_in_repo_orchestrator_state_for_dirty_checks`
- `test_merge_transaction_blocks_dirty_main_workspace`
- `test_merge_transaction_blocks_base_ref_mismatch`
- `test_merge_transaction_blocks_patch_outside_recorded_changed_files`
- `test_merge_transaction_blocks_failed_final_verification`

- [ ] **Step 3: Run merge tests to verify they fail**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_merge_transaction.py -q
```

Expected: FAIL because `V4MergeTransaction.accept()` does not enforce readiness yet and `_latest_v4_result_events()` does not filter by ready round.

- [ ] **Step 4: Set ready event round_id in workflow**

In `src/codex_claude_orchestrator/v4/workflow.py`, update `mark_ready()` append call:

```python
        return self._events.append(
            stream_id=crew_id,
            type="crew.ready_for_accept",
            crew_id=crew_id,
            round_id=round_id,
            idempotency_key=f"{crew_id}/{round_id}/ready/{digest}",
            payload={"round_id": round_id},
            artifact_refs=artifact_refs,
        )
```

- [ ] **Step 5: Integrate readiness gate and ready-round patch loading**

In `src/codex_claude_orchestrator/v4/merge_transaction.py`, add the import:

```python
from codex_claude_orchestrator.v4.accept_readiness import AcceptReadinessGate
```

At the start of `accept()` after verification command validation, insert:

```python
        readiness = AcceptReadinessGate(event_store=self._events).evaluate(crew_id)
        if not readiness.allowed:
            return self._blocked(
                crew_id,
                reason=readiness.reason,
                readiness=readiness.to_payload(),
            )
```

Then change patch loading:

```python
        try:
            patches = self._load_worker_patches(crew_id, round_id=readiness.round_id)
        except MergeInputError as exc:
            return self._blocked(crew_id, reason=exc.reason, errors=exc.errors)
        if not patches:
            return self._blocked(crew_id, reason="no_worker_patches_for_ready_round")
```

Remove the old post-load empty patch block:

```python
        if not patches:
            return self._blocked(crew_id, reason="no worker patches recorded")
```

Change method signatures and internals:

```python
    def _load_worker_patches(self, crew_id: str, *, round_id: str = "") -> list[WorkerPatch]:
        v4_patches = self._load_v4_worker_patches(crew_id, round_id=round_id)
        if v4_patches:
            return v4_patches
        if round_id and self._has_v4_result_events(crew_id):
            return []
        return self._load_legacy_worker_patches(crew_id)

    def _load_v4_worker_patches(self, crew_id: str, *, round_id: str = "") -> list[WorkerPatch]:
        result_events = self._latest_v4_result_events(crew_id, round_id=round_id)
```

Replace `_latest_v4_result_events()` with:

```python
    def _latest_v4_result_events(self, crew_id: str, *, round_id: str = ""):
        latest_by_worker = {}
        for event in self._events.list_stream(crew_id):
            if event.type != "worker.result.recorded":
                continue
            if round_id and event.round_id != round_id:
                continue
            worker_id = event.worker_id or str(event.payload.get("worker_id", ""))
            if not worker_id:
                continue
            latest_by_worker[worker_id] = event
        return [latest_by_worker[worker_id] for worker_id in sorted(latest_by_worker)]

    def _has_v4_result_events(self, crew_id: str) -> bool:
        return any(event.type == "worker.result.recorded" for event in self._events.list_stream(crew_id))
```

- [ ] **Step 6: Run merge tests**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_accept_readiness.py tests/v4/test_merge_transaction.py -q
```

Expected: all tests pass.

- [ ] **Step 7: Commit Task 2**

```bash
git add src/codex_claude_orchestrator/v4/workflow.py src/codex_claude_orchestrator/v4/merge_transaction.py tests/v4/test_merge_transaction.py
git commit -m "feat: enforce v4 accept readiness"
```

---

### Task 3: Remove Unsafe Source Worker Fallback

**Files:**
- Modify: `src/codex_claude_orchestrator/v4/crew_runner.py`
- Modify: `tests/v4/test_crew_runner.py`

- [ ] **Step 1: Write failing crew runner test**

Add this test after `test_v4_crew_runner_prefers_high_quality_compatible_source_worker`:

```python
def test_v4_crew_runner_does_not_reuse_incompatible_source_worker(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    controller = FakeController(
        [{"passed": True, "summary": "command passed"}],
        workers=[
            _source_worker(
                worker_id="worker-docs",
                write_scope=["docs/"],
            ),
            _review_worker(),
        ],
    )
    supervisor = FakeV4Supervisor(
        [
            {"status": "turn_completed", "turn_id": "round-1-worker-source-source"},
            {"status": "turn_completed", "turn_id": "round-1-worker-review-review"},
        ],
        event_store=store,
        review_summaries=[
            "<<<CODEX_REVIEW\nverdict: OK\nsummary: patch matches spec and quality bar\nfindings:\n>>>"
        ],
    )

    result = V4CrewRunner(
        controller=controller,
        supervisor=supervisor,
        event_store=store,
    ).run(
        repo_root=tmp_path,
        goal="Fix source",
        verification_commands=["pytest -q"],
        max_rounds=1,
        spawn_policy="dynamic",
    )

    assert result["status"] == "ready_for_codex_accept"
    assert controller.ensured[0]["contract"].write_scope == ["src/"]
    assert supervisor.turns[0]["worker_id"] == "worker-source"
```

If `_source_worker()` helper does not accept `write_scope`, update it at the bottom of `tests/v4/test_crew_runner.py`:

```python
def _source_worker(
    *,
    worker_id: str = "worker-source",
    contract_id: str = "source_write",
    write_scope: list[str] | None = None,
) -> dict:
    return {
        "worker_id": worker_id,
        "role": WorkerRole.IMPLEMENTER.value,
        "status": "running",
        "capabilities": ["edit_source", "run_tests"],
        "authority_level": "source_write",
        "write_scope": write_scope or ["src/", "tests/"],
        "contract_id": contract_id,
        "workspace_path": f"/tmp/{worker_id}",
        "terminal_pane": f"crew-{worker_id}:claude.0",
        "transcript_artifact": f"workers/{worker_id}/transcript.txt",
    }
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_crew_runner.py::test_v4_crew_runner_does_not_reuse_incompatible_source_worker -q
```

Expected: FAIL because `_source_worker()` reuses `worker-docs` instead of spawning `worker-source`.

- [ ] **Step 3: Remove fallback**

In `src/codex_claude_orchestrator/v4/crew_runner.py`, replace `_source_worker()` body after planner selection with:

```python
        if selected is not None:
            return selected
        return None
```

Remove this old fallback block:

```python
        workers = [
            worker
            for worker in details.get("workers", [])
            if worker.get("status", "running") not in {"failed", "stopped"}
        ]
        return next((worker for worker in workers if worker.get("role") == WorkerRole.IMPLEMENTER.value), None)
```

- [ ] **Step 4: Run crew runner tests**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_crew_runner.py -q
```

Expected: all crew runner tests pass.

- [ ] **Step 5: Commit Task 3**

```bash
git add src/codex_claude_orchestrator/v4/crew_runner.py tests/v4/test_crew_runner.py
git commit -m "fix: remove unsafe source worker fallback"
```

---

### Task 4: Initialize Transcript Cursor Before Send

**Files:**
- Modify: `src/codex_claude_orchestrator/v4/adapters/tmux_claude.py`
- Modify: `tests/v4/test_tmux_claude_adapter.py`

- [ ] **Step 1: Write failing tmux adapter test**

Add this fake session class below `FakeNativeSession`:

```python
class TranscriptWritingNativeSession(FakeNativeSession):
    def __init__(self, transcript_path: Path):
        super().__init__()
        self.transcript_path = transcript_path
        self.observe_exception = RuntimeError("capture-pane failed")

    def send(self, **kwargs):
        result = super().send(**kwargs)
        self.transcript_path.write_text(
            self.transcript_path.read_text(encoding="utf-8") + "during send\nmarker-1\n",
            encoding="utf-8",
        )
        return result
```

Add this test near existing transcript cursor tests:

```python
def test_tmux_adapter_initializes_transcript_cursor_before_send(tmp_path: Path):
    transcript = tmp_path / "transcript.txt"
    transcript.write_text("before turn\n", encoding="utf-8")
    native = TranscriptWritingNativeSession(transcript)
    adapter = ClaudeCodeTmuxAdapter(native_session=native)
    adapter.register_worker(
        WorkerSpec(
            crew_id="crew-1",
            worker_id="worker-1",
            runtime_type="tmux_claude",
            contract_id="contract-1",
            terminal_pane="pane-1",
            transcript_artifact=str(transcript),
        )
    )
    turn = TurnEnvelope(
        crew_id="crew-1",
        worker_id="worker-1",
        turn_id="turn-1",
        round_id="round-1",
        phase="source",
        message="Implement",
        expected_marker="marker-1",
    )

    adapter.deliver_turn(turn)
    events = list(adapter.watch_turn(turn))

    assert [event.type for event in events] == [
        "runtime.output.appended",
        "marker.detected",
        "runtime.observe_failed",
    ]
    assert events[0].payload["text"] == "during send\nmarker-1\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_tmux_claude_adapter.py::test_tmux_adapter_initializes_transcript_cursor_before_send -q
```

Expected: FAIL because no `runtime.output.appended` is emitted; the cursor was initialized after `send()`.

- [ ] **Step 3: Move initialization before send**

In `src/codex_claude_orchestrator/v4/adapters/tmux_claude.py`, update `deliver_turn()` to initialize before `send()`:

```python
    def deliver_turn(self, turn: TurnEnvelope) -> DeliveryResult:
        worker = self._workers.get(turn.worker_id)
        terminal_pane = _terminal_pane_for(turn, worker)
        self._initialize_filesystem_stream(turn, worker)
        result = self._native_session.send(
            terminal_pane=terminal_pane,
            message=_compiled_turn_message(turn),
            turn_marker=turn.expected_marker,
        )
        marker = _non_empty_str(result.get("marker")) or turn.expected_marker
        reason = _non_empty_str(result.get("reason"))
        if result.get("delivered") is False or result.get("ok") is False:
            return DeliveryResult(
                delivered=False,
                marker=marker,
                reason=reason,
            )
        return DeliveryResult(
            delivered=True,
            marker=marker,
            reason=reason or "sent to tmux pane",
        )
```

- [ ] **Step 4: Run tmux adapter tests**

Run:

```bash
.venv/bin/python -m pytest tests/v4/test_tmux_claude_adapter.py -q
```

Expected: all tmux adapter tests pass.

- [ ] **Step 5: Commit Task 4**

```bash
git add src/codex_claude_orchestrator/v4/adapters/tmux_claude.py tests/v4/test_tmux_claude_adapter.py
git commit -m "fix: initialize transcript cursor before send"
```

---

### Task 5: Update Current Issues Documentation and Verify

**Files:**
- Modify: `docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md`

- [ ] **Step 1: Run focused V4/CLI regression suite**

Run:

```bash
.venv/bin/python -m pytest tests/v4 tests/cli/test_cli.py -q
```

Expected: all tests pass.

- [ ] **Step 2: Run full test suite**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass. Record the exact count, for example `559 passed`.

- [ ] **Step 3: Update current issues document**

In `docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md`:

- Change the status line from reopening the 2 P1 and 1 P2 to saying those issues are closed.
- Move the three reopened sections under `当前已关闭的问题`.
- Update the priority table rows:

```markdown
| Closed | accept 强制要求 `crew.ready_for_accept` / review OK / 无 blocking challenge | 已关闭 |
| Closed | source worker fallback 绕过 write scope 兼容性 | 已关闭 |
| Closed | transcript cursor 初始化发生在 send 之后 | 已关闭 |
```

- Update the test result block to the exact full-suite count from Step 2.
- Update completion criteria to say these checks are now satisfied, not pending.

- [ ] **Step 4: Search docs for stale reopened wording**

Run:

```bash
rg -n "未解决|重新打开|reopens|source worker fallback|transcript cursor 初始化发生在 send 之后|accept 没有强制要求" docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md docs/superpowers/specs/2026-05-03-v4-accept-readiness-worker-safety-design.md
```

Expected:

- The current issues document should not say the three issues are unresolved.
- The design spec may still mention the original problem statements as context.

- [ ] **Step 5: Run full suite again after docs update**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: same all-pass result as Step 2.

- [ ] **Step 6: Commit Task 5**

```bash
git add docs/superpowers/plans/2026-05-02-v4-current-issues.zh.md
git commit -m "docs: close v4 accept readiness issues"
```

---

## Final Verification

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python -m pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Inspect git status**

```bash
git status --short
```

Expected: only unrelated pre-existing workspace changes remain, or a clean tree if implementing in an isolated worktree.

- [ ] **Step 3: Summarize implementation**

Report:

- `AcceptReadinessGate` was added and integrated into `V4MergeTransaction`.
- `crew.ready_for_accept` events now carry `round_id`.
- V4 merge inputs are filtered to the ready round.
- Source worker fallback no longer bypasses planner compatibility.
- Transcript cursor initializes before `send()`.
- Focused and full test results.
