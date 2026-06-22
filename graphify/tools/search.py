# 搜索工具：根据主题词检索候选 URL
# 正式版接入搜索 API（SerpAPI / Bing Search API）；当前为存根，测试时直接 mock
from __future__ import annotations
from loguru import logger
from langchain_core.tools import tool


@tool
def search_urls(
    terms: list[str],
    limit: int,
    region: str = "CN",
    lang: list[str] | None = None,
) -> list[str]:
    """根据主题词检索候选 URL（搜索 API / 站点地图 / 定向源）。

    返回最多 limit 条候选 URL，顺序按相关性排列。
    未配置搜索 API 时返回空列表并打印警告。
    """
    if not terms:
        return []

    # TODO: 接入 SerpAPI / Bing Search API，按 region / lang 过滤
    logger.warning(
        "search_urls 未配置搜索 API，返回空列表。"
        f"搜索词={terms[:3]}…，limit={limit}"
    )
    return []
