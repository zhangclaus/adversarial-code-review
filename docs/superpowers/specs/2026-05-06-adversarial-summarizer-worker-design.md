# Adversarial Summarizer Worker Design

## Problem

Context Layer 的"摘要"实际是机械压缩（过滤 + 截断），没有语义理解。黑板条目积累后，Supervisor 需要花大量 context window 去阅读原始条目才能做决策。

## Solution

新增一个 `summarizer` Worker 模板。当黑板条目超过阈值时自动 spawn，由 Supervisor 通过 accept/challenge 机制验证摘要质量。

## Design

### 1. Worker 模板

在 `WORKER_TEMPLATES` 中新增：

```python
"summarizer": WorkerContract(
    contract_id="template-summarizer",
    label="summarizer",
    mission="Read all blackboard entries for this crew. Produce a concise summary covering: "
            "1) Key findings and facts, 2) Open risks, 3) Current progress, "
            "4) Pending challenges or unresolved questions. "
            "Write the summary to the blackboard as a 'summary' entry.",
    required_capabilities=["inspect_code"],
    authority_level=AuthorityLevel.READONLY,
    workspace_policy=WorkspacePolicy.READONLY,
)
```

权限：readonly。summarizer 只读黑板、写黑板条目，不修改源码。

### 2. 触发机制

在 `crew_blackboard` tool 中内置触发逻辑。调用 `crew_blackboard` 时：

```
1. 读取黑板条目
2. 条目数 > 20 且需要新摘要？
   → 异步 spawn summarizer Worker（不阻塞当前调用）
3. 返回当前条目（机械压缩）
```

判断是否需要新摘要：

```python
def _should_trigger_summarizer(entries: list[dict], threshold: int = 20) -> bool:
    if len(entries) <= threshold:
        return False
    summaries = [e for e in entries if e.get("type") == "summary"]
    if not summaries:
        return True  # 无摘要
    latest_summary_ts = max(e.get("timestamp", "") for e in summaries)
    non_summaries = [e for e in entries if e.get("type") != "summary"]
    latest_entry_ts = max(e.get("timestamp", "") for e in non_summaries)
    return latest_entry_ts > latest_summary_ts  # 有更新的条目
```

触发是异步的：spawn summarizer 后立即返回当前数据，不等待摘要完成。

### 3. 摘要输出

summarizer 写回黑板的条目：

```json
{
  "type": "summary",
  "actor_id": "summarizer-worker-id",
  "content": "3 workers active. Key findings: auth module refactored (w1), "
             "migration script added (w2). Risks: untested error path in login, "
             "missing rollback for user table migration. "
             "Verification: w1 passed, w2 failed (test timeout).",
  "confidence": 0.85
}
```

`content` 是自然语言摘要，由 LLM 产出。

### 4. 对抗验证

summarizer 的生命周期与其他 Worker 完全一致：

```
spawn → 读取黑板 → 产出摘要 → 写回黑板 → 打印完成标记
                                                ↓
                                    Supervisor 通过 crew_observe 看到摘要
                                                ↓
                                    ┌─── 准确 → crew_accept 或继续编排
                                    └─── 不准确 → crew_challenge(summary="遗漏了 X")
                                                          ↓
                                                summarizer 修订 → 重新写回
```

不需要任何特殊机制。Supervisor 已有的 accept/challenge 能力天然覆盖摘要验证。

### 5. 与 context tools 集成

- `crew_status`：`compress_crew_status` 从黑板中提取最新 `type=summary` 条目，附加到返回结果的 `summary` 字段
- `crew_blackboard(entry_type="summary")`：直接获取摘要条目
- `crew_events`：summarizer 的 `turn.completed` 事件会被 `filter_events` 保留（属于 `_KEY_EVENT_TYPES`）

### 6. 不改变现有架构

- MCP Server 不新增 tool，不改变 server.py
- 不引入 Anthropic SDK 或新的 API 调用
- summarizer 通过现有 `crew_spawn` → `ensure_worker` 路径启动
- 摘要验证走现有 accept/challenge 路径
- 唯一新增：`WORKER_TEMPLATES["summarizer"]` + `crew_blackboard` 中的触发逻辑

## Files to Modify

| File | Change |
|------|--------|
| `src/codex_claude_orchestrator/mcp_server/tools/crew_lifecycle.py` | 添加 `summarizer` 模板 |
| `src/codex_claude_orchestrator/mcp_server/tools/crew_context.py` | `crew_blackboard` 中添加触发逻辑 |
| `src/codex_claude_orchestrator/crew/models.py` | `BlackboardEntryType` 添加 `SUMMARY = "summary"` |
| `skills/orchestration-default.md` | 添加 summarizer 模板说明 |
| `tests/mcp_server/test_crew_context_tools.py` | 测试触发逻辑 |
| `tests/mcp_server/test_crew_lifecycle_tools.py` | 测试 summarizer 模板 |

## Testing

1. `crew_blackboard` 条目 <= 20 → 不触发 summarizer
2. `crew_blackboard` 条目 > 20 且无 summary → 触发 spawn
3. `crew_blackboard` 条目 > 20 且 summary 新鲜 → 不触发
4. `crew_blackboard` 条目 > 20 且有比 summary 更新的条目 → 触发
5. summarizer 模板的 contract 字段正确（readonly, inspect_code）
6. 集成测试：summarizer spawn 后 controller.ensure_worker 被调用
