# Graph Builder Agent：LLM 抽取三元组 + 写入 Neo4j 知识图谱
from __future__ import annotations
from graphify.schemas.graph import ExtractionResult
from graphify.graphdb.dao import GraphDAO

# 允许的节点和关系类型（受控 schema）
SCHEMA_HINT = (
    "允许的节点: Company,Industry,Component,Product,Metric,Person,NewsArticle; "
    "允许的关系: BELONGS_TO,SUPPLIES,PART_OF_SUPPLY_CHAIN,PRODUCES,HAS_METRIC,MENTIONED_IN"
)


def extract(item: dict, llm=None) -> ExtractionResult:
    """从单篇正文中 LLM 抽取三元组，支持注入 FakeLLM 替身。"""
    from graphify.llm import get_llm
    llm = llm or get_llm()
    structured = llm.with_structured_output(ExtractionResult)
    res: ExtractionResult = structured.invoke([
        ("system", f"严格按受控 schema 抽取知识图谱三元组。{SCHEMA_HINT}"),
        # 截取前 8000 字，避免超出 context window
        ("human", item["text"][:8000]),
    ])
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
