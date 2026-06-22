# 搜索工具：根据主题词检索候选 URL（存根，后续里程碑实现）
from __future__ import annotations
from langchain_core.tools import tool


@tool
def search_urls(
    terms: list[str],
    limit: int,
    region: str = "CN",
    lang: list[str] | None = None,
) -> list[str]:
    """根据主题词检索候选 URL（搜索 API / 站点地图 / 定向源）。"""
    # TODO: 接入搜索 API（如 SerpAPI、Bing Search API）
    raise NotImplementedError("search_urls 尚未实现")
