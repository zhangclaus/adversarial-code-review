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
