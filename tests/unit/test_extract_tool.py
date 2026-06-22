# 测试 graphify/tools/extract.py（_extract_fields 与 extract_content）
from __future__ import annotations
import pytest
from graphify.tools.extract import _extract_fields, extract_content


# ════════════════════════════════════════════════════════════════
# 一、_extract_fields 纯函数测试（正则字段提取）
# ════════════════════════════════════════════════════════════════

def test_extract_price_field() -> None:
    """'股价：12.5' 应提取 price='12.5'。"""
    fields = _extract_fields("公司股价：12.5元，同比增长5%")
    assert "price" in fields
    assert fields["price"] == "12.5"


def test_extract_volume_field() -> None:
    """'销量 3000' 应提取 volume='3000'。"""
    fields = _extract_fields("今年销量 3000 台")
    assert "volume" in fields
    assert fields["volume"] == "3000"


def test_extract_growth_field() -> None:
    """'增长15%' 应提取 growth='15'。"""
    fields = _extract_fields("同比增长15%")
    assert "growth" in fields
    assert fields["growth"] == "15"


def test_extract_multiple_fields() -> None:
    """一段文本中同时有多个字段时均应被提取。"""
    text = "股价：25.3元，销量：500台，增幅：8%"
    fields = _extract_fields(text)
    assert "price" in fields
    assert "volume" in fields
    assert "growth" in fields


def test_extract_no_fields_returns_empty_dict() -> None:
    """不包含任何模式的文本应返回空 dict。"""
    fields = _extract_fields("今天天气晴朗，适合户外活动。")
    assert fields == {}


def test_extract_empty_string_returns_empty_dict() -> None:
    """空字符串应返回空 dict，不抛异常。"""
    fields = _extract_fields("")
    assert fields == {}


# ════════════════════════════════════════════════════════════════
# 二、extract_content 工具测试
# ════════════════════════════════════════════════════════════════

def test_extract_content_returns_dict_with_keys() -> None:
    """extract_content 应返回含 text/title/fields 三个键的 dict。"""
    html = "<html><head><title>报告</title></head><body><p>内容</p></body></html>"
    result = extract_content.invoke({"html": html})
    assert "text" in result
    assert "title" in result
    assert "fields" in result


def test_extract_content_title_from_html() -> None:
    """title 应从 <title> 标签提取。"""
    html = "<html><head><title>机器人行业</title></head><body>正文</body></html>"
    result = extract_content.invoke({"html": html})
    assert result["title"] == "机器人行业"


def test_extract_content_text_excludes_scripts() -> None:
    """正文 text 不应包含 <script> 内容。"""
    html = "<html><body><script>alert(1)</script><p>有效内容</p></body></html>"
    result = extract_content.invoke({"html": html})
    assert "有效内容" in result["text"]
    assert "alert" not in result["text"]


def test_extract_content_fields_populated_from_text() -> None:
    """当正文含数值模式时，fields 应被填充。"""
    html = "<html><body><p>股价：18.8元</p></body></html>"
    result = extract_content.invoke({"html": html})
    assert "price" in result["fields"]


def test_extract_content_empty_html() -> None:
    """空字符串 HTML 不应抛异常，返回 title/text 均为空。"""
    result = extract_content.invoke({"html": ""})
    assert result["title"] == ""
    assert isinstance(result["text"], str)
    assert result["fields"] == {}


def test_extract_content_strips_noise_tags() -> None:
    """nav/footer 等噪音标签内容不应出现在正文中。"""
    html = "<html><body><nav>菜单</nav><p>正文段落</p><footer>页脚</footer></body></html>"
    result = extract_content.invoke({"html": html})
    assert "正文段落" in result["text"]
    assert "菜单" not in result["text"]
    assert "页脚" not in result["text"]
