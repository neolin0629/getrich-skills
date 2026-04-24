import json, os, pandas as pd

data_dir = r'C:\Users\Administrator\.workbuddy\skills\weekly-review\data'
with open(os.path.join(data_dir, 'weekly_data.json'), encoding='utf-8') as f:
    d = json.load(f)

# 北向资金：看哪几列有数据
nb = d.get('northbound', [])
if nb:
    df = pd.DataFrame(nb)
    print('northbound columns:', list(df.columns))
    # 非空统计
    for col in df.columns:
        non_null = df[col].notna().sum()
        if non_null > 0:
            print(f'  {col}: {non_null}/{len(df)} non-null, sample={df[col].dropna().iloc[-1] if not df[col].dropna().empty else "N/A"}')

print()
# margin: check
mg = d.get('margin', [])
if mg:
    df_m = pd.DataFrame(mg)
    print('margin columns:', list(df_m.columns))
    print('  last 3:', df_m.tail(3)[['信用交易日期','融资余额','融资融券余额']].to_dict('records'))
