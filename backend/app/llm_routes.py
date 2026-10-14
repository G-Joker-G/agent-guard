"""真实 LLM 运行路由（V2-M2）。

main.py 以 try/except ImportError 挂载本模块的 router：
    from .llm_routes import router as llm_router
    app.include_router(llm_router)

无 key 时 POST /run-llm 返回 409（llm_not_configured），不启动任何线程；
LLM_KILL_SWITCH=1 时返回 409（llm_kill_switch），同样不启动线程。
循环内的成本熔断见 app/llm_budget.py。
"""

from __future__ import annotations

import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from . import db, llm_agent, llm_budget
from .models import Task

router = APIRouter()


class RunLLMIn(BaseModel):
    goal: str


@router.get("/api/llm/status")
def llm_status():
    """LLM 配置状态（绝不返回 key）。"""
    return llm_agent.llm_status()


@router.post("/api/tasks/{task_id}/run-llm")
def run_llm(task_id: int, body: RunLLMIn):
    """启动真实 LLM Agent 循环（后台线程）。

    无 key 时 409（llm_not_configured）；kill switch 开启时 409（llm_kill_switch）；
    任务不存在时 404。循环内的每一步推理与工具裁决
    都会写入审计，前端可通过 /api/events (SSE) 实时订阅。
    """
    # 熔断优先于配置检查：kill switch 是最强的"不许跑"信号
    if llm_budget.kill_switch_on():
        raise HTTPException(status_code=409, detail="llm_kill_switch")
    if not llm_agent.llm_configured():
        raise HTTPException(status_code=409, detail="llm_not_configured")
    session = db.SessionLocal()
    try:
        task = session.get(Task, task_id)
    finally:
        session.close()
    if task is None:
        raise HTTPException(status_code=404, detail="task not found")
    threading.Thread(
        target=llm_agent.run_llm_task, args=(task_id, body.goal), daemon=True
    ).start()
    return {"task_id": task_id, "status": "running"}
