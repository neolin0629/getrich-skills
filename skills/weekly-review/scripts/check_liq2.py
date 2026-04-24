import json, os
script_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\scripts'
data_dir = os.path.join(script_dir, '..', 'data')
with open(os.path.join(data_dir, 'liquidity_data.json'), encoding='utf-8') as f:
    d = json.load(f)
print('fred keys:', list(d.get('fred', {}).keys()))
for k in list(d.get('fred', {}).keys())[:3]:
    v = d['fred'][k]
    if isinstance(v, list) and v:
        print(f'  {k}: len={len(v)}, sample={v[-1]}')
print('global_yearly keys:', list(d.get('global_yearly', {}).keys()))
for k in list(d.get('global_yearly', {}).keys())[:3]:
    v = d['global_yearly'][k]
    if isinstance(v, list) and v:
        print(f'  {k}: len={len(v)}, sample={v[-1]}')
