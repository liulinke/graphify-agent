# 全局配置：从环境变量或 .env 文件读取，启动时校验
from __future__ import annotations
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic.aliases import AliasChoices


class Settings(BaseSettings):
    """Graphify 服务端配置。

    大多数字段可通过 GRAPHIFY_* 前缀环境变量覆盖；
    LLM 相关字段同时支持无前缀形式（方便与第三方 .env 兼容）：
      LLM_MODEL          → llm_model
      DASHSCOPE_API_KEY  → dashscope_api_key
    """

    # Neo4j 连接
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "password"

    # LLM 后端：优先读 GRAPHIFY_LLM_MODEL，回退到 LLM_MODEL
    # qwen-* 模型由 ChatTongyi 驱动；其他格式交 init_chat_model 处理
    llm_model: str = Field(
        default="anthropic:claude-sonnet-4-6",
        validation_alias=AliasChoices("GRAPHIFY_LLM_MODEL", "LLM_MODEL"),
    )

    # DashScope API Key（通义千问）：优先读 GRAPHIFY_DASHSCOPE_API_KEY，回退到 DASHSCOPE_API_KEY
    dashscope_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GRAPHIFY_DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY"),
    )

    # Tavily Search API Key：优先读 GRAPHIFY_TAVILY_API_KEY，回退到 TAVILY_API_KEY
    tavily_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("GRAPHIFY_TAVILY_API_KEY", "TAVILY_API_KEY"),
    )

    # 去重阈值
    dedup_simhash_threshold: int = 3          # SimHash 汉明距离上限（≤ 此值视为重复）
    dedup_semantic_threshold: float = 0.95    # 语义相似度上限（≥ 此值视为重复）
    enable_semantic_dedup: bool = False        # 语义去重默认关闭（需向量化，成本较高）

    # 采集限制
    fetch_timeout_s: int = 30                 # 单页抓取超时（秒）
    fetch_max_retries: int = 3                # 最大重试次数

    # 是否信任系统/环境代理（macOS 系统代理不稳定时会导致
    # Tavily/DashScope 间歇性 SSL 断连，默认 False = 全部直连）
    trust_env_proxy: bool = False

    model_config = SettingsConfigDict(
        env_prefix="GRAPHIFY_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",          # 忽略未声明的 GRAPHIFY_* 环境变量
        populate_by_name=True,   # 允许同时用字段名和 alias 设值
    )


# 单例：模块加载时读取一次，测试中可用 Settings(...) 构造隔离实例
settings = Settings()


def apply_proxy_policy(s: Settings | None = None) -> None:
    """按配置应用代理策略，应在 CLI / API 入口显式调用一次。

    trust_env_proxy=False（默认）时设置 NO_PROXY=*，让 requests/httpx
    忽略系统代理直连——不稳定的本地代理（如 127.0.0.1:1087）会造成
    DashScope/Tavily 间歇性 Broken pipe / SSL EOF 错误。
    """
    import os
    s = s or settings
    if not s.trust_env_proxy:
        os.environ["NO_PROXY"] = "*"
        os.environ["no_proxy"] = "*"
