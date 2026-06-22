# LLM 工厂：封装 init_chat_model，统一从配置读取模型 ID
# qwen-* 模型走 ChatTongyi（DashScope），其他模型走 init_chat_model
from __future__ import annotations
from langchain.chat_models import init_chat_model
from graphify.config import settings


def get_llm(model: str | None = None):
    """返回 LangChain ChatModel 实例。

    - qwen-* 模型：使用 ChatTongyi（langchain-community），读取 DASHSCOPE_API_KEY
    - 其他模型：使用 init_chat_model，格式如 'anthropic:claude-sonnet-4-6'
    测试中可传入 FakeLLM 替身，生产中不传则用配置中的 llm_model。
    """
    model_name = model or settings.llm_model
    if model_name.startswith("qwen"):
        import warnings
        # 忽略 langchain-community sunset 警告，ChatTongyi 仍是 DashScope 的标准接口
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            from langchain_community.chat_models import ChatTongyi
        # dashscope_api_key 为空时 ChatTongyi 自动读取环境变量 DASHSCOPE_API_KEY
        api_key = settings.dashscope_api_key or None
        # request_timeout 经由 model_kwargs 传给 DashScope SDK（默认 300s 太长，容易卡死流水线）
        return ChatTongyi(
            model=model_name,
            dashscope_api_key=api_key,
            model_kwargs={"request_timeout": 60},
        )
    return init_chat_model(model_name)


def model_id() -> str:
    """返回当前配置的模型 ID 字符串（供日志、元数据记录使用）。"""
    return settings.llm_model
