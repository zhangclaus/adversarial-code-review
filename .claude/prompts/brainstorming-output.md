## 输出 think_result.json

在 brainstorming 确认 spec 后，使用 Write tool 将结构化数据写入 `.crew/think_result.json`。

JSON 必须包含以下字段：

```json
{
  "spec": "需求规格（用户确认后的版本，完整文本）",
  "stages": [
    {
      "stage_id": 1,
      "goal": "阶段目标",
      "acceptance_criteria": ["可量化的验收标准1", "可量化的验收标准2"],
      "contract": {
        "api_endpoints": [
          {
            "method": "POST",
            "path": "/api/auth/login",
            "request_body": {"email": "str", "password": "str"},
            "response_body": {"token": "str"},
            "description": "用户登录"
          }
        ],
        "data_models": [
          {"name": "User", "fields": {"id": "int", "email": "str"}}
        ],
        "shared_types": ["AuthToken"],
        "conventions": ["使用 snake_case 命名"]
      },
      "sub_tasks": [
        {
          "task_id": "1a",
          "role": "backend-developer",
          "goal": "实现 JWT API",
          "dependencies": [],
          "write_scope": ["src/api/auth.py"],
          "worker_template": "targeted-code-editor"
        }
      ],
      "dependencies": []
    }
  ],
  "contract": {
    "api_endpoints": [],
    "data_models": [],
    "shared_types": [],
    "conventions": []
  },
  "project_context": {
    "structure": "项目结构摘要",
    "existing_patterns": ["FastAPI", "SQLAlchemy"],
    "tech_stack": ["Python 3.11", "FastAPI"],
    "related_files": ["src/auth/"],
    "constraints": ["不能改数据库 schema"]
  },
  "acceptance_criteria": ["全局验收标准1", "全局验收标准2"],
  "open_questions": ["未解决的问题1"]
}
```

### 注意事项
- contract 的 api_endpoints 必须包含 method, path, response_body
- sub_tasks 的 write_scope 必须是具体的文件路径列表
- worker_template 使用现有模板名：targeted-code-editor, backend-developer, frontend-developer, test-writer, repo-context-scout
- acceptance_criteria 必须可量化、可测试
- stages 至少包含 2-3 个阶段
- 每个 stage 至少包含 1 个 sub_task
