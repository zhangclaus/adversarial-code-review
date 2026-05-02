"""Governed learning recorders for V4 runtime events."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any

from codex_claude_orchestrator.v4.adversarial_models import (
    ActivationPayload,
    ApprovalPayload,
    CandidatePayload,
    LearningNotePayload,
    WorkerQualityPayload,
)
from codex_claude_orchestrator.v4.event_store_protocol import EventStore
from codex_claude_orchestrator.v4.events import AgentEvent, normalize
from codex_claude_orchestrator.v4.paths import V4Paths


_worker_quality_projection_lock = Lock()


class LearningRecorder:
    def __init__(self, *, event_store: EventStore, paths: V4Paths) -> None:
        self._events = event_store
        self._paths = paths

    def create_note(
        self,
        *,
        note_id: str,
        source_challenge_ids: list[str],
        source_event_ids: list[str],
        failure_class: str,
        lesson: str,
        trigger_conditions: list[str],
        scope: str,
    ) -> AgentEvent:
        payload = LearningNotePayload(
            note_id=note_id,
            source_challenge_ids=list(source_challenge_ids),
            source_event_ids=list(source_event_ids),
            failure_class=failure_class,
            lesson=lesson,
            trigger_conditions=list(trigger_conditions),
            scope=scope,
        ).to_payload()
        artifact_ref = _artifact_ref(self._paths, self._paths.learning_note_path(note_id))
        idempotency_key = _idempotency_key(
            self._paths.crew_id,
            "learning.note_created",
            {"note_id": note_id},
        )
        if existing := self._events.get_by_idempotency_key(idempotency_key):
            return existing
        _write_json_atomic(self._paths.learning_note_path(note_id), payload)
        return self._events.append(
            stream_id=self._paths.crew_id,
            type="learning.note_created",
            crew_id=self._paths.crew_id,
            idempotency_key=idempotency_key,
            payload=payload,
            artifact_refs=[artifact_ref],
        )


class SkillCandidateGate:
    def __init__(self, *, event_store: EventStore, paths: V4Paths) -> None:
        self._events = event_store
        self._paths = paths

    def create_candidate(
        self,
        *,
        candidate_id: str,
        source_note_ids: list[str],
        source_event_ids: list[str],
        summary: str,
        trigger_conditions: list[str],
        body: str,
    ) -> AgentEvent:
        artifact_path = self._paths.skill_candidate_path(candidate_id)
        artifact_ref = _artifact_ref(self._paths, artifact_path)
        payload = CandidatePayload(
            candidate_id=candidate_id,
            source_note_ids=list(source_note_ids),
            source_event_ids=list(source_event_ids),
            kind="skill",
            summary=summary,
            trigger_conditions=list(trigger_conditions),
            artifact_ref=artifact_ref,
        ).to_payload()
        idempotency_key = _idempotency_key(
            self._paths.crew_id,
            "skill.candidate_created",
            {"candidate_id": candidate_id},
        )
        if existing := self._events.get_by_idempotency_key(idempotency_key):
            return existing
        _write_json_atomic(artifact_path, {**payload, "body": body})
        return self._append_candidate_event(
            event_type="skill.candidate_created",
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[artifact_ref],
            idempotency_key=idempotency_key,
        )

    def approve_candidate(
        self,
        *,
        candidate_id: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        return self._append_decision(
            candidate_id=candidate_id,
            event_type="skill.approved",
            decision="approved",
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        )

    def reject_candidate(
        self,
        *,
        candidate_id: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        return self._append_decision(
            candidate_id=candidate_id,
            event_type="skill.rejected",
            decision="rejected",
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        )

    def activate_candidate(
        self,
        *,
        candidate_id: str,
        activation_id: str,
        activated_by: str,
        activated_at: str,
        rollback_plan: str = "Deactivate through a follow-up governed learning event.",
    ) -> AgentEvent:
        artifact_path = self._paths.skill_candidate_path(candidate_id)
        artifact_ref = _require_artifact(self._paths, artifact_path)
        idempotency_key = _idempotency_key(
            self._paths.crew_id,
            "skill.activated",
            {"candidate_id": candidate_id, "activation_id": activation_id},
        )
        if existing := self._events.get_by_idempotency_key(idempotency_key):
            return existing
        _require_candidate_approved(
            events=self._events,
            crew_id=self._paths.crew_id,
            candidate_id=candidate_id,
            event_prefix="skill.",
        )
        payload = ActivationPayload(
            candidate_id=candidate_id,
            activation_id=activation_id,
            activated_by=activated_by,
            activated_at=activated_at,
            active_artifact_ref=artifact_ref,
            rollback_plan=rollback_plan,
        ).to_payload()
        return self._append_candidate_event(
            event_type="skill.activated",
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[artifact_ref],
            idempotency_key=idempotency_key,
        )

    def _append_decision(
        self,
        *,
        candidate_id: str,
        event_type: str,
        decision: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        payload = ApprovalPayload(
            candidate_id=candidate_id,
            decision=decision,
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        ).to_payload()
        return self._append_candidate_event(
            event_type=event_type,
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[],
            idempotency_key=_idempotency_key(
                self._paths.crew_id,
                event_type,
                {"candidate_id": candidate_id, "decision": decision},
            ),
        )

    def _append_candidate_event(
        self,
        *,
        event_type: str,
        candidate_id: str,
        payload: dict[str, Any],
        artifact_refs: list[str],
        idempotency_key: str = "",
    ) -> AgentEvent:
        if not idempotency_key:
            idempotency_key = _idempotency_key(
                self._paths.crew_id,
                event_type,
                {"candidate_id": candidate_id, "payload": payload},
            )
        return self._events.append(
            stream_id=self._paths.crew_id,
            type=event_type,
            crew_id=self._paths.crew_id,
            idempotency_key=idempotency_key,
            payload=payload,
            artifact_refs=artifact_refs,
        )


class GuardrailMemory:
    def __init__(self, *, event_store: EventStore, paths: V4Paths) -> None:
        self._events = event_store
        self._paths = paths

    def create_candidate(
        self,
        *,
        candidate_id: str,
        source_note_ids: list[str],
        source_event_ids: list[str],
        rule_summary: str,
        enforcement_point: str,
        trigger_conditions: list[str],
    ) -> AgentEvent:
        artifact_path = self._paths.guardrail_candidate_path(candidate_id)
        artifact_ref = _artifact_ref(self._paths, artifact_path)
        payload = CandidatePayload(
            candidate_id=candidate_id,
            source_note_ids=list(source_note_ids),
            source_event_ids=list(source_event_ids),
            kind="guardrail",
            summary=rule_summary,
            trigger_conditions=list(trigger_conditions),
            artifact_ref=artifact_ref,
        ).to_payload()
        idempotency_key = _idempotency_key(
            self._paths.crew_id,
            "guardrail.candidate_created",
            {"candidate_id": candidate_id},
        )
        if existing := self._events.get_by_idempotency_key(idempotency_key):
            return existing
        _write_json_atomic(
            artifact_path,
            {
                **payload,
                "rule_summary": rule_summary,
                "enforcement_point": enforcement_point,
            },
        )
        return self._append_candidate_event(
            event_type="guardrail.candidate_created",
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[artifact_ref],
            idempotency_key=idempotency_key,
        )

    def approve_candidate(
        self,
        *,
        candidate_id: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        return self._append_decision(
            candidate_id=candidate_id,
            event_type="guardrail.approved",
            decision="approved",
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        )

    def reject_candidate(
        self,
        *,
        candidate_id: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        return self._append_decision(
            candidate_id=candidate_id,
            event_type="guardrail.rejected",
            decision="rejected",
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        )

    def activate_candidate(
        self,
        *,
        candidate_id: str,
        activation_id: str,
        activated_by: str,
        activated_at: str,
        rollback_plan: str = "Deactivate through a follow-up governed learning event.",
    ) -> AgentEvent:
        artifact_path = self._paths.guardrail_candidate_path(candidate_id)
        artifact_ref = _require_artifact(self._paths, artifact_path)
        idempotency_key = _idempotency_key(
            self._paths.crew_id,
            "guardrail.activated",
            {"candidate_id": candidate_id, "activation_id": activation_id},
        )
        if existing := self._events.get_by_idempotency_key(idempotency_key):
            return existing
        _require_candidate_approved(
            events=self._events,
            crew_id=self._paths.crew_id,
            candidate_id=candidate_id,
            event_prefix="guardrail.",
        )
        payload = ActivationPayload(
            candidate_id=candidate_id,
            activation_id=activation_id,
            activated_by=activated_by,
            activated_at=activated_at,
            active_artifact_ref=artifact_ref,
            rollback_plan=rollback_plan,
        ).to_payload()
        return self._append_candidate_event(
            event_type="guardrail.activated",
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[artifact_ref],
            idempotency_key=idempotency_key,
        )

    def _append_decision(
        self,
        *,
        candidate_id: str,
        event_type: str,
        decision: str,
        decision_reason: str,
        approver: str,
        decided_at: str,
    ) -> AgentEvent:
        payload = ApprovalPayload(
            candidate_id=candidate_id,
            decision=decision,
            decision_reason=decision_reason,
            approver=approver,
            decided_at=decided_at,
        ).to_payload()
        return self._append_candidate_event(
            event_type=event_type,
            candidate_id=candidate_id,
            payload=payload,
            artifact_refs=[],
            idempotency_key=_idempotency_key(
                self._paths.crew_id,
                event_type,
                {"candidate_id": candidate_id, "decision": decision},
            ),
        )

    def _append_candidate_event(
        self,
        *,
        event_type: str,
        candidate_id: str,
        payload: dict[str, Any],
        artifact_refs: list[str],
        idempotency_key: str = "",
    ) -> AgentEvent:
        if not idempotency_key:
            idempotency_key = _idempotency_key(
                self._paths.crew_id,
                event_type,
                {"candidate_id": candidate_id, "payload": payload},
            )
        return self._events.append(
            stream_id=self._paths.crew_id,
            type=event_type,
            crew_id=self._paths.crew_id,
            idempotency_key=idempotency_key,
            payload=payload,
            artifact_refs=artifact_refs,
        )


class WorkerQualityTracker:
    def __init__(self, *, event_store: EventStore, paths: V4Paths) -> None:
        self._events = event_store
        self._paths = paths

    def update_quality(
        self,
        *,
        worker_id: str,
        score_delta: int,
        reason_codes: list[str],
        source_event_ids: list[str],
        expires_at: str,
    ) -> AgentEvent:
        payload = WorkerQualityPayload(
            worker_id=worker_id,
            score_delta=score_delta,
            reason_codes=list(reason_codes),
            source_event_ids=list(source_event_ids),
            expires_at=expires_at,
        ).to_payload()
        event, _ = self._events.append_claim(
            stream_id=self._paths.crew_id,
            type="worker.quality_updated",
            crew_id=self._paths.crew_id,
            worker_id=worker_id,
            idempotency_key=_idempotency_key(
                self._paths.crew_id,
                "worker.quality_updated",
                {"worker_id": worker_id, "payload": payload},
            ),
            payload=payload,
            artifact_refs=["learning/worker_quality.json"],
        )
        self._rebuild_projection()
        return event

    def _rebuild_projection(self) -> None:
        with _worker_quality_projection_lock:
            state: dict[str, Any] = {}
            for event in self._events.list_stream(self._paths.crew_id):
                if event.type != "worker.quality_updated":
                    continue
                payload = event.payload
                worker_id = str(payload.get("worker_id") or event.worker_id)
                if not worker_id:
                    continue
                current = state.get(worker_id, {"worker_id": worker_id, "score": 0})
                score = int(current.get("score", 0)) + int(payload["score_delta"])
                current.update(
                    {
                        "worker_id": worker_id,
                        "score": score,
                        "last_score_delta": payload["score_delta"],
                        "reason_codes": payload["reason_codes"],
                        "source_event_ids": payload["source_event_ids"],
                        "expires_at": payload["expires_at"],
                    }
                )
                state[worker_id] = current
            _write_json_atomic(self._paths.worker_quality_path, state)


def _artifact_ref(paths: V4Paths, artifact_path: Path) -> str:
    return artifact_path.relative_to(paths.artifact_root).as_posix()


def _require_artifact(paths: V4Paths, artifact_path: Path) -> str:
    if not artifact_path.exists():
        raise FileNotFoundError(artifact_path)
    return _artifact_ref(paths, artifact_path)


def _require_candidate_approved(
    *,
    events: EventStore,
    crew_id: str,
    candidate_id: str,
    event_prefix: str,
) -> None:
    state = ""
    for event in events.list_stream(crew_id):
        if not event.type.startswith(event_prefix):
            continue
        if event.payload.get("candidate_id") != candidate_id:
            continue
        if event.type.endswith(".candidate_created"):
            state = "pending"
        elif event.type.endswith(".approved"):
            state = "approved"
        elif event.type.endswith(".rejected"):
            state = "rejected"
        elif event.type.endswith(".activated"):
            state = "activated"
    if state != "approved":
        raise ValueError("candidate is not approved")


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(
        json.dumps(normalize(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _idempotency_key(crew_id: str, event_type: str, identity: dict[str, Any]) -> str:
    content = json.dumps(
        normalize(identity),
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return f"learning/{crew_id}/{event_type}/{digest}"


__all__ = [
    "GuardrailMemory",
    "LearningRecorder",
    "SkillCandidateGate",
    "WorkerQualityTracker",
]
