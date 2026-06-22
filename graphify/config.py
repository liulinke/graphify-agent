# 全局配置：从环境变量或 .env 文件读取，启动时校验
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Graphify 服务端配置，所有字段均可通过 GRAPHIFY_* 环境变量覆盖。"""

    # Neo4j 连接
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # LLM 后端（格式：provider:model-id，兼容 init_chat_model）
    llm_model: str = "anthropic:claude-sonnet-4-6"

    # 去重阈值
    dedup_simhash_threshold: int = 3          # SimHash 汉明距离上限（≤ 此值视为重复）
    dedup_semantic_threshold: float = 0.95    # 语义相似度上限（≥ 此值视为重复）
    enable_semantic_dedup: bool = False        # 语义去重默认关闭（需向量化，成本较高）

    # 采集限制
    fetch_timeout_s: int = 30                 # 单页抓取超时（秒）
    fetch_max_retries: int = 3                # 最大重试次数

    model_config = SettingsConfigDict(
        env_prefix="GRAPHIFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


# 单例：模块加载时读取一次，测试中可用 Settings(...) 构造隔离实例
settings = Settings()
