# LangGraph 主工作流编排：采集闭环（plan → discover → dedup → collect → extract → build）
from __future__ import annotations
from langgraph.graph import StateGraph, START, END
from graphify.state import CollectState
from graphify.agents import planner, collector, graph_builder


def _plan_node(state: CollectState) -> dict:
    """解析自然语言指令为 CollectPlan。"""
    plan = planner.parse_instruction(state["kb_id"], state["instruction"])
    return {"plan": plan}


def _discover_node(state: CollectState) -> dict:
    """根据采集计划发现候选 URL。"""
    urls = collector.discover_urls(state["plan"])
    return {"candidate_urls": urls}


def _dedup_url_node(state: CollectState) -> dict:
    """URL 级去重，过滤已采集来源，保留 fresh_urls。"""
    fresh = collector.filter_known_urls(
        state["plan"].kb_id,
        state["candidate_urls"],
        state["plan"].source_limit,
    )
    return {"fresh_urls": fresh}


def _collect_node(state: CollectState) -> dict:
    """网页抓取 + 内容/语义去重 + 正文抽取（失败隔离）。"""
    fetched, errs = collector.run(state["plan"], state["fresh_urls"])
    return {"fetched": fetched, "errors": errs}


def _extract_node(state: CollectState) -> dict:
    """LLM 对每篇正文抽取三元组（ExtractionResult）。"""
    results = [graph_builder.extract(item) for item in state["fetched"]]
    return {"extractions": results}


def _build_node(state: CollectState) -> dict:
    """实体消歧 + MERGE 写 Neo4j + 追加时序快照，返回统计 report。"""
    report = graph_builder.persist(state["plan"].kb_id, state["extractions"])
    return {"report": report}


def build_workflow(checkpointer=None):
    """构建并编译 LangGraph 采集工作流，checkpointer 支持断点续跑。"""
    g: StateGraph = StateGraph(CollectState)
    g.add_node("plan", _plan_node)
    g.add_node("discover", _discover_node)
    g.add_node("dedup_url", _dedup_url_node)
    g.add_node("collect", _collect_node)
    g.add_node("extract_kg", _extract_node)
    g.add_node("build_graph", _build_node)

    g.add_edge(START, "plan")
    g.add_edge("plan", "discover")
    g.add_edge("discover", "dedup_url")
    g.add_edge("dedup_url", "collect")
    g.add_edge("collect", "extract_kg")
    g.add_edge("extract_kg", "build_graph")
    g.add_edge("build_graph", END)
    return g.compile(checkpointer=checkpointer)
