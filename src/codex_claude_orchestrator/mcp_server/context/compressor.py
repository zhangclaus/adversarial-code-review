from __future__ import annotations

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


def compress_crew_status(raw: dict) -> dict:
    crew = raw.get("crew", {})
    workers = raw.get("workers", [])
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
