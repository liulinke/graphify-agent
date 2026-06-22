# 全局测试固件：FakeLLM、FakeDAO、sample_plan（设计文档 10.2 节）
from __future__ import annotations
import pytest
from typing import Any
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from graphify.schemas.plan import CollectPlan
from graphify.schemas.graph import Entity, ExtractionResult


# ────────────────────────── FakeLLM ──────────────────────────

class FakeLLM(FakeListChatModel):
    """按顺序返回预设回复的 LLM 替身，外部依赖零调用。

    用法：
        llm = FakeLLM(responses=["MATCH (n) RETURN n LIMIT 10"])
    """
    pass


# ────────────────────────── FakeDAO ──────────────────────────

class FakeDAO:
    """内存实现的 GraphDAO 替身，记录所有调用，不连接 Neo4j。"""

    def __init__(self) -> None:
        # 用于断言测试：记录各方法被调用的参数
        self.merged_sources: list[str] = []
        self.merged_entities: list[tuple] = []
        self.linked_sources: list[tuple] = []
        self.merged_relations: list[tuple] = []
        self.appended_snapshots: list[tuple] = []
        self.read_calls: list[tuple] = []

    def merge_source(self, url: str) -> int:
        """模拟 MERGE NewsArticle 节点，返回自增 id。"""
        self.merged_sources.append(url)
        return len(self.merged_sources)

    def resolve_and_merge_entity(self, kb_id: str, entity: Any) -> int:
        """模拟实体消歧 + MERGE，返回自增 id。"""
        self.merged_entities.append((kb_id, entity))
        return len(self.merged_entities)

    def link_source(self, node_id: int, source_id: int) -> None:
        """模拟 MERGE MENTIONED_IN 关系。"""
        self.linked_sources.append((node_id, source_id))

    def merge_relation(self, kb_id: str, rel: Any) -> None:
        """模拟关系写入。"""
        self.merged_relations.append((kb_id, rel))

    def append_snapshot(self, kb_id: str, snap: Any) -> None:
        """模拟时序快照追加（CREATE，不覆盖）。"""
        self.appended_snapshots.append((kb_id, snap))

    def run_read(self, cypher: str, params: dict | None = None) -> list[dict]:
        """模拟只读查询，返回空列表（测试中可 monkeypatch 替换）。"""
        self.read_calls.append((cypher, params))
        return []

    def expand_node(self, kb_id: str, node_id: int, rel_types: list[str]) -> list[dict]:
        """模拟节点展开查询。"""
        return []

    def close(self) -> None:
        """无需关闭连接。"""
        pass


# ────────────────────────── Fixtures ──────────────────────────

@pytest.fixture
def fake_llm() -> FakeLLM:
    """默认返回空字符串的 FakeLLM 实例，测试中可覆盖 responses。"""
    return FakeLLM(responses=[""])


@pytest.fixture
def fake_dao() -> FakeDAO:
    """每个测试函数获得独立的 FakeDAO 实例。"""
    return FakeDAO()


@pytest.fixture
def sample_plan() -> CollectPlan:
    """用于测试的标准采集计划。"""
    return CollectPlan(
        kb_id="kb_test_001",
        domain="机器人",
        topics=["工业机器人", "协作机器人"],
        include_supply_chain=True,
        region="CN",
        source_limit=10,
    )


@pytest.fixture
def sample_extraction() -> ExtractionResult:
    """用于测试的标准抽取结果，包含一个高置信度实体。"""
    return ExtractionResult(
        entities=[Entity(label="Company", name="埃斯顿", confidence=0.9)],
        relations=[],
        snapshots=[],
        source_url="https://example.com/news/1",
    )
