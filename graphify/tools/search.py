# 搜索工具：用 Tavily Search API 根据主题词检索候选 URL
# 无 TAVILY_API_KEY 时优雅降级，返回空列表并打印警告
from __future__ import annotations
from loguru import logger
from langchain_core.tools import tool
from graphify.config import settings

# 单次查询最多返回条数；Tavily 免费层上限 20
_MAX_RESULTS_PER_TERM = 20


def _build_tavily():
    """构造 TavilySearch 实例；未配置 API key 时返回 None。

    - topic="general"：比 "news" 覆盖更广，对中文词友好
    - search_depth="advanced"：更彻底，提升中文词命中率
    - 显式传入 api_key，避免依赖 os.environ（pydantic-settings 的 .env 不回写环境变量）
    """
    api_key = settings.tavily_api_key
    if not api_key:
        return None
    from langchain_tavily import TavilySearch
    return TavilySearch(
        tavily_api_key=api_key,
        max_results=_MAX_RESULTS_PER_TERM,
        topic="general",       # general 覆盖新闻 + 网页，对中文词更友好
        search_depth="advanced",
    )


def _search_term(tavily, term: str) -> list[str]:
    """对单个搜索词调用 Tavily，返回结果 URL 列表。

    Tavily 内部异常时会把 {"error": <exc>} 作为 dict 返回而非抛出，
    此处显式检测并打印警告，避免静默丢失错误。
    """
    try:
        result = tavily.invoke(term)

        # Tavily 把内部异常封装成 {"error": ...} dict 返回（不抛异常）
        if isinstance(result, dict) and "error" in result:
            logger.warning(
                f"Tavily 搜索返回错误：term={term!r}, error={result['error']}"
            )
            return []

        urls = [
            r["url"]
            for r in result.get("results", [])
            if isinstance(r, dict) and r.get("url")
        ]
        logger.debug(f"Tavily term={term!r}: {len(urls)} 条结果")
        return urls

    except Exception as exc:
        logger.warning(f"Tavily 搜索异常：term={term!r}, err={exc}")
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
            f"search_urls: 未配置 TAVILY_API_KEY，返回空列表。terms={terms[:3]}, limit={limit}"
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
