from pathlib import Path

from codex_claude_orchestrator.v4.adapters.verification import VerificationAdapter
from codex_claude_orchestrator.v4.artifacts import ArtifactStore


def test_verification_adapter_records_passed_command(tmp_path: Path):
    adapter = VerificationAdapter(artifact_store=ArtifactStore(tmp_path / "artifacts"))

    result = adapter.run(command=".venv/bin/python -c 'print(123)'", cwd=tmp_path, verification_id="verification-1")

    assert result["passed"] is True
    assert result["exit_code"] == 0
    assert result["stdout_artifact"] == "verification/verification-1/stdout.txt"
    assert "123" in (tmp_path / "artifacts" / result["stdout_artifact"]).read_text(encoding="utf-8")


def test_verification_adapter_records_failed_command(tmp_path: Path):
    adapter = VerificationAdapter(artifact_store=ArtifactStore(tmp_path / "artifacts"))

    result = adapter.run(
        command=".venv/bin/python -c 'import sys; print(\"bad\"); sys.exit(3)'",
        cwd=tmp_path,
        verification_id="verification-2",
    )

    assert result["passed"] is False
    assert result["exit_code"] == 3
    assert "bad" in (tmp_path / "artifacts" / result["stdout_artifact"]).read_text(encoding="utf-8")
