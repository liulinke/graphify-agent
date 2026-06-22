# 测试 planner.parse_instruction（设计文档 10.3 节）
# planner 现在用 prompt-based JSON 输出，FakeLLM 返回 JSON 字符串
from __future__ import annotations
import pytest
from graphify.agents.planner import parse_instruction, _extract_json
from graphify.schemas.plan import CollectPlan, SupplyChain
from tests.conftest import FakeLLM


def _make_llm(plan: CollectPlan) -> FakeLLM:
    """构造返回 plan 的 JSON 字符串的 FakeLLM（与新版 planner 的 invoke 路径兼容）。"""
    return FakeLLM(payload=plan.model_dump_json())


# ════════════════════════════════════════════════════════════════
# 一、_extract_json 辅助函数
# ════════════════════════════════════════════════════════════════

def test_extract_json_from_plain_json() -> None:
    """纯 JSON 字符串应直接返回。"""
    raw = '{"domain": "robotics", "source_limit": 100}'
    assert _extract_json(raw) == raw


def test_extract_json_from_markdown_block() -> None:
    """```json ... ``` 代码块内的 JSON 应被提取。"""
    raw = '这是计划：\n```json\n{"domain": "robotics"}\n```\n'
    result = _extract_json(raw)
    assert result == '{"domain": "robotics"}'


def test_extract_json_from_mixed_text() -> None:
    """JSON 前后有多余文字时，应提取出 JSON 对象。"""
    raw = '好的，这是计划 {"domain": "stock"} 请确认。'
    result = _extract_json(raw)
    assert '"domain"' in result


# ════════════════════════════════════════════════════════════════
# 二、parse_instruction 端到端
# ════════════════════════════════════════════════════════════════

def test_source_limit_injected() -> None:
    """指令中的来源数量应从 LLM JSON 输出中正确透传。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", source_limit=100)
    result = parse_instruction("kb1", "采集机器人行业新闻，来源100", llm=_make_llm(plan))
    assert result.source_limit == 100


def test_kb_id_is_overwritten() -> None:
    """parse_instruction 必须将传入的 kb_id 写回 plan，不依赖 LLM 输出。"""
    plan = CollectPlan(kb_id="llm_generated_id", domain="机器人")
    result = parse_instruction("correct_kb_id", "任意指令", llm=_make_llm(plan))
    assert result.kb_id == "correct_kb_id"


def test_include_supply_chain_recognized() -> None:
    """指令含"上下游/产业链"时，LLM 应输出 include_supply_chain=True。"""
    plan = CollectPlan(
        kb_id="kb1",
        domain="机器人",
        include_supply_chain=True,
        supply_chain=SupplyChain(upstream=["伺服电机"], downstream=["物流"]),
    )
    result = parse_instruction("kb1", "采集机器人产业链，含上下游", llm=_make_llm(plan))
    assert result.include_supply_chain is True
    assert "伺服电机" in result.supply_chain.upstream
    assert "物流" in result.supply_chain.downstream


def test_daily_schedule_recognized() -> None:
    """指令含"每日"时，schedule 应为 daily。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", schedule="daily")
    result = parse_instruction("kb1", "每日采集机器人新闻", llm=_make_llm(plan))
    assert result.schedule == "daily"


def test_returns_collect_plan_instance() -> None:
    """parse_instruction 应返回 CollectPlan，而非原始字典或字符串。"""
    plan = CollectPlan(kb_id="kb1", domain="股票")
    result = parse_instruction("kb1", "采集股票新闻", llm=_make_llm(plan))
    assert isinstance(result, CollectPlan)


def test_multiple_topics_passed_through() -> None:
    """LLM 输出的多个主题应完整保留。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", topics=["工业机器人", "协作机器人", "四足机器人"])
    result = parse_instruction("kb1", "采集三类机器人新闻", llm=_make_llm(plan))
    assert len(result.topics) == 3
    assert "工业机器人" in result.topics


def test_parse_json_wrapped_in_markdown() -> None:
    """LLM 用代码块包裹 JSON 时也能正确解析。"""
    plan = CollectPlan(kb_id="x", domain="stock", source_limit=50)
    json_str = plan.model_dump_json()
    # 模拟 LLM 返回 ```json ... ``` 格式
    payload = f"好的，这是采集计划：\n```json\n{json_str}\n```"
    llm = FakeLLM(payload=payload)
    result = parse_instruction("x", "采集股票", llm=llm)
    assert result.source_limit == 50
    assert result.kb_id == "x"
