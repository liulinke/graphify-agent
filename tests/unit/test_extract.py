# 测试 graph_builder.extract（设计文档 10.3 节）
# graph_builder.extract 现在用 prompt-based JSON 输出，FakeLLM 返回 JSON 字符串
from __future__ import annotations
import pytest
from graphify.agents.graph_builder import extract, _extract_json, SCHEMA_HINT
from graphify.schemas.graph import ExtractionResult, Entity, Relation
from tests.conftest import FakeLLM


def _result_to_json(result: ExtractionResult) -> str:
    """将 ExtractionResult 序列化为 LLM 响应风格的 JSON 字符串。"""
    data = result.model_dump(exclude={"source_url"})
    import json
    return json.dumps(data, ensure_ascii=False)


def _llm(result: ExtractionResult) -> FakeLLM:
    """构造返回 ExtractionResult JSON 字符串的 FakeLLM。"""
    return FakeLLM(payload=_result_to_json(result))


# ════════════════════════════════════════════════════════════════
# 一、_extract_json 辅助函数
# ════════════════════════════════════════════════════════════════

def test_extract_json_plain() -> None:
    """纯 JSON 字符串应直接返回。"""
    raw = '{"entities": [], "relations": [], "snapshots": []}'
    assert _extract_json(raw) == raw


def test_extract_json_from_markdown() -> None:
    """```json ... ``` 包裹时应提取内部 JSON。"""
    raw = '```json\n{"entities": []}\n```'
    assert _extract_json(raw) == '{"entities": []}'


# ════════════════════════════════════════════════════════════════
# 二、source_url 从 item["url"] 注入
# ════════════════════════════════════════════════════════════════

def test_source_url_injected_from_item() -> None:
    """extract 必须将 item['url'] 写回 result.source_url，不依赖 LLM 输出。"""
    fake_result = ExtractionResult(
        entities=[Entity(label="Company", name="埃斯顿")],
        source_url="llm_placeholder",
    )
    item = {"url": "https://real.example.com/article/1", "text": "埃斯顿发布新品"}
    res = extract(item, llm=_llm(fake_result))
    assert res.source_url == "https://real.example.com/article/1"


# ════════════════════════════════════════════════════════════════
# 三、返回值是 ExtractionResult 实例
# ════════════════════════════════════════════════════════════════

def test_returns_extraction_result_instance() -> None:
    """extract 应返回 ExtractionResult，而非原始字典或字符串。"""
    item = {"url": "https://example.com/", "text": "正文"}
    res = extract(item, llm=_llm(ExtractionResult()))
    assert isinstance(res, ExtractionResult)


# ════════════════════════════════════════════════════════════════
# 四、长文本截断（≤ 8000 字后传给 LLM）
# ════════════════════════════════════════════════════════════════

def test_long_text_is_truncated() -> None:
    """text 超过 8000 字时，传给 LLM 的内容应截断，不应报错。"""
    long_text = "机器人行业" * 2000
    item = {"url": "https://example.com/long", "text": long_text}
    res = extract(item, llm=_llm(ExtractionResult()))
    assert isinstance(res, ExtractionResult)


# ════════════════════════════════════════════════════════════════
# 五、entities/relations 字段保持原样透传
# ════════════════════════════════════════════════════════════════

def test_entities_and_relations_preserved() -> None:
    """LLM 返回的实体和关系应原封不动保留在结果中。"""
    fake_result = ExtractionResult(
        entities=[
            Entity(label="Company", name="宇树科技", confidence=0.9),
            Entity(label="Industry", name="机器人", confidence=0.8),
        ],
        relations=[
            Relation(type="BELONGS_TO", source_name="宇树科技", target_name="机器人", confidence=0.85),
        ],
    )
    item = {"url": "https://example.com/", "text": "宇树科技属于机器人行业"}
    res = extract(item, llm=_llm(fake_result))
    assert len(res.entities) == 2
    assert len(res.relations) == 1
    assert res.entities[0].name == "宇树科技"


# ════════════════════════════════════════════════════════════════
# 六、JSON 解析失败时返回空 ExtractionResult（不崩溃）
# ════════════════════════════════════════════════════════════════

def test_invalid_json_returns_empty_result() -> None:
    """LLM 返回无效 JSON 时，extract 应返回空 ExtractionResult，不抛异常。"""
    bad_llm = FakeLLM(payload="我无法理解这篇文章")
    item = {"url": "https://example.com/", "text": "正文"}
    res = extract(item, llm=bad_llm)
    assert isinstance(res, ExtractionResult)
    assert res.entities == []
    assert res.source_url == "https://example.com/"


def test_partial_json_returns_empty_result() -> None:
    """LLM 返回截断的 JSON 时，extract 应返回空 ExtractionResult。"""
    bad_llm = FakeLLM(payload='{"entities": [{"label": "Company"')
    item = {"url": "https://x.com/", "text": "文本"}
    res = extract(item, llm=bad_llm)
    assert isinstance(res, ExtractionResult)
    assert res.entities == []


# ════════════════════════════════════════════════════════════════
# 七、网络错误时返回空 ExtractionResult（不崩溃）
# ════════════════════════════════════════════════════════════════

class _NetworkErrorLLM:
    """模拟 DashScope / 任意 LLM 在 invoke 时抛网络异常的替身，记录调用次数。"""
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, msgs):
        self.calls += 1
        raise ConnectionError("Remote end closed connection without response")


def test_network_error_returns_empty_result(monkeypatch) -> None:
    """LLM invoke 持续抛 ConnectionError 时，extract 重试耗尽后应返回空结果，不传播异常。"""
    # 退避调零，避免单元测试真实 sleep
    monkeypatch.setattr("graphify.agents.graph_builder._RETRY_BACKOFF_S", (0, 0))
    item = {"url": "https://example.com/net-err", "text": "正文"}
    llm = _NetworkErrorLLM()
    res = extract(item, llm=llm)
    assert isinstance(res, ExtractionResult)
    assert res.entities == []
    assert res.source_url == "https://example.com/net-err"
    assert llm.calls == 3  # 首次 + 重试 2 次


class _FlakyLLM:
    """前 N 次抛网络异常、之后返回正常 JSON 的替身（模拟瞬时代理断连）。"""
    def __init__(self, fail_times: int, payload: str) -> None:
        self.fail_times = fail_times
        self.payload = payload
        self.calls = 0

    def invoke(self, msgs):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise ConnectionError("Broken pipe")

        class _M:
            pass

        m = _M()
        m.content = self.payload
        return m


def test_invalid_snapshot_does_not_discard_whole_page() -> None:
    """个别脏快照（value=null）只跳过该条，同页实体/关系必须保留。"""
    payload = (
        '{"entities": [{"label": "Company", "name": "宇树科技", "props": {}, "confidence": 0.9}],'
        ' "relations": [],'
        ' "snapshots": ['
        '   {"company": "宇树科技", "metric": "估值", "value": null, "ts": "2026-06-01", "unit": "亿元"},'
        '   {"company": "宇树科技", "metric": "股价", "value": 12.5, "ts": "2026-06-01", "unit": "元"}'
        ' ]}'
    )
    res = extract({"url": "https://x.com/", "text": "正文"}, llm=FakeLLM(payload=payload))
    assert len(res.entities) == 1          # 实体不受脏快照影响
    assert len(res.snapshots) == 1         # 只保留合法快照
    assert res.snapshots[0].value == 12.5


def test_schema_violating_labels_filtered() -> None:
    """schema 外的标签（如 Technology）和关系类型应被过滤，合法条目保留。"""
    payload = (
        '{"entities": ['
        '   {"label": "Company", "name": "宇树科技", "props": {}, "confidence": 0.9},'
        '   {"label": "Technology", "name": "强化学习", "props": {}, "confidence": 0.9}'
        ' ],'
        ' "relations": ['
        '   {"type": "SUPPLIES", "source_name": "A", "target_name": "B", "props": {}, "confidence": 0.8},'
        '   {"type": "USES_TECH", "source_name": "A", "target_name": "C", "props": {}, "confidence": 0.8}'
        ' ],'
        ' "snapshots": []}'
    )
    res = extract({"url": "https://x.com/", "text": "正文"}, llm=FakeLLM(payload=payload))
    assert [e.label for e in res.entities] == ["Company"]     # Technology 被过滤
    assert [r.type for r in res.relations] == ["SUPPLIES"]    # USES_TECH 被过滤


def test_transient_network_error_retried(monkeypatch) -> None:
    """瞬时网络错误应自动重试，第二次成功即返回正常抽取结果。"""
    monkeypatch.setattr("graphify.agents.graph_builder._RETRY_BACKOFF_S", (0, 0))
    payload = '{"entities": [{"label": "Company", "name": "宇树科技", "props": {}, "confidence": 0.9}], "relations": [], "snapshots": []}'
    llm = _FlakyLLM(fail_times=1, payload=payload)
    res = extract({"url": "https://x.com/", "text": "正文"}, llm=llm)
    assert llm.calls == 2
    assert len(res.entities) == 1
    assert res.entities[0].name == "宇树科技"
