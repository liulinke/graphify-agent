# graphify-agent

网络信息采集 → 知识图谱（Neo4j）→ 图形化/自然语言查询的服务端。

## 功能特性

- **增量采集**：同一知识库可多次运行 `collect`，系统自动跳过已采集的 URL，只处理新内容
- **三层去重**：URL 规范化 → SimHash 内容指纹 → 语义向量（可选），防止重复内容进入图谱
- **幂等写入**：所有节点和关系通过 `MERGE` 写入 Neo4j，重复运行不会产生重复节点
- **时序快照**：随时间变化的数值（股价、销量等）用 `CREATE` 追加快照，历史数据永不覆盖
- **NL2Cypher**：自然语言查询转 Cypher，内置只读护栏（拦截写操作）
- **LangGraph 工作流**：plan → discover → dedup → collect → extract → build，支持断点续跑
- **CLI / REST API**：Typer CLI 调试入口 + FastAPI HTTP 接口

## 技术栈

| 用途 | 库 |
|---|---|
| Agent 编排 | LangChain / LangGraph |
| 图数据库 | Neo4j 5.x（官方 driver） |
| HTTP 抓取 | httpx + BeautifulSoup |
| 配置 | pydantic-settings |
| CLI | Typer |
| 日志 | loguru |

## 安装

```bash
# 要求 Python 3.11+，使用 uv 管理环境
uv venv && source .venv/bin/activate
uv sync
```

## 环境配置

复制示例并按需修改：

```bash
cp .env.example .env
```

关键变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `GRAPHIFY_NEO4J_URI` | `bolt://localhost:7687` | Neo4j 连接地址 |
| `GRAPHIFY_NEO4J_USER` | `neo4j` | 用户名 |
| `GRAPHIFY_NEO4J_PASSWORD` | `password` | 密码 |
| `GRAPHIFY_LLM_MODEL` | `anthropic:claude-sonnet-4-6` | LLM 模型（provider:model-id） |

## CLI 示例

```bash
# 解析采集指令（不实际采集）
uv run python -m graphify.cli.main plan kb_demo "采集机器人行业新闻，来源100"

# 端到端采集（首次）
uv run python -m graphify.cli.main collect kb_demo "采集工业机器人行业新闻"

# 增量采集：再次运行同一指令，已采集 URL 自动跳过，只处理新内容
uv run python -m graphify.cli.main collect kb_demo "采集工业机器人行业新闻"

# 限制本次最多采集页数（适合快速测试）
uv run python -m graphify.cli.main collect kb_demo "采集工业机器人行业新闻" --limit 5

# 自然语言查询知识图谱
uv run python -m graphify.cli.main ask kb_demo "埃斯顿的主要客户有哪些？"
```

## 增量采集工作原理

每次 `collect` 运行时，系统按以下三层去重决定是否处理某条 URL：

```
候选 URL
   │
   ▼
① URL 去重：规范化后与已见 URL 表比对
   ├─ 完全相同 URL 且内容未变 → 跳过
   ├─ 相同 URL 但内容已更新 → 写入时序快照（保留历史）
   └─ 新 URL → 继续
   │
   ▼
② SimHash 内容指纹：与近期采集页面的指纹比对
   └─ 汉明距离 ≤ 阈值（默认 3）→ 跳过（近似重复内容）
   │
   ▼
③ 语义去重（可选，GRAPHIFY_ENABLE_SEMANTIC_DEDUP=true）
   └─ 向量相似度 ≥ 阈值 → 跳过
   │
   ▼
通过去重 → LLM 抽取三元组 → MERGE 写入 Neo4j
```

**写入保证**：
- 实体/关系：`MERGE` 幂等，同一实体多次采集只存一个节点
- 时序数值：`CREATE` 追加，每次更新都保留为独立快照，可查看历史变化趋势

## 开发流程

```bash
# 写代码 → 测试 → 修复 → 重跑，直到全绿
uv run pytest tests/unit -q --cov=graphify --cov-report=term-missing

# 集成测试（需 Docker，启动 Neo4j testcontainer）
uv run pytest -m integration -q
```

## 项目结构

```
graphify/
├── config.py          # pydantic-settings 全局配置
├── llm.py             # LLM 工厂（init_chat_model 封装）
├── state.py           # LangGraph 工作流状态定义
├── graph_workflow.py  # 主工作流（StateGraph）
├── agents/            # Planner / Collector / GraphBuilder / QueryAgent
├── tools/             # fetch / dedup / cypher 工具节点
├── graphdb/           # Neo4j driver / DAO / CQL 模板
├── schemas/           # Pydantic 数据模型
├── dedup/             # SimHash / 语义去重
├── store/             # 已采集 URL 持久化
├── cli/               # Typer CLI 入口
└── api/               # FastAPI REST 入口
tests/
├── unit/              # 离线单元测试（默认运行）
└── integration/       # 集成测试（需 Docker）
```

## 故障排查

- **Neo4j 连接失败**：确认 `GRAPHIFY_NEO4J_*` 环境变量正确，Neo4j 容器已启动
- **LLM 调用报错**：检查 API KEY（如 `DASHSCOPE_API_KEY` / `ANTHROPIC_API_KEY`）是否已设置
- **SimHash 去重过激**：调整 `GRAPHIFY_DEDUP_SIMHASH_THRESHOLD`（默认 3，越小越严格）
- **增量采集未生效**：进程级去重状态在进程退出后会丢失；如需跨进程持久化去重，需将 `store/source_repo.py` 中的 `_default_repo` 替换为 SQLite/Redis 持久化实现
