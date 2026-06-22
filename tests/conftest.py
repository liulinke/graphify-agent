# 全局测试固件：FakeLLM、FakeDAO、常用 fixture（设计文档 10.2 节）
from __future__ import annotations
import pytest
from typing import Any
from graphify.schemas.plan import CollectPlan, SupplyChain
from graphify.schemas.graph import Entity, ExtractionResult


# ────────────────────────── FakeLLM ──────────────────────────

class FakeLLM:
    """可编程的 LLM 替身，支持普通 invoke 与 with_structured_output 两种调用路径。

    用法：
        # 结构化输出
        llm = FakeLLM(payload=some_pydantic_obj)
        result = llm.with_structured_output(Schema).invoke(msgs)  # → some_pydantic_obj

        # 普通文本输出
        llm = FakeLLM(payload="MATCH (n) RETURN n LIMIT 10")
        result = llm.invoke(msgs)  # → 伪 message，.content == "MATCH ..."
    """

    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self._structured = False

    def with_structured_output(self, schema: type) -> "FakeLLM":
        """返回自身，标记下次 invoke 走结构化路径。"""
        self._schema = schema
        self._structured = True
        return self

    def invoke(self, msgs: Any) -> Any:
        if self._structured:
            self._structured = False  # 重置，避免污染后续调用
            return self.payload

        # 普通 invoke：包装成有 .content 属性的假消息
        class _Msg:
            def __init__(self, content: str) -> None:
                self.content = content

        return _Msg(self.payload)


# ────────────────────────── FakeDAO ──────────────────────────

class FakeDAO:
    """内存实现的 GraphDAO 替身，记录所有调用，不连接 Neo4j。

    属性名与设计文档 10.2 节保持一致：
        snapshots   — append_snapshot 写入的快照列表
        entities    — resolve_and_merge_entity 写入的实体列表
        relations   — merge_relation 写入的关系列表
        read_rows   — run_read 返回的预设行（测试中可直接赋值）
    """

    def __init__(self) -> None:
        self.snapshots: list = []
        self.entities: list = []
        self.relations: list = []
        self.read_rows: list[dict] = []
        # 额外记录 merge_source / link_source 调用，供细粒度断言
        self.merged_sources: list[str] = []
        self.linked_sources: list[tuple] = []

    def merge_source(self, url: str) -> dict:
        """模拟 MERGE NewsArticle 节点，返回含 url 的字典。"""
        self.merged_sources.append(url)
        return {"url": url}

    def resolve_and_merge_entity(self, kb_id: str, entity: Any) -> int:
        """模拟实体消歧 + MERGE，返回自增 id。"""
        self.entities.append(entity)
        return len(self.entities)

    def link_source(self, node_id: Any, source: Any) -> None:
        """模拟 MERGE MENTIONED_IN 关系。"""
        self.linked_sources.append((node_id, source))

    def merge_relation(self, kb_id: str, rel: Any) -> None:
        """模拟关系写入。"""
        self.relations.append(rel)

    def append_snapshot(self, kb_id: str, snap: Any) -> None:
        """模拟时序快照追加（CREATE，不覆盖历史）。"""
        self.snapshots.append(snap)

    def run_read(self, cypher: str, params: dict | None = None) -> list[dict]:
        """返回预设 read_rows，测试中可直接赋值覆盖。"""
        return self.read_rows

    def expand_node(self, kb_id: str, node_id: int, rel_types: list[str]) -> list[dict]:
        """模拟节点展开查询，默认返回空列表。"""
        return []

    def close(self) -> None:
        """无需关闭连接。"""


# ────────────────────────── Fixtures ──────────────────────────

@pytest.fixture
def fake_llm() -> FakeLLM:
    """默认 payload 为空字符串的 FakeLLM 实例。"""
    return FakeLLM(payload="")


@pytest.fixture
def fake_dao() -> FakeDAO:
    """每个测试函数获得独立的 FakeDAO 实例。"""
    return FakeDAO()


@pytest.fixture
def sample_plan() -> CollectPlan:
    """标准采集计划 fixture（含上下游）。"""
    return CollectPlan(
        kb_id="kb1",
        domain="机器人/股票",
        topics=["机器人", "股票"],
        include_supply_chain=True,
        supply_chain=SupplyChain(upstream=["伺服电机"], downstream=["物流"]),
        source_limit=100,
    )


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    """标准抽取结果 fixture，包含一个高置信度实体。"""
    return ExtractionResult(
        entities=[Entity(label="Company", name="埃斯顿", confidence=0.9)],
        source_url="https://example.com/news/1",
    )
