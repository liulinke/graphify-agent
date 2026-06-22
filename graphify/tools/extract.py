# 内容抽取工具：正文提取 + 结构化字段（存根）
from __future__ import annotations
from langchain_core.tools import tool


@tool
def extract_content(html: str) -> dict:
    """正文抽取 + 结构化字段（股价/销量等）。返回 {text, title, fields}。"""
    # TODO: BeautifulSoup 正文提取 + 结构化字段解析
    raise NotImplementedError("extract_content 尚未实现")


@tool
def extract_graph(text: str, schema_hint: str) -> dict:
    """LLM 受控抽取实体/关系/时序快照（带置信度），返回 ExtractionResult 兼容 dict。"""
    # TODO: 调用 LLM structured output
    raise NotImplementedError("extract_graph 尚未实现")
