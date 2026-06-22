# 来源指纹仓库：记录已采集 URL 的去重指纹，防止重复采集
from __future__ import annotations


class SourceRepo:
    """
    来源仓库接口：持久化 URL 去重记录与内容哈希。
    正式实现将对接 SQLite / PostgreSQL；InMemorySourceRepo 供单元测试使用。
    """

    def url_seen(self, kb_id: str, normalized_url: str) -> bool:
        """URL 是否已被采集。"""
        raise NotImplementedError

    def get_content_hash(self, kb_id: str, normalized_url: str) -> str | None:
        """获取该 URL 上次采集时的 MD5 内容哈希，未见过返回 None。"""
        raise NotImplementedError

    def mark_seen(
        self,
        kb_id: str,
        normalized_url: str,
        content_hash: str,
        simhash_fp: int = 0,
    ) -> None:
        """标记 URL 为已采集，写入内容哈希与 SimHash 指纹。"""
        raise NotImplementedError

    def get_recent_fingerprints(self, kb_id: str, limit: int = 1000) -> list[int]:
        """获取该 kb_id 最近 limit 条 SimHash 指纹，供内容级去重比对。"""
        raise NotImplementedError

    def log_dedup(
        self,
        kb_id: str,
        url: str,
        level: str,
        matched_id: str | None,
    ) -> None:
        """写 dedup_log 审计记录。"""
        raise NotImplementedError


class InMemorySourceRepo(SourceRepo):
    """完全内存的 SourceRepo 实现，供单元测试注入。"""

    def __init__(self) -> None:
        # (kb_id, nu) → {"hash": str, "simhash": int}
        self._store: dict[tuple[str, str], dict] = {}
        self.logs: list[dict] = []

    def url_seen(self, kb_id: str, normalized_url: str) -> bool:
        return (kb_id, normalized_url) in self._store

    def get_content_hash(self, kb_id: str, normalized_url: str) -> str | None:
        return self._store.get((kb_id, normalized_url), {}).get("hash")

    def mark_seen(
        self,
        kb_id: str,
        normalized_url: str,
        content_hash: str,
        simhash_fp: int = 0,
    ) -> None:
        self._store[(kb_id, normalized_url)] = {"hash": content_hash, "simhash": simhash_fp}

    def get_recent_fingerprints(self, kb_id: str, limit: int = 1000) -> list[int]:
        fps = [v["simhash"] for (kb, _), v in self._store.items() if kb == kb_id]
        return fps[-limit:]

    def log_dedup(
        self,
        kb_id: str,
        url: str,
        level: str,
        matched_id: str | None,
    ) -> None:
        self.logs.append({"kb_id": kb_id, "url": url, "level": level, "matched_id": matched_id})


# 进程级单例：同一次运行内所有 collect 调用共享同一份已见 URL 表，避免重复抓取同一 URL。
# 注意：进程退出后状态丢失；生产环境应替换为 SQLite/Redis 持久化实现。
_default_repo = InMemorySourceRepo()
