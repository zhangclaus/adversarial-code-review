# Design Docs

本目录保留 codex-claude-orchestrator 的内部设计文档（不包含在开源仓库中）。

## 项目文档

完整项目文档见 `docs/项目完整文档.md`，包含架构、模块实现、MCP Server、CLI 命令等全部内容。

## 当前核心架构

### V4 事件溯源运行时

系统已演进到 V4 架构。核心模块：

- `v4/event_store.py` — SQLite/PostgreSQL 事件存储
- `v4/domain_events.py` — 类型化事件发射器（DomainEventEmitter）
- `v4/crew_state_projection.py` — 从事件流重建 Crew 状态
- `v4/crew_runner.py` — 主编排循环
- `v4/supervisor.py` — V4 监督者
- `v4/long_task_supervisor.py` — 多阶段长任务执行

### Long Task 多阶段执行

系统核心特性——将单阶段对抗性验证扩展为多阶段、并行 Worker 的长任务执行运行时。

流程图见项目根目录 `liuchengtu.png`。

### MCP Server

基于 FastMCP，通过 stdio 协议运行。纯基础设施——只提供 Tools，不含循环或决策逻辑。

关键 Tools：`crew_run`（非阻塞）、`crew_job_status`（Delta 轮询）、`crew_cancel`、`crew_verify`、`crew_accept`。

## 目录规则

- **Spec**: 架构规格文档，描述"是什么"和"为什么"
- **Plan**: 实现计划，描述"怎么做"
- 内部设计文档不包含在开源仓库中（已 .gitignore）
