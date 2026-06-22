# 测试 LangGraph 主工作流编排（设计文档 10.3/10.4 节）
# 验证：节点顺序、状态累积、errors 不中断工作流
from __future__ import annotations
from unittest.mock import patch, MagicMock, call
import pytest
from graphify.graph_workflow import build_workflow
from graphify.schemas.plan import CollectPlan
from graphify.schemas.graph import ExtractionResult


# ── 辅助：构造测试用 plan ──────────────────────────────────────
def _plan(kb_id: str = "kb1") -> CollectPlan:
    return CollectPlan(kb_id=kb_id, domain="test", source_limit=10)


# ── 设计文档 10.4 原版用例 ────────────────────────────────────
@patch("graphify.graph_workflow.graph_builder.persist", return_value={"nodes": 2})
@patch("graphify.graph_workflow.graph_builder.extract")
@patch("graphify.graph_workflow.collector.run", return_value=([{"url": "u", "text": "t"}], []))
@patch("graphify.graph_workflow.collector.filter_known_urls", return_value=["u"])
@patch("graphify.graph_workflow.collector.discover_urls", return_value=["u", "u2"])
@patch("graphify.graph_workflow.planner.parse_instruction")
def test_workflow_runs_and_returns_report(mock_plan, mock_disc, mock_filt, mock_run, mock_ex, mock_per):
    mock_plan.return_value = _plan()
    mock_ex.return_value = ExtractionResult()

    wf = build_workflow()
    out = wf.invoke({"kb_id": "kb1", "instruction": "x"})

    assert out["report"] == {"nodes": 2}


# ── 所有节点按顺序执行 ────────────────────────────────────────
def test_workflow_node_execution_order() -> None:
    """plan → discover → dedup_url → collect → extract_kg → build_graph 顺序执行。"""
    call_order: list[str] = []

    def track(name, ret):
        def fn(*args, **kwargs):
            call_order.append(name)
            return ret
        return fn

    plan = _plan()

    with patch("graphify.graph_workflow.planner.parse_instruction",
               side_effect=track("plan", plan)), \
         patch("graphify.graph_workflow.collector.discover_urls",
               side_effect=track("discover", ["u1"])), \
         patch("graphify.graph_workflow.collector.filter_known_urls",
               side_effect=track("dedup_url", ["u1"])), \
         patch("graphify.graph_workflow.collector.run",
               side_effect=track("collect", ([{"url": "u1", "text": "t"}], []))), \
         patch("graphify.graph_workflow.graph_builder.extract",
               side_effect=track("extract_kg", ExtractionResult())), \
         patch("graphify.graph_workflow.graph_builder.persist",
               side_effect=track("build_graph", {"nodes": 1, "relations": 0, "snapshots": 0, "skipped_low_conf": 0})):

        wf = build_workflow()
        wf.invoke({"kb_id": "kb1", "instruction": "采集测试"})

    assert call_order == ["plan", "discover", "dedup_url", "collect", "extract_kg", "build_graph"]


# ── 状态在节点间正确累积 ────────────────────────────────────
def test_workflow_state_accumulation() -> None:
    """candidate_urls 由 discover 写入；fresh_urls 由 dedup_url 写入；均应体现在最终 out 中。"""
    plan = _plan()

    with patch("graphify.graph_workflow.planner.parse_instruction", return_value=plan), \
         patch("graphify.graph_workflow.collector.discover_urls", return_value=["u1", "u2", "u3"]), \
         patch("graphify.graph_workflow.collector.filter_known_urls", return_value=["u1", "u2"]), \
         patch("graphify.graph_workflow.collector.run", return_value=([{"url": "u1", "text": "t"}], [])), \
         patch("graphify.graph_workflow.graph_builder.extract", return_value=ExtractionResult()), \
         patch("graphify.graph_workflow.graph_builder.persist",
               return_value={"nodes": 0, "relations": 0, "snapshots": 0, "skipped_low_conf": 0}):

        wf = build_workflow()
        out = wf.invoke({"kb_id": "kb1", "instruction": "test"})

    assert out["candidate_urls"] == ["u1", "u2", "u3"]
    assert out["fresh_urls"] == ["u1", "u2"]
    assert len(out["fetched"]) == 1
    assert len(out["extractions"]) == 1


# ── collector.run 的 errors 写入 out["errors"]，工作流不中断 ──
def test_workflow_errors_recorded_without_crash() -> None:
    """采集部分 URL 失败时，错误记录在 out['errors']，工作流仍完整执行到最后。"""
    plan = _plan()

    with patch("graphify.graph_workflow.planner.parse_instruction", return_value=plan), \
         patch("graphify.graph_workflow.collector.discover_urls", return_value=["u1", "u2"]), \
         patch("graphify.graph_workflow.collector.filter_known_urls", return_value=["u1", "u2"]), \
         patch("graphify.graph_workflow.collector.run",
               return_value=([], ["https://u1.com: ConnectionError", "https://u2.com: Timeout"])), \
         patch("graphify.graph_workflow.graph_builder.extract", return_value=ExtractionResult()), \
         patch("graphify.graph_workflow.graph_builder.persist",
               return_value={"nodes": 0, "relations": 0, "snapshots": 0, "skipped_low_conf": 0}):

        wf = build_workflow()
        out = wf.invoke({"kb_id": "kb1", "instruction": "test"})

    # 工作流完成，report 存在
    assert "report" in out
    # 错误被累积到 errors 字段
    assert len(out["errors"]) == 2
    assert any("ConnectionError" in e for e in out["errors"])


# ── build_workflow 接受 checkpointer=None（无持久化模式） ──────
def test_build_workflow_without_checkpointer() -> None:
    """不传 checkpointer 时 build_workflow 应正常返回可调用的工作流。"""
    wf = build_workflow(checkpointer=None)
    # 只验证可以构建，不实际运行
    assert callable(wf.invoke)


# ── 多篇文章的 extractions 通过 add reducer 累积 ────────────
def test_extractions_accumulate_via_reducer() -> None:
    """fetched 包含 2 条时，extract_kg 节点应产生 2 条 ExtractionResult。"""
    plan = _plan()
    ex_results = [ExtractionResult(source_url="http://a.com"),
                  ExtractionResult(source_url="http://b.com")]

    call_args: list = []

    def fake_extract(item):
        idx = call_args.__len__()
        call_args.append(item)
        return ex_results[idx]

    with patch("graphify.graph_workflow.planner.parse_instruction", return_value=plan), \
         patch("graphify.graph_workflow.collector.discover_urls", return_value=["u1", "u2"]), \
         patch("graphify.graph_workflow.collector.filter_known_urls", return_value=["u1", "u2"]), \
         patch("graphify.graph_workflow.collector.run",
               return_value=([{"url": "u1", "text": "t1"}, {"url": "u2", "text": "t2"}], [])), \
         patch("graphify.graph_workflow.graph_builder.extract", side_effect=fake_extract), \
         patch("graphify.graph_workflow.graph_builder.persist",
               return_value={"nodes": 2, "relations": 0, "snapshots": 0, "skipped_low_conf": 0}):

        wf = build_workflow()
        out = wf.invoke({"kb_id": "kb1", "instruction": "test"})

    assert len(out["extractions"]) == 2
    assert len(call_args) == 2
