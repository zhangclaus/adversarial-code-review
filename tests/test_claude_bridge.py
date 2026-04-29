from __future__ import annotations

from pathlib import Path
from subprocess import CalledProcessError, CompletedProcess

from codex_claude_orchestrator.claude_bridge import ClaudeBridge


def test_bridge_start_runs_claude_and_records_latest_session(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    calls = []

    def fake_runner(command, **kwargs):
        calls.append({"command": list(command), "cwd": kwargs["cwd"]})
        return CompletedProcess(
            command,
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"已检查项目结构。"}',
            stderr="",
        )

    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=fake_runner,
        bridge_id_factory=lambda: "bridge-fixed",
        turn_id_factory=lambda: "turn-start",
    )

    result = bridge.start(repo_root=repo_root, goal="检查项目结构，不要修改文件", workspace_mode="readonly")

    assert result["bridge"]["bridge_id"] == "bridge-fixed"
    assert result["bridge"]["claude_session_id"] == "claude-session-1"
    assert result["bridge"]["status"] == "active"
    assert result["latest_turn"]["result_text"] == "已检查项目结构。"
    assert calls[0]["cwd"] == str(repo_root.resolve())
    assert calls[0]["command"][0:2] == ["claude", "--print"]
    assert "--output-format" in calls[0]["command"]
    assert "--allowedTools" in calls[0]["command"]
    assert "Read,Glob,Grep,LS" in calls[0]["command"]

    tail = bridge.tail(repo_root=repo_root, bridge_id=None, limit=5)

    assert tail["bridge"]["bridge_id"] == "bridge-fixed"
    assert tail["turns"][0]["turn_id"] == "turn-start"
    assert (repo_root / ".orchestrator" / "claude-bridge" / "latest").read_text(encoding="utf-8") == "bridge-fixed"


def test_bridge_start_with_log_visual_opens_append_only_window(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    visual_calls = []
    call_order = []

    def fake_runner(command, **kwargs):
        call_order.append("claude")
        return CompletedProcess(
            command,
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"第一轮完成。"}',
            stderr="",
        )

    def fake_visual_runner(command, **kwargs):
        call_order.append("visual")
        visual_calls.append(list(command))
        return CompletedProcess(command, 0, stdout="", stderr="")

    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=fake_runner,
        visual_runner=fake_visual_runner,
        bridge_id_factory=lambda: "bridge-visible",
        turn_id_factory=lambda: "turn-start",
    )

    result = bridge.start(
        repo_root=repo_root,
        goal="检查项目结构",
        workspace_mode="readonly",
        visual="log",
    )

    visual = result["visual"]
    watch_script = Path(visual["watch_script_path"])
    log_path = Path(visual["log_path"])

    assert visual["mode"] == "log"
    assert visual["launched"] is True
    assert call_order == ["visual", "claude"]
    assert watch_script.is_file()
    assert log_path.is_file()
    assert visual_calls[0][:2] == ["osascript", "-e"]
    assert "activate" in visual_calls[0]
    assert any(part.startswith("do script") for part in visual_calls[0])
    script = watch_script.read_text(encoding="utf-8")
    log_text = log_path.read_text(encoding="utf-8")
    assert "tail -n +1 -f" in script
    assert "while true" not in script
    assert "clear" not in script
    assert "Claude bridge log" in log_text
    assert "第一轮完成。" in log_text


def test_bridge_send_appends_human_readable_log(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    responses = [
        CompletedProcess(
            ["claude"],
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"开始。"}',
            stderr="",
        ),
        CompletedProcess(
            ["claude"],
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"继续完成。"}',
            stderr="",
        ),
    ]

    def fake_runner(command, **kwargs):
        return responses.pop(0)

    turn_ids = iter(["turn-start", "turn-send"])
    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=fake_runner,
        visual_runner=lambda command, **kwargs: CompletedProcess(command, 0, stdout="", stderr=""),
        bridge_id_factory=lambda: "bridge-log",
        turn_id_factory=lambda: next(turn_ids),
    )

    bridge.start(repo_root=repo_root, goal="检查项目结构", workspace_mode="readonly", visual="log")
    bridge.send(repo_root=repo_root, bridge_id=None, message="继续检查")

    log_path = repo_root / ".orchestrator" / "claude-bridge" / "bridge-log" / "bridge.log"
    log_text = log_path.read_text(encoding="utf-8")

    assert "[USER]" in log_text
    assert "[CLAUDE]" in log_text
    assert "继续检查" in log_text
    assert "继续完成。" in log_text


def test_bridge_start_with_visual_failure_does_not_start_claude(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    claude_calls = []

    def fake_runner(command, **kwargs):
        claude_calls.append(list(command))
        return CompletedProcess(command, 0, stdout="", stderr="")

    def fake_visual_runner(command, **kwargs):
        return CompletedProcess(command, 1, stdout="", stderr="operation not permitted")

    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=fake_runner,
        visual_runner=fake_visual_runner,
        bridge_id_factory=lambda: "bridge-visual-fail",
        turn_id_factory=lambda: "turn-never",
    )

    try:
        bridge.start(
            repo_root=repo_root,
            goal="检查项目结构",
            workspace_mode="readonly",
            visual="log",
        )
    except CalledProcessError as exc:
        assert "operation not permitted" in str(exc.stderr)
    else:
        raise AssertionError("expected CalledProcessError")

    assert claude_calls == []


def test_bridge_send_resumes_existing_claude_session(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    responses = [
        CompletedProcess(
            ["claude"],
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"开始。"}',
            stderr="",
        ),
        CompletedProcess(
            ["claude"],
            0,
            stdout='{"type":"result","session_id":"claude-session-1","result":"继续检查后端接口。"}',
            stderr="",
        ),
    ]
    calls = []

    def fake_runner(command, **kwargs):
        calls.append({"command": list(command), "cwd": kwargs["cwd"]})
        return responses.pop(0)

    turn_ids = iter(["turn-start", "turn-send"])
    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=fake_runner,
        bridge_id_factory=lambda: "bridge-fixed",
        turn_id_factory=lambda: next(turn_ids),
    )

    bridge.start(repo_root=repo_root, goal="检查项目结构", workspace_mode="readonly")
    result = bridge.send(repo_root=repo_root, bridge_id=None, message="继续检查后端接口")

    assert result["bridge"]["claude_session_id"] == "claude-session-1"
    assert result["latest_turn"]["turn_id"] == "turn-send"
    assert result["latest_turn"]["result_text"] == "继续检查后端接口。"
    assert "--resume" in calls[1]["command"]
    assert "claude-session-1" in calls[1]["command"]
    assert "继续检查后端接口" in calls[1]["command"]

    tail = bridge.tail(repo_root=repo_root, bridge_id="bridge-fixed", limit=1)

    assert len(tail["turns"]) == 1
    assert tail["turns"][0]["turn_id"] == "turn-send"


def test_bridge_send_requires_claude_session_for_real_send(tmp_path: Path):
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    bridge = ClaudeBridge(
        state_root=repo_root / ".orchestrator",
        runner=lambda command, **kwargs: CompletedProcess(command, 0, stdout="", stderr=""),
        bridge_id_factory=lambda: "bridge-dry",
        turn_id_factory=lambda: "turn-dry",
    )
    result = bridge.start(repo_root=repo_root, goal="准备会话", workspace_mode="readonly", dry_run=True)

    assert result["bridge"]["status"] == "created"
    assert result["bridge"]["claude_session_id"] is None

    try:
        bridge.send(repo_root=repo_root, bridge_id=None, message="继续")
    except ValueError as exc:
        assert "no Claude session id" in str(exc)
    else:
        raise AssertionError("expected ValueError")
