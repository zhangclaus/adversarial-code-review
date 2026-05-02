from __future__ import annotations

import hashlib
import json
from typing import Any

from codex_claude_orchestrator.v4.adversarial_models import ChallengeIssuePayload, ChallengeSeverity
from codex_claude_orchestrator.v4.event_store_protocol import EventStore
from codex_claude_orchestrator.v4.events import AgentEvent, normalize


class AdversarialEvaluator:
    def __init__(self, *, event_store: EventStore) -> None:
        self._events = event_store

    def evaluate_completed_turn(self, completed_event: AgentEvent) -> AgentEvent:
        if completed_event.type != "turn.completed":
            raise ValueError("AdversarialEvaluator requires a turn.completed event")

        evidence = [
            event
            for event in self._events.list_by_turn(completed_event.turn_id)
            if event.crew_id == completed_event.crew_id
        ]
        if self._has_passed_verification(evidence):
            return self._append_pass_review(completed_event)
        return self._append_missing_verification_challenge(completed_event)

    def _has_passed_verification(self, evidence: list[AgentEvent]) -> bool:
        for event in evidence:
            if event.type == "verification.passed":
                return True
            if event.type != "worker.outbox.detected":
                continue
            verification = event.payload.get("verification", [])
            if not isinstance(verification, list):
                continue
            if any(isinstance(item, dict) and item.get("status") == "passed" for item in verification):
                return True
        return False

    def _append_missing_verification_challenge(self, source: AgentEvent) -> AgentEvent:
        payload = ChallengeIssuePayload(
            challenge_id=f"challenge-{source.event_id}",
            source_turn_id=source.turn_id,
            source_event_ids=[source.event_id],
            severity=ChallengeSeverity.BLOCK,
            category="missing_verification",
            finding="Completed turn does not include passed verification evidence.",
            required_response=(
                "Repair the turn by adding or running relevant verification and writing a valid repair outbox."
            ),
            repair_allowed=True,
            artifact_refs=list(source.artifact_refs),
        ).to_payload()
        return self._append_evaluation_event(
            source=source,
            event_type="challenge.issued",
            payload=payload,
            artifact_refs=list(source.artifact_refs),
        )

    def _append_pass_review(self, source: AgentEvent) -> AgentEvent:
        payload = {
            "verdict": "pass",
            "source_event_ids": [source.event_id],
        }
        return self._append_evaluation_event(
            source=source,
            event_type="review.completed",
            payload=payload,
            artifact_refs=list(source.artifact_refs),
        )

    def _append_evaluation_event(
        self,
        *,
        source: AgentEvent,
        event_type: str,
        payload: dict[str, Any],
        artifact_refs: list[str],
    ) -> AgentEvent:
        return self._events.append(
            stream_id=source.crew_id,
            type=event_type,
            crew_id=source.crew_id,
            worker_id=source.worker_id,
            turn_id=source.turn_id,
            round_id=source.round_id,
            contract_id=source.contract_id,
            idempotency_key=self._idempotency_key(
                source=source,
                event_type=event_type,
                payload=payload,
                artifact_refs=artifact_refs,
            ),
            payload=payload,
            artifact_refs=artifact_refs,
        )

    def _idempotency_key(
        self,
        *,
        source: AgentEvent,
        event_type: str,
        payload: dict[str, Any],
        artifact_refs: list[str],
    ) -> str:
        digest = self._digest(
            {
                "source_event_id": source.event_id,
                "event_type": event_type,
                "payload": payload,
                "artifact_refs": artifact_refs,
            }
        )
        return f"{source.crew_id}/{source.turn_id}/{event_type}/{digest}"

    def _digest(self, value: dict[str, Any]) -> str:
        content = json.dumps(normalize(value), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()
