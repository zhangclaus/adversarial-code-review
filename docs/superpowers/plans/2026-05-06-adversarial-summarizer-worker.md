# Adversarial Summarizer Worker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `summarizer` Worker template that auto-spawns when blackboard entries exceed 20, producing LLM-generated summaries verified by the Supervisor through accept/challenge.

**Architecture:** The summarizer is a regular Worker (Claude CLI in tmux) with readonly permissions. Trigger logic lives in `crew_blackboard` tool — when entries exceed 20 and no fresh summary exists, it async-spawns a summarizer via the existing `ensure_worker` path. The Supervisor reviews the summary like any other Worker output.

**Tech Stack:** Python 3.11, MCP (FastMCP), existing WorkerContract/WorkerPool infrastructure

---

### Task 1: Add `SUMMARY` to `BlackboardEntryType`

**Files:**
- Modify: `src/codex_claude_orchestrator/crew/models.py:61-69`

- [ ] **Step 1: Add SUMMARY enum value**

In `src/codex_claude_orchestrator/crew/models.py`, add `SUMMARY = "summary"` to the `BlackboardEntryType` enum:

```python
class BlackboardEntryType(StrEnum):
    FACT = "fact"
    CLAIM = "claim"
    QUESTION = "question"
    RISK = "risk"
    PATCH = "patch"
    VERIFICATION = "verification"
    REVIEW = "review"
    DECISION = "decision"
    SUMMARY = "summary"
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `pytest tests/crew/ -v`
Expected: All existing tests PASS (adding an enum value is backward-compatible)

- [ ] **Step 3: Commit**

```bash
git add src/codex_claude_orchestrator/crew/models.py
git commit -m "feat: add SUMMARY to BlackboardEntryType"
```

---

### Task 2: Add `summarizer` Worker template

**Files:**
- Modify: `src/codex_claude_orchestrator/mcp_server/tools/crew_lifecycle.py:20-53`
- Test: `tests/mcp_server/test_crew_lifecycle_tools.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/mcp_server/test_crew_lifecycle_tools.py`:

```python
def test_crew_spawn_summarizer_template():
    """crew_spawn with summarizer label creates readonly contract."""
    server = FakeServer()
    controller = MagicMock()
    controller.ensure_worker.return_value = {"worker_id": "ws1", "status": "running"}
    register_lifecycle_tools(server, controller)
    import asyncio
    result = asyncio.run(server.tools["crew_spawn"](
        repo="/repo", crew_id="c1", label="summarizer",
    ))
    data = json.loads(result[0].text)
    assert data["worker_id"] == "ws1"
    call_kwargs = controller.ensure_worker.call_args[1]
    assert call_kwargs["contract"].label == "summarizer"
    assert call_kwargs["contract"].authority_level.value == "readonly"
    assert call_kwargs["contract"].workspace_policy.value == "readonly"
    assert "inspect_code" in call_kwargs["contract"].required_capabilities
    assert "summary" in call_kwargs["contract"].mission.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/mcp_server/test_crew_lifecycle_tools.py::test_crew_spawn_summarizer_template -v`
Expected: FAIL — `summarizer` not in `WORKER_TEMPLATES`, falls through to custom label path with `source_write` authority

- [ ] **Step 3: Add summarizer template**

In `src/codex_claude_orchestrator/mcp_server/tools/crew_lifecycle.py`, add to `WORKER_TEMPLATES` dict (after `verification-failure-analyst`):

```python
    "summarizer": WorkerContract(
        contract_id="template-summarizer",
        label="summarizer",
        mission="Read all blackboard entries for this crew. Produce a concise summary covering: "
                "1) Key findings and facts, 2) Open risks, 3) Current progress, "
                "4) Pending challenges or unresolved questions. "
                "Write the summary to the blackboard as a 'summary' entry.",
        required_capabilities=["inspect_code"],
        authority_level=AuthorityLevel.READONLY,
        workspace_policy=WorkspacePolicy.READONLY,
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/mcp_server/test_crew_lifecycle_tools.py::test_crew_spawn_summarizer_template -v`
Expected: PASS

- [ ] **Step 5: Run all lifecycle tests**

Run: `pytest tests/mcp_server/test_crew_lifecycle_tools.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/codex_claude_orchestrator/mcp_server/tools/crew_lifecycle.py tests/mcp_server/test_crew_lifecycle_tools.py
git commit -m "feat: add summarizer worker template"
```

---

### Task 3: Add `_should_trigger_summarizer` helper

**Files:**
- Create: `src/codex_claude_orchestrator/mcp_server/context/summarizer_trigger.py`
- Test: `tests/mcp_server/test_summarizer_trigger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp_server/test_summarizer_trigger.py`:

```python
from codex_claude_orchestrator.mcp_server.context.summarizer_trigger import (
    should_trigger_summarizer,
)


def test_below_threshold_no_trigger():
    """Entries <= threshold should not trigger."""
    entries = [
        {"type": "fact", "content": f"entry {i}", "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(15)
    ]
    assert should_trigger_summarizer(entries, threshold=20) is False


def test_above_threshold_no_summary_triggers():
    """Entries > threshold with no summary should trigger."""
    entries = [
        {"type": "fact", "content": f"entry {i}", "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(25)
    ]
    assert should_trigger_summarizer(entries, threshold=20) is True


def test_above_threshold_fresh_summary_no_trigger():
    """Entries > threshold with a fresh summary (newest timestamp) should not trigger."""
    entries = [
        {"type": "fact", "content": f"entry {i}", "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(22)
    ]
    entries.append({
        "type": "summary", "content": "the summary",
        "timestamp": "2026-05-06T50:00:00",
    })
    assert should_trigger_summarizer(entries, threshold=20) is False


def test_above_threshold_stale_summary_triggers():
    """Entries > threshold with a stale summary (older than latest entry) should trigger."""
    entries = [
        {"type": "fact", "content": f"entry {i}", "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(22)
    ]
    entries.append({
        "type": "summary", "content": "old summary",
        "timestamp": "2026-05-06T01:00:00",
    })
    assert should_trigger_summarizer(entries, threshold=20) is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp_server/test_summarizer_trigger.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement `should_trigger_summarizer`**

Create `src/codex_claude_orchestrator/mcp_server/context/summarizer_trigger.py`:

```python
from __future__ import annotations


def should_trigger_summarizer(entries: list[dict], threshold: int = 20) -> bool:
    """Check if a summarizer worker should be spawned.

    Returns True when:
    - Blackboard entries exceed threshold
    - AND either no summary exists, or the latest summary is older than
      the latest non-summary entry.
    """
    if len(entries) <= threshold:
        return False
    summaries = [e for e in entries if e.get("type") == "summary"]
    if not summaries:
        return True
    latest_summary_ts = max(e.get("timestamp", "") for e in summaries)
    non_summaries = [e for e in entries if e.get("type") != "summary"]
    if not non_summaries:
        return False
    latest_entry_ts = max(e.get("timestamp", "") for e in non_summaries)
    return latest_entry_ts > latest_summary_ts
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp_server/test_summarizer_trigger.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/codex_claude_orchestrator/mcp_server/context/summarizer_trigger.py tests/mcp_server/test_summarizer_trigger.py
git commit -m "feat: add should_trigger_summarizer helper"
```

---

### Task 4: Add trigger logic to `crew_blackboard`

**Files:**
- Modify: `src/codex_claude_orchestrator/mcp_server/tools/crew_context.py:16-28`
- Test: `tests/mcp_server/test_crew_context_tools.py`

The `crew_blackboard` tool needs a `repo` parameter to call `ensure_worker`. This is additive — existing callers that don't pass `repo` still work (trigger is skipped).

- [ ] **Step 1: Write the failing tests**

Add to `tests/mcp_server/test_crew_context_tools.py`:

```python
def test_crew_blackboard_triggers_summarizer_when_over_threshold():
    """When blackboard has >20 entries and no fresh summary, spawn summarizer async."""
    from pathlib import Path
    from codex_claude_orchestrator.crew.models import AuthorityLevel
    server = FakeServer()
    controller = MagicMock()
    entries = [
        {"entry_id": f"e{i}", "type": "fact", "content": f"entry {i}",
         "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(25)
    ]
    controller.blackboard_entries.return_value = entries
    controller.ensure_worker.return_value = {"worker_id": "ws1", "status": "running"}
    register_context_tools(server, controller)
    import asyncio
    result = asyncio.run(server.tools["crew_blackboard"](crew_id="c1", repo="/repo"))
    data = json.loads(result[0].text)
    assert len(data) > 0
    controller.ensure_worker.assert_called_once()
    call_kwargs = controller.ensure_worker.call_args[1]
    assert call_kwargs["contract"].label == "summarizer"
    assert call_kwargs["repo_root"] == Path("/repo")


def test_crew_blackboard_no_trigger_when_under_threshold():
    """When blackboard has <=20 entries, no summarizer spawned."""
    server = FakeServer()
    controller = MagicMock()
    entries = [
        {"entry_id": f"e{i}", "type": "fact", "content": f"entry {i}",
         "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(10)
    ]
    controller.blackboard_entries.return_value = entries
    register_context_tools(server, controller)
    import asyncio
    result = asyncio.run(server.tools["crew_blackboard"](crew_id="c1", repo="/repo"))
    data = json.loads(result[0].text)
    assert len(data) > 0
    controller.ensure_worker.assert_not_called()


def test_crew_blackboard_no_trigger_when_fresh_summary():
    """When a fresh summary exists, no summarizer spawned even if over threshold."""
    server = FakeServer()
    controller = MagicMock()
    entries = [
        {"entry_id": f"e{i}", "type": "fact", "content": f"entry {i}",
         "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(22)
    ]
    entries.append({
        "entry_id": "s1", "type": "summary", "content": "the summary",
        "timestamp": "2026-05-06T50:00:00",
    })
    controller.blackboard_entries.return_value = entries
    register_context_tools(server, controller)
    import asyncio
    result = asyncio.run(server.tools["crew_blackboard"](crew_id="c1", repo="/repo"))
    data = json.loads(result[0].text)
    assert len(data) > 0
    controller.ensure_worker.assert_not_called()


def test_crew_blackboard_no_trigger_without_repo():
    """When repo is not provided, trigger is skipped even if over threshold."""
    server = FakeServer()
    controller = MagicMock()
    entries = [
        {"entry_id": f"e{i}", "type": "fact", "content": f"entry {i}",
         "timestamp": f"2026-05-06T{i:02d}:00:00"}
        for i in range(25)
    ]
    controller.blackboard_entries.return_value = entries
    register_context_tools(server, controller)
    import asyncio
    result = asyncio.run(server.tools["crew_blackboard"](crew_id="c1"))
    data = json.loads(result[0].text)
    assert len(data) > 0
    controller.ensure_worker.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp_server/test_crew_context_tools.py -k "trigger" -v`
Expected: FAIL — `repo` parameter not accepted, `ensure_worker` not called

- [ ] **Step 3: Add trigger logic to `crew_blackboard`**

Modify `src/codex_claude_orchestrator/mcp_server/tools/crew_context.py`. The full file becomes:

```python
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from mcp.server import Server
from mcp.types import TextContent

from codex_claude_orchestrator.mcp_server.context.compressor import (
    compress_blackboard,
    filter_events,
)
from codex_claude_orchestrator.mcp_server.context.summarizer_trigger import (
    should_trigger_summarizer,
)
from codex_claude_orchestrator.mcp_server.context.token_budget import truncate_json


def register_context_tools(server: Server, controller) -> None:

    def _spawn_summarizer_if_needed(crew_id: str, entries: list[dict], repo: str) -> None:
        """Spawn summarizer worker synchronously if needed."""
        from codex_claude_orchestrator.mcp_server.tools.crew_lifecycle import WORKER_TEMPLATES
        if not repo or not should_trigger_summarizer(entries):
            return
        contract = WORKER_TEMPLATES["summarizer"]
        controller.ensure_worker(
            repo_root=Path(repo),
            crew_id=crew_id,
            contract=contract,
        )

    @server.tool("crew_blackboard")
    async def crew_blackboard(
        crew_id: str,
        worker_id: str | None = None,
        entry_type: str | None = None,
        limit: int = 10,
        repo: str = "",
    ) -> list[TextContent]:
        """读取黑板条目（过滤后，默认最近 10 条）。"""
        entries = controller.blackboard_entries(crew_id=crew_id)
        _spawn_summarizer_if_needed(crew_id, entries, repo)
        filtered = compress_blackboard(entries, limit=limit, worker_id=worker_id, entry_type=entry_type)
        return [TextContent(type="text", text=truncate_json(filtered))]

    @server.tool("crew_events")
    async def crew_events(repo: str, crew_id: str, limit: int = 20) -> list[TextContent]:
        """读取关键事件（过滤中间事件，默认最近 20 条）。"""
        raw = controller.status(repo_root=Path(repo), crew_id=crew_id)
        events = raw.get("decisions", []) + raw.get("messages", [])
        filtered = filter_events(events, limit=limit)
        return [TextContent(type="text", text=truncate_json(filtered))]

    @server.tool("crew_observe")
    async def crew_observe(repo: str, crew_id: str, worker_id: str) -> list[TextContent]:
        """观察某个 Worker 的当前轮次输出。"""
        observation = controller.observe_worker(repo_root=Path(repo), crew_id=crew_id, worker_id=worker_id)
        return [TextContent(type="text", text=truncate_json(observation))]

    @server.tool("crew_changes")
    async def crew_changes(crew_id: str) -> list[TextContent]:
        """查看 Crew 的文件变更列表。"""
        changes = controller.changes(crew_id=crew_id)
        return [TextContent(type="text", text=json.dumps(changes, ensure_ascii=False))]

    @server.tool("crew_diff")
    async def crew_diff(crew_id: str, file: str | None = None) -> list[TextContent]:
        """查看具体文件的 diff。"""
        changes = controller.changes(crew_id=crew_id)
        if file:
            changes = [c for c in changes if c.get("file") == file]
        return [TextContent(type="text", text=truncate_json(changes))]
```

Note: `_spawn_summarizer_if_needed` is synchronous (not async). `ensure_worker` is a synchronous call that starts a tmux process. We call it inline before returning the blackboard data. This keeps the logic simple — the summarizer starts, and the Supervisor gets the current blackboard data in the same call.

- [ ] **Step 4: Run trigger tests**

Run: `pytest tests/mcp_server/test_crew_context_tools.py -k "trigger" -v`
Expected: All 4 new tests PASS

- [ ] **Step 5: Run all context tests**

Run: `pytest tests/mcp_server/test_crew_context_tools.py -v`
Expected: All tests PASS (existing tests don't pass `repo`, so trigger is skipped)

- [ ] **Step 6: Commit**

```bash
git add src/codex_claude_orchestrator/mcp_server/tools/crew_context.py tests/mcp_server/test_crew_context_tools.py
git commit -m "feat: add summarizer auto-trigger to crew_blackboard"
```

---

### Task 5: Update `crew_status` to include latest summary

**Files:**
- Modify: `src/codex_claude_orchestrator/mcp_server/context/compressor.py:22-41`
- Test: `tests/mcp_server/test_compressor.py` (create if not exists)

- [ ] **Step 1: Write the failing tests**

Create `tests/mcp_server/test_compressor.py`:

```python
from codex_claude_orchestrator.mcp_server.context.compressor import compress_crew_status


def test_compress_crew_status_includes_latest_summary():
    """compress_crew_status extracts the latest summary entry from blackboard."""
    raw = {
        "crew": {"crew_id": "c1", "root_goal": "test", "status": "running"},
        "workers": [],
        "blackboard": [
            {"type": "fact", "content": "old fact", "timestamp": "2026-05-06T10:00:00"},
            {"type": "summary", "content": "first summary", "timestamp": "2026-05-06T11:00:00"},
            {"type": "fact", "content": "new fact", "timestamp": "2026-05-06T12:00:00"},
            {"type": "summary", "content": "latest summary", "timestamp": "2026-05-06T13:00:00"},
        ],
    }
    result = compress_crew_status(raw)
    assert result["summary"] == "latest summary"


def test_compress_crew_status_no_summary():
    """compress_crew_status returns empty string when no summary exists."""
    raw = {
        "crew": {"crew_id": "c1", "root_goal": "test", "status": "running"},
        "workers": [],
        "blackboard": [
            {"type": "fact", "content": "a fact", "timestamp": "2026-05-06T10:00:00"},
        ],
    }
    result = compress_crew_status(raw)
    assert result["summary"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/mcp_server/test_compressor.py -v`
Expected: FAIL — `compress_crew_status` returns dict without `summary` key

- [ ] **Step 3: Add summary extraction to `compress_crew_status`**

In `src/codex_claude_orchestrator/mcp_server/context/compressor.py`, modify `compress_crew_status`:

```python
def compress_crew_status(raw: dict) -> dict:
    crew = raw.get("crew", {})
    workers = raw.get("workers", [])
    blackboard = raw.get("blackboard", [])
    return {
        "crew_id": crew.get("crew_id"),
        "goal": crew.get("root_goal"),
        "status": crew.get("status"),
        "workers": [
            {
                "id": w.get("worker_id"),
                "role": w.get("role"),
                "status": w.get("status"),
                "summary": _worker_summary(w),
            }
            for w in workers
        ],
        "verification_passed": _check_verification_passed(raw),
        "verification_failures": _count_failures(raw),
        "changed_files": _extract_changed_files(raw),
        "summary": _extract_latest_summary(blackboard),
    }
```

Add the helper function:

```python
def _extract_latest_summary(blackboard: list[dict]) -> str:
    """Extract the content of the latest summary entry."""
    summaries = [e for e in blackboard if e.get("type") == "summary"]
    if not summaries:
        return ""
    latest = max(summaries, key=lambda e: e.get("timestamp", ""))
    return latest.get("content", "")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/mcp_server/test_compressor.py -v`
Expected: All PASS

- [ ] **Step 5: Run all compressor-related tests**

Run: `pytest tests/mcp_server/ -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/codex_claude_orchestrator/mcp_server/context/compressor.py tests/mcp_server/test_compressor.py
git commit -m "feat: include latest summary in compress_crew_status"
```

---

### Task 6: Update orchestration skill

**Files:**
- Modify: `skills/orchestration-default.md:20-31`

- [ ] **Step 1: Add summarizer to Worker Templates table**

In `skills/orchestration-default.md`, add the `summarizer` row to the Worker Templates table:

```markdown
| Label | Authority | Workspace | Use when |
|-------|-----------|-----------|----------|
| `targeted-code-editor` | source_write | worktree | Implementing code changes |
| `repo-context-scout` | readonly | readonly | Need to explore codebase first |
| `patch-risk-auditor` | readonly | readonly | Reviewing changes before accept |
| `verification-failure-analyst` | source_write | worktree | Diagnosing repeated test failures |
| `summarizer` | readonly | readonly | Auto-spawns when blackboard > 20 entries |
```

- [ ] **Step 2: Add auto-summarization note**

Add a new section after the Worker Templates section:

```markdown
## Auto-Summarization

When `crew_blackboard` detects more than 20 entries without a fresh summary, a `summarizer` Worker is automatically spawned. The summarizer reads all blackboard entries and writes a concise summary back as a `summary` entry.

You can:
- Read the summary: `crew_blackboard(crew_id, entry_type="summary")`
- Review it in `crew_status` output (the `summary` field)
- Challenge it: `crew_challenge(crew_id, summary="summary missed X", task_id=summarizer_id)`
```

- [ ] **Step 3: Commit**

```bash
git add skills/orchestration-default.md
git commit -m "docs: add summarizer to orchestration skill"
```

---

### Task 7: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Verify test count increased**

Run: `pytest --co -q | tail -1`
Expected: ~651 tests (641 original + ~10 new)

- [ ] **Step 3: Final commit if needed**

If any test files were missed, add and commit.
