from codex_claude_orchestrator.runtime.marker_policy import MarkerObservationPolicy


def test_marker_policy_completes_when_pane_snapshot_contains_exact_marker():
    observation = MarkerObservationPolicy().evaluate(
        snapshot="worker done\n<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        expected_marker="<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        transcript_text="",
        transcript_artifact="workers/w/transcript.txt",
    )

    assert observation.status == "completed"
    assert observation.marker_seen is True
    assert observation.reason == "marker found in pane snapshot"
    assert observation.evidence_refs == ["workers/w/transcript.txt"]


def test_marker_policy_completes_when_transcript_contains_marker():
    observation = MarkerObservationPolicy().evaluate(
        snapshot="last pane lines without marker",
        expected_marker="<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        transcript_text="older transcript\n<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        transcript_artifact="workers/w/transcript.txt",
    )

    assert observation.status == "completed"
    assert observation.marker_seen is True
    assert observation.reason == "marker found in transcript"


def test_marker_policy_reports_mismatch_for_contract_marker_only():
    observation = MarkerObservationPolicy().evaluate(
        snapshot="<<<CODEX_TURN_DONE crew=crew-1 contract=source_write>>>",
        expected_marker="<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        transcript_text="",
        contract_marker="<<<CODEX_TURN_DONE crew=crew-1 contract=source_write>>>",
    )

    assert observation.status == "mismatch"
    assert observation.marker_seen is False
    assert observation.reason == "contract marker found but expected turn marker was missing"


def test_marker_policy_waits_when_no_marker_is_present():
    observation = MarkerObservationPolicy().evaluate(
        snapshot="still working",
        expected_marker="<<<CODEX_TURN_DONE crew=crew-1 worker=w phase=p round=1>>>",
        transcript_text="still working",
    )

    assert observation.status == "waiting"
    assert observation.marker_seen is False
    assert observation.reason == "expected marker not found"
