# 去重工具：三层去重（URL级→内容级→语义级），存根
from __future__ import annotations
from langchain_core.tools import tool


@tool
def check_duplicate(kb_id: str, url: str, text: str) -> dict:
    """
    三层去重：URL级 → 内容级（SimHash）→ 语义级（向量，可选）。
    返回 {is_duplicate, level, matched_source_id, changed}。
    changed=True 表示同 URL 内容已变，走时序快照更新而非丢弃。
    """
    # TODO: 调用 SourceRepo + simhash + semantic（若启用）
    raise NotImplementedError("check_duplicate 尚未实现")
