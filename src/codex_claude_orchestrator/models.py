from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return {item.name: _normalize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, dict):
        return {key: _normalize(inner) for key, inner in value.items()}
    if isinstance(value, list):
        return [_normalize(inner) for inner in value]
    return value


class WorkspaceMode(StrEnum):
    ISOLATED = "isolated"
    SHARED = "shared"
    READONLY = "readonly"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"
    COMPLETED = "completed"
    FAILED = "failed"


class FailureClass(StrEnum):
    INVOCATION_ERROR = "invocation_error"
    EXECUTION_ERROR = "execution_error"
    POLICY_BLOCK = "policy_block"
    QUALITY_REJECT = "quality_reject"
    MERGE_CONFLICT = "merge_conflict"


class NextAction(StrEnum):
    ACCEPT = "accept"
    RETRY_SAME_AGENT = "retry_same_agent"
    RETRY_WITH_TIGHTER_PROMPT = "retry_with_tighter_prompt"
    REROUTE_OTHER_AGENT = "reroute_other_agent"
    ASK_HUMAN = "ask_human"
    DISCARD_WORKSPACE = "discard_workspace"
    PROMOTE_TO_SHARED_MERGE = "promote_to_shared_merge"


@dataclass(slots=True)
class TaskRecord:
    task_id: str
    parent_task_id: str | None
    origin: str
    assigned_agent: str
    goal: str
    task_type: str
    scope: str
    workspace_mode: WorkspaceMode
    status: TaskStatus = TaskStatus.QUEUED
    priority: int = 50
    allowed_tools: list[str] = field(default_factory=list)
    stop_conditions: list[str] = field(default_factory=list)
    verification_expectations: list[str] = field(default_factory=list)
    human_notes: list[str] = field(default_factory=list)
    shared_write_allowed: bool = False
    expected_output_schema: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class RunRecord:
    run_id: str
    task_id: str
    agent: str
    adapter: str
    workspace_id: str
    started_at: str = field(default_factory=utc_now)
    ended_at: str | None = None
    status: TaskStatus = TaskStatus.RUNNING
    result_summary: str = ""
    failure_class: FailureClass | None = None
    next_action: NextAction | None = None
    adapter_invocation: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class EventRecord:
    event_id: str
    task_id: str
    run_id: str
    from_agent: str
    to_agent: str
    event_type: str
    timestamp: str = field(default_factory=utc_now)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class ArtifactRecord:
    artifact_id: str
    task_id: str
    run_id: str
    kind: str
    path_or_inline_data: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class WorkspaceAllocation:
    workspace_id: str
    path: Path
    mode: WorkspaceMode
    writable: bool
    baseline_snapshot: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class WorkerResult:
    raw_output: str
    stdout: str
    stderr: str
    exit_code: int
    structured_output: dict[str, Any] | None = None
    changed_files: list[str] = field(default_factory=list)
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


@dataclass(slots=True)
class EvaluationOutcome:
    accepted: bool
    next_action: NextAction
    summary: str
    failure_class: FailureClass | None = None
    needs_human: bool = False

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)
