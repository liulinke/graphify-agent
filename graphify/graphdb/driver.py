# Neo4j 驱动单例（通过依赖注入传入，单元测试时替换为 mock）
from __future__ import annotations
from neo4j import GraphDatabase, Driver
from graphify.config import settings

_driver: Driver | None = None


def get_driver() -> Driver:
    """获取 Neo4j 驱动单例，仅在首次调用时初始化。"""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
            # 关闭服务端通知（避免 DEPRECATION 等 WARNING 刷屏）
            notifications_min_severity="OFF",
        )
    return _driver


def close_driver() -> None:
    """关闭驱动（应用退出时调用）。"""
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
