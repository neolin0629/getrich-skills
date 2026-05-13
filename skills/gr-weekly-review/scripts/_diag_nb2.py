import json, os, sys
sys.stdout.reconfigure(encoding='utf-8')
wd = json.load(open('C:/Users/Administrator/.workbuddy/skills/weekly-review/data/weekly_data.json', encoding='utf-8'))
nb = wd.get('northbound', [])

valid = [r for r in nb if r.get('历史累计净买额') is not None and str(r.get('历史累计净买额')) != 'nan']
valid = sorted(valid, key=lambda x: x.get('日期', ''))
print(f'历史累计净买额有效记录: {len(valid)}')
print('最近10条:')
for r in valid[-10:]:
    print(f"  {r.get('日期')} 累计={r.get('历史累计净买额')}")

# 用累计计算日净买额 = 今日累计 - 昨日累计
print('\n用累计差值计算日净买额:')
for i in range(1, min(5, len(valid))):
    today_val = valid[-i].get('历史累计净买额')
    yesterday_val = valid[-i-1].get('历史累计净买额')
    diff = today_val - yesterday_val
    print(f"  {valid[-i].get('日期')} 净买={diff:.2f}亿 (累计{today_val} - 前日{yesterday_val})")
