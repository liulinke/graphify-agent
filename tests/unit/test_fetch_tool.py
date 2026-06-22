# 测试 graphify/tools/fetch.py（_extract_text 与 fetch_page）
# 用 unittest.mock.patch 替代 httpx.Client，不做真实网络请求
from __future__ import annotations
import pytest
import httpx
from unittest.mock import MagicMock, patch
from graphify.tools.fetch import _extract_text, fetch_page


# ════════════════════════════════════════════════════════════════
# 一、_extract_text 纯函数测试（无 IO）
# ════════════════════════════════════════════════════════════════

def test_extract_text_returns_title() -> None:
    """<title> 标签内容应被正确提取为 title。"""
    html = "<html><head><title>测试页面</title></head><body><p>正文</p></body></html>"
    title, text = _extract_text(html)
    assert title == "测试页面"


def test_extract_text_strips_noise_tags() -> None:
    """script/style/nav 等噪音标签应从正文中剔除。"""
    html = """<html><body>
        <script>var x=1;</script>
        <nav>导航</nav>
        <p>真正的正文内容</p>
        <footer>页脚</footer>
    </body></html>"""
    _, text = _extract_text(html)
    assert "真正的正文内容" in text
    assert "var x=1" not in text
    assert "导航" not in text
    assert "页脚" not in text


def test_extract_text_empty_title_when_missing() -> None:
    """HTML 中无 <title> 时，title 应为空字符串。"""
    html = "<html><body><p>正文</p></body></html>"
    title, _ = _extract_text(html)
    assert title == ""


def test_extract_text_returns_body_text() -> None:
    """<body> 中的文本应被提取为正文。"""
    html = "<html><body><p>第一段</p><p>第二段</p></body></html>"
    _, text = _extract_text(html)
    assert "第一段" in text
    assert "第二段" in text


def test_extract_text_empty_html() -> None:
    """空字符串 HTML 不应抛异常，title 和 text 均为空或空字符串。"""
    title, text = _extract_text("")
    assert isinstance(title, str)
    assert isinstance(text, str)


# ════════════════════════════════════════════════════════════════
# 二、fetch_page 工具测试（mock httpx.Client）
# ════════════════════════════════════════════════════════════════

def _make_mock_response(html: str, status: int = 200) -> MagicMock:
    """构造模拟的 httpx 响应对象。"""
    resp = MagicMock()
    resp.text = html
    resp.status_code = status
    resp.raise_for_status = MagicMock()  # 200 时不抛异常
    return resp


@patch("graphify.tools.fetch.httpx.Client")
def test_fetch_page_returns_dict(mock_client_cls) -> None:
    """fetch_page 成功时应返回包含 url/html/text/title/status 的 dict。"""
    html = "<html><head><title>标题</title></head><body><p>内容</p></body></html>"
    ctx = MagicMock()
    ctx.get.return_value = _make_mock_response(html)
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = fetch_page.invoke({"url": "http://example.com"})
    assert result["url"] == "http://example.com"
    assert result["status"] == 200
    assert "标题" in result["title"]
    assert "内容" in result["text"]
    assert result["html"] == html


@patch("graphify.tools.fetch.httpx.Client")
def test_fetch_page_raises_on_4xx(mock_client_cls) -> None:
    """4xx 状态码应直接抛出 HTTPStatusError，不重试。"""
    resp = MagicMock()
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "404", request=MagicMock(), response=MagicMock()
    )
    ctx = MagicMock()
    ctx.get.return_value = resp
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_page.invoke({"url": "http://example.com/notfound"})


@patch("graphify.tools.fetch.httpx.Client")
def test_fetch_page_retries_on_network_error(mock_client_cls) -> None:
    """网络错误时应重试（最多 max_retries 次），最终仍失败则上抛。"""
    ctx = MagicMock()
    ctx.get.side_effect = httpx.ConnectError("连接失败")
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    with pytest.raises(httpx.ConnectError):
        fetch_page.invoke({"url": "http://unreachable.example.com"})

    # 应尝试 max_retries（3）次
    from graphify.config import settings
    assert ctx.get.call_count == settings.fetch_max_retries


@patch("graphify.tools.fetch.httpx.Client")
def test_fetch_page_extracts_title_in_result(mock_client_cls) -> None:
    """结果中的 title 应来自 HTML <title> 标签。"""
    html = "<html><head><title>机器人行业报告</title></head><body>内容</body></html>"
    ctx = MagicMock()
    ctx.get.return_value = _make_mock_response(html)
    mock_client_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)

    result = fetch_page.invoke({"url": "http://example.com"})
    assert result["title"] == "机器人行业报告"
