# 测试 graphify/llm.py 的工厂函数（不实际调用 LLM）
from __future__ import annotations
import pytest
from unittest.mock import patch, MagicMock
from graphify.llm import get_llm, model_id
from graphify.config import Settings


def test_model_id_returns_config_value(monkeypatch):
    """model_id() 应返回配置中的 llm_model 字符串。"""
    monkeypatch.setenv("GRAPHIFY_LLM_MODEL", "anthropic:claude-sonnet-4-6")
    # 直接导入后配置已固化，用 mock 绕过模块级 settings 单例
    from graphify import llm as llm_module
    with patch.object(llm_module, "settings", Settings()):
        result = llm_module.model_id()
    assert result == "anthropic:claude-sonnet-4-6"


def test_get_llm_calls_init_chat_model():
    """get_llm() 应透传 model 参数给 init_chat_model，不直接调用 LLM。"""
    mock_model = MagicMock()
    with patch("graphify.llm.init_chat_model", return_value=mock_model) as mock_init:
        result = get_llm("openai:gpt-4o")
    mock_init.assert_called_once_with("openai:gpt-4o")
    assert result is mock_model


def test_get_llm_uses_config_when_no_model_given():
    """不传 model 时，应使用 settings.llm_model 的值。"""
    mock_model = MagicMock()
    fake_settings = Settings()
    from graphify import llm as llm_module
    with patch("graphify.llm.init_chat_model", return_value=mock_model) as mock_init, \
         patch.object(llm_module, "settings", fake_settings):
        result = get_llm()
    mock_init.assert_called_once_with(fake_settings.llm_model)
    assert result is mock_model
