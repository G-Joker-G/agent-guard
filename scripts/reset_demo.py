#!/usr/bin/env python3
"""一键重置演示数据：调用后端 POST /api/admin/reset。

用法：python3 scripts/reset_demo.py [--base http://127.0.0.1:8000]
仅依赖 Python 标准库。
"""
import argparse, json, urllib.request

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    args = ap.parse_args()
    req = urllib.request.Request(args.base.rstrip("/") + "/api/admin/reset",
                                 data=b"", method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        print("reset ->", r.status, r.read().decode())

if __name__ == "__main__":
    main()
