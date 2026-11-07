# -*- coding: utf-8 -*-
import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DEMO_GUIDE_MD = ROOT_DIR / "docs" / "DEMO_GUIDE.md"
OUTPUT_HTML = ROOT_DIR / "docs" / "DEMO_GUIDE_PRINT.html"
OUTPUT_PDF = ROOT_DIR / "docs" / "Agent_Guard_产品Demo与评委试用指南.pdf"

EDGE_BIN = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

# 借用 build_bp_pdf 中的解析函数
from build_bp_pdf import md_to_html

md_text = DEMO_GUIDE_MD.read_text(encoding="utf-8")
body_html = md_to_html(md_text)

full_html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Agent Guard 产品 Demo 与评委极速试用指南 - 易星衍</title>
<style>
@page {{
    size: A4;
    margin: 16mm 16mm 16mm 16mm;
    @bottom-center {{
        content: counter(page);
        font-size: 8.5pt;
        color: #718096;
    }}
}}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    color: #1e293b;
    line-height: 1.6;
    font-size: 10pt;
    margin: 0;
}}
.header-badge {{
    display: inline-block;
    background: #0f172a;
    color: #fff;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 8pt;
    font-weight: 700;
    margin-bottom: 8px;
}}
h1.main-title {{
    font-size: 18pt;
    color: #0f172a;
    margin: 0 0 10px 0;
    border-bottom: 2px solid #2563eb;
    padding-bottom: 6px;
}}
h2.section-title {{
    font-size: 12pt;
    color: #0f172a;
    margin-top: 18px;
    border-left: 4px solid #2563eb;
    padding-left: 8px;
}}
h3.subsection-title {{
    font-size: 10.5pt;
    color: #334155;
    margin-top: 12px;
}}
code {{
    font-family: Consolas, monospace;
    background: #f1f5f9;
    padding: 2px 4px;
    border-radius: 3px;
    font-size: 8.5pt;
}}
pre.code-block {{
    background: #0f172a;
    color: #f8fafc;
    padding: 10px 12px;
    border-radius: 6px;
    font-size: 8pt;
    line-height: 1.4;
}}
pre.code-block code {{ background: transparent; color: inherit; padding: 0; }}
.callout {{
    background: #f8fafc;
    border-left: 4px solid #2563eb;
    padding: 8px 12px;
    margin: 10px 0;
    border-radius: 0 4px 4px 0;
}}
table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; margin: 10px 0; }}
th {{ background: #f1f5f9; padding: 6px 8px; border: 1px solid #cbd5e1; text-align: left; }}
td {{ padding: 5px 8px; border: 1px solid #e2e8f0; }}
tr:nth-child(even) td {{ background: #f8fafc; }}
li {{ margin: 3px 0; }}
hr {{ border: 0; height: 1px; background: #e2e8f0; margin: 16px 0; }}
</style>
</head>
<body>
<div class="header-badge">MINMAX 粤港澳大湾区创客 AI Agent 黑客松 · 评审专享</div>
{body_html}
</body>
</html>
"""

OUTPUT_HTML.write_text(full_html, encoding="utf-8")

cmd = [
    EDGE_BIN,
    "--headless",
    "--disable-gpu",
    "--run-all-compositor-stages-before-draw",
    f"--print-to-pdf={OUTPUT_PDF}",
    "--no-pdf-header-footer",
    str(OUTPUT_HTML.resolve()),
]

res = subprocess.run(cmd, capture_output=True, text=True)
if res.returncode == 0 and OUTPUT_PDF.exists():
    print(f"[OK] 成功生成 Demo 指南 PDF: {OUTPUT_PDF}")
else:
    print(f"[错误] 生成失败: {res.stderr}")
