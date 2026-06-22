# 测试 graph_builder.persist（设计文档 10.3 节 + 10.4 示例）
from __future__ import annotations
import pytest
from graphify.agents.graph_builder import persist
from graphify.schemas.graph import (
    Entity, Relation, MetricSnapshot, ExtractionResult,
)
from tests.conftest import FakeDAO


# ── 设计文档 10.4 原版用例 ────────────────────────────────────
def test_persist_skips_low_confidence_and_appends_snapshot() -> None:
    """低置信度实体被 skip；快照走 append 不覆盖；统计数正确。"""
    dao = FakeDAO()
    ex = ExtractionResult(
        entities=[
            Entity(label="Company", name="宇树科技", confidence=0.9),
            Entity(label="Company", name="噪声实体", confidence=0.2),   # < 0.6 → skip
        ],
        relations=[
            Relation(type="SUPPLIES", source_name="A", target_name="B", confidence=0.8),
        ],
        snapshots=[
            MetricSnapshot(company="宇树科技", metric="股价", value=12.3, ts="2026-06-22"),
        ],
        source_url="http://x.com",
    )
    report = persist("kb1", [ex], dao=dao, min_conf=0.6)

    assert report["nodes"] == 1             # 只有"宇树科技"通过
    assert report["skipped_low_conf"] == 1  # "噪声实体"被跳过
    assert report["relations"] == 1
    assert report["snapshots"] == 1
    assert len(dao.snapshots) == 1          # append 而非覆盖（关键！）


# ── 低置信度关系也被跳过 ────────────────────────────────────
def test_low_confidence_relation_skipped() -> None:
    """置信度低于阈值的关系应被 skip 计数。"""
    dao = FakeDAO()
    ex = ExtractionResult(
        entities=[Entity(label="Company", name="A", confidence=0.9)],
        relations=[
            Relation(type="SUPPLIES", source_name="A", target_name="B", confidence=0.3),  # skip
        ],
        source_url="http://x.com",
    )
    report = persist("kb1", [ex], dao=dao, min_conf=0.6)
    assert report["relations"] == 0
    assert report["skipped_low_conf"] == 1
    assert len(dao.relations) == 0


# ── 多条 ExtractionResult 的统计累加 ────────────────────────
def test_persist_accumulates_across_extractions() -> None:
    """多篇文章的结果应在同一个 report 中累加统计。"""
    dao = FakeDAO()
    ex1 = ExtractionResult(
        entities=[Entity(label="Company", name="埃斯顿", confidence=0.9)],
        source_url="http://a.com",
    )
    ex2 = ExtractionResult(
        entities=[Entity(label="Company", name="汇川技术", confidence=0.9)],
        source_url="http://b.com",
    )
    report = persist("kb1", [ex1, ex2], dao=dao)
    assert report["nodes"] == 2
    assert len(dao.entities) == 2


# ── 空 extractions 不报错 ──────────────────────────────────
def test_persist_empty_extractions() -> None:
    dao = FakeDAO()
    report = persist("kb1", [], dao=dao)
    assert report == {"nodes": 0, "relations": 0, "snapshots": 0, "skipped_low_conf": 0}


# ── min_conf 阈值可调整 ────────────────────────────────────
def test_persist_custom_min_conf() -> None:
    """min_conf=0 时，所有实体/关系均通过（不被跳过）。"""
    dao = FakeDAO()
    ex = ExtractionResult(
        entities=[Entity(label="Company", name="低置信", confidence=0.1)],
        source_url="http://x.com",
    )
    report = persist("kb1", [ex], dao=dao, min_conf=0.0)
    assert report["nodes"] == 1
    assert report["skipped_low_conf"] == 0


# ── merge_source 对每篇文章调用一次 ────────────────────────
def test_merge_source_called_per_extraction() -> None:
    """每篇文章应触发一次 merge_source，写入来源 URL。"""
    dao = FakeDAO()
    exs = [
        ExtractionResult(source_url="http://a.com"),
        ExtractionResult(source_url="http://b.com"),
    ]
    persist("kb1", exs, dao=dao)
    assert dao.merged_sources == ["http://a.com", "http://b.com"]
