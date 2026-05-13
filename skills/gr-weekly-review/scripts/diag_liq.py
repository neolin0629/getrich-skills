import json, os

data_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\data'
with open(os.path.join(data_dir, 'liquidity_data.json'), encoding='utf-8') as f:
    d = json.load(f)

print('=== top-level keys ===')
for k in d:
    v = d[k]
    print(f'{k}: type={type(v).__name__}')

print()
fred = d.get('fred', {})
print(f'=== fred keys: {list(fred.keys())} ===')
for k in list(fred.keys())[:5]:
    print(f'  {k}: len={len(fred[k])}, sample={fred[k][:2] if fred[k] else "EMPTY"}')

print()
sy = d.get('global_yearly', {})
print(f'=== global_yearly keys: {list(sy.keys())} ===')
for k in ['黄金', 'WTI原油', 'VIX', '美元指数']:
    v = sy.get(k, [])
    if v:
        print(f'  {k}: len={len(v)}, first={v[0]}, last={v[-1]}')

print()
shibor = d.get('shibor', [])
print(f'=== shibor: len={len(shibor)} ===')
if shibor:
    print(f'  first: {shibor[0]}')
    print(f'  last: {shibor[-1]}')
