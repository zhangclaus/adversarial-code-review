from pathlib import Path

from codex_claude_orchestrator.models import TaskRecord, WorkspaceMode, WorkerResult
from codex_claude_orchestrator.policy_gate import PolicyGate
from codex_claude_orchestrator.prompt_compiler import PromptCompiler
from codex_claude_orchestrator.result_evaluator import ResultEvaluator
from codex_claude_orchestrator.run_recorder import RunRecorder
from codex_claude_orchestrator.supervisor import Supervisor
from codex_claude_orchestrator.workspace_manager import WorkspaceManager


class FakeAdapter:
    def build_command(self, compiled):
        return ["claude", "-p", compiled.user_prompt]

    def execute(self, compiled, allocation):
        (allocation.path / "app.py").write_text("print('new')\n", encoding="utf-8")
        return WorkerResult(
            raw_output='{"summary":"done","status":"completed","changed_files":["app.py"],"verification_commands":["pytest -q"],"notes_for_supervisor":[]}',
            stdout='{"summary":"done","status":"completed","changed_files":["app.py"],"verification_commands":["pytest -q"],"notes_for_supervisor":[]}',
            stderr="",
            exit_code=0,
            structured_output={
                "summary": "done",
                "status": "completed",
                "changed_files": ["app.py"],
                "verification_commands": ["pytest -q"],
                "notes_for_supervisor": [],
            },
        )


def test_dispatch_runs_worker_records_run_and_returns_acceptance(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / "app.py").write_text("print('old')\n", encoding="utf-8")
    state_root = tmp_path / ".orchestrator"

    supervisor = Supervisor(
        prompt_compiler=PromptCompiler(),
        workspace_manager=WorkspaceManager(state_root),
        adapter=FakeAdapter(),
        policy_gate=PolicyGate(),
        run_recorder=RunRecorder(state_root),
        result_evaluator=ResultEvaluator(),
    )
    task = TaskRecord(
        task_id="task-supervisor",
        parent_task_id=None,
        origin="user",
        assigned_agent="claude",
        goal="Update app.py",
        task_type="implementation",
        scope="repo root",
        workspace_mode=WorkspaceMode.ISOLATED,
    )

    outcome = supervisor.dispatch(task, repo_root)

    assert outcome.accepted is True
    assert outcome.summary == "done"
    run_root = state_root / "runs"
    assert len(list(run_root.iterdir())) == 1
