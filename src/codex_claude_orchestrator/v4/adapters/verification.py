from __future__ import annotations

import shlex
import subprocess
from pathlib import Path

from codex_claude_orchestrator.v4.artifacts import ArtifactStore


class VerificationAdapter:
    def __init__(self, *, artifact_store: ArtifactStore):
        self._artifacts = artifact_store
        self._repo_root = Path.cwd().resolve()

    def run(self, *, command: str, cwd: Path, verification_id: str) -> dict:
        argv = self._resolve_repo_relative_executable(shlex.split(command), cwd)
        result = subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)
        stdout_artifact = self._artifacts.write_text(
            f"verification/{verification_id}/stdout.txt",
            result.stdout,
        )
        stderr_artifact = self._artifacts.write_text(
            f"verification/{verification_id}/stderr.txt",
            result.stderr,
        )
        return {
            "verification_id": verification_id,
            "command": command,
            "passed": result.returncode == 0,
            "exit_code": result.returncode,
            "summary": f"command {'passed' if result.returncode == 0 else 'failed'}: exit code {result.returncode}",
            "stdout_artifact": stdout_artifact.path,
            "stderr_artifact": stderr_artifact.path,
        }

    def _resolve_repo_relative_executable(self, argv: list[str], cwd: Path) -> list[str]:
        if not argv:
            return argv

        executable = Path(argv[0])
        if executable.is_absolute() or not self._is_relative_path_executable(argv[0]):
            return argv
        if (cwd / executable).exists():
            return argv

        repo_executable = self._repo_root / executable
        if repo_executable.exists():
            return [str(repo_executable), *argv[1:]]
        return argv

    def _is_relative_path_executable(self, value: str) -> bool:
        return "/" in value or value.startswith(".")
