# 测试 collector.run（设计文档 10.3 节）
from __future__ import annotations
from unittest.mock import MagicMock
import pytest
from graphify.agents.collector import run
from graphify.schemas.plan import CollectPlan


def _plan() -> CollectPlan:
    return CollectPlan(kb_id="kb1", domain="test", topics=[])


def _mock_fetch(side_effect=None, return_value=None) -> MagicMock:
    m = MagicMock()
    if side_effect is not None:
        m.invoke.side_effect = side_effect
    else:
        m.invoke.return_value = return_value
    return m


def _mock_dedup(return_value: dict) -> MagicMock:
    m = MagicMock()
    m.invoke.return_value = return_value
    return m


def _mock_extract(return_value: dict) -> MagicMock:
    m = MagicMock()
    m.invoke.return_value = return_value
    return m


# ── 抓取异常被隔离写 errors ───────────────────────────────────
def test_run_fetch_exception_goes_to_errors(monkeypatch) -> None:
    """fetch_page 抛出异常时，错误写入 errors，不中断整批。"""
    monkeypatch.setattr(
        "graphify.agents.collector.fetch_page",
        _mock_fetch(side_effect=ConnectionError("网络不通")),
    )

    fetched, errors = run(_plan(), ["https://fail.example.com"])
    assert len(fetched) == 0
    assert len(errors) == 1
    assert "网络不通" in errors[0]


# ── 重复内容被跳过，不进 fetched ──────────────────────────────
def test_run_duplicate_is_skipped(monkeypatch) -> None:
    """check_duplicate 返回 is_duplicate=True 时，URL 被跳过（不进 fetched 也不进 errors）。"""
    monkeypatch.setattr(
        "graphify.agents.collector.fetch_page",
        _mock_fetch(return_value={"url": "u", "html": "<p>x</p>", "text": "x", "status": 200}),
    )
    monkeypatch.setattr(
        "graphify.agents.collector.check_duplicate",
        _mock_dedup({"is_duplicate": True, "level": "url", "matched_source_id": None, "changed": False}),
    )

    fetched, errors = run(_plan(), ["https://dup.example.com"])
    assert len(fetched) == 0
    assert len(errors) == 0


# ── 成功抓取的非重复内容进入 fetched ─────────────────────────
def test_run_fresh_content_in_fetched(monkeypatch) -> None:
    """抓取成功且非重复时，内容（含 url）进入 fetched。"""
    monkeypatch.setattr(
        "graphify.agents.collector.fetch_page",
        _mock_fetch(return_value={"url": "https://fresh.example.com", "html": "<p>正文</p>", "text": "正文", "status": 200}),
    )
    monkeypatch.setattr(
        "graphify.agents.collector.check_duplicate",
        _mock_dedup({"is_duplicate": False, "level": None, "matched_source_id": None, "changed": False}),
    )
    monkeypatch.setattr(
        "graphify.agents.collector.extract_content",
        _mock_extract({"text": "提取后正文", "title": "标题", "fields": {}}),
    )

    fetched, errors = run(_plan(), ["https://fresh.example.com"])
    assert len(fetched) == 1
    assert fetched[0]["url"] == "https://fresh.example.com"
    assert fetched[0]["text"] == "提取后正文"
    assert len(errors) == 0


# ── 多 URL 混合：异常/重复/成功各独立处理 ─────────────────────
def test_run_mixed_urls(monkeypatch) -> None:
    """多 URL 中异常、重复、成功应分别写 errors、跳过、进 fetched。"""
    urls = [
        "https://fail.example.com",    # 抓取失败
        "https://dup.example.com",     # 重复
        "https://fresh.example.com",   # 成功
    ]

    def fake_fetch_invoke(params: dict) -> dict:
        if "fail" in params["url"]:
            raise TimeoutError("超时")
        return {"url": params["url"], "html": "<p>x</p>", "text": "x", "status": 200}

    def fake_dedup_invoke(params: dict) -> dict:
        is_dup = "dup" in params["url"]
        return {"is_duplicate": is_dup, "level": None, "matched_source_id": None, "changed": False}

    fetch_mock = MagicMock()
    fetch_mock.invoke.side_effect = fake_fetch_invoke
    dedup_mock = MagicMock()
    dedup_mock.invoke.side_effect = fake_dedup_invoke
    extract_mock = _mock_extract({"text": "正文", "title": "标题", "fields": {}})

    monkeypatch.setattr("graphify.agents.collector.fetch_page", fetch_mock)
    monkeypatch.setattr("graphify.agents.collector.check_duplicate", dedup_mock)
    monkeypatch.setattr("graphify.agents.collector.extract_content", extract_mock)

    fetched, errors = run(_plan(), urls)
    assert len(errors) == 1
    assert len(fetched) == 1
    assert fetched[0]["url"] == "https://fresh.example.com"


# ── extract_content 异常也被隔离 ──────────────────────────────
def test_run_extract_exception_isolated(monkeypatch) -> None:
    """extract_content 抛出异常时，错误写入 errors，其他 URL 不受影响。"""
    monkeypatch.setattr(
        "graphify.agents.collector.fetch_page",
        _mock_fetch(return_value={"url": "u", "html": "<p>x</p>", "text": "x", "status": 200}),
    )
    monkeypatch.setattr(
        "graphify.agents.collector.check_duplicate",
        _mock_dedup({"is_duplicate": False, "level": None, "matched_source_id": None, "changed": False}),
    )
    extract_mock = MagicMock()
    extract_mock.invoke.side_effect = ValueError("解析失败")
    monkeypatch.setattr("graphify.agents.collector.extract_content", extract_mock)

    fetched, errors = run(_plan(), ["https://example.com"])
    assert len(fetched) == 0
    assert len(errors) == 1
    assert "解析失败" in errors[0]
