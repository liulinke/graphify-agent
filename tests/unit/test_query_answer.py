# 测试 query_agent.answer 端到端流程（设计文档 10.3 节）
from __future__ import annotations
import pytest
from graphify.agents.query_agent import answer
from graphify.schemas.query import QueryResult
from tests.conftest import FakeDAO


# ── 辅助：按顺序返回多个响应的 LLM 替身 ─────────────────────
class _SeqLLM:
    """按调用顺序依次返回预设响应（第 1 次=Cypher，第 2 次=答案）。"""

    def __init__(self, *responses: str) -> None:
        self._it = iter(responses)

    def invoke(self, msgs):
        content = next(self._it)

        class _M:
            pass

        m = _M()
        m.content = content
        return m


# ── 合规 Cypher 常量（含 kb_id + LIMIT）─────────────────────
_SAFE_CYPHER = "MATCH (c:Company {kb_id:$kb_id}) RETURN c.name AS name, c.url AS url LIMIT 10"


# ════════════════════════════════════════════════════════════
# 一、基本调用：返回 QueryResult
# ════════════════════════════════════════════════════════════

def test_answer_returns_query_result() -> None:
    """answer() 应返回 QueryResult 实例。"""
    llm = _SeqLLM(_SAFE_CYPHER, "宇树科技是四足机器人领先企业。")
    res = answer("kb1", "宇树科技是做什么的？", dao=FakeDAO(), llm=llm)
    assert isinstance(res, QueryResult)


def test_answer_cypher_field_contains_generated_cypher() -> None:
    """QueryResult.cypher 应为 LLM 生成的 Cypher 字符串。"""
    llm = _SeqLLM(_SAFE_CYPHER, "答案")
    res = answer("kb1", "测试", dao=FakeDAO(), llm=llm)
    assert res.cypher == _SAFE_CYPHER


def test_answer_field_contains_llm_answer() -> None:
    """QueryResult.answer 应为第二次 LLM 调用的返回内容。"""
    expected_answer = "宇树科技是四足机器人领先企业，主要客户包括华为等。"
    llm = _SeqLLM(_SAFE_CYPHER, expected_answer)
    res = answer("kb1", "宇树科技的客户？", dao=FakeDAO(), llm=llm)
    assert res.answer == expected_answer


# ════════════════════════════════════════════════════════════
# 二、sources 从 rows 提取
# ════════════════════════════════════════════════════════════

def test_sources_extracted_from_rows_url_field() -> None:
    """sources 应从 rows 中含 url 字段的行提取。"""
    dao = FakeDAO()
    dao.read_rows = [
        {"name": "宇树科技", "url": "http://news.com/1"},
        {"name": "埃斯顿",   "url": "http://news.com/2"},
    ]
    llm = _SeqLLM(_SAFE_CYPHER, "答案")
    res = answer("kb1", "公司列表", dao=dao, llm=llm)
    assert "http://news.com/1" in res.sources
    assert "http://news.com/2" in res.sources


def test_rows_without_url_excluded_from_sources() -> None:
    """rows 中不含 url 字段的行不应出现在 sources 中。"""
    dao = FakeDAO()
    dao.read_rows = [
        {"name": "宇树科技"},          # 无 url 字段
        {"name": "埃斯顿", "url": ""},  # 空字符串 url
        {"name": "汇川技术", "url": "http://news.com/3"},
    ]
    llm = _SeqLLM(_SAFE_CYPHER, "答案")
    res = answer("kb1", "公司列表", dao=dao, llm=llm)
    assert len(res.sources) == 1
    assert res.sources[0] == "http://news.com/3"


def test_empty_rows_gives_empty_sources() -> None:
    """rows 为空时 sources 应为空列表。"""
    llm = _SeqLLM(_SAFE_CYPHER, "未找到相关结果。")
    res = answer("kb1", "xxx", dao=FakeDAO(), llm=llm)
    assert res.sources == []
    assert res.rows == []


# ════════════════════════════════════════════════════════════
# 三、dao.run_read 被正确调用
# ════════════════════════════════════════════════════════════

def test_dao_run_read_called_with_kb_id() -> None:
    """dao.run_read 应以生成的 Cypher 和 kb_id 参数被调用。"""
    dao = FakeDAO()
    dao.read_rows = []

    class _TrackDAO(FakeDAO):
        def __init__(self):
            super().__init__()
            self.calls: list[tuple] = []

        def run_read(self, cypher, params=None):
            self.calls.append((cypher, params))
            return self.read_rows

    tracking_dao = _TrackDAO()
    llm = _SeqLLM(_SAFE_CYPHER, "答案")
    answer("kb1", "问题", dao=tracking_dao, llm=llm)

    assert len(tracking_dao.calls) == 1
    called_cypher, called_params = tracking_dao.calls[0]
    assert called_cypher == _SAFE_CYPHER
    assert called_params == {"kb_id": "kb1"}


# ════════════════════════════════════════════════════════════
# 四、LLM 被调用两次（NL→Cypher，再→答案）
# ════════════════════════════════════════════════════════════

def test_llm_invoked_twice() -> None:
    """answer() 应对 LLM 调用两次：第一次生成 Cypher，第二次生成自然语言答案。"""
    call_count = 0
    responses = [_SAFE_CYPHER, "测试答案"]

    class _CountingLLM:
        def invoke(self, msgs):
            nonlocal call_count
            content = responses[call_count]
            call_count += 1

            class _M:
                pass

            m = _M()
            m.content = content
            return m

    answer("kb1", "问题", dao=FakeDAO(), llm=_CountingLLM())
    assert call_count == 2


# ════════════════════════════════════════════════════════════
# 五、不同 kb_id 隔离
# ════════════════════════════════════════════════════════════

def test_kb_id_passed_to_dao() -> None:
    """不同 kb_id 应传入 dao.run_read，确保知识库隔离。"""
    for kb in ("kb_robotics", "kb_stock", "kb_test"):
        dao = FakeDAO()
        dao.read_rows = []

        class _KbDAO(FakeDAO):
            def __init__(self):
                super().__init__()
                self.last_params: dict = {}

            def run_read(self, cypher, params=None):
                self.last_params = params or {}
                return []

        tracking = _KbDAO()
        llm = _SeqLLM(_SAFE_CYPHER, "答案")
        answer(kb, "问题", dao=tracking, llm=llm)
        assert tracking.last_params.get("kb_id") == kb
