from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


_STATUS_MAP = {
    "OK": "ok",
    "WARN": "warn",
    "BLOCK": "block",
}
_UNKNOWN_SUMMARY = "review verdict was not parseable"


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


@dataclass
class ReviewVerdict:
    status: str
    summary: str
    findings: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    raw_artifact: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _normalize(self)


class ReviewVerdictParser:
    _block_pattern = re.compile(r"<<<CODEX_REVIEW\s*(.*?)\s*>>>", re.DOTALL)
    _verdict_pattern = re.compile(r"^\s*verdict\s*:\s*(\S+)\s*$", re.IGNORECASE)
    _summary_pattern = re.compile(r"^\s*summary\s*:\s*(.*?)\s*$", re.IGNORECASE)
    _findings_pattern = re.compile(r"^\s*findings\s*:\s*$", re.IGNORECASE)
    _bullet_pattern = re.compile(r"^\s*-\s*(.*?)\s*$")

    def parse(
        self,
        text: str,
        *,
        evidence_refs: list[str] | None = None,
        raw_artifact: str = "",
    ) -> ReviewVerdict:
        refs = list(evidence_refs or [])
        block = self._extract_structured_block(text)
        if block is not None:
            verdict = self._parse_verdict_text(block, evidence_refs=refs, raw_artifact=raw_artifact)
            if verdict.status != "unknown":
                return verdict

        return self._parse_verdict_text(text, evidence_refs=refs, raw_artifact=raw_artifact)

    def _extract_structured_block(self, text: str) -> str | None:
        match = self._block_pattern.search(text)
        if not match:
            return None
        return match.group(1)

    def _parse_verdict_text(
        self,
        text: str,
        *,
        evidence_refs: list[str],
        raw_artifact: str,
    ) -> ReviewVerdict:
        verdict: str | None = None
        summary = ""
        findings: list[str] = []
        in_findings = False

        for line in text.splitlines():
            verdict_match = self._verdict_pattern.match(line)
            if verdict_match:
                verdict = verdict_match.group(1).upper()
                in_findings = False
                continue

            summary_match = self._summary_pattern.match(line)
            if summary_match:
                summary = summary_match.group(1).strip()
                in_findings = False
                continue

            if self._findings_pattern.match(line):
                in_findings = True
                continue

            if in_findings:
                bullet_match = self._bullet_pattern.match(line)
                if bullet_match:
                    finding = bullet_match.group(1).strip()
                    if finding:
                        findings.append(finding)
                    continue
                if line.strip():
                    in_findings = False

        if verdict not in _STATUS_MAP:
            return ReviewVerdict(
                status="unknown",
                summary=_UNKNOWN_SUMMARY,
                evidence_refs=evidence_refs,
                raw_artifact=raw_artifact,
            )

        return ReviewVerdict(
            status=_STATUS_MAP[verdict],
            summary=summary,
            findings=findings,
            evidence_refs=evidence_refs,
            raw_artifact=raw_artifact,
        )
