# Graph Builder Agent：LLM 抽取三元组 + 写入 Neo4j 知识图谱
# 使用 prompt-based JSON 输出代替 with_structured_output，兼容 qwen 等工具调用不稳定的模型
from __future__ import annotations
import json
import re
from graphify.schemas.graph import ExtractionResult
from graphify.graphdb.dao import GraphDAO

# 允许的节点和关系类型（受控 schema）
SCHEMA_HINT = (
    "允许的节点: Company,Industry,Component,Product,Metric,Person,NewsArticle; "
    "允许的关系: BELONGS_TO,SUPPLIES,PART_OF_SUPPLY_CHAIN,PRODUCES,HAS_METRIC,MENTIONED_IN"
)

# 系统提示：要求模型输出完整 JSON，包含字段说明与示例
_EXTRACT_SYS = f"""你是知识图谱三元组抽取器。从新闻正文中严格抽取实体、关系和时序指标，
以 JSON 格式输出（不加任何解释，不加代码块标记）。

受控 schema：{SCHEMA_HINT}

输出格式（完整 JSON，必须以 }} 结尾）：
{{
  "entities": [
    {{"label": "Company", "name": "公司名", "props": {{}}, "confidence": 0.9}}
  ],
  "relations": [
    {{"type": "SUPPLIES", "source_name": "A公司", "target_name": "B公司", "props": {{}}, "confidence": 0.8}}
  ],
  "snapshots": [
    {{"company": "A公司", "metric": "股价", "value": 12.5, "ts": "2026-06-22", "unit": "元"}}
  ]
}}

规则：
- confidence 范围 0~1，不确定时填 0.6
- 无时序数据时 snapshots 为 []
- 只输出 JSON 对象，禁止输出任何文字说明"""


def _extract_json(text: str) -> str:
    """从 LLM 响应中提取第一个完整 JSON 对象（兼容代码块包裹）。"""
    md = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if md:
        return md.group(1)
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text.strip()


def extract(item: dict, llm=None) -> ExtractionResult:
    """从单篇正文中 LLM 抽取三元组，支持注入 FakeLLM 替身。

    使用 prompt-based JSON 输出，兼容 qwen-plus 工具调用截断的问题。
    网络错误或 JSON 解析失败时返回空 ExtractionResult，不中断整批处理。
    """
    from graphify.llm import get_llm
    from loguru import logger
    llm = llm or get_llm()

    try:
        msg = llm.invoke([
            ("system", _EXTRACT_SYS),
            ("human", item["text"][:8000]),  # 截取前 8000 字，避免超出 context window
        ])
        raw = msg.content if hasattr(msg, "content") else str(msg)
        data = json.loads(_extract_json(raw))
        res = ExtractionResult.model_validate(data)
    except Exception as exc:
        # 网络错误、LLM 调用失败或 JSON 解析错误均降级为空结果，不中断整批处理
        logger.warning(f"extract 失败，返回空结果：url={item.get('url')!r}, err={exc}")
        res = ExtractionResult()

    res.source_url = item["url"]
    return res


def persist(
    kb_id: str,
    extractions: list[ExtractionResult],
    dao: GraphDAO | None = None,
    min_conf: float = 0.6,
) -> dict:
    """将抽取结果写入 Neo4j，低置信度实体/关系跳过，快照追加不覆盖历史。"""
    dao = dao or GraphDAO()
    added_nodes = added_rels = added_snaps = skipped = 0
    for ex in extractions:
        src = dao.merge_source(ex.source_url)
        for ent in ex.entities:
            if ent.confidence < min_conf:
                skipped += 1
                continue
            node_id = dao.resolve_and_merge_entity(kb_id, ent)
            dao.link_source(node_id, src)
            added_nodes += 1
        for rel in ex.relations:
            if rel.confidence < min_conf:
                skipped += 1
                continue
            dao.merge_relation(kb_id, rel)
            added_rels += 1
        for snap in ex.snapshots:
            # 时序数据只追加（CREATE），不允许覆盖历史
            dao.append_snapshot(kb_id, snap)
            added_snaps += 1
    return {
        "nodes": added_nodes,
        "relations": added_rels,
        "snapshots": added_snaps,
        "skipped_low_conf": skipped,
    }
