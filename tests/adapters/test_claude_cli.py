from pathlib import Path
from subprocess import CompletedProcess

from codex_claude_orchestrator.adapters.claude_cli import ClaudeCliAdapter
from codex_claude_orchestrator.models import WorkspaceAllocation, WorkspaceMode
from codex_claude_orchestrator.prompt_compiler import CompiledPrompt


def test_execute_uses_json_schema_and_parses_structured_output(tmp_path: Path):
    seen: dict[str, object] = {}

    def fake_runner(command: list[str], **kwargs) -> CompletedProcess[str]:
        seen["command"] = command
        seen["cwd"] = kwargs["cwd"]
        return CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"type":"result","result":{"summary":"done","status":"completed","changed_files":["src/app.py"],"verification_commands":["pytest -q"],"notes_for_supervisor":[]}}',
            stderr="",
        )

    adapter = ClaudeCliAdapter(runner=fake_runner)
    compiled = CompiledPrompt(
        system_prompt="system",
        user_prompt="goal",
        schema={
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
        metadata={"task_id": "task-adapter", "allowed_tools": ["Read", "Edit"]},
    )
    allocation = WorkspaceAllocation(
        workspace_id="workspace-1",
        path=tmp_path,
        mode=WorkspaceMode.ISOLATED,
        writable=True,
    )

    result = adapter.execute(compiled, allocation)

    assert "--json-schema" in seen["command"]
    assert "--output-format" in seen["command"]
    assert "--system-prompt" in seen["command"]
    assert "--allowedTools" in seen["command"]
    assert seen["cwd"] == str(tmp_path)
    assert result.structured_output["summary"] == "done"
    assert result.changed_files == ["src/app.py"]
