from __future__ import annotations

import pytest

from codex_claude_orchestrator.v4.accept_readiness import AcceptReadinessGate
from codex_claude_orchestrator.v4.event_store import SQLiteEventStore


def test_accept_readiness_blocks_missing_ready_event(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")

    decision = AcceptReadinessGate(store).evaluate("crew-1")

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
    challenge = _challenge(store, severity="block")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "blocking_challenge_open"
    assert decision.review_event_id == review.event_id
    assert decision.blocking_challenge_event_ids == [challenge.event_id]


def test_accept_readiness_blocks_challenge_with_missing_severity_before_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    challenge = _challenge(store, severity=None)
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "blocking_challenge_open"
    assert decision.blocking_challenge_event_ids == [challenge.event_id]


def test_accept_readiness_ignores_non_blocking_challenge_before_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    _challenge(store, severity="warn")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is True
    assert decision.reason == "ready"
    assert decision.blocking_challenge_event_ids == []


def test_accept_readiness_allows_repaired_blocking_challenge_before_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    _challenge(store, challenge_id="challenge-1", severity="block")
    _repair_completed(store, challenge_id="challenge-1", outcome="fixed")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is True
    assert decision.reason == "ready"
    assert decision.blocking_challenge_event_ids == []


def test_accept_readiness_blocks_unfixed_challenge_before_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    challenge = _challenge(store, challenge_id="challenge-1", severity="block")
    _repair_completed(store, challenge_id="challenge-1", outcome="not_fixed")
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "blocking_challenge_open"
    assert decision.blocking_challenge_event_ids == [challenge.event_id]


def test_accept_readiness_blocks_post_ready_challenge_even_when_later_repaired(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    _verification_passed(store)
    _ready(store)
    challenge = _challenge(store, challenge_id="challenge-1", severity="block")
    _repair_completed(store, challenge_id="challenge-1", outcome="fixed")

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_invalidated_after_ready"
    assert decision.invalidating_event_ids == [challenge.event_id]


@pytest.mark.parametrize(
    "event_type",
    [
        "human.required",
        "turn.failed",
        "turn.timeout",
        "turn.inconclusive",
        "verification.failed",
        "challenge.issued",
    ],
)
def test_accept_readiness_blocks_invalidating_events_after_ready(tmp_path, event_type):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="warn")
    _verification_passed(store)
    _ready(store)
    invalidating_event = store.append(
        stream_id="crew-1",
        type=event_type,
        crew_id="crew-1",
        round_id="round-1",
        payload={"severity": "block", "command": "pytest -q"},
    )

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_invalidated_after_ready"
    assert decision.invalidating_event_ids == [invalidating_event.event_id]


@pytest.mark.parametrize("status", ["fail", "error", ""])
def test_accept_readiness_rejects_non_acceptable_review_statuses(tmp_path, status):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status=status)
    _verification_passed(store)
    _ready(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing_review"


def test_accept_readiness_ignores_review_completed_after_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _verification_passed(store)
    _ready(store)
    _review_completed(store, status="ok")

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing_review"


def test_accept_readiness_ignores_verification_passed_after_ready(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    _review_completed(store, status="ok")
    _ready(store)
    _verification_passed(store)

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is False
    assert decision.reason == "ready_round_missing_verification"


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


def test_accept_readiness_uses_ready_payload_round_id_fallback(tmp_path):
    store = SQLiteEventStore(tmp_path / "events.sqlite3")
    review = _review_completed(store, status="ok")
    verification = _verification_passed(store)
    ready = store.append(
        stream_id="crew-1",
        type="crew.ready_for_accept",
        crew_id="crew-1",
        payload={"round_id": "round-1"},
    )

    decision = AcceptReadinessGate(event_store=store).evaluate("crew-1")

    assert decision.allowed is True
    assert decision.reason == "ready"
    assert decision.round_id == "round-1"
    assert decision.ready_event_id == ready.event_id
    assert decision.review_event_id == review.event_id
    assert decision.verification_event_ids == [verification.event_id]


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


def _challenge(
    store,
    *,
    round_id="round-1",
    challenge_id="challenge-1",
    severity="block",
):
    payload = {"challenge_id": challenge_id, "finding": "review block"}
    if severity is not None:
        payload["severity"] = severity
    return store.append(
        stream_id="crew-1",
        type="challenge.issued",
        crew_id="crew-1",
        worker_id="worker-source",
        round_id=round_id,
        payload=payload,
    )


def _repair_completed(
    store,
    *,
    round_id="round-1",
    challenge_id="challenge-1",
    outcome="fixed",
):
    return store.append(
        stream_id="crew-1",
        type="repair.completed",
        crew_id="crew-1",
        worker_id="worker-source",
        round_id=round_id,
        payload={"challenge_id": challenge_id, "outcome": outcome},
    )
