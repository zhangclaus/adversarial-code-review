from codex_claude_orchestrator.models import TaskRecord, TaskStatus, WorkspaceMode


def test_task_record_to_dict_normalizes_enum_fields():
    task = TaskRecord(
        task_id="task-1",
        parent_task_id=None,
        origin="user",
        assigned_agent="claude",
        goal="Review the repository",
        task_type="review",
        scope="repo root",
        workspace_mode=WorkspaceMode.ISOLATED,
        status=TaskStatus.QUEUED,
        expected_output_schema={"type": "object"},
    )

    data = task.to_dict()

    assert data["workspace_mode"] == "isolated"
    assert data["status"] == "queued"
    assert data["shared_write_allowed"] is False
    assert data["expected_output_schema"]["type"] == "object"
