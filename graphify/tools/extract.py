# 内容抽取工具：BeautifulSoup 正文提取 + 基础结构化字段
from __future__ import annotations
import re
from langchain_core.tools import tool
from bs4 import BeautifulSoup

# 移除正文噪音标签
_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]

# 简单数值字段模式（后续里程碑用 LLM 替换）
_FIELD_PATTERNS: dict[str, re.Pattern] = {
    "price":  re.compile(r"(?:股价|价格)[：:\s]*([0-9]+\.?[0-9]*)"),
    "volume": re.compile(r"(?:销量|出货量)[：:\s]*([0-9]+\.?[0-9]*)"),
    "growth": re.compile(r"(?:增长|增幅)[：:\s]*([0-9]+\.?[0-9]*)%"),
}


def _extract_fields(text: str) -> dict:
    """用正则从正文中提取简单数值字段（价格、销量、增幅）。"""
    fields: dict[str, str] = {}
    for name, pat in _FIELD_PATTERNS.items():
        m = pat.search(text)
        if m:
            fields[name] = m.group(1)
    return fields


@tool
def extract_content(html: str) -> dict:
    """从 HTML 中抽取正文、标题和基础结构化字段。

    返回 {text, title, fields}，供 graph_builder.extract 进一步 LLM 处理。
    """
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    fields = _extract_fields(text)
    return {"text": text, "title": title, "fields": fields}


@tool
def extract_graph(text: str, schema_hint: str) -> dict:
    """LLM 受控抽取实体/关系/时序快照（带置信度）。

    返回与 ExtractionResult 兼容的 dict。
    本工具由 graph_builder.extract 包装，直接在那里调用 LLM；
    此处作为 Agent 工具暴露接口。
    """
    # 实际逻辑在 graph_builder.extract，此处通过 LLM 注入调用
    # 后续里程碑实现
    raise NotImplementedError("extract_graph 应通过 graph_builder.extract 调用")
