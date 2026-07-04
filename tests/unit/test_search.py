# 测试 graphify/tools/search.py（Tavily 搜索集成）
# 全部 mock Tavily，不做真实网络请求
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
from graphify.tools.search import _build_tavily, _search_term, search_urls


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch):
    """失败重试的退避调零，避免单元测试真实 sleep。"""
    monkeypatch.setattr("graphify.tools.search._RETRY_BACKOFF_S", (0, 0))


# ════════════════════════════════════════════════════════════════
# 一、_build_tavily：API key 存在/缺失时的工厂行为
# ════════════════════════════════════════════════════════════════

def test_build_tavily_returns_none_without_api_key(monkeypatch) -> None:
    """未配置 TAVILY_API_KEY 时，_build_tavily 应返回 None。"""
    from graphify.tools import search as search_mod
    # 构造一个 tavily_api_key 为空的 settings 替身
    fake_settings = MagicMock()
    fake_settings.tavily_api_key = ""
    with patch.object(search_mod, "settings", fake_settings):
        result = search_mod._build_tavily()
    assert result is None


def test_build_tavily_returns_instance_with_api_key(monkeypatch) -> None:
    """配置了 TAVILY_API_KEY 时，_build_tavily 应返回 TavilySearch 实例。"""
    from graphify.tools import search as search_mod
    fake_settings = MagicMock()
    fake_settings.tavily_api_key = "tvly-test-key"
    mock_tavily_cls = MagicMock()
    with patch.object(search_mod, "settings", fake_settings), \
         patch("graphify.tools.search.TavilySearch", mock_tavily_cls, create=True):
        # 通过补丁注入，不实际调用真实 TavilySearch
        from langchain_tavily import TavilySearch as _TS
        mock_instance = MagicMock()
        with patch("langchain_tavily.TavilySearch", return_value=mock_instance):
            result = search_mod._build_tavily()
    # 只要没有抛出，且返回值不是 None 即可（真实 key 分支）
    assert result is not None


# ════════════════════════════════════════════════════════════════
# 二、_search_term：单词搜索与异常处理
# ════════════════════════════════════════════════════════════════

def _make_tavily_mock(results: list[dict]) -> MagicMock:
    """构造返回固定结果的 Tavily mock 对象。"""
    m = MagicMock()
    m.invoke.return_value = {"results": results, "query": "test"}
    return m


def test_search_term_extracts_urls() -> None:
    """_search_term 应从结果中提取 url 字段。"""
    tavily = _make_tavily_mock([
        {"url": "http://a.com", "title": "A", "content": "内容A"},
        {"url": "http://b.com", "title": "B", "content": "内容B"},
    ])
    urls = _search_term(tavily, "机器人")
    assert urls == ["http://a.com", "http://b.com"]


def test_search_term_skips_missing_url() -> None:
    """结果中缺少 url 字段的条目应被跳过。"""
    tavily = _make_tavily_mock([
        {"title": "无 URL 条目", "content": "内容"},
        {"url": "http://valid.com", "title": "有效"},
    ])
    urls = _search_term(tavily, "搜索词")
    assert urls == ["http://valid.com"]


def test_search_term_returns_empty_on_empty_results() -> None:
    """Tavily 返回空 results 时应返回空列表。"""
    tavily = _make_tavily_mock([])
    # 空列表会触发 TavilySearch 内部的 ToolException，mock 忽略
    tavily.invoke.return_value = {"results": [], "query": "test"}
    urls = _search_term(tavily, "无结果词")
    assert urls == []


def test_search_term_handles_exception_gracefully() -> None:
    """Tavily 抛出异常时应捕获并返回空列表，不向上传播。"""
    tavily = MagicMock()
    tavily.invoke.side_effect = RuntimeError("网络超时")
    urls = _search_term(tavily, "搜索词")
    assert urls == []


def test_search_term_handles_error_dict_response() -> None:
    """Tavily 内部异常时返回 {"error": ...} dict，应被检测到并返回空列表。

    这是 TavilySearch._run 遇到 SSLError 等网络异常时的实际行为。
    """
    tavily = MagicMock()
    tavily.invoke.return_value = {"error": Exception("SSL EOF")}
    urls = _search_term(tavily, "工业机器人")
    assert urls == []


def test_search_term_retries_transient_error() -> None:
    """瞬时网络错误应重试；第二次成功时返回正常结果。"""
    tavily = MagicMock()
    tavily.invoke.side_effect = [
        {"error": Exception("SSL EOF")},                       # 第一次失败
        {"results": [{"url": "http://ok.com"}], "query": "t"}  # 第二次成功
    ]
    urls = _search_term(tavily, "机器人")
    assert urls == ["http://ok.com"]
    assert tavily.invoke.call_count == 2


def test_search_term_skips_empty_url_string() -> None:
    """url 字段为空字符串的条目应被跳过。"""
    tavily = _make_tavily_mock([
        {"url": "", "title": "空 URL"},
        {"url": "http://good.com", "title": "正常"},
    ])
    urls = _search_term(tavily, "词")
    assert urls == ["http://good.com"]


# ════════════════════════════════════════════════════════════════
# 三、search_urls @tool：整体流程
# ════════════════════════════════════════════════════════════════

def _patch_build_tavily(mock_tavily, mod):
    """替换 search 模块的 _build_tavily 函数，返回 mock_tavily。"""
    return patch.object(mod, "_build_tavily", return_value=mock_tavily)


def test_search_urls_returns_empty_when_no_api_key() -> None:
    """未配置 API key（_build_tavily 返回 None）时应返回空列表。"""
    from graphify.tools import search as search_mod
    with patch.object(search_mod, "_build_tavily", return_value=None):
        result = search_urls.invoke({"terms": ["机器人"], "limit": 10})
    assert result == []


def test_search_urls_returns_empty_for_empty_terms() -> None:
    """terms 为空列表时不应调用 Tavily，直接返回空列表。"""
    mock_tavily = MagicMock()
    from graphify.tools import search as search_mod
    with _patch_build_tavily(mock_tavily, search_mod):
        result = search_urls.invoke({"terms": [], "limit": 10})
    mock_tavily.invoke.assert_not_called()
    assert result == []


def test_search_urls_deduplicates_across_terms() -> None:
    """多个搜索词返回重复 URL 时，结果应去重。"""
    from graphify.tools import search as search_mod

    call_count = 0
    def fake_invoke(term):
        # 两个词都返回 http://dup.com，只应出现一次
        return {"results": [
            {"url": "http://dup.com", "title": "重复"},
            {"url": f"http://unique-{term}.com", "title": "唯一"},
        ]}

    mock_tavily = MagicMock()
    mock_tavily.invoke.side_effect = fake_invoke

    with _patch_build_tavily(mock_tavily, search_mod):
        result = search_urls.invoke({"terms": ["词A", "词B"], "limit": 100})

    assert result.count("http://dup.com") == 1
    assert "http://unique-词A.com" in result
    assert "http://unique-词B.com" in result


def test_search_urls_respects_limit() -> None:
    """返回的 URL 数量不超过 limit。"""
    from graphify.tools import search as search_mod

    mock_tavily = MagicMock()
    mock_tavily.invoke.return_value = {"results": [
        {"url": f"http://site{i}.com"} for i in range(20)
    ]}

    with _patch_build_tavily(mock_tavily, search_mod):
        result = search_urls.invoke({"terms": ["机器人", "电机", "减速机"], "limit": 5})

    assert len(result) <= 5


def test_search_urls_stops_early_when_limit_reached() -> None:
    """达到 limit 后不应继续调用后续搜索词。"""
    from graphify.tools import search as search_mod

    mock_tavily = MagicMock()
    # 每次调用返回 3 个唯一 URL
    call_idx = [0]
    def fake_invoke(term):
        i = call_idx[0]
        call_idx[0] += 1
        return {"results": [{"url": f"http://site{i}-{j}.com"} for j in range(3)]}
    mock_tavily.invoke.side_effect = fake_invoke

    with _patch_build_tavily(mock_tavily, search_mod):
        # limit=3，第一个词就满了，不应再调用第二个词
        result = search_urls.invoke({"terms": ["词A", "词B", "词C"], "limit": 3})

    assert len(result) == 3
    assert mock_tavily.invoke.call_count == 1   # 只调用了第一个词


def test_search_urls_collects_from_multiple_terms() -> None:
    """多个词的搜索结果应汇聚在一起（未达 limit 时继续下一个词）。"""
    from graphify.tools import search as search_mod

    mock_tavily = MagicMock()
    mock_tavily.invoke.side_effect = [
        {"results": [{"url": "http://a.com"}, {"url": "http://b.com"}]},
        {"results": [{"url": "http://c.com"}]},
    ]

    with _patch_build_tavily(mock_tavily, search_mod):
        result = search_urls.invoke({"terms": ["词A", "词B"], "limit": 10})

    assert set(result) == {"http://a.com", "http://b.com", "http://c.com"}
    assert mock_tavily.invoke.call_count == 2


def test_search_urls_tolerates_per_term_failure() -> None:
    """某个词搜索失败时应跳过，继续搜索下一个词。"""
    from graphify.tools import search as search_mod

    mock_tavily = MagicMock()
    mock_tavily.invoke.side_effect = [
        RuntimeError("词A 超时"),  # 第一个词失败
        {"results": [{"url": "http://from-b.com"}]},  # 第二个词成功
    ]

    with _patch_build_tavily(mock_tavily, search_mod):
        result = search_urls.invoke({"terms": ["词A", "词B"], "limit": 10})

    assert result == ["http://from-b.com"]
