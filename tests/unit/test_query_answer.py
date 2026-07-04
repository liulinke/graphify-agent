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

# ── 辅助：返回非空行的 FakeDAO（避免触发空结果降级重查分支）──
def _dao_with_rows() -> FakeDAO:
    dao = FakeDAO()
    dao.read_rows = [{"name": "宇树科技"}]
    return dao


def test_answer_returns_query_result() -> None:
    """answer() 应返回 QueryResult 实例。"""
    llm = _SeqLLM(_SAFE_CYPHER, "宇树科技是四足机器人领先企业。")
    res = answer("kb1", "宇树科技是做什么的？", dao=_dao_with_rows(), llm=llm)
    assert isinstance(res, QueryResult)


def test_answer_cypher_field_contains_generated_cypher() -> None:
    """QueryResult.cypher 应为 LLM 生成的 Cypher 字符串。"""
    llm = _SeqLLM(_SAFE_CYPHER, "答案")
    res = answer("kb1", "测试", dao=_dao_with_rows(), llm=llm)
    assert res.cypher == _SAFE_CYPHER


def test_answer_field_contains_llm_answer() -> None:
    """QueryResult.answer 应为第二次 LLM 调用的返回内容。"""
    expected_answer = "宇树科技是四足机器人领先企业，主要客户包括华为等。"
    llm = _SeqLLM(_SAFE_CYPHER, expected_answer)
    res = answer("kb1", "宇树科技的客户？", dao=_dao_with_rows(), llm=llm)
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
    """rows 为空时 sources 应为空列表（空结果会触发一次降级重查，需 3 个响应）。"""
    llm = _SeqLLM(_SAFE_CYPHER, _SAFE_CYPHER, "未找到相关结果。")
    res = answer("kb1", "xxx", dao=FakeDAO(), llm=llm)
    assert res.sources == []
    assert res.rows == []


def test_empty_result_triggers_fallback_query() -> None:
    """首次查询空结果时应降级重查一次，并采用重查语句与结果。"""
    fallback_cypher = "MATCH (c:Company) WHERE c.kb_id = $kb_id AND c.name CONTAINS '机器人' RETURN c.name AS name LIMIT 50"

    class _FallbackDAO(FakeDAO):
        """第一次 run_read 返回空，第二次返回数据（模拟关系联查落空）。"""
        def __init__(self):
            super().__init__()
            self.queries: list[str] = []

        def run_read(self, cypher, params=None):
            self.queries.append(cypher)
            return [] if len(self.queries) == 1 else [{"name": "宇树科技"}]

    dao = _FallbackDAO()
    llm = _SeqLLM(_SAFE_CYPHER, fallback_cypher, "找到 1 家公司：宇树科技")
    res = answer("kb1", "有哪些机器人公司？", dao=dao, llm=llm)
    assert len(dao.queries) == 2                 # 确实重查了一次
    assert res.cypher == fallback_cypher         # 记录实际生效的降级语句
    assert res.rows == [{"name": "宇树科技"}]


def test_unsafe_first_cypher_regenerated_with_feedback() -> None:
    """首条 Cypher 违规（缺 kb_id）时应带反馈重生成一次，修正后正常执行。"""
    bad = "MATCH (c:Company) RETURN c.kb_id, c.name LIMIT 50"  # RETURN 中的 kb_id 不算过滤
    llm = _SeqLLM(bad, _SAFE_CYPHER, "答案")
    res = answer("kb1", "问题", dao=_dao_with_rows(), llm=llm)
    assert res.cypher == _SAFE_CYPHER  # 采用修正后的合规语句


def test_unsafe_cypher_still_blocked_after_retry() -> None:
    """反馈重生成后仍违规时应抛出 ValueError（护栏不放水）。"""
    bad = "MATCH (c:Company) RETURN c.name LIMIT 50"  # 始终缺 kb_id
    llm = _SeqLLM(bad, bad)
    with pytest.raises(ValueError, match="kb_id"):
        answer("kb1", "问题", dao=FakeDAO(), llm=llm)


def test_unsafe_fallback_query_discarded() -> None:
    """降级查询不合规（如缺 kb_id）时应放弃重查，保留首次空结果，不抛异常。

    调用序列：① 首条 Cypher（合规）② 降级 Cypher（违规）③ 违规反馈重生成
    （仍违规）④ 生成最终答案。
    """
    bad_fallback = "MATCH (c:Company) RETURN c.name LIMIT 50"  # 缺 kb_id 过滤
    llm = _SeqLLM(_SAFE_CYPHER, bad_fallback, bad_fallback, "未找到")
    res = answer("kb1", "问题", dao=FakeDAO(), llm=llm)
    assert res.cypher == _SAFE_CYPHER  # 保留首次合规语句
    assert res.rows == []


# ════════════════════════════════════════════════════════════
# 三、dao.run_read 被正确调用
# ════════════════════════════════════════════════════════════

def test_dao_run_read_called_with_kb_id() -> None:
    """dao.run_read 应以生成的 Cypher 和 kb_id 参数被调用。"""

    class _TrackDAO(FakeDAO):
        def __init__(self):
            super().__init__()
            self.calls: list[tuple] = []

        def run_read(self, cypher, params=None):
            self.calls.append((cypher, params))
            return self.read_rows

    tracking_dao = _TrackDAO()
    tracking_dao.read_rows = [{"name": "宇树科技"}]  # 非空，避免触发降级重查
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
    """结果非空时 LLM 应恰好调用两次：第一次生成 Cypher，第二次生成答案。"""
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

    answer("kb1", "问题", dao=_dao_with_rows(), llm=_CountingLLM())
    assert call_count == 2


# ════════════════════════════════════════════════════════════
# 五、不同 kb_id 隔离
# ════════════════════════════════════════════════════════════

def test_cypher_code_fences_stripped() -> None:
    """LLM 输出带 ```cypher 围栏时应剥离后再过安全检查与执行。"""
    fenced = f"```cypher\n{_SAFE_CYPHER}\n```"
    llm = _SeqLLM(fenced, "答案")
    res = answer("kb1", "问题", dao=_dao_with_rows(), llm=llm)
    assert res.cypher == _SAFE_CYPHER  # 存入结果的 Cypher 应是干净的


def test_nl2cypher_prompt_contains_graph_schema() -> None:
    """NL2Cypher 系统提示必须注入真实图谱 schema，防止 LLM 凭空猜标签。"""
    from graphify.agents.query_agent import NL2CYPHER_SYS
    # 受控 schema 中的核心标签与关系必须出现在提示词里
    for token in ("Company", "Industry", "Source", "CITED_BY", "HAS_SNAPSHOT", "SUPPLIES"):
        assert token in NL2CYPHER_SYS


def test_answer_prompt_includes_question() -> None:
    """第二次 LLM 调用（生成答案）的消息中必须包含原始问题。"""
    captured: list = []

    class _CaptureLLM:
        def __init__(self):
            self.n = 0

        def invoke(self, msgs):
            self.n += 1
            captured.append(msgs)

            class _M:
                pass

            m = _M()
            m.content = _SAFE_CYPHER if self.n == 1 else "答案"
            return m

    answer("kb1", "宇树科技的客户有哪些？", dao=_dao_with_rows(), llm=_CaptureLLM())
    # 第二次调用的 human 消息应带上原问题，避免 LLM 不知道在回答什么
    second_call_text = str(captured[1])
    assert "宇树科技的客户有哪些？" in second_call_text


def test_kb_id_passed_to_dao() -> None:
    """不同 kb_id 应传入 dao.run_read，确保知识库隔离。"""
    for kb in ("kb_robotics", "kb_stock", "kb_test"):

        class _KbDAO(FakeDAO):
            def __init__(self):
                super().__init__()
                self.last_params: dict = {}

            def run_read(self, cypher, params=None):
                self.last_params = params or {}
                return [{"name": "宇树科技"}]  # 非空，避免触发降级重查

        tracking = _KbDAO()
        llm = _SeqLLM(_SAFE_CYPHER, "答案")
        answer(kb, "问题", dao=tracking, llm=llm)
        assert tracking.last_params.get("kb_id") == kb
