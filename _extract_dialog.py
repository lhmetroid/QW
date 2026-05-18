import sys, re
sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

content = Path(r'd:\items\QW\claude-code-2026-05-15-dialog-table-linebreaks.html').read_text(encoding='utf-8')
rows = re.findall(r'<td class="col-time">(.*?)</td>\s*<td class="col-role">(.*?)</td>\s*<td class="col-content">(.*?)</td>', content, re.DOTALL)

for t, role, c in rows:
    c_clean = re.sub(r'<br>', '\n', c)
    c_clean = re.sub(r'<[^>]+>', '', c_clean)
    c_clean = c_clean.strip()[:400]
    print(f'[{t}] [{role}]')
    print(c_clean)
    print('===')
