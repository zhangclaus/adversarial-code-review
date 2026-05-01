from pathlib import Path

from codex_claude_orchestrator.v4.event_store import SQLiteEventStore
from codex_claude_orchestrator.v4.reconciler import Reconciler


def test_reconciler_marks_delivered_turn_without_completion_as_inconclusive(tmp_path: Path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    store.append(stream_id="crew-1", type="turn.requested", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")
    store.append(stream_id="crew-1", type="turn.delivered", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")

    event = Reconciler(event_store=store).reconcile_turn("crew-1", "turn-1")

    assert event.type == "turn.inconclusive"
    assert "delivered without completion" in event.payload["reason"]


def test_reconciler_does_not_duplicate_existing_completion(tmp_path: Path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    store.append(stream_id="crew-1", type="turn.delivered", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")
    store.append(stream_id="crew-1", type="turn.completed", crew_id="crew-1", worker_id="worker-1", turn_id="turn-1")

    event = Reconciler(event_store=store).reconcile_turn("crew-1", "turn-1")

    assert event is None
