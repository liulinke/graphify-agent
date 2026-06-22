# Collector Agent：URL 发现、去重过滤、网页抓取与内容去重编排
from __future__ import annotations
from graphify.schemas.plan import CollectPlan
from graphify.tools.search import search_urls
from graphify.tools.fetch import fetch_page
from graphify.tools.dedup import check_duplicate
from graphify.tools.extract import extract_content
from graphify.dedup.url_norm import normalize_url


def discover_urls(plan: CollectPlan) -> list[str]:
    """根据采集计划生成候选搜索词，调用 search_urls 返回候选 URL 列表。"""
    terms = plan.topics + plan.supply_chain.upstream + plan.supply_chain.downstream
    # 预留 1.5~2x 候选量，抵消后续去重和抓取失败的损耗
    return search_urls.invoke({
        "terms": terms,
        "limit": int(plan.source_limit * 2),
        "region": plan.region,
        "lang": plan.language,
    })


def filter_known_urls(
    kb_id: str,
    urls: list[str],
    limit: int,
    repo=None,
) -> list[str]:
    """URL 级去重：过滤已采集的 URL，返回最多 limit 条新鲜 URL。"""
    from graphify.store.source_repo import _default_repo
    repo = repo or _default_repo
    fresh: list[str] = []
    for u in urls:
        # 先检查是否已达上限，避免 limit=0 时仍追加一条
        if len(fresh) >= limit:
            break
        nu = normalize_url(u)
        if not repo.url_seen(kb_id, nu):
            fresh.append(u)
    return fresh


def run(
    plan: CollectPlan,
    urls: list[str],
    repo=None,
) -> tuple[list[dict], list[str]]:
    """
    确定性采集编排：逐 URL 抓取 → 去重 → 正文抽取，失败隔离不影响整批。
    返回 (fetched, errors)。
    """
    fetched: list[dict] = []
    errors: list[str] = []
    for u in urls:
        try:
            page = fetch_page.invoke({"url": u})
            dup = check_duplicate.invoke({
                "kb_id": plan.kb_id,
                "url": u,
                "text": page["text"],
            })
            if dup["is_duplicate"]:
                continue
            content = extract_content.invoke({"html": page["html"]})
            fetched.append({"url": u, **content})
        except Exception as e:
            # 单个 URL 失败不中断整批采集，记录错误后继续
            errors.append(f"{u}: {e}")
    return fetched, errors
