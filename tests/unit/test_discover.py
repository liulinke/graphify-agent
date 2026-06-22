# 测试 collector.discover_urls（设计文档 10.3 节）
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from graphify.agents.collector import discover_urls
from graphify.schemas.plan import CollectPlan, SupplyChain


def _mock_search(return_value: list[str]) -> MagicMock:
    """构造替代 search_urls 的 mock 对象，记录 invoke 调用参数。"""
    m = MagicMock()
    m.invoke.return_value = return_value
    return m


# ── 候选 URL 数为 source_limit 的 2 倍 ───────────────────────
def test_discover_limit_is_2x(monkeypatch) -> None:
    """discover_urls 应以 source_limit*2 为 limit 参数调用 search_urls。"""
    mock = _mock_search([f"https://example.com/{i}" for i in range(20)])
    monkeypatch.setattr("graphify.agents.collector.search_urls", mock)

    plan = CollectPlan(kb_id="kb1", domain="机器人", topics=["机器人"], source_limit=10)
    urls = discover_urls(plan)

    called_params = mock.invoke.call_args[0][0]
    assert called_params["limit"] == 20   # 2x
    assert len(urls) == 20


# ── 主题词 + 上下游词全部合并 ────────────────────────────────
def test_discover_includes_supply_chain_terms(monkeypatch) -> None:
    """搜索词应包含 topics + upstream + downstream。"""
    mock = _mock_search([])
    monkeypatch.setattr("graphify.agents.collector.search_urls", mock)

    plan = CollectPlan(
        kb_id="kb1",
        domain="机器人",
        topics=["工业机器人"],
        supply_chain=SupplyChain(upstream=["伺服电机"], downstream=["物流"]),
        source_limit=10,
    )
    discover_urls(plan)

    terms = mock.invoke.call_args[0][0]["terms"]
    assert "工业机器人" in terms
    assert "伺服电机" in terms
    assert "物流" in terms


# ── 空主题词不报错 ────────────────────────────────────────────
def test_discover_empty_topics_returns_empty(monkeypatch) -> None:
    """主题词和上下游词均为空时，search_urls 仍被调用，结果为空列表。"""
    mock = _mock_search([])
    monkeypatch.setattr("graphify.agents.collector.search_urls", mock)

    plan = CollectPlan(kb_id="kb1", domain="机器人", topics=[], source_limit=5)
    result = discover_urls(plan)

    mock.invoke.assert_called_once()
    assert result == []


# ── region 和 lang 透传 ───────────────────────────────────────
def test_discover_passes_region_and_lang(monkeypatch) -> None:
    """region 和 language 字段应透传到 search_urls。"""
    mock = _mock_search([])
    monkeypatch.setattr("graphify.agents.collector.search_urls", mock)

    plan = CollectPlan(
        kb_id="kb1",
        domain="机器人",
        topics=["机器人"],
        region="US",
        language=["en"],
        source_limit=5,
    )
    discover_urls(plan)

    params = mock.invoke.call_args[0][0]
    assert params["region"] == "US"
    assert params["lang"] == ["en"]
