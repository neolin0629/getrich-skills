import json, os
script_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\scripts'
data_dir = os.path.join(script_dir, '..', 'data')
with open(os.path.join(data_dir, 'liquidity_data.json'), encoding='utf-8') as f:
    d = json.load(f)
print('keys:', list(d.keys()))
for k in list(d.keys())[:5]:
    v = d[k]
    print(f'{k}: type={type(v).__name__}')
    if isinstance(v, list) and v:
        print(f'  sample[0]: {v[0]}')
