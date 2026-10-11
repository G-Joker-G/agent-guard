#!/usr/bin/env python3
"""Agent Guard 三条演示路径的端到端脚本（直调后端 HTTP API）。

证明三条路径真实调用了后端网关/执行器，而非前端状态切换：
  A. 正常审批流：跟进任务 → 读放行 → 发邮件走审批 → 批准 → 模拟发送成功 → 审计可查
  B. 越权拦截：  导出请求 → 策略拒绝 → 执行器未执行 → 审计记录拒绝原因
  C. 急停流程：  批量操作 → 急停 → 后续动作被阻止 → 显式恢复后才能继续执行

用法：先启动后端（uvicorn app.main:app --port 8000），再运行：
    python3 scripts/demo_e2e.py [--base http://127.0.0.1:8000] [--path a|b|c|all]
仅依赖 Python 标准库。
"""
import argparse, json, sys, urllib.request, urllib.error

class API:
    def __init__(self, base):
        self.base = base.rstrip("/")
    def call(self, method, path, body=None, note=""):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                resp = json.loads(r.read().decode() or "null")
                code = r.status
        except urllib.error.HTTPError as e:
            raw = e.read().decode() or "null"
            try:
                resp = json.loads(raw)
            except ValueError:
                resp = {"detail": raw}
            code = e.code
        print(f"  {method} {path} -> {code}  {note}")
        return code, resp

def check(cond, msg):
    print(("  [OK] " if cond else "  [FAIL] ") + msg)
    if not cond:
        raise SystemExit(f"E2E 断言失败: {msg}")

def path_a(api):
    print("\n=== 路径 A：正常审批流 ===")
    api.call("POST", "/api/admin/reset", note="重置演示数据")
    code, t = api.call("POST", "/api/tasks", {"title": "客户跟进：华南贸易", "scenario": "followup"})
    tid = t["id"]
    code, plan = api.call("POST", f"/api/tasks/{tid}/plan", note="演示 Agent 生成结构化请求")
    check(isinstance(plan, list) and len(plan) == 2, "生成 2 个动作请求 (crm.read + mail.send)")
    code, adv = api.call("POST", f"/api/tasks/{tid}/advance", note="网关推进：策略评估+自动执行放行项")
    acts = {a["tool"]: a for a in adv["actions"]}
    check(acts["crm.read"]["status"] == "executed", "crm.read 被策略自动放行并真实执行")
    check(acts["crm.read"]["decision"] == "allow", "crm.read 判定为 allow")
    check(acts["mail.send"]["status"] == "needs_approval", "mail.send 进入人工审批")
    code, ap = api.call("GET", "/api/approvals?status=pending")
    mail_ap = [x for x in ap if x["action_id"] == acts["mail.send"]["id"]][0]
    check(bool((mail_ap.get("action") or {}).get("risk")), "审批单含风险说明")
    check(bool((mail_ap.get("action") or {}).get("params")), "审批单含参数摘要")
    code, dec = api.call("POST", f"/api/approvals/{mail_ap['id']}/decide",
                         {"decision": "approve", "approver": "admin", "note": "内容已审核"},
                         note="管理员批准")
    check(dec["status"] == "approved" and dec["used"] == 0, "审批单 approved 且未使用")
    code, ex = api.call("POST", f"/api/actions/{acts['mail.send']['id']}/execute",
                        note="执行已批准的动作（网关复查审批绑定）")
    check(ex["status"] == "executed", "mail.send 获批后真实执行")
    code, outbox = api.call("GET", "/api/outbox")
    mine = [m for m in outbox if m.get("action_id") == acts["mail.send"]["id"]]
    check(len(mine) == 1 and mine[0]["to_email"], "模拟发件箱产生可验证的发送记录 (DB 真实写入)")
    code, ex2 = api.call("POST", f"/api/actions/{acts['mail.send']['id']}/execute",
                         note="重复执行同一动作（幂等/防重放）")
    check(ex2["status"] == "executed", "重复执行不产生副作用（审批一次一用）")
    code, outbox2 = api.call("GET", "/api/outbox")
    check(len(outbox2) == len(outbox), "发件箱记录数未增加：无重复执行")
    code, audit = api.call("GET", f"/api/audit?task_id=%d&limit=200" % tid)
    events = {e["event"] for e in audit}
    for need in ("task.created", "action.proposed", "action.policy", "approval.created",
                 "approval.approved", "action.executed"):
        check(need in events, f"审计含事件 {need}")
    code, v = api.call("GET", "/api/audit/verify")
    check(v["ok"] is True, "审计哈希链校验通过 (checked=%s)" % v["checked"])
    print("路径 A 通过")

def path_b(api):
    print("\n=== 路径 B：越权拦截 ===")
    api.call("POST", "/api/admin/reset", note="重置演示数据")
    code, t = api.call("POST", "/api/tasks", {"title": "攻击测试：注入诱导导出", "scenario": "export_attack"})
    tid = t["id"]
    code, plan = api.call("POST", f"/api/tasks/{tid}/plan", note="演示 Agent 被注入诱导，产出导出请求")
    tools = [a["tool"] for a in plan]
    check("crm.export_all" in tools, "演示 Agent 产出了 crm.export_all 请求（含模拟诱导）")
    code, adv = api.call("POST", f"/api/tasks/{tid}/advance", note="网关策略评估")
    exp = [a for a in adv["actions"] if a["tool"] == "crm.export_all"][0]
    check(exp["status"] == "denied", "策略引擎拒绝导出请求")
    check(exp["decision"] == "deny" and bool(exp["decision_reason"]), "拒绝原因已记录")
    code, ex = api.call("POST", f"/api/actions/{exp['id']}/execute", note="尝试强行执行被拒绝的动作")
    check(ex.get("status") == "denied", "被拒绝的动作无法执行（网关幂等+执行器纵深拒绝）")
    code, outbox = api.call("GET", "/api/outbox")
    check(all(m.get("action_id") != exp["id"] for m in outbox), "无任何导出/发送副作用产生")
    code, audit = api.call("GET", f"/api/audit?task_id=%d&limit=200" % tid)
    denies = [e for e in audit if e["event"] == "action.denied"]
    check(len(denies) >= 1, "审计记录了拒绝事件")
    det = denies[0].get("detail") or {}
    if isinstance(det, str):
        try:
            det = json.loads(det)
        except ValueError:
            det = {"reason": det}
    check(bool(det.get("reason")), "审计拒绝事件含原因：%s" % det.get("reason"))
    print("路径 B 通过")

def path_c(api):
    print("\n=== 路径 C：急停流程 ===")
    api.call("POST", "/api/admin/reset", note="重置演示数据")
    code, t = api.call("POST", "/api/tasks", {"title": "批量跟进操作", "scenario": "batch"})
    tid = t["id"]
    api.call("POST", f"/api/tasks/{tid}/plan", note="生成多步批量计划")
    code, st = api.call("POST", "/api/admin/stop", {"by": "admin"}, note="管理员一键急停")
    check(st.get("emergency_stop") is True, "急停标志生效")
    code, adv = api.call("POST", f"/api/tasks/{tid}/advance", note="急停后尝试推进")
    blocked = [a for a in adv["actions"] if a["status"] == "blocked_by_stop"]
    check(len(blocked) == len(adv["actions"]) and len(blocked) > 0,
          "急停后全部未处理动作被阻止 (%d 个 blocked_by_stop)" % len(blocked))
    # 第二段：已批准动作在急停期间同样被阻止，显式恢复后可执行
    api.call("POST", "/api/admin/reset", note="重置（同时解除急停）")
    code, t2 = api.call("POST", "/api/tasks", {"title": "批量跟进操作(2)", "scenario": "batch"})
    tid2 = t2["id"]
    api.call("POST", f"/api/tasks/{tid2}/plan")
    code, adv1 = api.call("POST", f"/api/tasks/{tid2}/advance", note="先推进到等待审批")
    need = [a for a in adv1["actions"] if a["status"] == "needs_approval"]
    check(len(need) > 0, "有动作进入等待审批")
    code, ap = api.call("GET", "/api/approvals?status=pending")
    target = [x for x in ap if x["action_id"] == need[0]["id"]][0]
    api.call("POST", f"/api/approvals/{target['id']}/decide",
             {"decision": "approve", "approver": "admin"}, note="批准其中一个动作")
    api.call("POST", "/api/admin/stop", {"by": "admin"}, note="再次急停")
    code, ex = api.call("POST", f"/api/actions/{need[0]['id']}/execute", note="急停期间尝试执行已批准动作")
    check(code == 409 and ex.get("status") != "executed", "急停期间已批准动作也被阻止（执行前复查急停）")
    code, rs = api.call("POST", "/api/admin/resume", {"by": "admin"}, note="管理员显式恢复")
    check(rs.get("emergency_stop") is False, "显式恢复后急停解除")
    code, ex2 = api.call("POST", f"/api/actions/{need[0]['id']}/execute", note="恢复后执行")
    check(code == 200 and ex2.get("status") == "executed", "恢复后动作可正常执行")
    code, audit = api.call("GET", f"/api/audit?task_id=%d&limit=200" % tid2)
    events = {e["event"] for e in audit}
    check("action.blocked_stop" in events, "审计记录执行被急停阻止事件")
    code, audit_all = api.call("GET", "/api/audit?limit=200", note="全局审计（含急停/恢复事件）")
    all_events = {e["event"] for e in audit_all}
    check("stop.engaged" in all_events and "stop.released" in all_events, "审计记录急停/恢复事件")
    print("路径 C 通过")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--path", choices=["a", "b", "c", "all"], default="all")
    args = ap.parse_args()
    api = API(args.base)
    code, h = api.call("GET", "/api/health")
    check(code == 200 and h.get("ok"), "后端健康检查通过")
    if args.path in ("a", "all"): path_a(api)
    if args.path in ("b", "all"): path_b(api)
    if args.path in ("c", "all"): path_c(api)
    print("\n全部演示路径 E2E 通过：每一步均为真实后端调用。")

if __name__ == "__main__":
    main()
