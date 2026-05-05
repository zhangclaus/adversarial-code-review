from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoopStepResult:
    action: str  # "waiting" | "needs_decision" | "ready_for_accept" | "max_steps_reached"
    reason: str = ""
    context: dict = field(default_factory=dict)
    snapshot: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "context": self.context,
            "snapshot": self.snapshot,
        }
