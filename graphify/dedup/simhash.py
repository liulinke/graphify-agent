# SimHash 内容指纹：用于内容级去重（汉明距离比较）
from __future__ import annotations
import hashlib
import re


def _tokenize(text: str) -> list[str]:
    """简单分词：中文字级别 + 英文词级别。"""
    # 中文按字拆分，英文按词拆分
    tokens = re.findall(r"[一-鿿]|[a-zA-Z0-9]+", text.lower())
    return tokens


def simhash(text: str, bits: int = 64) -> int:
    """计算文本的 SimHash 指纹。"""
    if not text:
        return 0
    tokens = _tokenize(text)
    v = [0] * bits
    for token in tokens:
        # 用 MD5 作为哈希函数
        h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
        for i in range(bits):
            bit = (h >> i) & 1
            v[i] += 1 if bit else -1
    # 正权重位置置 1，否则置 0
    result = 0
    for i in range(bits):
        if v[i] > 0:
            result |= 1 << i
    return result


def hamming(a: int, b: int) -> int:
    """计算两个整数的汉明距离（不同比特数）。"""
    return bin(a ^ b).count("1")


def is_near_dup(a: int, b: int, threshold: int = 3) -> bool:
    """汉明距离 ≤ threshold 则判定为近似重复。"""
    return hamming(a, b) <= threshold
