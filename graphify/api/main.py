# FastAPI 应用入口（从简，后续里程碑完善）
from __future__ import annotations
from fastapi import FastAPI
from graphify.config import apply_proxy_policy

# API 入口统一应用代理策略（默认绕过不稳定的系统代理，全部直连）
apply_proxy_policy()

app = FastAPI(title="Graphify Agent API", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    """健康检查端点。"""
    return {"status": "ok"}
