from __future__ import annotations

import json


def truncate_to_tokens(text: str, max_tokens: int = 2000) -> str:
    """按字符近似截断（1 token ≈ 4 chars）。"""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[已截断，可用其他 tool 获取更多详情]"


def truncate_json(data: dict | list, max_tokens: int = 2000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return truncate_to_tokens(text, max_tokens)
