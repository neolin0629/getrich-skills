import json
d=json.load(open('C:/Users/Administrator/.workbuddy/skills/weekly-review/data/weekly_data.json','r',encoding='utf-8'))
for n,r in d.get('global',{}).items():
    if r:
        last = r[-1]
        c = last.get('Close', last.get('close','?'))
        print(f'{n}: {c}')
print(f'zt={d.get("zt_count")}, dt={d.get("dt_count")}')
