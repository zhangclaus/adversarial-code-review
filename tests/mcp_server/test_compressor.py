from codex_claude_orchestrator.mcp_server.context.compressor import (
    compress_crew_status,
    compress_blackboard,
    filter_events,
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
