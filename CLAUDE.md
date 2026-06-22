# CLAUDE.md

本文件供 Claude Code 每次会话自动读取，定义本项目的实现规则。

## 项目

**graphify-agent** —— 网络信息采集 → 知识图谱（Neo4j）→ 图形化/自然语言查询的服务端。
完整设计见 `docs/服务端详细开发设计文档.md`，需求见 `docs/知识图谱采集Agent_软件需求说明书.md`。
实现必须以设计文档为准；目录结构见设计文档第 2 章。

## 技术栈

- Python 3.11+
- LangChain / LangGraph / deepagents（Agent 编排）
- Neo4j 5.x（图数据库，`neo4j` 官方 driver）
- httpx + BeautifulSoup（抓取）
- Typer（CLI）
- pydantic / pydantic-settings（数据模型与配置）
- pytest + pytest-cov + responses + testcontainers[neo4j]（测试）

## 硬性规则（务必遵守）

1. **每个模块必须配 pytest 单元测试**，测试清单见设计文档第 10.3 节。
2. **外部依赖一律 mock**：LLM、网络抓取、Neo4j 在单元测试中不得真实调用。用设计文档第 10.2 节的 `FakeLLM` / `FakeDAO` 等替身。
3. **依赖注入**：所有 agent / dao / repo / llm 都通过参数传入，默认值才构造真实实例（便于测试）。
4. **提交前 `pytest tests/unit -q` 必须全绿**，行覆盖目标 ≥ 85%。
5. 不要一次性生成整个项目。**按里程碑逐个模块实现**，每个模块写完即跑对应测试，修到全绿再继续。
6. 不要引入设计文档之外的新框架/重型依赖（如 Playwright、Selenium），除非显式要求。
7. NL2Cypher 查询通道**只读**：必须拦截 CREATE/MERGE/DELETE/SET，强制 LIMIT 与 kb_id 过滤。
8. 图谱写入用 `MERGE` 保证幂等；随时间变化的数值用 `append_snapshot` 追加快照，绝不覆盖历史。

## 环境与常用命令（使用 uv）

本项目用 **uv** 管理 Python 环境与依赖。

```bash
# 初始化（仅首次）
uv venv && source .venv/bin/activate
uv sync                                   # 按 pyproject.toml / uv.lock 安装

# 添加依赖
uv add langchain langgraph deepagents neo4j httpx beautifulsoup4 typer pydantic pydantic-settings loguru
uv add --dev pytest pytest-mock pytest-asyncio pytest-cov responses "testcontainers[neo4j]"

# 运行测试
uv run pytest tests/unit -q --cov=graphify --cov-report=term-missing
uv run pytest tests/integration -q        # 需 Docker (Neo4j testcontainers)
uv run pytest -m integration              # 仅跑标记为 integration 的用例

# 运行 CLI
uv run python -m graphify.cli.main plan kb_demo "采集机器人行业新闻，来源100"
```

## 验证循环（每个模块照此执行）

写代码 → 运行该模块的测试 → 读报错 → 修复 → 重跑，直到测试全绿才算完成该模块。
不要在测试未通过时声称完成。

---

# Python 工程规范（通用标准）

> 下列为通用 Python 工程标准。**当与本项目设计文档冲突时，以 `docs/服务端详细开发设计文档.md` 为准**——
> 特别是**项目结构**：本项目采用设计文档第 2 章的 `graphify/` 包布局（agents / tools / graphdb / dedup / store / cli），
> 而非下文示例中的 `src/app/` 通用布局。下文的技术栈、配置、日志、测试、uv 等要求全部适用。

## 角色与核心原则

以资深 Python 工程师的标准产出**生产级**代码，要求：简单可维护、结构清晰可扩展、强类型、可完整测试、易运维易调试、适合长期演进。
显式优于魔法，避免不必要的抽象。

## 标准技术栈（默认，除非有充分理由）

| 用途 | 库 |
|---|---|
| 日志 | loguru |
| CLI | typer |
| 配置与数据模型 | pydantic |
| HTTP 客户端 | httpx |
| 文件系统 | pathlib |
| 异步 | asyncio |

补充：广泛使用 typing；仅在无需 Pydantic 时才用 dataclass；常量用 Enum；避免全局可变状态；尽量少引第三方依赖。

## 项目初始化

1. 初始化 Git：`git init -b main`（默认分支 **main**，禁用 master）。
2. 生成合适的 `.gitignore`，典型条目：

```
__pycache__/
*.py[cod]
.venv/
.env
.pytest_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
.idea/
.vscode/
.DS_Store
```

## 通用项目结构（参考；本项目以设计文档为准）

```
project-name/
├── README.md
├── pyproject.toml
├── uv.lock
├── .gitignore
├── src/app/{__init__.py,main.py,cli.py,config.py,models/,services/,clients/,utils/,exceptions/}
├── tests/{unit/,integration/,fixtures/}
└── scripts/
```

约定：`models/` Pydantic 模型；`services/` 业务逻辑；`clients/` 外部集成；`utils/` 复用工具；`exceptions/` 自定义异常；tests 镜像源码结构。为未来扩展而设计。

## 配置

用 **Pydantic Settings**：环境变量优先、合理默认、启动时校验、类型安全；支持 `.env`、环境变量、多环境。

## 日志

用 **loguru**：控制台日志（必要时文件日志）、结构化消息、合适的日志级别、包含异常堆栈。避免过度日志。

## CLI

用 **typer**：清晰的命令/子命令、有用的 `--help`、类型安全参数、良好错误信息。自文档化、直观。

## HTTP 层

用 **httpx**：设置超时、必要时重试、妥善的异常处理、连接复用、支持异步。绝不忽略网络失败。

## 文件操作

用 **pathlib**：不硬编码路径分隔符、统一使用 Path、安全创建目录、必要时校验文件存在。

## 异步

用 **asyncio**：网络 I/O 优先异步、异步函数内避免阻塞调用、正确处理任务取消、避免不必要的并发。仅在确有收益处使用异步。

## 类型安全

处处使用类型注解、尽量避免 `Any`、显式返回类型、开启严格静态类型。代码对 **mypy / pyright** 友好。

## 测试要求（强制）

**离线单元测试**（默认）：无网络依赖、执行快、结果确定、广泛 mock 外部系统、业务逻辑高覆盖；覆盖正常 / 边界 / 失败 / 非法输入。工具：`pytest`、`pytest-mock`。

**集成测试**（仅必要时，如 HTTP API / 数据库 / 外部服务）：隔离环境、显式 marker、可选执行，例如 `uv run pytest -m integration`。离线测试始终为默认。

## README（务必生成）

`README.md` 应包含：项目概述、特性、架构概览、安装、环境配置、运行方式、CLI 示例、开发流程、测试说明、集成测试说明、项目结构、故障排查、未来扩展指引。

## Python 环境管理（uv，默认）

```bash
uv init                       # 初始化项目
uv venv && source .venv/bin/activate
uv add typer loguru pydantic httpx
uv add --dev pytest pytest-mock pytest-asyncio
uv run python -m app.main
uv run pytest
uv run pytest -m integration
uv sync                       # 同步/更新依赖
```

## 代码质量期望

可读、模块化、可测试、类型安全、可扩展、生产就绪；遵循清晰架构与关注点分离；避免过度工程、过早抽象与不必要依赖。
