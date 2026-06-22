# 测试 graph_builder.extract（设计文档 10.3 节）
from __future__ import annotations
import pytest
from graphify.agents.graph_builder import extract, SCHEMA_HINT
from graphify.schemas.graph import ExtractionResult, Entity, Relation
from tests.conftest import FakeLLM


# ── FakeLLM 辅助 ───────────────────────────────────────────────
def _llm(result: ExtractionResult) -> FakeLLM:
    return FakeLLM(payload=result)


# ── source_url 从 item["url"] 注入 ─────────────────────────────
def test_source_url_injected_from_item() -> None:
    """extract 必须将 item['url'] 写回 result.source_url，不依赖 LLM 输出。"""
    fake_result = ExtractionResult(
        entities=[Entity(label="Company", name="埃斯顿")],
        source_url="llm_placeholder",   # LLM 可能输出错误值
    )
    item = {"url": "https://real.example.com/article/1", "text": "埃斯顿发布新品"}
    res = extract(item, llm=_llm(fake_result))
    assert res.source_url == "https://real.example.com/article/1"


# ── 返回值是 ExtractionResult 实例 ────────────────────────────
def test_returns_extraction_result_instance() -> None:
    fake_result = ExtractionResult()
    item = {"url": "https://example.com/", "text": "正文"}
    res = extract(item, llm=_llm(fake_result))
    assert isinstance(res, ExtractionResult)


# ── 长文本被截断（≤ 8000 字符后 LLM 调用） ─────────────────────
def test_long_text_is_truncated() -> None:
    """text 超过 8000 字时，传给 LLM 的内容应截断，不应报错。"""
    long_text = "机器人行业" * 2000      # > 10000 字
    fake_result = ExtractionResult()
    item = {"url": "https://example.com/long", "text": long_text}
    # 只要不抛异常即可；FakeLLM 不关心消息内容
    res = extract(item, llm=_llm(fake_result))
    assert isinstance(res, ExtractionResult)


# ── FakeLLM 走 with_structured_output 路径 ────────────────────
def test_llm_structured_output_path_called() -> None:
    """extract 应调用 llm.with_structured_output(ExtractionResult)。"""
    invoked_with_schema: list = []

    class _TrackingLLM:
        def with_structured_output(self, schema):
            invoked_with_schema.append(schema)
            return self

        def invoke(self, msgs):
            return ExtractionResult(source_url="x")

    item = {"url": "https://example.com/", "text": "文章正文"}
    extract(item, llm=_TrackingLLM())
    assert len(invoked_with_schema) == 1
    assert invoked_with_schema[0] is ExtractionResult


# ── entities/relations 字段保持原样透传 ────────────────────────
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
