import json, os
data_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\data'
with open(os.path.join(data_dir, 'weekly_data.json'), encoding='utf-8') as f:
    d = json.load(f)
print('keys:', list(d.keys()))
for k in ['northbound', 'margin', 'volume', 'shibor']:
    v = d.get(k)
    if v:
        print(f'{k}: len={len(v)}, sample={v[-2] if len(v)>1 else v[0]}')
    else:
        print(f'{k}: EMPTY or None')
