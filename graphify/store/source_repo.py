# 来源指纹仓库：记录已采集 URL 的去重指纹，防止重复采集
from __future__ import annotations


class SourceRepo:
    """
    来源仓库存根：持久化 URL 去重记录与内容哈希。
    正式实现将对接 SQLite / PostgreSQL，此处为骨架占位。
    """

    def url_seen(self, kb_id: str, normalized_url: str) -> bool:
        """URL 是否已被采集（已在去重记录中）。"""
        # TODO: 查询 source/dedup_log 表
        raise NotImplementedError

    def get_content_hash(self, kb_id: str, normalized_url: str) -> str | None:
        """获取该 URL 上次采集时的内容哈希（SimHash 指纹）。"""
        # TODO: 查询 source 表
        raise NotImplementedError

    def mark_seen(self, kb_id: str, normalized_url: str, content_hash: str) -> None:
        """标记 URL 为已采集，写入内容哈希。"""
        # TODO: 写入 source 表
        raise NotImplementedError

    def log_dedup(self, kb_id: str, url: str, level: str, matched_id: str | None) -> None:
        """写 dedup_log 审计记录。"""
        # TODO: 写入 dedup_log 表
        raise NotImplementedError
