# Cypher 安全工具：NL2Cypher 只读护栏，拦截写操作
from __future__ import annotations
import re

# 被禁止的写操作关键字（大小写不敏感）
_WRITE_KEYWORDS = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH\s+DELETE|SET|REMOVE|DROP)\b",
    re.IGNORECASE,
)


def is_read_only(cypher: str) -> bool:
    """检查 Cypher 是否为纯只读语句，含写操作关键字则返回 False。"""
    return not bool(_WRITE_KEYWORDS.search(cypher))


def assert_read_only(cypher: str) -> None:
    """断言 Cypher 只读，含写操作则抛出 ValueError（安全护栏）。"""
    if not is_read_only(cypher):
        raise ValueError(f"生成的 Cypher 含写操作，已拦截：{cypher[:200]}")
