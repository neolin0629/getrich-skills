"""
周复盘完整流水线
Step 0: 确认时间区间（由主Agent在对话中完成，不在此脚本中执行）
Step 1-3: 数据采集
Step 4-6: 图表生成
Step 7-9: HTML报告生成

用法（由主Agent调用，日期由对话确认后传入）：
  python run_pipeline.py --start 20260420 --end 20260424

⚠️ 注意：日期必须是YYYYMMDD格式，且start/end必须是实际交易日。
  运行前需先用 ak.tool_trade_date_hist_sina() 验证是否为交易日。
"""
import subprocess
import sys
import os
import argparse
from datetime import datetime

parser = argparse.ArgumentParser(description='周复盘流水线')
parser.add_argument('--start', help='开始日期 YYYYMMDD（本周一，需为实际交易日）')
parser.add_argument('--end', help='结束日期 YYYYMMDD（本周五，需为实际交易日）')
args = parser.parse_args()

if not args.start or not args.end:
    print("❌ 错误：必须指定 --start 和 --end 参数（格式：YYYYMMDD）")
    print("   例如：python run_pipeline.py --start 20260420 --end 20260424")
    print("   ⚠️ 运行前请先用 ak.tool_trade_date_hist_sina() 确认这两个日期是否为实际交易日")
    sys.exit(1)

start_fmt = f"{args.start[:4]}-{args.start[4:6]}-{args.start[6:]}"
end_fmt = f"{args.end[:4]}-{args.end[4:6]}-{args.end[6:]}"

print("=" * 60)
print(f"周复盘数据采集")
print(f"  确认时间窗口：{start_fmt} ~ {end_fmt}")
print("=" * 60)

result = subprocess.run(
    [sys.executable, "fetch_data.py", "--start", start_fmt, "--end", end_fmt],
    capture_output=True, text=True, encoding="utf-8",
    cwd=os.path.dirname(os.path.abspath(__file__)) + "\\scripts"
)
print(result.stdout)
if result.stderr:
    print("STDERR:", result.stderr)

# Step 4-6: 图表生成
print("\n" + "=" * 60)
print("图表生成")
print("=" * 60)
result2 = subprocess.run(
    [sys.executable, "generate_charts_mpl.py"],
    capture_output=True, text=True, encoding="utf-8",
    cwd=os.path.dirname(os.path.abspath(__file__)) + "\\scripts"
)
print(result2.stdout)
if result2.stderr:
    print("STDERR:", result2.stderr)

# Step 7-9: HTML报告生成
print("\n" + "=" * 60)
print("HTML报告生成")
print("=" * 60)
result3 = subprocess.run(
    [sys.executable, "build_report_v2.py"],
    capture_output=True, text=True, encoding="utf-8",
    cwd=os.path.dirname(os.path.abspath(__file__)) + "\\scripts"
)
print(result3.stdout)
if result3.stderr:
    print("STDERR:", result3.stderr)