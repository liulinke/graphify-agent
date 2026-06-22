# 采集计划数据模型
from typing import Literal
from pydantic import BaseModel, Field


class SupplyChain(BaseModel):
    """产业链上下游词表。"""
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)


class CollectPlan(BaseModel):
    """结构化采集计划，由 Planner Agent 从自然语言指令解析而来。"""
    kb_id: str
    task_type: Literal["collect"] = "collect"
    domain: str = ""
    topics: list[str] = Field(default_factory=list)
    include_supply_chain: bool = False
    supply_chain: SupplyChain = Field(default_factory=SupplyChain)
    region: str = "CN"
    # 去重后纳入的 URL 上限
    source_limit: int = 100
    freshness: Literal["incremental", "full"] = "incremental"
    language: list[str] = Field(default_factory=lambda: ["zh", "en"])
    schedule: Literal["once", "daily"] = "once"
