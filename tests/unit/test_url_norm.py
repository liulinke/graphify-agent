# 测试 URL 规范化：设计文档 10.3 节 test_url_norm.py
import pytest
from graphify.dedup.url_norm import normalize_url


# ── 参数化：设计文档列出的典型用例 ──────────────────────────────
@pytest.mark.parametrize("raw,expected", [
    # 去 utm 参数、fragment；query 字母序；域名大小写归一
    (
        "https://A.com/p/?utm_source=x&b=2&a=1#frag",
        "https://a.com/p?a=1&b=2",
    ),
    # 路径尾斜杠去除
    (
        "http://x.com/path/",
        "http://x.com/path",
    ),
    # 无路径时保留根 /
    (
        "https://x.com",
        "https://x.com/",
    ),
])
def test_normalize_parametrized(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


# ── 追踪参数全家 ─────────────────────────────────────────────
def test_drops_all_tracking_params() -> None:
    url = (
        "https://news.cn/article?id=123"
        "&utm_source=wechat&utm_medium=social&utm_campaign=spring"
        "&utm_term=robot&utm_content=banner"
        "&ref=homepage&fbclid=abc&gclid=xyz"
    )
    result = normalize_url(url)
    # 只剩业务参数
    assert "id=123" in result
    # 追踪参数全部消失
    for bad in ("utm_", "fbclid", "gclid", "ref="):
        assert bad not in result


# ── fragment 移除 ────────────────────────────────────────────
def test_removes_fragment() -> None:
    assert "#" not in normalize_url("https://example.com/page#section-2")


# ── query 字典序稳定 ─────────────────────────────────────────
def test_query_order_is_stable() -> None:
    url1 = normalize_url("https://example.com/?z=3&a=1&m=2")
    url2 = normalize_url("https://example.com/?m=2&z=3&a=1")
    assert url1 == url2
    assert url1 == "https://example.com/?a=1&m=2&z=3"


# ── 域名大小写归一 ────────────────────────────────────────────
def test_domain_lowercased() -> None:
    result = normalize_url("HTTPS://News.Example.COM/Article")
    assert result.startswith("https://news.example.com/")


# ── http scheme 保留（不强制升级 https）────────────────────────
def test_http_scheme_preserved() -> None:
    result = normalize_url("http://example.com/page")
    assert result.startswith("http://")


# ── 前后空白剥离 ─────────────────────────────────────────────
def test_strips_whitespace() -> None:
    result = normalize_url("  https://example.com/page  ")
    assert result == "https://example.com/page"


# ── 规范化后等价 URL 相同（用于去重场景） ─────────────────────
def test_equivalent_urls_normalize_to_same() -> None:
    a = normalize_url("https://Example.COM/news/?utm_source=twitter&id=42#comments")
    b = normalize_url("https://example.com/news?id=42")
    assert a == b
