# LangGraph 工作流状态定义
from typing import TypedDict, Annotated
from operator import add
from graphify.schemas.plan import CollectPlan
from graphify.schemas.graph import ExtractionResult


class CollectState(TypedDict):
    """采集工作流的完整状态，贯穿各 LangGraph 节点。"""
    kb_id: str
    instruction: str                        # 用户自然语言指令
    plan: CollectPlan | None
    candidate_urls: list[str]               # 发现的候选 URL
    fresh_urls: list[str]                   # URL 去重后保留
    fetched: Annotated[list[dict], add]     # [{url, html, text, ...}]，多节点追加
    extractions: Annotated[list[ExtractionResult], add]
    report: dict                            # 采集统计汇总
    errors: Annotated[list[str], add]       # 失败记录，多节点追加
