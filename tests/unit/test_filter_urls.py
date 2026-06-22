# 测试 collector.filter_known_urls（设计文档 10.3 节）
from __future__ import annotations
import pytest
from graphify.agents.collector import filter_known_urls
from graphify.dedup.url_norm import normalize_url


# ── FakeRepo：仅实现 url_seen ─────────────────────────────────
class _FakeRepo:
    def __init__(self, seen: set[tuple[str, str]] | None = None) -> None:
        # seen 是 (kb_id, normalized_url) 元组集合
        self._seen: set[tuple[str, str]] = seen or set()

    def url_seen(self, kb_id: str, nu: str) -> bool:
        return (kb_id, nu) in self._seen


# ── 已知 URL 被过滤 ───────────────────────────────────────────
def test_filter_removes_known_urls() -> None:
    """已在 SourceRepo 中的 URL 应被过滤掉。"""
    nu1 = normalize_url("https://example.com/news/1")
    repo = _FakeRepo(seen={("kb1", nu1)})

    result = filter_known_urls(
        "kb1",
        ["https://example.com/news/1", "https://example.com/news/2"],
        limit=10,
        repo=repo,
    )
    assert "https://example.com/news/1" not in result
    assert "https://example.com/news/2" in result


# ── 结果数 ≤ limit ────────────────────────────────────────────
def test_filter_result_count_le_limit() -> None:
    """过滤后的 URL 数不超过 limit。"""
    repo = _FakeRepo()  # 全部未见过
    urls = [f"https://example.com/{i}" for i in range(20)]
    result = filter_known_urls("kb1", urls, limit=5, repo=repo)
    assert len(result) == 5


# ── 等价 URL（追踪参数不同）视为同一 URL ──────────────────────
def test_filter_equivalent_urls_deduped() -> None:
    """带追踪参数的 URL 规范化后等价，应被已知 URL 命中过滤。"""
    nu = normalize_url("https://example.com/news/1")
    repo = _FakeRepo(seen={("kb1", nu)})

    result = filter_known_urls(
        "kb1",
        ["https://example.com/news/1?utm_source=twitter#section"],
        limit=10,
        repo=repo,
    )
    assert len(result) == 0


# ── 全部未见过时全部返回（受 limit 约束） ─────────────────────
def test_filter_all_fresh_urls_returned() -> None:
    """全部未见过时返回 min(len(urls), limit) 条。"""
    repo = _FakeRepo()
    urls = ["https://example.com/a", "https://example.com/b"]
    result = filter_known_urls("kb1", urls, limit=10, repo=repo)
    assert set(result) == set(urls)


# ── 空输入不报错 ──────────────────────────────────────────────
def test_filter_empty_input_returns_empty() -> None:
    repo = _FakeRepo()
    assert filter_known_urls("kb1", [], limit=10, repo=repo) == []


# ── limit=0 返回空列表 ────────────────────────────────────────
def test_filter_limit_zero() -> None:
    repo = _FakeRepo()
    result = filter_known_urls("kb1", ["https://example.com"], limit=0, repo=repo)
    assert result == []
