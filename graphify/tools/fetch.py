# 网页抓取工具：用 httpx 抓取页面，遵守限速与 robots（存根）
from __future__ import annotations
from langchain_core.tools import tool


@tool
def fetch_page(url: str) -> dict:
    """用 httpx 抓取网页，遵守 robots/限速，返回 {url, html, text, status}。"""
    # TODO: httpx 实现，含超时、重试、User-Agent、robots 解析
    raise NotImplementedError("fetch_page 尚未实现")
