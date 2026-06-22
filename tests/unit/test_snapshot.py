# 测试时序快照追加语义（设计文档 10.3 节）
# 核心规则：同公司同指标不同日期 → 多条快照全部保留，绝不覆盖历史
from __future__ import annotations
import pytest
from graphify.agents.graph_builder import persist
from graphify.schemas.graph import Entity, MetricSnapshot, ExtractionResult
from tests.conftest import FakeDAO


# ── 同公司同指标多日 → 多条快照保留历史 ──────────────────────
def test_multiple_days_all_snapshots_appended() -> None:
    """同公司同指标在不同日期应产生多条快照，全部追加到 dao.snapshots。"""
    dao = FakeDAO()
    exs = [
        ExtractionResult(
            entities=[Entity(label="Company", name="宇树科技", confidence=0.9)],
            snapshots=[MetricSnapshot(company="宇树科技", metric="股价", value=10.0, ts="2026-06-20")],
            source_url="http://a.com",
        ),
        ExtractionResult(
            entities=[Entity(label="Company", name="宇树科技", confidence=0.9)],
            snapshots=[MetricSnapshot(company="宇树科技", metric="股价", value=11.5, ts="2026-06-21")],
            source_url="http://b.com",
        ),
        ExtractionResult(
            entities=[Entity(label="Company", name="宇树科技", confidence=0.9)],
            snapshots=[MetricSnapshot(company="宇树科技", metric="股价", value=12.3, ts="2026-06-22")],
            source_url="http://c.com",
        ),
    ]
    report = persist("kb1", exs, dao=dao)

    # 三天三条快照全部保留
    assert report["snapshots"] == 3
    assert len(dao.snapshots) == 3

    # 历史值没有被覆盖（三条都在，且值各不同）
    values = {snap.value for snap in dao.snapshots}
    assert values == {10.0, 11.5, 12.3}

    # 日期各不相同
    dates = {snap.ts for snap in dao.snapshots}
    assert dates == {"2026-06-20", "2026-06-21", "2026-06-22"}


# ── 同公司不同指标 → 各自独立追加 ────────────────────────────
def test_different_metrics_all_appended() -> None:
    """同一公司不同指标（股价、销量）的快照应各自独立追加。"""
    dao = FakeDAO()
    ex = ExtractionResult(
        snapshots=[
            MetricSnapshot(company="埃斯顿", metric="股价", value=30.0, ts="2026-06-22"),
            MetricSnapshot(company="埃斯顿", metric="销量", value=5000.0, ts="2026-06-22"),
        ],
        source_url="http://x.com",
    )
    report = persist("kb1", [ex], dao=dao)
    assert report["snapshots"] == 2
    assert len(dao.snapshots) == 2

    metrics = {snap.metric for snap in dao.snapshots}
    assert metrics == {"股价", "销量"}


# ── 快照追加顺序与输入顺序一致 ────────────────────────────────
def test_snapshots_appended_in_order() -> None:
    """快照应按输入顺序追加（先进先出）。"""
    dao = FakeDAO()
    ex = ExtractionResult(
        snapshots=[
            MetricSnapshot(company="X", metric="股价", value=1.0, ts="2026-01-01"),
            MetricSnapshot(company="X", metric="股价", value=2.0, ts="2026-01-02"),
            MetricSnapshot(company="X", metric="股价", value=3.0, ts="2026-01-03"),
        ],
        source_url="http://x.com",
    )
    persist("kb1", [ex], dao=dao)
    assert [s.value for s in dao.snapshots] == [1.0, 2.0, 3.0]


# ── append_snapshot 每次都被调用（不是 update/overwrite） ──────
def test_append_snapshot_called_not_merge() -> None:
    """每条快照都触发一次 append_snapshot，而非更新已有记录。"""
    call_count = 0
    original_append = FakeDAO.append_snapshot

    class CountingDAO(FakeDAO):
        def append_snapshot(self, kb_id, snap):
            nonlocal call_count
            call_count += 1
            super().append_snapshot(kb_id, snap)

    dao = CountingDAO()
    ex = ExtractionResult(
        snapshots=[
            MetricSnapshot(company="A", metric="m", value=1.0, ts="2026-01-01"),
            MetricSnapshot(company="A", metric="m", value=2.0, ts="2026-01-02"),
        ],
        source_url="http://x.com",
    )
    persist("kb1", [ex], dao=dao)
    # 两条快照应调用 append 两次（而非 1 次 merge）
    assert call_count == 2
