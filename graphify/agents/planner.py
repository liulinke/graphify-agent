# Planner Agent：将自然语言采集指令解析为结构化 CollectPlan
from __future__ import annotations
from graphify.schemas.plan import CollectPlan

PLANNER_SYS = """你是采集计划解析器。把用户的中文采集指令解析为结构化采集计划。
- 识别领域、主题、区域、来源数量(source_limit)、是否每日采集。
- 若提到"上下游/产业链"，结合行业知识扩展 upstream / downstream 词表。
只输出符合 schema 的结构化结果。"""


def parse_instruction(kb_id: str, instruction: str, llm=None) -> CollectPlan:
    """将自然语言指令解析为 CollectPlan，支持传入 FakeLLM 替身进行单测。"""
    from graphify.llm import get_llm
    llm = llm or get_llm()
    structured = llm.with_structured_output(CollectPlan)
    plan: CollectPlan = structured.invoke(
        [("system", PLANNER_SYS), ("human", instruction)]
    )
    plan.kb_id = kb_id
    return plan
