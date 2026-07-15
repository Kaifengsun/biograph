"""
FDA 公开 API 数据获取器
=======================
从 OpenFDA 获取补充数据，增强核心数据集：
- Drug Enforcement (召回事件)
- Drug Labels (药品说明书关键信息)
- Drug Adverse Events (不良事件报告)

注意：核心图谱可在离线模式下通过 core_data.py 直接构建，
      本模块用于在线增强，获取更多真实数据。
"""

import requests
import pandas as pd
import time
import json
import os
from typing import Optional, Dict, List
from . import config


class FDADataFetcher:
    """FDA OpenAPI 数据获取器"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PharmaKG-Research/1.0 (Academic Use)'
        })
        # 确保不走代理
        self.session.trust_env = False

    def _safe_get(self, url: str, params: dict = None) -> Optional[dict]:
        """安全的 GET 请求"""
        for attempt in range(config.FDA_MAX_RETRIES):
            try:
                resp = self.session.get(
                    url,
                    params=params,
                    timeout=config.FDA_TIMEOUT
                )
                if resp.status_code == 200:
                    return resp.json()
                elif resp.status_code == 404:
                    return None
                else:
                    print(f"  ⚠️  HTTP {resp.status_code}, 第 {attempt+1} 次重试...")
            except requests.exceptions.RequestException as e:
                print(f"  ⚠️  请求失败: {str(e)[:60]}, 第 {attempt+1} 次重试...")
            time.sleep(config.FDA_REQUEST_DELAY * (attempt + 1))
        return None

    # ============================================================
    #  Drug Enforcement (药品召回事件)
    # ============================================================
    def fetch_drug_enforcement(self, drug_name: str, limit: int = 10) -> List[Dict]:
        """
        获取药品召回事件
        
        Args:
            drug_name: 药品通用名
            limit: 最大返回记录数
        
        Returns:
            召回事件列表
        """
        params = {
            "search": f'openfda.generic_name:"{drug_name}"',
            "limit": limit,
            "sort": "report_date:desc"
        }

        data = self._safe_get(config.FDA_DRUG_ENFORCEMENT_API, params)
        if data and "results" in data:
            events = []
            for r in data["results"]:
                events.append({
                    "drug_name": drug_name,
                    "recall_number": r.get("recall_number", ""),
                    "reason": r.get("reason_for_recall", ""),
                    "classification": r.get("classification", ""),
                    "status": r.get("status", ""),
                    "recalling_firm": r.get("recalling_firm", ""),
                    "report_date": r.get("report_date", ""),
                    "city": r.get("city", ""),
                    "country": r.get("country", ""),
                })
            return events
        return []

    # ============================================================
    #  Drug Labels (药品说明书)
    # ============================================================
    def fetch_drug_label(self, drug_name: str) -> Optional[Dict]:
        """
        获取药品说明书关键信息（相互作用、警告等）
        
        Args:
            drug_name: 药品通用名
        
        Returns:
            说明书关键信息
        """
        params = {
            "search": f'openfda.generic_name:"{drug_name}"',
            "limit": 1
        }

        data = self._safe_get(config.FDA_DRUG_LABEL_API, params)
        if data and "results" in data:
            result = data["results"][0]
            return {
                "drug_name": drug_name,
                "brand_name": result.get("openfda", {}).get("brand_name", []),
                "manufacturer": result.get("openfda", {}).get("manufacturer_name", []),
                "warnings": (result.get("warnings", [""])[0][:500]
                             if result.get("warnings") else ""),
                "drug_interactions": (result.get("drug_interactions", [""])[0][:500]
                                     if result.get("drug_interactions") else ""),
                "active_ingredient": result.get("openfda", {}).get("substance_name", []),
                "route": result.get("openfda", {}).get("route", []),
                "product_type": result.get("openfda", {}).get("product_type", []),
            }
        return None

    # ============================================================
    #  Drug Adverse Events (不良事件)
    # ============================================================
    def fetch_adverse_events(self, drug_name: str, limit: int = 5) -> List[Dict]:
        """
        获取药品不良事件报告摘要
        
        Args:
            drug_name: 药品通用名
            limit: 最大返回记录数
        
        Returns:
            不良事件摘要列表
        """
        params = {
            "search": f'patient.drug.openfda.generic_name:"{drug_name}"+AND+serious:1',
            "limit": limit
        }

        data = self._safe_get(config.FDA_DRUG_EVENT_API, params)
        if data and "results" in data:
            events = []
            for r in data["results"]:
                reactions = []
                for reaction in r.get("patient", {}).get("reaction", []):
                    reactions.append(reaction.get("reactionmeddrapt", ""))

                events.append({
                    "drug_name": drug_name,
                    "receive_date": r.get("receivedate", ""),
                    "serious": r.get("serious", ""),
                    "reactions": reactions[:5],
                    "outcome": r.get("patient", {}).get("patientonsetage", ""),
                })
            return events
        return []

    # ============================================================
    #  批量获取
    # ============================================================
    def fetch_all_for_drugs(self, drug_names: List[str],
                            fetch_labels: bool = True,
                            fetch_enforcement: bool = True,
                            fetch_adverse: bool = False) -> Dict:
        """
        为一组药品批量获取 FDA 数据
        
        Args:
            drug_names: 药品通用名列表
            fetch_labels: 是否获取说明书
            fetch_enforcement: 是否获取召回事件
            fetch_adverse: 是否获取不良事件
        
        Returns:
            {drug_name: {"label": ..., "enforcement": [...], "adverse": [...]}}
        """
        results = {}
        total = len(drug_names)

        for i, name in enumerate(drug_names):
            # 提取英文名（去掉中文括号部分）
            en_name = name.split("（")[0].split("(")[0].strip()
            print(f"  [{i+1}/{total}] {en_name}...", end=" ")

            drug_data = {}

            if fetch_labels:
                label = self.fetch_drug_label(en_name)
                if label:
                    drug_data["label"] = label
                    print("✓label", end=" ")
                time.sleep(config.FDA_REQUEST_DELAY)

            if fetch_enforcement:
                enforcement = self.fetch_drug_enforcement(en_name, limit=5)
                if enforcement:
                    drug_data["enforcement"] = enforcement
                    print(f"✓recall({len(enforcement)})", end=" ")
                time.sleep(config.FDA_REQUEST_DELAY)

            if fetch_adverse:
                adverse = self.fetch_adverse_events(en_name, limit=3)
                if adverse:
                    drug_data["adverse"] = adverse
                    print(f"✓ae({len(adverse)})", end=" ")
                time.sleep(config.FDA_REQUEST_DELAY)

            results[name] = drug_data
            print()

        return results

    def save_fda_data(self, data: Dict, filepath: str = None):
        """保存 FDA 数据到 JSON 文件"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "fda_enrichment_data.json")

        # 将数据转换为可序列化格式
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        print(f"\n✓ FDA 增强数据已保存: {filepath}")

    def load_fda_data(self, filepath: str = None) -> Optional[Dict]:
        """加载已保存的 FDA 数据"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "fda_enrichment_data.json")

        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None


def test_fda_connection():
    """测试 FDA API 连通性"""
    print("测试 FDA OpenAPI 连通性...")

    fetcher = FDADataFetcher()

    # 测试1: Drug Label
    print("\n1. 测试 Drug Label API...")
    label = fetcher.fetch_drug_label("amoxicillin")
    if label:
        print(f"   ✓ 成功获取 Amoxicillin 说明书")
        if label.get("manufacturer"):
            print(f"   制造商: {label['manufacturer'][:3]}")
    else:
        print("   ✗ 获取失败")

    # 测试2: Enforcement
    print("\n2. 测试 Drug Enforcement API...")
    recalls = fetcher.fetch_drug_enforcement("heparin", limit=3)
    if recalls:
        print(f"   ✓ 获取到 {len(recalls)} 条肝素召回记录")
    else:
        print("   ✗ 获取失败")

    # 测试3: Adverse Events
    print("\n3. 测试 Drug Adverse Event API...")
    events = fetcher.fetch_adverse_events("warfarin", limit=2)
    if events:
        print(f"   ✓ 获取到 {len(events)} 条华法林不良事件")
    else:
        print("   ✗ 获取失败")

    return label is not None or recalls or events


if __name__ == "__main__":
    test_fda_connection()
