# -*- coding: utf-8 -*-
"""
Agent Guard - 商业计划书 PDF 生成器
使用 Python 读取 docs/BUSINESS_PLAN.md，渲染为精美 HTML 并调用系统 Edge Headless 导出高保真 PDF。
"""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
BP_MD = ROOT_DIR / "docs" / "BUSINESS_PLAN.md"
OUTPUT_HTML = ROOT_DIR / "docs" / "BUSINESS_PLAN_PRINT.html"
OUTPUT_PDF = ROOT_DIR / "docs" / "Agent_Guard_商业计划书.pdf"

EDGE_PATHS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]


def md_to_html(md_text: str) -> str:
    # 基础 Markdown 解析转换
    lines = md_text.splitlines()
    html_lines = []
    in_table = False
    in_code = False
    code_lang = ""
    code_block = []

    for line in lines:
        # Code block
        if line.startswith("```"):
            if not in_code:
                in_code = True
                code_lang = line[3:].strip()
                code_block = []
            else:
                in_code = False
                escaped = "\n".join(code_block).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                html_lines.append(f'<pre class="code-block {code_lang}"><code>{escaped}</code></pre>')
            continue

        if in_code:
            code_block.append(line)
            continue

        # Table
        if line.strip().startswith("|") and line.strip().endswith("|"):
            cells = [c.strip() for c in line.strip()[1:-1].split("|")]
            if all(set(c) <= {"-", ":"} for c in cells):
                continue  # separator line
            if not in_table:
                in_table = True
                html_lines.append('<div class="table-container"><table><thead><tr>')
                for c in cells:
                    html_lines.append(f"<th>{inline_format(c)}</th>")
                html_lines.append("</tr></thead><tbody>")
            else:
                html_lines.append("<tr>")
                for c in cells:
                    html_lines.append(f"<td>{inline_format(c)}</td>")
                html_lines.append("</tr>")
            continue
        elif in_table:
            in_table = False
            html_lines.append("</tbody></table></div>")

        stripped = line.strip()
        if not stripped:
            continue

        # Headings
        if stripped.startswith("# "):
            html_lines.append(f'<h1 class="main-title">{inline_format(stripped[2:])}</h1>')
        elif stripped.startswith("## "):
            html_lines.append(f'<h2 class="section-title">{inline_format(stripped[3:])}</h2>')
        elif stripped.startswith("### "):
            html_lines.append(f'<h3 class="subsection-title">{inline_format(stripped[4:])}</h3>')
        elif stripped.startswith("#### "):
            html_lines.append(f'<h4 class="sub-subsection-title">{inline_format(stripped[5:])}</h4>')
        elif stripped.startswith("> "):
            html_lines.append(f'<div class="callout"><p>{inline_format(stripped[2:])}</p></div>')
        elif stripped.startswith("- "):
            html_lines.append(f'<li class="list-item">{inline_format(stripped[2:])}</li>')
        elif re.match(r"^\d+\.\s", stripped):
            content = re.sub(r"^\d+\.\s", "", stripped)
            html_lines.append(f'<li class="ordered-item">{inline_format(content)}</li>')
        elif stripped == "---":
            html_lines.append('<hr class="divider" />')
        else:
            html_lines.append(f"<p>{inline_format(stripped)}</p>")

    if in_table:
        html_lines.append("</tbody></table></div>")

    return "\n".join(html_lines)


def inline_format(text: str) -> str:
    # 粗体
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    # 斜体
    text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
    # 行内代码
    text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
    # 链接
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" target="_blank">\1</a>', text)
    return text


def build_full_html(body_html: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Agent Guard 商业计划书 - 易星衍</title>
<style>
@page {{
    size: A4;
    margin: 18mm 18mm 18mm 18mm;
    @bottom-center {{
        content: counter(page);
        font-size: 9pt;
        color: #718096;
    }}
}}

* {{
    box-sizing: border-box;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    color: #1a202c;
    background-color: #ffffff;
    line-height: 1.65;
    font-size: 10.5pt;
    margin: 0;
    padding: 0;
}}

/* 封面设计 */
.cover-page {{
    page-break-after: always;
    min-height: 90vh;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    padding: 40px 10px 20px 10px;
}}

.cover-header {{
    border-bottom: 2px solid #0f172a;
    padding-bottom: 20px;
}}

.cover-badge {{
    display: inline-block;
    background: #0f172a;
    color: #ffffff;
    font-size: 9pt;
    font-weight: 700;
    padding: 4px 12px;
    border-radius: 4px;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 15px;
}}

.cover-title {{
    font-size: 28pt;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.2;
    margin: 10px 0;
    letter-spacing: -0.02em;
}}

.cover-subtitle {{
    font-size: 14pt;
    color: #475569;
    font-weight: 500;
    margin-top: 10px;
    line-height: 1.4;
}}

.cover-pills {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 25px;
}}

.cover-pill {{
    background: #f1f5f9;
    color: #0f172a;
    border: 1px solid #cbd5e1;
    font-size: 8.5pt;
    padding: 4px 10px;
    border-radius: 9999px;
    font-weight: 600;
}}

.cover-body {{
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 5px solid #2563eb;
    border-radius: 6px;
    padding: 24px;
    margin: 40px 0;
}}

.cover-body-title {{
    font-size: 12pt;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 12px;
}}

.cover-body-text {{
    color: #334155;
    font-size: 10pt;
    line-height: 1.6;
    margin: 0;
}}

.cover-footer {{
    border-top: 1px solid #e2e8f0;
    padding-top: 20px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}}

.founder-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 16px 20px;
    max-width: 420px;
}}

.founder-title {{
    font-size: 8.5pt;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}

.founder-name {{
    font-size: 13pt;
    font-weight: 800;
    color: #0f172a;
    margin: 4px 0;
}}

.founder-role {{
    font-size: 9pt;
    color: #2563eb;
    font-weight: 600;
}}

.founder-link {{
    font-size: 8.5pt;
    color: #64748b;
    text-decoration: none;
    margin-top: 6px;
    display: block;
}}

.meta-info {{
    text-align: right;
    font-size: 8.5pt;
    color: #64748b;
    line-height: 1.5;
}}

/* 正文样式 */
h1.main-title {{
    font-size: 20pt;
    font-weight: 800;
    color: #0f172a;
    margin-top: 30px;
    margin-bottom: 15px;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 8px;
    page-break-after: avoid;
}}

h2.section-title {{
    font-size: 13.5pt;
    font-weight: 700;
    color: #0f172a;
    margin-top: 24px;
    margin-bottom: 10px;
    padding-left: 8px;
    border-left: 4px solid #2563eb;
    page-break-after: avoid;
}}

h3.subsection-title {{
    font-size: 11pt;
    font-weight: 700;
    color: #1e293b;
    margin-top: 16px;
    margin-bottom: 6px;
    page-break-after: avoid;
}}

h4.sub-subsection-title {{
    font-size: 10pt;
    font-weight: 700;
    color: #334155;
    margin-top: 12px;
    margin-bottom: 4px;
}}

p {{
    margin: 6px 0;
    text-align: justify;
    line-height: 1.6;
}}

strong {{
    color: #0f172a;
    font-weight: 700;
}}

code {{
    font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace;
    font-size: 8.5pt;
    background: #f1f5f9;
    color: #0f172a;
    padding: 2px 5px;
    border-radius: 3px;
    border: 1px solid #e2e8f0;
}}

pre.code-block {{
    background: #0f172a;
    color: #e2e8f0;
    padding: 12px 14px;
    border-radius: 6px;
    font-size: 8pt;
    line-height: 1.45;
    overflow-x: auto;
    margin: 10px 0;
    page-break-inside: avoid;
}}

pre.code-block code {{
    background: transparent;
    color: inherit;
    border: none;
    padding: 0;
}}

.callout {{
    background: #f8fafc;
    border-left: 4px solid #2563eb;
    padding: 10px 14px;
    border-radius: 0 4px 4px 0;
    margin: 12px 0;
    color: #334155;
    font-size: 9.5pt;
    page-break-inside: avoid;
}}

.table-container {{
    margin: 14px 0;
    page-break-inside: avoid;
}}

table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    line-height: 1.4;
}}

th {{
    background: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
    text-align: left;
    padding: 7px 9px;
    border: 1px solid #cbd5e1;
}}

td {{
    padding: 6px 9px;
    border: 1px solid #e2e8f0;
    color: #334155;
}}

tr:nth-child(even) td {{
    background: #f8fafc;
}}

ul, ol {{
    margin: 6px 0;
    padding-left: 20px;
}}

li.list-item, li.ordered-item {{
    margin: 3px 0;
    line-height: 1.5;
}}

hr.divider {{
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 20px 0;
}}

a {{
    color: #2563eb;
    text-decoration: none;
}}

a:hover {{
    text-decoration: underline;
}}

/* 打印优化 */
@media print {{
    body {{
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
    }}
    .no-print {{
        display: none;
    }}
}}
</style>
</head>
<body>

<!-- 独立封面 -->
<div class="cover-page">
    <div class="cover-header">
        <span class="cover-badge">MINMAX 粤港澳大湾区创客 AI Agent 黑客松挑战赛</span>
        <h1 class="cover-title">Agent Guard</h1>
        <div class="cover-subtitle">企业级 AI Agent 可信执行与安全控制平台 · 商业计划书</div>
        <div class="cover-pills">
            <span class="cover-pill">执行控制层 Reference Monitor</span>
            <span class="cover-pill">三态自适应策略引擎</span>
            <span class="cover-pill">密码学 scope_hash 参数绑定</span>
            <span class="cover-pill">一键人工急停 Kill Switch</span>
            <span class="cover-pill">原生标准 MCP 协议支持</span>
            <span class="cover-pill">防篡改审计哈希链</span>
        </div>
    </div>

    <div class="cover-body">
        <div class="cover-body-title">【核心立论】智能的供给，必须与执行的权力彻底分开</div>
        <p class="cover-body-text">
            “We need to separate the supply of intelligence from the authority over it.”<br>
            大模型时代，企业不敢向 Agent 放权调用业务系统，根本症结在于缺乏独立于模型的执行安全网关。Agent Guard 借鉴经典计算机安全体系，在模型外部筑起物理隔离防线，打造企业敢用、好用、可溯源的 AI Agent 基础设施。
        </p>
    </div>

    <div class="cover-footer">
        <div class="founder-card">
            <div class="founder-title">创始人 / Founder</div>
            <div class="founder-name">易星衍 (YIXINGYAN)</div>
            <div class="founder-role">AI-Native Builder ｜ 企业 AI 落地 · AI 原生构建 · 出海数字基础设施</div>
            <a class="founder-link" href="https://yixingyan.com/">个人品牌：https://yixingyan.com/</a>
            <a class="founder-link" href="https://blog.yixingyan.com/">思想博客：https://blog.yixingyan.com/</a>
        </div>
        <div class="meta-info">
            <div><strong>赛事</strong>：MINMAX 粤港澳大湾区创客 AI Agent 黑客松</div>
            <div><strong>版本</strong>：V2.0 商业计划书正式版</div>
            <div><strong>日期</strong>：2026 年 11 月</div>
            <div><strong>密级</strong>：商业计划书 (公开评审)</div>
        </div>
    </div>
</div>

<!-- 正文内容 -->
<div class="doc-body">
{body_html}
</div>

</body>
</html>
"""


def main():
    if not BP_MD.exists():
        print(f"Error: {BP_MD} not found!")
        sys.exit(1)

    print(f"[--] 读取 Markdown 文件: {BP_MD}")
    md_text = BP_MD.read_text(encoding="utf-8")

    print("[--] 转换为专业打印排版 HTML...")
    body_html = md_to_html(md_text)
    full_html = build_full_html(body_html)

    OUTPUT_HTML.write_text(full_html, encoding="utf-8")
    print(f"[OK] HTML 排版文件生成完成: {OUTPUT_HTML}")

    # 寻找 Edge 浏览器
    edge_bin = None
    for p in EDGE_PATHS:
        if os.path.exists(p):
            edge_bin = p
            break

    if not edge_bin:
        print("[警告] 未找到 Microsoft Edge，无法直接调用 Headless 打印 PDF。")
        print(f"请在浏览器中打开 {OUTPUT_HTML}，按 Ctrl+P 另存为 PDF 即可。")
        return

    print(f"[--] 找到 Edge 引擎: {edge_bin}")
    print(f"[--] 正在渲染高保真 PDF: {OUTPUT_PDF} ...")

    cmd = [
        edge_bin,
        "--headless",
        "--disable-gpu",
        "--run-all-compositor-stages-before-draw",
        f"--print-to-pdf={OUTPUT_PDF}",
        "--no-pdf-header-footer",
        str(OUTPUT_HTML.resolve()),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0 and OUTPUT_PDF.exists():
        size_kb = OUTPUT_PDF.stat().st_size / 1024
        print(f"[OK] 成功生成商业计划书 PDF: {OUTPUT_PDF} ({size_kb:.1f} KB)")
    else:
        print(f"[错误] Edge 打印失败: {res.stderr}")


if __name__ == "__main__":
    main()
