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
