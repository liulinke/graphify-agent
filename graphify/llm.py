# LLM 工厂：封装 init_chat_model，统一从配置读取模型 ID
from __future__ import annotations
from langchain.chat_models import init_chat_model
from graphify.config import settings


def get_llm(model: str | None = None):
    """返回 LangChain ChatModel 实例。

    测试中可传入 FakeLLM 替身，生产中不传则用配置中的 llm_model。
    model 格式示例：'anthropic:claude-sonnet-4-6'、'openai:gpt-4o'
    """
    return init_chat_model(model or settings.llm_model)


def model_id() -> str:
    """返回当前配置的模型 ID 字符串（供日志、元数据记录使用）。"""
    return settings.llm_model
