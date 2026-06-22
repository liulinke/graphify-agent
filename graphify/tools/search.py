# 搜索工具：用 Tavily Search API 根据主题词检索候选 URL
# 无 TAVILY_API_KEY 时优雅降级，返回空列表并打印警告
from __future__ import annotations
from loguru import logger
from langchain_core.tools import tool
from graphify.config import settings


def _build_tavily():
    """构造 TavilySearch 实例；未配置 API key 时返回 None。

    每次调用构造新实例，确保配置热更新生效（测试中也便于 mock）。
    """
    api_key = settings.tavily_api_key
    if not api_key:
        return None
    from langchain_tavily import TavilySearch
    # 显式传入 api_key，避免依赖 os.environ（pydantic-settings 从 .env 读取后不回写环境变量）
    return TavilySearch(
        tavily_api_key=api_key,
        max_results=10,
        topic="news",
        search_depth="basic",
    )


def _search_term(tavily, term: str) -> list[str]:
    """对单个搜索词调用 Tavily，返回结果 URL 列表。

    任何异常均被捕获并记录，不向上传播（避免单个词失败中断整批采集）。
    """
    try:
        result = tavily.invoke(term)
        # TavilySearch 返回 {"results": [{"url": ..., "title": ..., "content": ...}, ...]}
        return [
            r["url"]
            for r in result.get("results", [])
            if isinstance(r, dict) and r.get("url")
        ]
    except Exception as exc:
        logger.warning(f"Tavily 搜索失败：term={term!r}, err={exc}")
        return []


@tool
def search_urls(
    terms: list[str],
    limit: int,
    region: str = "CN",
    lang: list[str] | None = None,
) -> list[str]:
    """用 Tavily Search API 根据主题词检索候选 URL。

    - 逐词查询，结果合并去重后截取 limit 条返回
    - 未配置 TAVILY_API_KEY 时返回空列表并打印警告
    """
    if not terms:
        return []

    tavily = _build_tavily()
    if tavily is None:
        logger.warning(
            "search_urls: 未配置 TAVILY_API_KEY，返回空列表。"
            f"搜索词={terms[:3]}，limit={limit}"
        )
        return []

    seen: set[str] = set()
    urls: list[str] = []

    for term in terms:
        if len(urls) >= limit:
            break
        for url in _search_term(tavily, term):
            if url not in seen:
                seen.add(url)
                urls.append(url)
                if len(urls) >= limit:
                    break

    logger.info(f"search_urls: terms={terms[:3]}…, 共返回 {len(urls)} 条 URL")
    return urls
