"""Agent Guard MCP 示例客户端（官方 mcp SDK，真实可跑）。

演示流程：
  1. 连接 /mcp/sse，发现并打印工具列表
  2. 调用 crm_read(1)            → 策略 allow，自动执行成功
  3. 调用 mail_send(...)         → 策略 needs_approval：脚本提示用户去 Web 控制台
     审批中心批准/拒绝，然后用 guard_check_status 轮询到终态
  4. 调用 crm_export_all()       → 策略 deny，被拒绝
  5. GET /api/audit 打印本次 task 的审计事件链，证明网关真实裁决

运行前：先启动后端（项目根目录 ./start-mac.sh，或 cd backend && venv/bin/python -m uvicorn app.main:app）
用法：python examples/mcp_client_demo.py [--base http://127.0.0.1:8000]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request

from mcp import ClientSession
from mcp.client.sse import sse_client

import httpx2

TERMINAL = {"executed", "failed", "denied", "rejected", "blocked_by_stop"}


def _no_proxy_client_factory(**kwargs):
    """httpx client 工厂：绕过环境代理变量。

    某些云电脑的代理环境变量会导致 httpx2 构造 Client 时 URL 解析异常；
    示例直连本地后端，不需要代理。用户在自己机器上一般不受影响。
    """
    kwargs.setdefault("trust_env", False)
    return httpx2.AsyncClient(**kwargs)


def api_get(base: str, path: str):
    with urllib.request.urlopen(base + path) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def main(base: str):
    sse_url = f"{base}/mcp/sse"
    print(f"连接 MCP: {sse_url}")
    async with sse_client(sse_url, httpx_client_factory=_no_proxy_client_factory) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. 工具发现
            tools = await session.list_tools()
            print("\n== 工具列表 ==")
            for t in tools.tools:
                print(f"  - {t.name}: {t.description}")

            # 2. allow 路径：crm_read
            print("\n== 调用 crm_read(customer_id=1) ==")
            res = await session.call_tool("crm_read", {"customer_id": 1})
            payload = json.loads(res.content[0].text)
            print(json.dumps(payload, ensure_ascii=False, indent=2)[:800])
            assert payload["decision"] == "allow" and payload["status"] == "executed", payload
            print("✓ 自动放行并执行成功")

            # 3. 审批路径：mail_send（阻塞在网关 wait 模式下等待人工决策）
            print("\n== 调用 mail_send（将阻塞等待人工审批） ==")
            print("   → 请现在打开 Web 控制台「审批中心」，找到来自 MCP 的 mail.send 审批单并 批准/拒绝")
            print("   → 本脚本会在后台轮询 guard_check_status 直到终态")
            mail_res = await session.call_tool("mail_send", {
                "customer_id": 1,
                "subject": "MCP 演示邮件",
                "body": "这是通过 MCP 网关发送的演示邮件，需经人工审批。",
                "batch": False,
            })
            mail_payload = json.loads(mail_res.content[0].text)
            action_id = mail_payload["action_id"]
            print(f"   网关返回：status={mail_payload['status']} error={mail_payload['error']}")

            # 4. 用 guard_check_status 轮询到终态
            print("\n== 轮询 guard_check_status ==")
            for _ in range(600):
                st = await session.call_tool("guard_check_status", {"action_id": action_id})
                info = json.loads(st.content[0].text)
                if info["status"] in TERMINAL:
                    print(json.dumps(info, ensure_ascii=False, indent=2)[:1200])
                    break
                time.sleep(2)
            else:
                print("轮询超时（600s），动作仍未终态")
                sys.exit(1)
            print(f"✓ mail_send 终态：{info['status']}")

            # 5. deny 路径：crm_export_all
            print("\n== 调用 crm_export_all() ==")
            exp_res = await session.call_tool("crm_export_all", {})
            exp_payload = json.loads(exp_res.content[0].text)
            print(json.dumps(exp_payload, ensure_ascii=False, indent=2)[:600])
            assert exp_payload["decision"] == "deny", exp_payload
            print("✓ 策略拒绝，未执行")

            task_id = mail_payload["task_id"]

    # 6. 审计验证：origin=mcp 的动作在 /api/audit 有完整事件链
    print(f"\n== 审计事件链（task_id={task_id}） ==")
    events = api_get(base, f"/api/audit?task_id={task_id}")
    kinds = [e["event"] for e in events]
    for e in events:
        print(f"  [{e['id']}] {e['event']} actor={e.get('actor')}")
    for required in ("action.proposed", "action.policy", "approval.created"):
        assert required in kinds, f"缺失审计事件: {required}"
    print("✓ 审计链完整（proposed → policy → approval.created …）")
    print("\n演示完成：外部 Agent 的每一次调用都经过网关裁决。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Guard MCP 演示客户端")
    parser.add_argument("--base", default="http://127.0.0.1:8000",
                        help="后端基地址（默认 http://127.0.0.1:8000）")
    args = parser.parse_args()
    import asyncio
    asyncio.run(main(args.base.rstrip("/")))
