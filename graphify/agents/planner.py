# Planner Agent：将自然语言采集指令解析为结构化 CollectPlan
# 用提示词驱动 JSON 输出代替 with_structured_output，兼容 qwen 等不支持工具调用的模型
from __future__ import annotations
import json
import re
from graphify.schemas.plan import CollectPlan

# 明确要求输出完整 JSON，并给出字段说明，防止 qwen 截断输出
PLANNER_SYS = """你是采集计划解析器。把用户的中文采集指令解析为 JSON 格式的采集计划。

严格按如下格式输出完整 JSON（不加任何解释、不加代码块标记）：
{
  "domain": "领域关键词（英文短语，如 robotics）",
  "topics": ["主题词1", "主题词2"],
  "include_supply_chain": false,
  "supply_chain": {"upstream": [], "downstream": []},
  "region": "CN",
  "source_limit": 100,
  "freshness": "incremental",
  "language": ["zh"],
  "schedule": "once"
}

解析规则：
- domain：领域英文简写，topics：具体中文搜索词（2~5 个）
- 若提到"上下游/产业链"，include_supply_chain 设为 true，并填充 upstream/downstream
- source_limit 默认 100，可从指令中提取（如"来源50"→50）
- 只输出 JSON 对象，必须以 } 结尾"""


def _extract_json(text: str) -> str:
    """从 LLM 响应文本中提取第一个完整 JSON 对象。

    兼容以下情况：
    - 纯 JSON 响应
    - ```json ... ``` 代码块包裹
    - JSON 前后有多余文字
    """
    # 优先匹配 ```json ... ``` 代码块
    md = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if md:
        return md.group(1)
    # 再找第一个 { ... } 块（贪婪匹配整个对象）
    brace = re.search(r"\{[\s\S]*\}", text)
    if brace:
        return brace.group(0)
    return text.strip()


def parse_instruction(kb_id: str, instruction: str, llm=None) -> CollectPlan:
    """将自然语言指令解析为 CollectPlan，支持传入 FakeLLM 替身进行单测。

    采用 prompt-based JSON 输出方式，兼容 qwen 等工具调用不稳定的模型。
    """
    from graphify.llm import get_llm
    llm = llm or get_llm()

    # 直接 invoke 获取文本响应，不用 with_structured_output（避免工具调用截断问题）
    msg = llm.invoke([
        ("system", PLANNER_SYS),
        ("human", instruction),
    ])
    raw = msg.content if hasattr(msg, "content") else str(msg)

    json_str = _extract_json(raw)
    data = json.loads(json_str)

    # kb_id 由调用方注入，不依赖 LLM；先写入 dict 再验证，避免 required 字段校验失败
    data["kb_id"] = kb_id
    plan = CollectPlan.model_validate(data)
    return plan
