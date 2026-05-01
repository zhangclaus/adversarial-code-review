from pathlib import Path

from codex_claude_orchestrator.v4.event_store import SQLiteEventStore
from codex_claude_orchestrator.v4.projections import CrewProjection


def test_projection_builds_turn_status_from_events(tmp_path: Path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    store.append(stream_id="crew-1", type="crew.started", crew_id="crew-1", payload={"goal": "Fix tests"})
    store.append(stream_id="crew-1", type="turn.requested", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")
    store.append(stream_id="crew-1", type="turn.delivered", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")
    store.append(stream_id="crew-1", type="turn.completed", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")

    projection = CrewProjection.from_events(store.list_stream("crew-1"))

    assert projection.crew_id == "crew-1"
    assert projection.goal == "Fix tests"
    assert projection.turns["turn-1"].status == "completed"


def test_projection_reports_waiting_turn():
    projection = CrewProjection.from_events([])

    assert projection.status == "empty"
    assert projection.turns == {}
