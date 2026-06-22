# 测试 Cypher 安全护栏（设计文档 10.3/10.4 节）
# 覆盖：写操作拦截、缺 LIMIT 拦截、缺 kb_id 拦截、只读放行
from __future__ import annotations
import pytest
from graphify.agents import query_agent
from graphify.tools.cypher import (
    is_read_only, has_limit, has_kb_id_filter, assert_safe_query,
)
from tests.conftest import FakeDAO


# ── 辅助：单返回值 LLM ────────────────────────────────────────
class _LLM:
    """返回固定 Cypher 字符串的 LLM 替身（设计文档 10.4 原版）。"""
    def __init__(self, cy: str) -> None:
        self.cy = cy

    def invoke(self, msgs):
        class _M:
            pass
        m = _M()
        m.content = self.cy
        return m


# ════════════════════════════════════════════════════════════
# 一、写操作被拦截（设计文档 10.4 原版 + 完整枚举）
# ════════════════════════════════════════════════════════════

def test_write_cypher_detach_delete_blocked() -> None:
    """设计文档原版：DETACH DELETE 被拦截抛 ValueError。"""
    bad = _LLM("MATCH (n) DETACH DELETE n")
    with pytest.raises(ValueError, match="写操作"):
        query_agent.answer("kb1", "删库", dao=FakeDAO(), llm=bad)


@pytest.mark.parametrize("cypher,label", [
    ("CREATE (n:Company {name:'X'})", "CREATE"),
    ("MERGE (n:Company {name:'X'})", "MERGE"),
    ("MATCH (n) DELETE n", "DELETE"),
    ("MATCH (n) SET n.name='X'", "SET"),
    ("MATCH (n) REMOVE n.name", "REMOVE"),
    ("DROP INDEX idx_name", "DROP"),
    ("FOREACH (x IN [1] | CREATE (n))", "FOREACH"),
    ("LOAD CSV FROM 'file.csv' AS row CREATE (n)", "LOAD CSV"),
])
def test_write_operations_all_blocked(cypher: str, label: str) -> None:
    """所有写操作关键字均应被 is_read_only 识别为非只读。"""
    assert is_read_only(cypher) is False, f"{label} 应被识别为写操作"


def test_write_cypher_blocked_via_answer() -> None:
    """CREATE 通过 answer() 调用时被拦截。"""
    with pytest.raises(ValueError):
        query_agent.answer("kb1", "建节点", dao=FakeDAO(), llm=_LLM("CREATE (n:Test)"))


# ════════════════════════════════════════════════════════════
# 二、缺 LIMIT 被拦截
# ════════════════════════════════════════════════════════════

def test_missing_limit_blocked() -> None:
    """读操作但无 LIMIT 时，assert_safe_query 应抛出 ValueError。"""
    cypher = "MATCH (n:Company {kb_id:$kb_id}) RETURN n"
    with pytest.raises(ValueError, match="LIMIT"):
        assert_safe_query(cypher)


def test_missing_limit_blocked_via_answer() -> None:
    """缺 LIMIT 的 Cypher 通过 answer() 被拦截。"""
    cy = "MATCH (n:Company {kb_id:$kb_id}) RETURN n"
    with pytest.raises(ValueError):
        query_agent.answer("kb1", "列公司", dao=FakeDAO(), llm=_LLM(cy))


def test_has_limit_true() -> None:
    assert has_limit("MATCH (n) RETURN n LIMIT 10") is True


def test_has_limit_false() -> None:
    assert has_limit("MATCH (n) RETURN n") is False


# ════════════════════════════════════════════════════════════
# 三、缺 kb_id 被拦截
# ════════════════════════════════════════════════════════════

def test_missing_kb_id_blocked() -> None:
    """无 kb_id 过滤时，assert_safe_query 应抛出 ValueError。"""
    cypher = "MATCH (n:Company) RETURN n LIMIT 10"
    with pytest.raises(ValueError, match="kb_id"):
        assert_safe_query(cypher)


def test_missing_kb_id_blocked_via_answer() -> None:
    """缺 kb_id 的 Cypher 通过 answer() 被拦截。"""
    cy = "MATCH (n:Company) RETURN n LIMIT 10"
    with pytest.raises(ValueError):
        query_agent.answer("kb1", "列公司", dao=FakeDAO(), llm=_LLM(cy))


def test_has_kb_id_filter_true() -> None:
    assert has_kb_id_filter("MATCH (n {kb_id:$kb_id}) RETURN n LIMIT 5") is True


def test_has_kb_id_filter_false() -> None:
    assert has_kb_id_filter("MATCH (n:Company) RETURN n LIMIT 5") is False


# ════════════════════════════════════════════════════════════
# 四、只读且合规的 Cypher 放行（设计文档 10.4 原版）
# ════════════════════════════════════════════════════════════

def test_read_cypher_passes() -> None:
    """设计文档原版：合规只读 Cypher 应成功返回 QueryResult 与 sources。"""
    good = _LLM("MATCH (c:Company {kb_id:$kb_id}) RETURN c LIMIT 10")
    dao = FakeDAO()
    dao.read_rows = [{"c": {"name": "宇树科技"}, "url": "http://a"}]
    res = query_agent.answer("kb1", "公司列表", dao=dao, llm=good)
    assert res.cypher.upper().startswith("MATCH")
    assert "http://a" in res.sources


def test_read_only_true_for_pure_match() -> None:
    assert is_read_only("MATCH (n) RETURN n LIMIT 5") is True


def test_case_insensitive_write_detection() -> None:
    """写操作检测大小写不敏感。"""
    assert is_read_only("match (n) create (m)") is False
    assert is_read_only("MATCH (n) Merge (m:X)") is False
    assert is_read_only("match (n) set n.x=1") is False


# ════════════════════════════════════════════════════════════
# 五、assert_safe_query 组合场景
# ════════════════════════════════════════════════════════════

def test_assert_safe_query_passes_valid() -> None:
    """同时满足只读 + LIMIT + kb_id 时不抛异常。"""
    assert_safe_query(
        "MATCH (n:Company {kb_id:$kb_id}) WHERE n.name = $name RETURN n LIMIT 50"
    )


def test_assert_safe_query_write_takes_priority() -> None:
    """写操作优先拦截，即使同时缺 LIMIT/kb_id 也只报写操作错误。"""
    with pytest.raises(ValueError, match="写操作"):
        assert_safe_query("CREATE (n:X)")
