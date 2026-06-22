# 语义去重（可选）：向量余弦相似度，由 enable_semantic_dedup 开关控制
from __future__ import annotations
from graphify.config import settings


def semantic_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的语义相似度（余弦），返回 0~1。

    当前为存根，后续里程碑接入 langchain embeddings 实现。
    """
    # TODO: 接入 embedding 模型（langchain embeddings / 向量库）
    raise NotImplementedError(
        "语义去重尚未实现，需在后续里程碑配置 embedding 模型"
    )


def is_semantic_dup(
    text_a: str,
    text_b: str,
    threshold: float | None = None,
) -> bool:
    """判断两段文本是否语义重复。

    开关关闭时直接返回 False，不调用向量化接口（避免不必要的成本）。
    threshold 默认取配置中的 dedup_semantic_threshold（0.95）。
    """
    # 开关未启用时跳过，不抛异常，便于三层去重逻辑统一调用
    if not settings.enable_semantic_dedup:
        return False
    th = threshold if threshold is not None else settings.dedup_semantic_threshold
    return semantic_similarity(text_a, text_b) >= th
