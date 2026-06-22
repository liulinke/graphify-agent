# 图谱数据访问层（DAL）：封装 Neo4j CRUD，上层只调此层
from __future__ import annotations
from neo4j import Driver
from graphify.config import settings
from graphify.schemas.graph import Entity, Relation, MetricSnapshot
from graphify.graphdb import cql


class GraphDAO:
    """Neo4j 数据访问对象，支持依赖注入（driver 可传入 mock）。"""

    def __init__(self, driver: Driver | None = None) -> None:
        # driver 为 None 时才创建真实驱动（便于单元测试注入替身）
        if driver is None:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_user, settings.neo4j_password),
            )
        self.driver = driver

    # ── 来源节点 ────────────────────────────────────────────────────────────

    def merge_source(self, url: str) -> dict:
        """MERGE Source 节点，返回节点数据。"""
        with self.driver.session() as s:
            result = s.run(cql.MERGE_SOURCE, url=url)
            return result.single()["s"]

    def link_source(self, node_id: int, source: dict) -> None:
        """将实体节点与来源节点关联（CITED_BY）。"""
        q = "MATCH (n) WHERE id(n)=$nid MATCH (s:Source {url:$url}) MERGE (n)-[:CITED_BY]->(s)"
        with self.driver.session() as s:
            s.run(q, nid=node_id, url=source["url"])

    # ── 实体 ─────────────────────────────────────────────────────────────────

    def resolve_and_merge_entity(self, kb_id: str, ent: Entity) -> int:
        """消歧 + MERGE 实体节点，返回内部节点 ID。"""
        q = cql.MERGE_ENTITY_TMPL.format(label=ent.label)
        with self.driver.session() as s:
            result = s.run(q, kb=kb_id, name=ent.name, props=ent.props)
            return result.single()["id"]

    # ── 关系 ─────────────────────────────────────────────────────────────────

    def merge_relation(self, kb_id: str, rel: Relation) -> None:
        """MERGE 关系（幂等），关系已存在则更新属性。"""
        q = cql.MERGE_RELATION_TMPL.format(type=rel.type)
        with self.driver.session() as s:
            s.run(q, kb=kb_id, src=rel.source_name, dst=rel.target_name, props=rel.props)

    # ── 时序快照 ──────────────────────────────────────────────────────────────

    def append_snapshot(self, kb_id: str, snap: MetricSnapshot) -> None:
        """追加时序快照，用 CREATE 而非 MERGE，保留历史数据。"""
        with self.driver.session() as s:
            s.run(
                cql.APPEND_SNAPSHOT,
                kb=kb_id,
                company=snap.company,
                metric=snap.metric,
                v=snap.value,
                ts=snap.ts,
                unit=snap.unit,
            )

    # ── 查询 ──────────────────────────────────────────────────────────────────

    def run_read(self, cypher: str, params: dict) -> list[dict]:
        """只读查询，强制使用 READ 访问模式。"""
        with self.driver.session(default_access_mode="READ") as s:
            return [r.data() for r in s.run(cypher, **params)]

    def expand_node(self, kb_id: str, node_id: int, rel_types: list[str], limit: int = 50) -> list[dict]:
        """展开指定节点的邻居（用于图形化探索）。"""
        q = (
            "MATCH (n)-[r]-(m) WHERE id(n)=$id AND type(r) IN $types "
            "RETURN n, r, m LIMIT $limit"
        )
        return self.run_read(q, {"id": node_id, "types": rel_types, "limit": limit})
