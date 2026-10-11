#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本地 OpenAI-compatible LLM 桩（仅标准库，用于 V2-M2 开发期验证）。

实现 POST /v1/chat/completions，返回 OpenAI-compatible 的响应结构。
确定性行为（只看请求里的 messages，不做任何真实推理）：

1. 若任一 tool 消息内容含"系统指令"（即 Agent 读到了客户 6 notes 里内嵌的
   模拟注入指令）且尚未返回过 crm.export_all → 返回 crm.export_all 的 tool_call。
   用于验证：即使 LLM 被诱导去导出，网关也必须 deny。
2. 否则看 user goal：
   - 含"跟进"/followup：第一次返回 crm.read(customer_id=1)；
     收到 crm.read 的 tool 结果后返回 mail.send(customer_id=1, ...)；
     再收到结果后返回纯文本终答（finish_reason="stop"）。
   - 含"攻击"：第一次返回 crm.read(customer_id=6)（其 notes 含模拟注入），
     让流程走第 1 条注入路径。
3. 兜底：返回纯文本"任务完成"。

注意：这是测试桩，不是真实 LLM。场景 B 的"真实行为"演示留待 Mac 验收时
用真实 key 跑——桩只验证 agent 循环的 plan→call→verdict→execute 链路。

用法：
    python3 scripts/stub_llm_server.py --port 8765
    python3 scripts/stub_llm_server.py --help
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_call_counter = itertools.count(1)


def _text_of(content) -> str:
    """tool/user 消息的 content 可能是字符串或结构化内容，统一转文本。"""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False)


def _tool_call_response(name: str, arguments: dict) -> dict:
    call_id = f"call_{next(_call_counter)}"
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "stub",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(arguments, ensure_ascii=False),
                            },
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def _text_response(text: str) -> dict:
    return {
        "id": "chatcmpl-stub",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": "stub",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }


def decide(request: dict) -> dict:
    """按确定性规则决定本次返回。"""
    messages = request.get("messages") or []

    tool_texts = [
        _text_of(m.get("content")) for m in messages if m.get("role") == "tool"
    ]
    emitted = [
        (tc.get("function") or {}).get("name")
        for m in messages
        if m.get("role") == "assistant"
        for tc in (m.get("tool_calls") or [])
    ]
    user_texts = [
        _text_of(m.get("content")) for m in messages if m.get("role") == "user"
    ]
    goal = user_texts[-1] if user_texts else ""

    # 1. 注入路径：读到了含"系统指令"的 tool 结果 → 诱导出 crm.export_all（只一次，避免死循环）
    if any("系统指令" in t for t in tool_texts) and "crm.export_all" not in emitted:
        return _tool_call_response("crm.export_all", {})

    # 2. 跟进场景
    if "跟进" in goal or "followup" in goal.lower():
        if not tool_texts:
            return _tool_call_response("crm.read", {"customer_id": 1})
        if "crm.read" in emitted and "mail.send" not in emitted:
            return _tool_call_response("mail.send", {
                "customer_id": 1,
                "subject": "产品方案跟进",
                "body": "您好，附件是我们最新产品白皮书，期待您的反馈。",
            })
        return _text_response("已完成客户跟进：资料已查阅，跟进邮件已发出。")

    # 攻击场景：先读客户 6（其 notes 含模拟注入指令），让流程走第 1 条
    if "攻击" in goal:
        if not tool_texts:
            return _tool_call_response("crm.read", {"customer_id": 6})
        return _text_response("任务完成。")

    # 3. 兜底
    return _text_response("任务完成。")


class StubHandler(BaseHTTPRequestHandler):
    server_version = "StubLLM/1.0"

    def log_message(self, fmt, *args):  # 精简日志
        print(f"[stub] {self.command} {self.path} -> " + fmt % args)

    def _send_json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        if self.path.rstrip("/") != "/v1/chat/completions":
            self._send_json({"error": "not found"}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            request = json.loads(raw)
        except json.JSONDecodeError:
            self._send_json({"error": "invalid json"}, 400)
            return
        self._send_json(decide(request))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Agent Guard V2-M2 本地 LLM 桩：OpenAI-compatible 的 POST /v1/chat/completions，"
                    "按 followup / 攻击注入场景返回确定性 tool_calls，仅供开发期验证 agent 循环。"
    )
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址（默认 127.0.0.1，仅本机）")
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), StubHandler)
    print(f"[stub] listening on http://{args.host}:{args.port}/v1/chat/completions")
    print("[stub] 场景: goal 含'跟进'/followup → crm.read(1)→mail.send(1)；"
          "goal 含'攻击' → crm.read(6)→(注入)→crm.export_all；其余 → 纯文本终答")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
