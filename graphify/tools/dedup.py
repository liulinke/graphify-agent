# 去重工具：三层去重（URL级→内容级 SimHash→语义级，可选）
from __future__ import annotations
import hashlib
from langchain_core.tools import tool
from graphify.dedup.url_norm import normalize_url
from graphify.dedup.simhash import simhash, is_near_dup
from graphify.dedup.semantic import is_semantic_dup
from graphify.config import settings


def check_duplicate_impl(
    kb_id: str,
    url: str,
    text: str,
    repo,
) -> dict:
    """三层去重核心逻辑（纯函数，支持注入 repo 替身以便单测）。

    返回:
        is_duplicate  : 是否判定为重复（True 时 collector 跳过该 URL）
        level         : 命中层（"url" / "simhash" / "semantic" / None）
        matched_source_id: 命中的标识（URL 层为规范化 URL，其他层为 None）
        changed       : URL 层命中但内容有变（需走时序快照，不算丢弃）
    """
    nu = normalize_url(url)
    curr_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    curr_fp = simhash(text)

    # ── 第一层：URL 级去重 ──────────────────────────────────────
    if repo.url_seen(kb_id, nu):
        prev_hash = repo.get_content_hash(kb_id, nu)
        if prev_hash == curr_hash:
            # 内容未变 → 真正重复，直接跳过
            repo.log_dedup(kb_id, url, "url", nu)
            return {
                "is_duplicate": True,
                "level": "url",
                "matched_source_id": nu,
                "changed": False,
            }
        else:
            # 内容变化 → 需要时序快照更新，不算重复
            repo.mark_seen(kb_id, nu, curr_hash, curr_fp)
            return {
                "is_duplicate": False,
                "level": "url",
                "matched_source_id": nu,
                "changed": True,
            }

    # ── 第二层：内容指纹（SimHash）去重 ──────────────────────────
    recent_fps = repo.get_recent_fingerprints(kb_id)
    for fp in recent_fps:
        if is_near_dup(curr_fp, fp, threshold=settings.dedup_simhash_threshold):
            repo.log_dedup(kb_id, url, "simhash", None)
            return {
                "is_duplicate": True,
                "level": "simhash",
                "matched_source_id": None,
                "changed": False,
            }

    # ── 第三层：语义去重（可选，enable_semantic_dedup 控制）─────
    # is_semantic_dup 当开关关闭时直接返回 False，不调用向量化
    # 语义层需要遍历已存文本，此处为框架存根；完整实现见后续里程碑
    if is_semantic_dup(text, ""):   # pragma: no cover — 需 enable_semantic_dedup=True
        repo.log_dedup(kb_id, url, "semantic", None)
        return {
            "is_duplicate": True,
            "level": "semantic",
            "matched_source_id": None,
            "changed": False,
        }

    # ── 未命中任何层：标记为已见，返回非重复 ─────────────────────
    repo.mark_seen(kb_id, nu, curr_hash, curr_fp)
    return {
        "is_duplicate": False,
        "level": None,
        "matched_source_id": None,
        "changed": False,
    }


@tool
def check_duplicate(kb_id: str, url: str, text: str) -> dict:
    """三层去重：URL级→内容级(SimHash)→语义级(向量，可选开关)。

    返回 {is_duplicate, level, matched_source_id, changed}。
    changed=True 表示同 URL 内容已变，collector 应走时序快照更新。
    """
    from graphify.store.source_repo import _default_repo
    # 使用进程级单例，避免同一次采集中重复处理同一 URL
    return check_duplicate_impl(kb_id, url, text, _default_repo)
