#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
央行公开市场买断式逆回购数据爬取脚本
爬取范围：2024-10 至最新
数据来源：http://www.pbc.gov.cn 公开市场操作公告

用法：
  python fetch_pbc_repo.py [--output-dir DIR]
  输出文件：pbc_outright_repo.csv

被 generate_charts.py 的 L_chart9_pbc_repo() 调用
"""
import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import os
import argparse
import sys

sys.stdout.reconfigure(encoding='utf-8')

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
BASE_URL = "http://www.pbc.gov.cn"

# 买断式逆回购招标公告列表页（分页）
LIST_PAGES = [
    "http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/index.html",
    "http://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125431/5492845/b0da893b-2.html",
]


def get_announcement_links():
    """获取所有招标公告链接（过滤非招标公告）"""
    links = []
    seen = set()
    for page_url in LIST_PAGES:
        try:
            r = requests.get(page_url, headers=HEADERS, timeout=15)
            r.encoding = "utf-8"
            soup = BeautifulSoup(r.text, "html.parser")
            for a in soup.find_all("a", href=True, attrs={"istitle": "true"}):
                href = a["href"]
                text = a.get_text(strip=True)
                if "买断式逆回购招标公告" not in text:
                    continue
                full_url = BASE_URL + href if href.startswith("/") else href
                if full_url in seen:
                    continue
                seen.add(full_url)
                parent = a.find_parent("li") or a.find_parent("div") or a.parent
                date_str = ""
                for span in parent.find_all("span"):
                    t = span.get_text(strip=True)
                    if re.match(r"\d{4}-\d{2}-\d{2}", t):
                        date_str = t
                        break
                links.append({"title": text, "pub_date": date_str, "url": full_url})
            print(f"[OK] {page_url} -> 累计 {len(links)} 条")
            time.sleep(0.5)
        except Exception as e:
            print(f"[WARN] {page_url}: {e}")
    return links


def parse_announcement(url, title):
    """解析单条公告正文，返回记录列表（支持多期限）"""
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.encoding = "utf-8"
        soup = BeautifulSoup(r.text, "html.parser")
        content = soup.get_text(separator="\n")

        # 操作日期
        op_date = ""
        m = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日[，,]?\s*中国人民银行将以|"
            r"(\d{4})年(\d{1,2})月(\d{1,2})日[，,]?\s*将以固定",
            content
        )
        if m:
            g = m.groups()
            if g[0]:
                op_date = f"{g[0]}-{int(g[1]):02d}-{int(g[2]):02d}"
            else:
                op_date = f"{g[3]}-{int(g[4]):02d}-{int(g[5]):02d}"

        # 多期限段：XXXX亿元 ... 期限为N个月
        terms = re.findall(r"(\d+(?:\.\d+)?)亿元.*?期限为(\d+个月|\d+天)", content)
        # 到期日
        expire_dates = re.findall(r"到期日为(\d{4})年(\d{1,2})月(\d{1,2})日", content)
        # 单次操作兜底
        single_amt = re.search(r"开展(\d+(?:\.\d+)?)亿元买断式逆回购操作", content)

        records = []
        if terms:
            for i, (amt, term) in enumerate(terms):
                exp = ""
                if i < len(expire_dates):
                    exp = f"{expire_dates[i][0]}-{int(expire_dates[i][1]):02d}-{int(expire_dates[i][2]):02d}"
                records.append({
                    "公告": title,
                    "操作日期": op_date,
                    "期限": term,
                    "金额(亿元)": float(amt),
                    "到期日": exp,
                })
        elif single_amt:
            m2 = re.search(r"期限为(\d+个月|\d+天)", content)
            term = m2.group(1) if m2 else ""
            exp = ""
            if expire_dates:
                exp = f"{expire_dates[0][0]}-{int(expire_dates[0][1]):02d}-{int(expire_dates[0][2]):02d}"
            records.append({
                "公告": title,
                "操作日期": op_date,
                "期限": term,
                "金额(亿元)": float(single_amt.group(1)),
                "到期日": exp,
            })
        else:
            records.append({
                "公告": title, "操作日期": op_date,
                "期限": "", "金额(亿元)": None, "到期日": "", "备注": "解析失败"
            })
        return records
    except Exception as e:
        return [{"公告": title, "操作日期": "", "期限": "",
                 "金额(亿元)": None, "到期日": "", "备注": str(e)}]


def fetch_and_save(output_dir=None):
    """主流程：爬取 + 解析 + 保存 CSV，返回 DataFrame"""
    print("=== 买断式逆回购数据爬取 ===")
    links = get_announcement_links()
    print(f"共 {len(links)} 条招标公告")

    all_records = []
    for i, item in enumerate(links):
        print(f"  [{i+1}/{len(links)}] {item['title']}")
        recs = parse_announcement(item["url"], item["title"])
        for r in recs:
            r["发布日期"] = item["pub_date"]
            r["链接"] = item["url"]
        all_records.extend(recs)
        time.sleep(0.3)

    df = pd.DataFrame(all_records)
    cols_order = ["公告", "发布日期", "操作日期", "期限", "金额(亿元)", "到期日"]
    cols = [c for c in cols_order if c in df.columns] + \
           [c for c in df.columns if c not in cols_order and c != "链接"]
    df = df[cols]
    df = df.sort_values("操作日期", ascending=True).reset_index(drop=True)

    # 保存
    if output_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, '..', 'data')
    os.makedirs(output_dir, exist_ok=True)

    out_path = os.path.join(output_dir, "pbc_outright_repo.csv")
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"✅ 已保存: {out_path}  ({len(df)} 条)")

    # 简单汇总
    valid = df[df["金额(亿元)"].notna()]
    print(f"\n按期限汇总:")
    print(valid.groupby("期限")["金额(亿元)"].agg(["count", "sum"])
          .rename(columns={"count": "次数", "sum": "合计(亿元)"}))
    return df


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()
    fetch_and_save(args.output_dir)


if __name__ == "__main__":
    main()
