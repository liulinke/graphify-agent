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
    """get_llm() 显式传非 qwen 模型时应走 init_chat_model 路径。"""
    mock_model = MagicMock()
    with patch("graphify.llm.init_chat_model", return_value=mock_model) as mock_init:
        result = get_llm("openai:gpt-4o")
    mock_init.assert_called_once_with("openai:gpt-4o")
    assert result is mock_model


def test_get_llm_uses_config_when_no_model_given():
    """不传 model 且 llm_model 为非 qwen 时，应调用 init_chat_model。"""
    mock_model = MagicMock()
    # 构造一个固定为非 qwen 模型的 settings，避免 .env 环境值干扰
    fake_settings = Settings(_env_file=None, LLM_MODEL="anthropic:claude-sonnet-4-6")
    from graphify import llm as llm_module
    with patch("graphify.llm.init_chat_model", return_value=mock_model) as mock_init, \
         patch.object(llm_module, "settings", fake_settings):
        result = get_llm()
    mock_init.assert_called_once_with("anthropic:claude-sonnet-4-6")
    assert result is mock_model


def test_get_llm_routes_qwen_to_chattongyi():
    """qwen-* 模型应走 ChatTongyi 路径，不调用 init_chat_model。"""
    mock_tongyi = MagicMock()
    fake_settings = Settings(_env_file=None, LLM_MODEL="qwen-plus")
    from graphify import llm as llm_module
    # mock ChatTongyi 类，避免真实实例化
    with patch("graphify.llm.init_chat_model") as mock_init, \
         patch("langchain_community.chat_models.ChatTongyi", return_value=mock_tongyi) as mock_cls, \
         patch.object(llm_module, "settings", fake_settings):
        result = get_llm()
    mock_init.assert_not_called()
    assert result is mock_tongyi


def test_get_llm_explicit_qwen_model():
    """显式传入 qwen-max 时也应走 ChatTongyi 路径。"""
    mock_tongyi = MagicMock()
    with patch("langchain_community.chat_models.ChatTongyi", return_value=mock_tongyi), \
         patch("graphify.llm.init_chat_model") as mock_init:
        result = get_llm("qwen-max")
    mock_init.assert_not_called()
    assert result is mock_tongyi
