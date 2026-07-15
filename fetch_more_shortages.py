"""
从 FDA Drug Shortages 公开数据获取更多历史短缺事件，补充仿真数据集。
使用 openFDA API: https://api.fda.gov/drug/shortage.json
"""
import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
from datetime import datetime

OUTPUT_FILE = "data/fda_shortage_additional.json"

def fetch_fda_shortages(limit: int = 100, skip: int = 0):
    """从 openFDA API 获取药品短缺数据"""
    base_url = "https://api.fda.gov/drug/shortage.json"
    params = {
        "limit": limit,
        "skip": skip,
    }
    url = base_url + "?" + urllib.parse.urlencode(params)
    print(f"  Fetching: {url[:80]}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as e:
        print(f"  Error: {e}")
        return None


def fetch_fda_shortage_by_reason(reason_category: str = "Manufacturing%2FQuality"):
    """按原因类别过滤"""
    base_url = "https://api.fda.gov/drug/shortage.json"
    search = f'reason_for_shortage:"{reason_category}"'
    params = {
        "search": search,
        "limit": 100,
    }
    url = base_url + "?" + urllib.parse.urlencode(params)
    print(f"  Fetching shortage by reason: {reason_category}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data
    except Exception as e:
        print(f"  Error: {e}")
        return None


def main():
    print("=== FDA Drug Shortage Data Collection ===")
    all_results = []

    # 方法 1: 直接获取 shortages
    print("\n[1] Fetching recent shortages (limit=100)...")
    data = fetch_fda_shortages(limit=100, skip=0)
    if data and "results" in data:
        records = data["results"]
        print(f"  Got {len(records)} records")
        # 过滤有记录的
        for r in records:
            shortage = {
                "source": "openfda",
                "generic_name": r.get("generic_name", ""),
                "proprietary_name": r.get("proprietary_name", r.get("generic_name", "")),
                "company": r.get("company_name", ""),
                "reason": r.get("reason_for_shortage", ""),
                "status": r.get("status", ""),
                "shortage_start": r.get("shortage_start_date", ""),
                "shortage_end": r.get("shortage_end_date", ""),
                "discontinuation_date": r.get("discontinuation_date", ""),
                "dosage_form": r.get("dosage_form", ""),
                "application_number": r.get("application_number", ""),
                "therapeutic_category": r.get("therapeutic_category", ""),
            }
            all_results.append(shortage)
        print(f"  Total so far: {len(all_results)}")
    else:
        print("  No results or API error")

    # 获取更多
    print("\n[2] Fetching more (skip=100)...")
    data2 = fetch_fda_shortages(limit=100, skip=100)
    if data2 and "results" in data2:
        for r in data2["results"]:
            shortage = {
                "source": "openfda",
                "generic_name": r.get("generic_name", ""),
                "company": r.get("company_name", ""),
                "reason": r.get("reason_for_shortage", ""),
                "status": r.get("status", ""),
                "shortage_start": r.get("shortage_start_date", ""),
                "shortage_end": r.get("shortage_end_date", ""),
                "dosage_form": r.get("dosage_form", ""),
                "therapeutic_category": r.get("therapeutic_category", ""),
            }
            all_results.append(shortage)
        print(f"  Total so far: {len(all_results)}")

    # 统计原因分布
    reason_counts = {}
    for r in all_results:
        reason = r.get("reason", "Unknown")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

    print("\n=== Reason for Shortage Distribution ===")
    for reason, count in sorted(reason_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {reason}: {count}")

    # 过滤出制造/质量和监管行动类
    mfg_reasons = [r for r in all_results if any(
        kw in r.get("reason", "").lower() for kw in
        ["manufactur", "quality", "recall", "gmp", "regulatory", "inspection"]
    )]
    print(f"\nManufacturing/Regulatory related: {len(mfg_reasons)} / {len(all_results)}")

    # 保存
    output = {
        "total": len(all_results),
        "manufacturing_regulatory": len(mfg_reasons),
        "reason_distribution": reason_counts,
        "shortages": all_results,
        "mfg_regulatory_shortages": mfg_reasons,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved to {OUTPUT_FILE}")

    # 打印几个代表性案例
    print("\n=== Sample Manufacturing/Quality Shortages ===")
    for r in mfg_reasons[:10]:
        print(f"  {r['generic_name'][:40]} | {r['company'][:30]} | {r['shortage_start']} | {r['reason'][:40]}")


if __name__ == "__main__":
    main()
