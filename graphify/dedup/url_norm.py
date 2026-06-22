# URL 规范化：去追踪参数、统一大小写、去 fragment、路径尾斜杠归一
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

# 常见追踪参数，规范化时丢弃
_DROP = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "fbclid", "gclid",
}


def normalize_url(url: str) -> str:
    """规范化 URL：去追踪参数、统一小写域名、去 fragment、query 字典序。"""
    s = urlsplit(url.strip())
    scheme = (s.scheme or "https").lower()
    netloc = s.netloc.lower()
    # 过滤追踪参数，按字母序排列剩余参数
    query = urlencode(sorted((k, v) for k, v in parse_qsl(s.query) if k not in _DROP))
    # 路径尾斜杠归一：非根路径去掉尾斜杠
    path = s.path.rstrip("/") or "/"
    # 去掉 fragment（锚点）
    return urlunsplit((scheme, netloc, path, query, ""))
