# 测试三层去重逻辑 check_duplicate_impl（设计文档 10.3 节）
from __future__ import annotations
import hashlib
import pytest
from graphify.tools.dedup import check_duplicate_impl
from graphify.dedup.url_norm import normalize_url
from graphify.dedup.simhash import simhash
from graphify.store.source_repo import InMemorySourceRepo


# ── 辅助函数 ──────────────────────────────────────────────────

def _md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _repo_with_url(kb_id: str, url: str, text: str) -> InMemorySourceRepo:
    """预先注册一条 URL 记录（用于测试命中分支）。"""
    repo = InMemorySourceRepo()
    nu = normalize_url(url)
    repo.mark_seen(kb_id, nu, _md5(text), simhash(text))
    return repo


# ── 第一层：URL 命中且内容未变 → 重复 ─────────────────────────
def test_url_hit_same_content_is_duplicate() -> None:
    text = "宇树科技发布新款四足机器人。"
    url = "https://example.com/news/1"
    repo = _repo_with_url("kb1", url, text)

    result = check_duplicate_impl("kb1", url, text, repo)

    assert result["is_duplicate"] is True
    assert result["level"] == "url"
    assert result["changed"] is False
    assert result["matched_source_id"] == normalize_url(url)


# ── 第一层：URL 命中但内容变化 → 非重复，changed=True ──────────
def test_url_hit_changed_content_not_duplicate() -> None:
    url = "https://example.com/news/1"
    repo = _repo_with_url("kb1", url, "旧内容")

    result = check_duplicate_impl("kb1", url, "全新不同的内容", repo)

    assert result["is_duplicate"] is False
    assert result["changed"] is True
    assert result["level"] == "url"


# ── 第一层命中时写 dedup_log ────────────────────────────────
def test_url_hit_writes_dedup_log() -> None:
    text = "某公司发布产品公告。"
    url = "https://example.com/news/2"
    repo = _repo_with_url("kb1", url, text)

    check_duplicate_impl("kb1", url, text, repo)

    assert len(repo.logs) == 1
    assert repo.logs[0]["level"] == "url"


# ── 第二层：内容指纹（SimHash）近似 → 重复 ────────────────────
def test_simhash_near_dup_detected() -> None:
    """SimHash 近似的两段文本（分开 URL）应被内容层判重。"""
    base = "工业机器人是中国制造2025的核心装备，广泛应用于汽车、3C、焊接等领域。" * 5
    text_a = base + "产量增长8%"
    text_b = base + "产量增长9%"  # 与 text_a simhash 汉明距离 ≤ 3

    repo = InMemorySourceRepo()
    # 先注册 text_a
    check_duplicate_impl("kb1", "https://a.com/1", text_a, repo)

    # text_b 来自不同 URL，走 simhash 层
    result = check_duplicate_impl("kb1", "https://b.com/2", text_b, repo)

    assert result["is_duplicate"] is True
    assert result["level"] == "simhash"


# ── 第二层：内容完全不同 → 非重复 ─────────────────────────────
def test_simhash_different_text_not_dup() -> None:
    text_a = "宇树科技四足机器人" * 30
    text_b = "A股大涨，沪深300指数创历史新高" * 30

    repo = InMemorySourceRepo()
    check_duplicate_impl("kb1", "https://a.com/1", text_a, repo)
    result = check_duplicate_impl("kb1", "https://b.com/2", text_b, repo)

    assert result["is_duplicate"] is False
    assert result["level"] is None


# ── 第三层：语义开关关闭时不走向量 ──────────────────────────
def test_semantic_dedup_disabled_by_default(monkeypatch) -> None:
    """enable_semantic_dedup=False（默认）时，不调用向量化，不触发语义层。"""
    called = False

    def fake_similarity(a: str, b: str) -> float:
        nonlocal called
        called = True
        return 0.99  # 如果被调用则应视为重复

    monkeypatch.setattr("graphify.dedup.semantic.semantic_similarity", fake_similarity)

    repo = InMemorySourceRepo()
    result = check_duplicate_impl("kb1", "https://example.com/x", "任意内容", repo)

    assert called is False          # 开关关闭时绝不调用
    assert result["is_duplicate"] is False


# ── 非重复时 mark_seen 被调用 ────────────────────────────────
def test_new_url_is_marked_seen() -> None:
    """全新 URL 通过所有层后，应被 mark_seen 记录。"""
    url = "https://brand-new.com/article"
    repo = InMemorySourceRepo()
    nu = normalize_url(url)

    assert not repo.url_seen("kb1", nu)

    check_duplicate_impl("kb1", url, "这是一篇新文章", repo)

    assert repo.url_seen("kb1", nu)


# ── URL 规范化后等价的两次请求 ────────────────────────────────
def test_url_normalization_in_dedup() -> None:
    """带追踪参数的 URL 应规范化后与已记录 URL 命中（第一层）。"""
    text = "某篇文章"
    base_url = "https://example.com/article"
    tracked_url = "https://example.com/article?utm_source=wechat"

    repo = InMemorySourceRepo()
    # 先以干净 URL 注册
    check_duplicate_impl("kb1", base_url, text, repo)
    # 再以带追踪参数的等价 URL 请求
    result = check_duplicate_impl("kb1", tracked_url, text, repo)

    assert result["is_duplicate"] is True
    assert result["level"] == "url"
