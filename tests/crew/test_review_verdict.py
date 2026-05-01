from codex_claude_orchestrator.crew.review_verdict import ReviewVerdictParser


def test_review_verdict_parser_parses_structured_ok_block():
    text = """review notes
<<<CODEX_REVIEW
verdict: OK
summary: Patch is safe.
findings:
- Tests cover the changed path.
>>>
done"""

    verdict = ReviewVerdictParser().parse(
        text,
        evidence_refs=["workers/worker-reviewer/transcript.txt"],
        raw_artifact="workers/worker-reviewer/transcript.txt",
    )

    assert verdict.status == "ok"
    assert verdict.summary == "Patch is safe."
    assert verdict.findings == ["Tests cover the changed path."]
    assert verdict.evidence_refs == ["workers/worker-reviewer/transcript.txt"]
    assert verdict.raw_artifact == "workers/worker-reviewer/transcript.txt"
    assert verdict.to_dict()["status"] == "ok"


def test_review_verdict_parser_parses_structured_warn_block():
    text = """<<<CODEX_REVIEW
verdict: WARN
summary: Patch is acceptable with a follow-up risk.
findings:
- The behavior is covered, but the fixture name is broad.
>>>"""

    verdict = ReviewVerdictParser().parse(text)

    assert verdict.status == "warn"
    assert verdict.summary == "Patch is acceptable with a follow-up risk."
    assert verdict.findings == ["The behavior is covered, but the fixture name is broad."]


def test_review_verdict_parser_parses_structured_block_block():
    text = """<<<CODEX_REVIEW
verdict: BLOCK
summary: Patch regresses retry behavior.
findings:
- The retry counter is reset inside the loop.
- The new test does not exercise the failure path.
>>>"""

    verdict = ReviewVerdictParser().parse(text)

    assert verdict.status == "block"
    assert verdict.summary == "Patch regresses retry behavior."
    assert verdict.findings == [
        "The retry counter is reset inside the loop.",
        "The new test does not exercise the failure path.",
    ]


def test_review_verdict_parser_parses_plain_text_fallback():
    text = """Reviewer output
Verdict: BLOCK
Summary: Missing assertion for failed verification.
Findings:
- Verification failure is swallowed.
"""

    verdict = ReviewVerdictParser().parse(text)

    assert verdict.status == "block"
    assert verdict.summary == "Missing assertion for failed verification."
    assert verdict.findings == ["Verification failure is swallowed."]


def test_review_verdict_parser_does_not_fallback_when_structured_block_is_invalid():
    text = """Reviewer output
<<<CODEX_REVIEW
summary: This structured block forgot the verdict.
findings:
- It should be authoritative despite being invalid.
>>>
Verdict: BLOCK
Summary: Plain text outside the block should not be used.
Findings:
- This fallback finding should be ignored.
"""

    verdict = ReviewVerdictParser().parse(text)

    assert verdict.status == "unknown"
    assert verdict.summary == "review verdict was not parseable"


def test_review_verdict_parser_returns_unknown_for_unparseable_output():
    verdict = ReviewVerdictParser().parse("Looks fine to me without a verdict line.")

    assert verdict.status == "unknown"
    assert verdict.summary == "review verdict was not parseable"
    assert verdict.findings == []
