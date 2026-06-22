# FastAPI 应用入口（从简，后续里程碑完善）
from __future__ import annotations
from fastapi import FastAPI

app = FastAPI(title="Graphify Agent API", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    """健康检查端点。"""
    return {"status": "ok"}
