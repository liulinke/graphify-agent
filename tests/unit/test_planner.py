# 测试 planner.parse_instruction（设计文档 10.3 节）
from __future__ import annotations
import pytest
from graphify.agents.planner import parse_instruction
from graphify.schemas.plan import CollectPlan, SupplyChain
from tests.conftest import FakeLLM


def _make_llm(plan: CollectPlan) -> FakeLLM:
    """构造返回指定 CollectPlan 的 FakeLLM。"""
    return FakeLLM(payload=plan)


# ── source_limit 解析 ─────────────────────────────────────────
def test_source_limit_injected() -> None:
    """指令中的来源数量应从 LLM 输出中正确透传。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", source_limit=100)
    result = parse_instruction("kb1", "采集机器人行业新闻，来源100", llm=_make_llm(plan))
    assert result.source_limit == 100


# ── kb_id 强制注入（覆盖 LLM 可能输出的错误 id）────────────────
def test_kb_id_is_overwritten() -> None:
    """parse_instruction 必须将传入的 kb_id 写回 plan，不依赖 LLM 输出。"""
    plan = CollectPlan(kb_id="llm_generated_id", domain="机器人")
    result = parse_instruction("correct_kb_id", "任意指令", llm=_make_llm(plan))
    assert result.kb_id == "correct_kb_id"


# ── include_supply_chain 识别 ──────────────────────────────────
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


# ── schedule=daily 识别 ────────────────────────────────────────
def test_daily_schedule_recognized() -> None:
    """指令含"每日"时，schedule 应为 daily。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", schedule="daily")
    result = parse_instruction("kb1", "每日采集机器人新闻", llm=_make_llm(plan))
    assert result.schedule == "daily"


# ── 返回值是 CollectPlan 实例 ──────────────────────────────────
def test_returns_collect_plan_instance() -> None:
    """parse_instruction 应返回 CollectPlan，而非原始字典或字符串。"""
    plan = CollectPlan(kb_id="kb1", domain="股票")
    result = parse_instruction("kb1", "采集股票新闻", llm=_make_llm(plan))
    assert isinstance(result, CollectPlan)


# ── topics 多主题透传 ──────────────────────────────────────────
def test_multiple_topics_passed_through() -> None:
    """LLM 输出的多个主题应完整保留。"""
    plan = CollectPlan(kb_id="kb1", domain="机器人", topics=["工业机器人", "协作机器人", "四足机器人"])
    result = parse_instruction("kb1", "采集三类机器人新闻", llm=_make_llm(plan))
    assert len(result.topics) == 3
    assert "工业机器人" in result.topics
