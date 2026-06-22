# 图谱三元组数据模型
from typing import Optional
from pydantic import BaseModel, Field


class Entity(BaseModel):
    """知识图谱节点实体。"""
    label: str          # Company / Industry / Component / Metric ...
    name: str
    props: dict = Field(default_factory=dict)
    confidence: float = 1.0


class Relation(BaseModel):
    """知识图谱关系（边）。"""
    type: str           # SUPPLIES / BELONGS_TO ...
    source_name: str
    target_name: str
    props: dict = Field(default_factory=dict)
    confidence: float = 1.0


class MetricSnapshot(BaseModel):
    """时序指标快照（如股价、销量），只追加不覆盖历史。"""
    company: str
    metric: str         # "股价" / "销量"
    value: float
    ts: str             # ISO date（如 "2026-06-22"）
    unit: Optional[str] = None


class ExtractionResult(BaseModel):
    """LLM 从单篇文本抽取的全部三元组结果。"""
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    snapshots: list[MetricSnapshot] = Field(default_factory=list)
    source_url: str = ""
