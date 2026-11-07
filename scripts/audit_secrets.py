# -*- coding: utf-8 -*-
import os
import re
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()

suspicious_patterns = [
    re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),
    re.compile(r'ghp_[a-zA-Z0-9]{20,}'),
    re.compile(r'AKIA[0-9A-Z]{16}'),
    re.compile(r'(?:api_key|secret|password)\s*=\s*[\'"][^\'"]{8,}[\'"]', re.I),
]

found = []
for f in tracked:
    if f.endswith(('.png', '.pdf', '.mp4', '.ico', '.svg', '.jpg', '.webm', 'package-lock.json', '.bat', '.ps1')):
        continue
    p = os.path.join(ROOT, f)
    if not os.path.exists(p):
        continue
    try:
        content = open(p, 'r', encoding='utf-8', errors='ignore').read()
        for pat in suspicious_patterns:
            matches = pat.findall(content)
            for m in matches:
                if any(x in m for x in ['placeholder', 'example', '...', '0000', 'xxxx', 'change_me']):
                    continue
                found.append((f, m))
    except Exception as e:
        pass

print(f"Secret scan completed. Suspicious items found: {len(found)}")
for f, m in found:
    print(f"  {f}: {m}")
