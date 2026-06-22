# Query Agent：自然语言 → Cypher 查询 → 自然语言答案（三道安全护栏）
from __future__ import annotations
from graphify.schemas.query import QueryResult
from graphify.graphdb.dao import GraphDAO
from graphify.tools.cypher import assert_safe_query

NL2CYPHER_SYS = """把用户问题转为 Neo4j 只读 Cypher。
- 仅允许 MATCH/RETURN/WHERE/ORDER BY/LIMIT，禁止 CREATE/MERGE/DELETE/SET/REMOVE/DROP。
- 必须带 kb_id 过滤（如 WHERE n.kb_id = $kb_id）和 LIMIT（如 LIMIT 50）。
- 使用参数化占位符（如 $kb_id），禁止字符串拼接。
只输出 Cypher 语句，不加任何解释。"""

ANSWER_SYS = "基于查询结果用中文简洁作答，并标注来源 URL。"


def answer(
    kb_id: str,
    question: str,
    dao: GraphDAO | None = None,
    llm=None,
) -> QueryResult:
    """将自然语言问题转为 Cypher 并执行，最终生成中文答案。

    三道护栏（assert_safe_query）：
    1. 写操作拦截（CREATE/MERGE/DELETE/SET …）
    2. 强制 LIMIT（防止全图扫描）
    3. 强制 kb_id 过滤（防止跨知识库越权查询）
    """
    from graphify.llm import get_llm
    dao = dao or GraphDAO()
    llm = llm or get_llm()

    # 第一步：NL → Cypher
    cypher: str = llm.invoke([
        ("system", NL2CYPHER_SYS),
        ("human", f"kb_id={kb_id}; 问题: {question}"),
    ]).content

    # 安全护栏：三道检查，任一不过直接抛出 ValueError
    assert_safe_query(cypher)

    # 第二步：执行只读查询
    rows = dao.run_read(cypher, {"kb_id": kb_id})

    # 第三步：LLM 生成自然语言答案
    summary: str = llm.invoke([
        ("system", ANSWER_SYS),
        ("human", str(rows)[:6000]),
    ]).content

    # 从查询结果中提取来源 URL（仅取含 url 字段的行）
    sources = [r["url"] for r in rows if isinstance(r, dict) and r.get("url")]
    return QueryResult(cypher=cypher, rows=rows, answer=summary, sources=sources)
