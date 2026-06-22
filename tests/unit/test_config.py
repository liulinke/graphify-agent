# 测试 graphify/config.py 的配置读取与环境变量覆盖
from __future__ import annotations
import pytest
from graphify.config import Settings


def test_default_values():
    """所有字段应有合理默认值，不依赖环境变量。"""
    cfg = Settings()
    assert cfg.neo4j_uri == "bolt://localhost:7687"
    assert cfg.neo4j_user == "neo4j"
    assert cfg.neo4j_password == "password"
    assert cfg.llm_model == "anthropic:claude-sonnet-4-6"
    assert cfg.dedup_simhash_threshold == 3
    assert cfg.dedup_semantic_threshold == 0.95
    assert cfg.enable_semantic_dedup is False
    assert cfg.fetch_timeout_s == 30
    assert cfg.fetch_max_retries == 3


def test_env_override(monkeypatch):
    """GRAPHIFY_* 环境变量应覆盖默认值。"""
    monkeypatch.setenv("GRAPHIFY_NEO4J_URI", "bolt://neo4j-host:7688")
    monkeypatch.setenv("GRAPHIFY_LLM_MODEL", "openai:gpt-4o")
    monkeypatch.setenv("GRAPHIFY_ENABLE_SEMANTIC_DEDUP", "true")

    cfg = Settings()
    assert cfg.neo4j_uri == "bolt://neo4j-host:7688"
    assert cfg.llm_model == "openai:gpt-4o"
    assert cfg.enable_semantic_dedup is True


def test_case_insensitive_env(monkeypatch):
    """环境变量名大小写不敏感（pydantic-settings 默认行为）。"""
    monkeypatch.setenv("GRAPHIFY_NEO4J_PASSWORD", "secret123")
    cfg = Settings()
    assert cfg.neo4j_password == "secret123"
