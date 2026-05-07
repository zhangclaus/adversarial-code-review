from __future__ import annotations

import json
from pathlib import Path

_KEY_EVENT_TYPES = frozenset([
    "crew.started",
    "turn.completed",
    "turn.failed",
    "turn.timeout",
    "challenge.issued",
    "repair.completed",
    "review.verdict",
    "readiness.evaluated",
    "crew.ready_for_accept",
])


def _worker_summary(worker: dict) -> str:
    status = worker.get("status", "unknown")
    role = worker.get("role", "unknown")
    return f"{role} - {status}"


def _extract_latest_summary(blackboard: list[dict]) -> str:
    """Extract the content of the latest summary entry."""
    summaries = [e for e in blackboard if e.get("type") == "summary"]
    if not summaries:
        return ""
    latest = max(summaries, key=lambda e: e.get("timestamp", ""))
    return latest.get("content", "")


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


def _check_verification_passed(raw: dict) -> bool:
    blackboard = raw.get("blackboard", [])
    for entry in reversed(blackboard):
        if entry.get("type") == "verification":
            return entry.get("content", "").lower().startswith("pass")
    return False


def _count_failures(raw: dict) -> int:
    blackboard = raw.get("blackboard", [])
    return sum(1 for e in blackboard if e.get("type") == "verification" and "fail" in e.get("content", "").lower())


def _extract_changed_files(raw: dict) -> list[str]:
    blackboard = raw.get("blackboard", [])
    files = []
    for entry in blackboard:
        if entry.get("type") == "patch" and "files" in entry:
            files.extend(entry["files"])
    return list(dict.fromkeys(files))


def compress_blackboard(
    entries: list[dict],
    *,
    limit: int = 10,
    worker_id: str | None = None,
    entry_type: str | None = None,
) -> list[dict]:
    filtered = entries
    if worker_id is not None:
        filtered = [e for e in filtered if e.get("actor_id") == worker_id]
    if entry_type is not None:
        filtered = [e for e in filtered if e.get("type") == entry_type]
    return filtered[-limit:]


def filter_events(events: list[dict], *, limit: int = 20) -> list[dict]:
    key_events = [e for e in events if e.get("type") in _KEY_EVENT_TYPES]
    return key_events[-limit:]


def read_latest_outbox(repo_root: Path, crew_id: str, worker_id: str) -> dict | None:
    """Read the latest outbox JSON for a worker. Returns None if not found."""
    outbox_dir = (
        repo_root / ".orchestrator" / "crews" / crew_id
        / "artifacts" / "v4" / "workers" / worker_id / "outbox"
    )
    if not outbox_dir.is_dir():
        return None

    json_files = sorted(outbox_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
    for path in reversed(json_files):
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
    return None


def compress_observe_result(
    raw_observation: dict,
    outbox: dict | None = None,
    *,
    worker_id: str = "",
) -> dict:
    """Extract structured report from worker observation + outbox data."""
    if outbox:
        status = outbox.get("status")
        if not status:
            status = "completed" if raw_observation.get("marker_seen") else "running"
        return {
            "worker_id": outbox.get("worker_id", worker_id),
            "status": status,
            "summary": outbox.get("summary", ""),
            "changed_files": outbox.get("changed_files", []),
            "risks": outbox.get("risks", []),
            "next_suggested_action": outbox.get("next_suggested_action", ""),
            "messages": raw_observation.get("message_blocks", []),
            "marker_seen": raw_observation.get("marker_seen", False),
        }

    marker_seen = raw_observation.get("marker_seen", False)
    return {
        "worker_id": worker_id,
        "status": "completed" if marker_seen else "running",
        "summary": "",
        "changed_files": [],
        "risks": [],
        "next_suggested_action": "",
        "messages": raw_observation.get("message_blocks", []),
        "marker_seen": marker_seen,
    }
