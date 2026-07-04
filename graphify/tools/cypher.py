# Cypher 安全工具：NL2Cypher 只读护栏
# 三道防线：① 拦截写操作 ② 强制 LIMIT ③ 强制 kb_id 过滤
from __future__ import annotations
import re

# ── 写操作关键字（大小写不敏感，单词边界匹配）──────────────────
# DETACH DELETE 放在 DELETE 之前，避免被 DELETE 分支先匹配
_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DETACH\s+DELETE|DELETE|SET|REMOVE|DROP|FOREACH|LOAD\s+CSV)\b",
    re.IGNORECASE,
)

# LIMIT 后必须跟数字（防止 "LIMIT" 仅出现在注释或字符串中）
_LIMIT_RE = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)

# kb_id 必须以参数化比较形式出现（n.kb_id = $kb_id 或 {kb_id:$kb_id}），
# 仅在 RETURN 中出现 kb_id（如 RETURN c.kb_id）不算过滤，防止越权查询
_KB_ID_RE = re.compile(r"\bkb_id\s*[:=]\s*\$kb_id\b", re.IGNORECASE)


# ── 单项检查函数 ──────────────────────────────────────────────

def is_read_only(cypher: str) -> bool:
    """不含写操作关键字则返回 True。"""
    return not bool(_WRITE_RE.search(cypher))


def has_limit(cypher: str) -> bool:
    """Cypher 含 LIMIT <n> 则返回 True。"""
    return bool(_LIMIT_RE.search(cypher))


def has_kb_id_filter(cypher: str) -> bool:
    """Cypher 含参数化 kb_id 过滤（kb_id = $kb_id）则返回 True。"""
    return bool(_KB_ID_RE.search(cypher))


# ── 组合断言（供 query_agent 使用）────────────────────────────

def assert_read_only(cypher: str) -> None:
    """仅检查写操作（向后兼容接口）。"""
    if not is_read_only(cypher):
        raise ValueError(f"Cypher 含写操作，已拦截：{cypher[:200]}")


def assert_safe_query(cypher: str) -> None:
    """完整安全检查（三道防线）：只读 + LIMIT + kb_id 过滤。

    任一条件不满足均抛出 ValueError，防止 LLM 生成危险或越权查询。
    """
    if not is_read_only(cypher):
        raise ValueError(f"Cypher 含写操作，已拦截：{cypher[:200]}")
    if not has_limit(cypher):
        raise ValueError(f"Cypher 缺少 LIMIT 子句，已拦截：{cypher[:200]}")
    if not has_kb_id_filter(cypher):
        raise ValueError(f"Cypher 缺少 kb_id 过滤，已拦截：{cypher[:200]}")
