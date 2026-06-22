# Typer CLI：调试与测试入口，支持逐节点单步触发
from __future__ import annotations
import json
import typer
from graphify.agents import planner, graph_builder, query_agent, collector

app = typer.Typer(help="Graphify 服务端调试 CLI")


@app.command()
def plan(kb_id: str, instruction: str) -> None:
    """仅解析采集指令为 CollectPlan（不采集）。"""
    p = planner.parse_instruction(kb_id, instruction)
    typer.echo(p.model_dump_json(indent=2, ensure_ascii=False))


@app.command()
def discover(kb_id: str, instruction: str) -> None:
    """解析指令 + URL 发现，打印候选 URL 列表。"""
    p = planner.parse_instruction(kb_id, instruction)
    urls = collector.discover_urls(p)
    typer.echo(json.dumps(urls, ensure_ascii=False, indent=2))


@app.command()
def fetch(url: str) -> None:
    """抓取单个 URL，打印正文摘要（前 1000 字符）。"""
    from graphify.tools.fetch import fetch_page
    page = fetch_page.invoke({"url": url})
    typer.echo(page["text"][:1000])


@app.command()
def dedup(kb_id: str, url: str) -> None:
    """对单个 URL 跑三层去重，打印结果。"""
    from graphify.tools.fetch import fetch_page
    from graphify.tools.dedup import check_duplicate
    page = fetch_page.invoke({"url": url})
    result = check_duplicate.invoke({"kb_id": kb_id, "url": url, "text": page["text"]})
    typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def collect(kb_id: str, instruction: str, dry_run: bool = False) -> None:
    """端到端运行采集工作流（含图谱写入）。"""
    from graphify.graph_workflow import build_workflow
    from langgraph.checkpoint.memory import MemorySaver
    # 运行时用内存 checkpointer；如需持久化可替换为 SqliteSaver
    checkpointer = MemorySaver()
    wf = build_workflow(checkpointer=checkpointer)
    out = wf.invoke(
        {"kb_id": kb_id, "instruction": instruction},
        config={"configurable": {"thread_id": f"{kb_id}-cli"}},
    )
    typer.echo(json.dumps(out["report"], ensure_ascii=False, indent=2))


@app.command()
def ask(kb_id: str, question: str) -> None:
    """自然语言查询知识图谱，打印 Cypher、答案和来源。"""
    res = query_agent.answer(kb_id, question)
    typer.echo(f"Cypher: {res.cypher}\n\n答案: {res.answer}\n来源: {res.sources}")


@app.command()
def expand(
    kb_id: str,
    node_id: int,
    rel_types: str = "SUPPLIES,HAS_METRIC",
) -> None:
    """图形化探索：展开指定节点的邻居关系。"""
    from graphify.graphdb.dao import GraphDAO
    rows = GraphDAO().expand_node(kb_id, node_id, rel_types.split(","))
    typer.echo(json.dumps(rows, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    app()
