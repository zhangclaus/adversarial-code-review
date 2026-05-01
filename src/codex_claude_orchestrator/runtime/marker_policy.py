from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


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


@dataclass(slots=True)
class MarkerObservation:
    status: str
    marker_seen: bool
    reason: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


class MarkerObservationPolicy:
    def evaluate(
        self,
        *,
        snapshot: str,
        expected_marker: str,
        transcript_text: str = "",
        transcript_artifact: str = "",
        contract_marker: str = "",
    ) -> MarkerObservation:
        evidence_refs = [transcript_artifact] if transcript_artifact else []

        if expected_marker in snapshot:
            return MarkerObservation(
                status="completed",
                marker_seen=True,
                reason="marker found in pane snapshot",
                evidence_refs=evidence_refs,
            )

        if expected_marker in transcript_text:
            return MarkerObservation(
                status="completed",
                marker_seen=True,
                reason="marker found in transcript",
                evidence_refs=evidence_refs,
            )

        if contract_marker and (contract_marker in snapshot or contract_marker in transcript_text):
            return MarkerObservation(
                status="mismatch",
                marker_seen=False,
                reason="contract marker found but expected turn marker was missing",
                evidence_refs=evidence_refs,
            )

        return MarkerObservation(
            status="waiting",
            marker_seen=False,
            reason="expected marker not found",
            evidence_refs=evidence_refs,
        )
