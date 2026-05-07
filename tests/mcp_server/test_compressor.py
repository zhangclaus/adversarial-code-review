import json
from pathlib import Path

from codex_claude_orchestrator.mcp_server.context.compressor import (
    compress_crew_status,
    compress_blackboard,
    compress_observe_result,
    filter_events,
    read_latest_outbox,
)


def test_compress_crew_status_basic():
    raw = {
        "crew": {"crew_id": "c1", "root_goal": "实现登录", "status": "running"},
        "workers": [
            {"worker_id": "w1", "role": "explorer", "status": "idle"},
            {"worker_id": "w2", "role": "implementer", "status": "busy"},
        ],
        "blackboard": [],
        "decisions": [],
        "messages": [],
    }
    result = compress_crew_status(raw)
    assert result["crew_id"] == "c1"
    assert result["goal"] == "实现登录"
    assert result["status"] == "running"
    assert len(result["workers"]) == 2
    assert result["workers"][0]["id"] == "w1"
    assert result["workers"][0]["role"] == "explorer"


def test_compress_crew_status_workers_summary():
    raw = {
        "crew": {"crew_id": "c1", "root_goal": "test", "status": "running"},
        "workers": [
            {"worker_id": "w1", "role": "explorer", "status": "idle"},
        ],
        "blackboard": [],
        "decisions": [],
        "messages": [],
    }
    result = compress_crew_status(raw)
    assert "summary" in result["workers"][0]


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


def test_compress_blackboard_default_limit():
    entries = [{"entry_id": f"e{i}", "content": f"item {i}"} for i in range(30)]
    result = compress_blackboard(entries)
    assert len(result) == 10


def test_compress_blackboard_filter_by_worker_id():
    entries = [
        {"entry_id": "e1", "actor_id": "w1", "content": "a"},
        {"entry_id": "e2", "actor_id": "w2", "content": "b"},
        {"entry_id": "e3", "actor_id": "w1", "content": "c"},
    ]
    result = compress_blackboard(entries, worker_id="w1")
    assert len(result) == 2


def test_compress_blackboard_filter_by_type():
    entries = [
        {"entry_id": "e1", "type": "fact", "content": "a"},
        {"entry_id": "e2", "type": "decision", "content": "b"},
        {"entry_id": "e3", "type": "fact", "content": "c"},
    ]
    result = compress_blackboard(entries, entry_type="fact")
    assert len(result) == 2


def test_filter_events_keeps_key_types():
    events = [
        {"type": "crew.started"},
        {"type": "turn.delivered"},
        {"type": "turn.completed"},
        {"type": "scope.evaluated"},
        {"type": "challenge.issued"},
        {"type": "review.verdict"},
    ]
    result = filter_events(events)
    types = [e["type"] for e in result]
    assert "crew.started" in types
    assert "turn.completed" in types
    assert "challenge.issued" in types
    assert "turn.delivered" not in types
    assert "scope.evaluated" not in types


def test_filter_events_respects_limit():
    events = [{"type": "turn.completed", "i": i} for i in range(20)]
    result = filter_events(events, limit=5)
    assert len(result) == 5


# --- read_latest_outbox ---


def test_read_latest_outbox_returns_latest_turn(tmp_path: Path):
    """Outbox with multiple turns returns the one with the highest modification time."""
    outbox_dir = tmp_path / ".orchestrator" / "crews" / "c1" / "artifacts" / "v4" / "workers" / "w1" / "outbox"
    outbox_dir.mkdir(parents=True)
    (outbox_dir / "turn-1.json").write_text(json.dumps({
        "crew_id": "c1", "worker_id": "w1", "turn_id": "turn-1",
        "status": "completed", "summary": "first turn",
    }))
    (outbox_dir / "turn-2.json").write_text(json.dumps({
        "crew_id": "c1", "worker_id": "w1", "turn_id": "turn-2",
        "status": "completed", "summary": "second turn",
    }))
    result = read_latest_outbox(tmp_path, "c1", "w1")
    assert result is not None
    assert result["turn_id"] == "turn-2"
    assert result["summary"] == "second turn"


def test_read_latest_outbox_returns_none_when_no_outbox(tmp_path: Path):
    """No outbox directory returns None."""
    result = read_latest_outbox(tmp_path, "c1", "w1")
    assert result is None


def test_read_latest_outbox_returns_none_when_empty_dir(tmp_path: Path):
    """Empty outbox directory returns None."""
    outbox_dir = tmp_path / ".orchestrator" / "crews" / "c1" / "artifacts" / "v4" / "workers" / "w1" / "outbox"
    outbox_dir.mkdir(parents=True)
    result = read_latest_outbox(tmp_path, "c1", "w1")
    assert result is None


def test_read_latest_outbox_handles_invalid_json(tmp_path: Path):
    """Invalid JSON in outbox file is skipped."""
    outbox_dir = tmp_path / ".orchestrator" / "crews" / "c1" / "artifacts" / "v4" / "workers" / "w1" / "outbox"
    outbox_dir.mkdir(parents=True)
    (outbox_dir / "turn-1.json").write_text("not valid json")
    result = read_latest_outbox(tmp_path, "c1", "w1")
    assert result is None


def test_read_latest_outbox_ignores_non_json_files(tmp_path: Path):
    """Non-JSON files in outbox directory are ignored."""
    outbox_dir = tmp_path / ".orchestrator" / "crews" / "c1" / "artifacts" / "v4" / "workers" / "w1" / "outbox"
    outbox_dir.mkdir(parents=True)
    (outbox_dir / "turn-1.txt").write_text("not json")
    (outbox_dir / "turn-2.json").write_text(json.dumps({
        "crew_id": "c1", "worker_id": "w1", "turn_id": "turn-2",
        "status": "completed", "summary": "actual result",
    }))
    result = read_latest_outbox(tmp_path, "c1", "w1")
    assert result is not None
    assert result["turn_id"] == "turn-2"


# --- compress_observe_result ---


def test_compress_observe_result_with_outbox():
    """When outbox is available, return structured report from outbox data."""
    raw_observation = {
        "snapshot": "full tmux output...",
        "marker_seen": True,
        "marker": "<<<CODEX_TURN_DONE>>>",
        "message_blocks": [{"from": "w1", "body": "msg1"}],
    }
    outbox = {
        "worker_id": "w-impl-1",
        "status": "completed",
        "summary": "实现了 JWT 中间件",
        "changed_files": ["src/auth/jwt.py", "tests/test_jwt.py"],
        "risks": ["未处理 token 刷新失败"],
        "next_suggested_action": "添加 refresh token 错误处理",
    }
    result = compress_observe_result(raw_observation, outbox)
    assert result["worker_id"] == "w-impl-1"
    assert result["status"] == "completed"
    assert result["summary"] == "实现了 JWT 中间件"
    assert result["changed_files"] == ["src/auth/jwt.py", "tests/test_jwt.py"]
    assert result["risks"] == ["未处理 token 刷新失败"]
    assert result["next_suggested_action"] == "添加 refresh token 错误处理"
    assert result["marker_seen"] is True
    assert result["messages"] == [{"from": "w1", "body": "msg1"}]
    assert "snapshot" not in result


def test_compress_observe_result_without_outbox_marker_seen():
    """Without outbox but marker seen, status is completed."""
    raw_observation = {
        "snapshot": "Worker finished implementing JWT middleware.\nSummary: Added RS256 signing.",
        "marker_seen": True,
        "marker": "<<<CODEX_TURN_DONE>>>",
        "message_blocks": [],
    }
    result = compress_observe_result(raw_observation, outbox=None, worker_id="w-explore")
    assert result["status"] == "completed"
    assert result["worker_id"] == "w-explore"
    assert result["marker_seen"] is True
    assert result["changed_files"] == []
    assert result["risks"] == []
    assert result["summary"] == ""
    assert "snapshot" not in result


def test_compress_observe_result_without_outbox_marker_not_seen():
    """Without outbox and marker not seen, status is running."""
    raw_observation = {
        "snapshot": "Still working on the implementation...",
        "marker_seen": False,
        "message_blocks": [],
    }
    result = compress_observe_result(raw_observation, outbox=None, worker_id="w-impl")
    assert result["status"] == "running"
    assert result["worker_id"] == "w-impl"
    assert result["marker_seen"] is False


def test_compress_observe_result_preserves_messages():
    """Message blocks are preserved in both paths."""
    raw_observation = {
        "snapshot": "done",
        "marker_seen": True,
        "message_blocks": [{"from": "w1", "body": "Need approval"}],
    }
    outbox = {"worker_id": "w1", "status": "completed", "summary": "done"}
    result = compress_observe_result(raw_observation, outbox)
    assert result["messages"] == [{"from": "w1", "body": "Need approval"}]


def test_compress_observe_result_outbox_without_status_falls_back_to_marker():
    """When outbox has no status field, fall back to marker_seen."""
    raw_observation = {"marker_seen": True, "message_blocks": []}
    outbox = {"worker_id": "w1", "summary": "done"}  # no "status" key
    result = compress_observe_result(raw_observation, outbox, worker_id="w1")
    assert result["status"] == "completed"  # marker_seen=True -> completed

    raw_observation2 = {"marker_seen": False, "message_blocks": []}
    result2 = compress_observe_result(raw_observation2, outbox, worker_id="w1")
    assert result2["status"] == "running"  # marker_seen=False -> running
