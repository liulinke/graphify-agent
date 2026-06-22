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
