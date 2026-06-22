# 语义去重（可选）：向量余弦相似度，由 enable_semantic_dedup 开关控制
# 此模块为存根，向量库集成在后续里程碑实现
from __future__ import annotations


def semantic_similarity(text_a: str, text_b: str) -> float:
    """计算两段文本的语义相似度（余弦），返回 0~1。"""
    # TODO: 接入 embedding 模型（langchain embeddings）
    raise NotImplementedError("语义去重尚未实现，需启用 enable_semantic_dedup=True 并配置 embedding")
