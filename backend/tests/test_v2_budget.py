"""V2 成本熔断（预算守卫）回归测试。

铁律：全程零真实外部调用。测试打 127.0.0.1 的本地 stub，
"真实调用"分支用 base_url="http://api.example.com/v1" 模拟——
熔断在 _make_client 之前拦截，断言 client 永远不会被创建（monkeypatch 抛错），
因此不产生任何网络流量。
"""

import socket
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
import stub_llm_server  # noqa: E402

from app import llm_agent, llm_budget  # noqa: E402


@pytest.fixture()
def stub():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = ThreadingHTTPServer(("127.0.0.1", port), stub_llm_server.StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def _create_task(api, title="预算测试", scenario="followup"):
    r = api.post("/api/tasks", json={"title": title, "scenario": scenario})
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ---------- kill switch ----------

def test_kill_switch_route_returns_409_no_thread(api, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "fake")
    monkeypatch.setenv("LLM_KILL_SWITCH", "1")
    task_id = _create_task(api)
    r = api.post(f"/api/tasks/{task_id}/run-llm", json={"goal": "x"})
    assert r.status_code == 409
    assert r.json()["detail"] == "llm_kill_switch"
    # 不启动后台线程：任务状态应保持 created
    r = api.get(f"/api/tasks/{task_id}")
    assert r.json()["status"] == "created"


def test_kill_switch_blocks_run_llm_task_direct(api, monkeypatch, stub):
    monkeypatch.setenv("LLM_KILL_SWITCH", "1")
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "你好", base_url=stub,
                                 api_key="stub", model="stub")
    assert res["status"] == "failed"
    assert res["error"] == "llm_kill_switch"
    assert res["steps"] == 0


# ---------- 每日额度 ----------

def test_budget_exhausted_blocks_real_call_no_network(api, monkeypatch):
    """额度用尽时：base_url 非回环 → 拒绝，且绝不创建 HTTP 客户端（零网络）。"""
    monkeypatch.setenv("LLM_DAILY_MAX_CALLS", "1")
    used = llm_budget.record_call()  # 模拟已用 1 次
    assert used >= 1

    def _boom(*a, **k):
        raise AssertionError("熔断失效：不应创建任何 HTTP 客户端")

    monkeypatch.setattr(llm_agent, "_make_client", _boom)
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "测试", base_url="http://api.example.com/v1",
                                 api_key="fake-key", model="fake-model")
    assert res["status"] == "failed"
    assert res["error"] == "llm_daily_budget_exhausted"
    assert res["steps"] == 0


def test_stub_calls_not_counted(api, stub):
    """本地 stub（回环地址）不计费、不计入额度。"""
    before = llm_budget.daily_used()
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "你好", base_url=stub,
                                 api_key="stub", model="stub")
    assert res["status"] == "completed", res
    assert res["steps"] == 1
    assert llm_budget.daily_used() == before


# ---------- 单轮步数上限 ----------

def test_max_steps_env_honored(api, stub, monkeypatch):
    monkeypatch.setenv("LLM_MAX_STEPS", "1")
    task_id = _create_task(api)
    res = llm_agent.run_llm_task(task_id, "请跟进客户 1，查阅资料后发送跟进邮件",
                                 base_url=stub, api_key="stub", model="stub")
    assert res["steps"] <= 1
    assert llm_budget.max_steps() == 1


def test_invalid_env_falls_back_to_defaults(monkeypatch):
    monkeypatch.setenv("LLM_MAX_STEPS", "abc")
    monkeypatch.setenv("LLM_DAILY_MAX_CALLS", "-5")
    assert llm_budget.max_steps() == 12
    assert llm_budget.daily_limit() == 50
    assert llm_budget.kill_switch_on() is False


# ---------- 状态接口 ----------

def test_llm_status_includes_budget(api, monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    r = api.get("/api/llm/status")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False
    assert data["max_steps"] >= 1
    assert data["daily_calls_used"] >= 0
    assert data["daily_calls_limit"] >= 1
    assert data["kill_switch"] is False
    # 绝不泄露 key
    import json as _json
    assert "api_key" not in _json.dumps(data).lower()
