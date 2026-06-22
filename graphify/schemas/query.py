# 自然语言查询相关数据模型
from typing import Any
from pydantic import BaseModel


class NLQuery(BaseModel):
    """用户自然语言查询请求。"""
    kb_id: str
    question: str


class QueryResult(BaseModel):
    """NL2Cypher 查询结果，包含生成的 Cypher、原始行数据、自然语言答案和来源。"""
    cypher: str
    rows: list[dict[str, Any]]
    answer: str
    sources: list[str]
