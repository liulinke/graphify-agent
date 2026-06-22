# Query Agent：自然语言 → Cypher 查询 → 自然语言答案（只读护栏）
from __future__ import annotations
from graphify.schemas.query import QueryResult
from graphify.graphdb.dao import GraphDAO
from graphify.tools.cypher import assert_read_only

NL2CYPHER_SYS = """把用户问题转为 Neo4j 只读 Cypher。
- 仅允许 MATCH/RETURN/WHERE/ORDER/LIMIT，禁止 CREATE/MERGE/DELETE/SET。
- 必须带 kb_id 过滤与 LIMIT。
- 使用参数化占位符（如 $kb_id）。"""

ANSWER_SYS = "基于查询结果用中文简洁作答，并标注来源URL。"


def answer(
    kb_id: str,
    question: str,
    dao: GraphDAO | None = None,
    llm=None,
) -> QueryResult:
    """将自然语言问题转为 Cypher 并执行，最终生成中文答案。"""
    from graphify.llm import get_llm
    dao = dao or GraphDAO()
    llm = llm or get_llm()

    # 第一步：NL → Cypher
    cypher: str = llm.invoke([
        ("system", NL2CYPHER_SYS),
        ("human", f"kb_id={kb_id}; 问题: {question}"),
    ]).content

    # 安全护栏：含写操作关键字则抛出 ValueError
    assert_read_only(cypher)

    # 第二步：执行只读查询
    rows = dao.run_read(cypher, {"kb_id": kb_id})

    # 第三步：LLM 生成自然语言答案
    summary: str = llm.invoke([
        ("system", ANSWER_SYS),
        ("human", str(rows)[:6000]),
    ]).content

    # 从查询结果中提取来源 URL
    sources = [r.get("url") for r in rows if isinstance(r, dict) and r.get("url")]
    return QueryResult(cypher=cypher, rows=rows, answer=summary, sources=sources)
