# 测试 SimHash 内容指纹：设计文档 10.3 节 test_simhash.py
import pytest
from graphify.dedup.simhash import simhash, hamming, is_near_dup


# ── 相同文本 hamming=0 ────────────────────────────────────────
def test_same_text_hamming_zero() -> None:
    text = "宇树科技发布新一代四足机器人，搭载自研关节电机。"
    h = simhash(text)
    assert hamming(h, h) == 0


# ── 改一个词，汉明距离 ≤ 阈值（默认 3）→ 判定为近似重复 ──────
def test_slightly_changed_text_is_near_dup() -> None:
    # SimHash 的特性：在足够长的文本中，一个 token 的变化对整体指纹影响极小
    # 使用重复基底保证单 token 差异被"稀释"，hamming 距离 ≤ 3
    _base = "工业机器人是中国制造2025的核心装备，广泛应用于汽车、3C、焊接等领域。" * 5
    text_a = _base + "产量增长8%"
    text_b = _base + "产量增长9%"
    h_a = simhash(text_a)
    h_b = simhash(text_b)
    assert is_near_dup(h_a, h_b, threshold=3)


# ── 完全不同内容，汉明距离 > 阈值 → 非重复 ─────────────────────
def test_completely_different_text_not_near_dup() -> None:
    text_a = "宇树科技发布新一代四足机器人，搭载自研关节电机。"
    text_b = "股市今日大涨，沪深300指数上涨2.3%，成交量创历史新高。"
    h_a = simhash(text_a)
    h_b = simhash(text_b)
    assert not is_near_dup(h_a, h_b, threshold=3)


# ── 空文本边界：返回 0 且不报错 ──────────────────────────────
def test_empty_text_returns_zero() -> None:
    assert simhash("") == 0
    assert hamming(0, 0) == 0
    assert is_near_dup(0, 0, threshold=3) is True


# ── hamming 距离对称性 ────────────────────────────────────────
def test_hamming_is_symmetric() -> None:
    h1 = simhash("埃斯顿机器人")
    h2 = simhash("埃斯顿工业自动化")
    assert hamming(h1, h2) == hamming(h2, h1)


# ── 阈值边界：hamming == threshold 应判为重复 ─────────────────
def test_is_near_dup_threshold_boundary() -> None:
    # 人为构造 hamming 恰好等于阈值
    a = 0b0000
    b = 0b0111  # hamming(a,b) = 3
    assert hamming(a, b) == 3
    assert is_near_dup(a, b, threshold=3) is True   # ≤ 阈值 → 重复
    assert is_near_dup(a, b, threshold=2) is False  # > 阈值 → 不重复


# ── 相同文本，不同 bits 参数，均不报错 ───────────────────────
@pytest.mark.parametrize("bits", [32, 64, 128])
def test_simhash_various_bits(bits: int) -> None:
    h = simhash("工业机器人行业分析报告", bits=bits)
    assert isinstance(h, int)
    assert h >= 0


# ── 大文本不报错，hamming 距离合法 ───────────────────────────
def test_large_text_no_error() -> None:
    long_text = "机器人" * 10_000
    h = simhash(long_text)
    assert isinstance(h, int)
    assert 0 <= hamming(h, 0) <= 64
