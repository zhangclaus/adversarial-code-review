from codex_claude_orchestrator.crew.loop_step_result import LoopStepResult


def test_loop_step_result_defaults():
    r = LoopStepResult(action="waiting")
    assert r.action == "waiting"
    assert r.reason == ""
    assert r.context == {}
    assert r.snapshot == {}


def test_loop_step_result_needs_decision():
    r = LoopStepResult(
        action="needs_decision",
        reason="验证失败 3 次",
        context={"failures": 3},
        snapshot={"crew_id": "c1", "workers": []},
    )
    assert r.action == "needs_decision"
    assert r.reason == "验证失败 3 次"
    assert r.context["failures"] == 3
    assert r.snapshot["crew_id"] == "c1"


def test_loop_step_result_to_dict():
    r = LoopStepResult(action="ready_for_accept", context={"passed": True})
    d = r.to_dict()
    assert d["action"] == "ready_for_accept"
    assert d["context"] == {"passed": True}
