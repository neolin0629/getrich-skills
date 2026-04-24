import os, json

# 读fetch_data.py看FRED是怎么调的
script_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\scripts'
with open(os.path.join(script_dir, 'fetch_data.py'), encoding='utf-8') as f:
    content = f.read()

# 找FRED相关代码
import re
fred_section = re.search(r'#.*FRED|fred|FRED', content, re.IGNORECASE)
lines = content.split('\n')
for i, l in enumerate(lines):
    if 'fred' in l.lower() or 'FRED' in l or 'WALNAL' in l or '欧洲央行' in l or '日央行' in l:
        print(f'{i+1}: {l}')
