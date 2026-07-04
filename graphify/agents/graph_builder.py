# Graph Builder Agent：LLM 抽取三元组 + 写入 Neo4j 知识图谱
# 使用 prompt-based JSON 输出代替 with_structured_output，兼容 qwen 等工具调用不稳定的模型
from __future__ import annotations
import json
import re
from graphify.schemas.graph import ExtractionResult
from graphify.graphdb.dao import GraphDAO

# 允许的节点和关系类型（受控 schema）
# 注意：label/type 会拼进 Cypher 模板，白名单校验同时防止注入
ALLOWED_LABELS = frozenset(
    {"Company", "Industry", "Component", "Product", "Metric", "Person", "NewsArticle"}
)
ALLOWED_RELATIONS = frozenset(
    {"BELONGS_TO", "SUPPLIES", "PART_OF_SUPPLY_CHAIN", "PRODUCES", "HAS_METRIC", "MENTIONED_IN"}
)
SCHEMA_HINT = (
    f"允许的节点: {','.join(sorted(ALLOWED_LABELS))}; "
    f"允许的关系: {','.join(sorted(ALLOWED_RELATIONS))}"
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
- label 和 type 只能用受控 schema 中列出的值，禁止发明新标签（如 Technology/Organization）
- Company 仅用于企业；政府机构、高校、研究院所不是 Company，若无合适标签则跳过该实体
- confidence 范围 0~1，不确定时填 0.6
- 无时序数据时 snapshots 为 []
- 只输出 JSON 对象，禁止输出任何文字说明"""


# LLM 调用瞬时失败的重试退避秒数（测试中可 monkeypatch 为 (0, 0) 加速）
_RETRY_BACKOFF_S: tuple[float, float] = (1.0, 2.0)


def _lenient_validate(data: dict) -> ExtractionResult:
    """逐条校验实体/关系/快照，跳过非法条目而非丢弃整页结果。

    - LLM 偶尔输出个别脏数据（如 snapshot.value=null），若整体 model_validate
      会导致该页全部实体/关系一起丢失，产量损失严重。
    - label/type 必须在受控 schema 白名单内：既保证图谱 schema 干净，
      也防止 LLM 输出被拼进 Cypher 模板造成注入。
    """
    from loguru import logger
    from graphify.schemas.graph import Entity, Relation, MetricSnapshot
    res = ExtractionResult()
    for raw in data.get("entities") or []:
        try:
            ent = Entity.model_validate(raw)
            if ent.label not in ALLOWED_LABELS:
                logger.debug(f"跳过 schema 外标签的实体：{ent.label}/{ent.name}")
                continue
            res.entities.append(ent)
        except Exception as exc:
            logger.debug(f"跳过非法 entities 条目：{raw!r}, err={exc}")
    for raw in data.get("relations") or []:
        try:
            rel = Relation.model_validate(raw)
            if rel.type not in ALLOWED_RELATIONS:
                logger.debug(f"跳过 schema 外类型的关系：{rel.type}")
                continue
            res.relations.append(rel)
        except Exception as exc:
            logger.debug(f"跳过非法 relations 条目：{raw!r}, err={exc}")
    for raw in data.get("snapshots") or []:
        try:
            res.snapshots.append(MetricSnapshot.model_validate(raw))
        except Exception as exc:
            logger.debug(f"跳过非法 snapshots 条目：{raw!r}, err={exc}")
    return res


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
    瞬时网络错误（如代理断连）自动重试 2 次；仍失败则返回空结果，不中断整批处理。
    """
    import time
    from graphify.llm import get_llm
    from loguru import logger
    llm = llm or get_llm()

    res: ExtractionResult | None = None
    last_exc: Exception | None = None
    for attempt in range(3):  # 最多尝试 3 次（首次 + 重试 2 次）
        try:
            msg = llm.invoke([
                ("system", _EXTRACT_SYS),
                ("human", item["text"][:8000]),  # 截取前 8000 字，避免超出 context window
            ])
        except Exception as exc:
            # LLM 调用失败（DashScope 代理偶发 Broken pipe 等瞬时网络错误），退避后重试
            last_exc = exc
            if attempt < 2:
                delay = _RETRY_BACKOFF_S[attempt]
                logger.warning(f"extract LLM 调用第 {attempt + 1} 次失败，{delay}s 后重试：err={exc}")
                time.sleep(delay)
            continue
        try:
            raw = msg.content if hasattr(msg, "content") else str(msg)
            data = json.loads(_extract_json(raw))
            # 逐条校验：个别脏条目（如 value=null 的快照）只跳过该条，不丢整页
            res = _lenient_validate(data)
        except Exception as exc:
            # JSON 解析失败是确定性错误，重试无意义，直接降级
            last_exc = exc
        break
    if res is None:
        # 重试耗尽或解析失败，降级为空结果，不中断整批处理
        logger.warning(f"extract 失败，返回空结果：url={item.get('url')!r}, err={last_exc}")
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
