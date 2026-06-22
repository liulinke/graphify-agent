# 网页抓取工具：httpx + BeautifulSoup，含超时、重试、User-Agent
from __future__ import annotations
import httpx
from bs4 import BeautifulSoup
from langchain_core.tools import tool
from graphify.config import settings

# 移除正文时不需要的标签
_NOISE_TAGS = ["script", "style", "nav", "footer", "header", "aside", "noscript"]

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (compatible; graphify-agent/0.1; "
        "+https://github.com/graphify-agent)"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def _extract_text(html: str) -> tuple[str, str]:
    """从 HTML 中提取正文和标题，返回 (title, text)。"""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    for tag in soup(_NOISE_TAGS):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return title, text


@tool
def fetch_page(url: str) -> dict:
    """用 httpx 抓取网页，返回 {url, html, text, title, status}。

    含超时（GRAPHIFY_FETCH_TIMEOUT_S）与重试（GRAPHIFY_FETCH_MAX_RETRIES）。
    抓取失败时抛出 httpx.HTTPError（由上层 collector.run 做失败隔离）。
    """
    timeout = settings.fetch_timeout_s
    max_retries = settings.fetch_max_retries

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(
                timeout=timeout,
                follow_redirects=True,
                headers=_HEADERS,
            ) as client:
                resp = client.get(url)
                resp.raise_for_status()
                html = resp.text
                title, text = _extract_text(html)
                return {
                    "url": url,
                    "html": html,
                    "text": text,
                    "title": title,
                    "status": resp.status_code,
                }
        except httpx.HTTPStatusError:
            raise  # 4xx/5xx 不重试，直接上抛
        except httpx.RequestError as exc:
            last_exc = exc
            # 网络错误才重试（最后一次后上抛）
            if attempt == max_retries - 1:
                raise

    raise RuntimeError(f"fetch_page: 意外退出重试循环 {url}") from last_exc
