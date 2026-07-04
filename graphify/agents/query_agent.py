# Query Agent：自然语言 → Cypher 查询 → 自然语言答案（三道安全护栏）
from __future__ import annotations
import re
from graphify.schemas.query import QueryResult
from graphify.graphdb.dao import GraphDAO
from graphify.tools.cypher import assert_safe_query

# 图谱真实 schema 描述：必须与 graph_builder 的受控 schema 保持一致。
# 不注入 schema 时，LLM 会凭空猜标签（如 :Entity）和关系（如 :HAS_COMPANY），
# 生成的 Cypher 查不到任何数据——这是查询质量问题的根源。
GRAPH_SCHEMA = """图谱 schema（只能使用以下标签和关系，禁止发明新的）：
节点标签及属性：
- Company(kb_id, name)        公司
- Industry(kb_id, name)       行业
- Component(kb_id, name)      零部件
- Product(kb_id, name)        产品
- Metric(kb_id, name)         指标（如 股价/销量）
- Person(kb_id, name)         人物
- NewsArticle(kb_id, name)    新闻文章
- Source(url)                 来源网页（无 kb_id，通过 CITED_BY 关联）
- MetricSnapshot(value, ts, unit)  时序快照（无 kb_id）
关系类型：
- (实体)-[:BELONGS_TO]->(Industry)        隶属行业
- (Company)-[:SUPPLIES]->(Company)        供应
- (实体)-[:PART_OF_SUPPLY_CHAIN]->(实体)  供应链环节
- (Company)-[:PRODUCES]->(Product)        生产
- (Company)-[:HAS_METRIC]->(Metric)       拥有指标
- (Metric)-[:HAS_SNAPSHOT]->(MetricSnapshot) 指标的历史快照
- (实体)-[:MENTIONED_IN]->(NewsArticle)   被新闻提及
- (实体)-[:CITED_BY]->(Source)            信息来源"""

NL2CYPHER_SYS = f"""把用户问题转为 Neo4j 只读 Cypher。

{GRAPH_SCHEMA}

规则：
- 仅允许 MATCH/OPTIONAL MATCH/RETURN/WHERE/WITH/ORDER BY/LIMIT，禁止 CREATE/MERGE/DELETE/SET/REMOVE/DROP。
- 第一个 MATCH 的节点必须带 kb_id 过滤：WHERE x.kb_id = $kb_id（或写在模式里 {{kb_id: $kb_id}}）。
  仅在 RETURN 中出现 kb_id 不算过滤，会被安全检查拦截。
- 必须带 LIMIT（如 LIMIT 50）。
- 使用参数化占位符 $kb_id，禁止把 kb_id 写成字符串字面量。
- 名称匹配优先用 CONTAINS 模糊匹配（如 n.name CONTAINS '机器人'），不要假设图中存在某个精确名称。
- 枚举类问题（"有哪些公司/产品/人物"）直接按标签查全部节点，不要加 name 过滤——
  公司名通常不含行业词（如"优必选"不含"机器人"），加了会漏掉大部分结果；
  也不要强行关联不确定存在的关系。
- 尽量附带来源：OPTIONAL MATCH (n)-[:CITED_BY]->(s:Source)，RETURN 中包含 s.url AS url。
只输出 Cypher 语句，不加任何解释、不加代码块标记。"""

ANSWER_SYS = """你是知识图谱问答助手。基于给定的 Cypher 查询结果，用中文简洁回答用户问题。
- 只依据查询结果作答，不要编造结果之外的内容。
- 若结果为空，直接回答"知识图谱中未找到相关信息"。
- 结果中若含 url 字段，在答案末尾列出来源 URL。"""


def _strip_cypher_fences(text: str) -> str:
    """剥离 LLM 输出中的 Markdown 代码块围栏（```cypher ... ```）。"""
    m = re.search(r"```(?:cypher)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return text.strip()


def _gen_safe_cypher(llm, human_msg: str) -> str:
    """生成 Cypher 并过安全护栏；首次违规时把原因反馈给 LLM 修正一次。

    LLM（尤其 qwen）偶尔漏写 kb_id 过滤，直接抛错用户体验差；
    反馈重生成一次通常即可修正，仍不合规才向上抛 ValueError。
    """
    cypher = _strip_cypher_fences(llm.invoke([
        ("system", NL2CYPHER_SYS),
        ("human", human_msg),
    ]).content)
    try:
        assert_safe_query(cypher)
        return cypher
    except ValueError as exc:
        fixed = _strip_cypher_fences(llm.invoke([
            ("system", NL2CYPHER_SYS),
            ("human",
             f"{human_msg}\n"
             f"你上一条生成的 Cypher 未通过安全检查：{exc}\n"
             "修正要求：必须在第一个 MATCH 后写 WHERE <节点别名>.kb_id = $kb_id "
             "（例如 MATCH (c:Company) WHERE c.kb_id = $kb_id），"
             "把 kb_id 放在 RETURN 里不算过滤。只输出修正后的 Cypher。"),
        ]).content)
        assert_safe_query(fixed)  # 修正后仍不合规则抛出，由上层处理
        return fixed


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

    # 第一步：NL → Cypher（护栏违规时会带反馈重生成一次）
    cypher: str = _gen_safe_cypher(llm, f"问题: {question}")

    # 第二步：执行只读查询
    rows = dao.run_read(cypher, {"kb_id": kb_id})

    # 空结果降级重查：LLM 首次生成的查询常带过强的关系约束（图谱抽取
    # 的关系较稀疏，联查易空），退化为标签 + 模糊匹配再试一次
    if not rows:
        try:
            retry_cypher = _gen_safe_cypher(
                llm,
                f"问题: {question}\n"
                f"上一条查询返回 0 行：{cypher}\n"
                "请生成更宽松的替代查询：去掉关系约束，只按最相关的节点标签查询。"
                "枚举类问题直接返回该标签全部节点（仅保留 kb_id 过滤）；"
                "查特定实体时 name 才用 CONTAINS 模糊匹配（只取最核心的 2~3 个字）。",
            )
            rows = dao.run_read(retry_cypher, {"kb_id": kb_id})
            if rows:
                cypher = retry_cypher  # 结果来自降级查询，记录实际生效的语句
        except ValueError:
            pass  # 降级查询不合规则放弃，保留首次（空）结果

    # 第三步：LLM 生成自然语言答案（带上原问题，避免模型不知道在回答什么）
    summary: str = llm.invoke([
        ("system", ANSWER_SYS),
        ("human", f"用户问题: {question}\n查询结果: {str(rows)[:6000]}"),
    ]).content

    # 从查询结果中提取来源 URL（仅取含 url 字段的行，去重保序）
    sources = list(dict.fromkeys(
        r["url"] for r in rows if isinstance(r, dict) and r.get("url")
    ))
    return QueryResult(cypher=cypher, rows=rows, answer=summary, sources=sources)
