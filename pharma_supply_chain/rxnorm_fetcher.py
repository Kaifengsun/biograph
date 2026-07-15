"""
RxNorm API 数据获取器
=====================
从 NIH RxNav API 获取:
  - 药品的标准 RxCUI 编码
  - 成分 (Ingredient) 关系
  - 品牌名 ↔ 通用名 映射
  - 相关药品（同成分的不同制剂）

API 文档: https://rxnav.nlm.nih.gov/RxNormAPIs.html
无需注册 / 无需 API Key / 完全免费
"""

import time
import json
import os
import requests
from typing import Dict, List, Optional, Tuple

from . import config


class RxNormFetcher:
    """RxNorm API 客户端"""

    BASE_URL = "https://rxnav.nlm.nih.gov/REST"

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"Accept": "application/json"})
        self._cache = {}  # name -> rxcui cache

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """发起 GET 请求"""
        url = f"{self.BASE_URL}/{endpoint}"
        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=15)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429:
                    time.sleep(2)
                    continue
            except requests.exceptions.RequestException:
                time.sleep(1)
        return None

    def get_rxcui(self, drug_name: str) -> Optional[str]:
        """获取药品的 RxCUI 编码"""
        if drug_name in self._cache:
            return self._cache[drug_name]

        data = self._get("rxcui.json", {"name": drug_name, "search": 2})
        if data:
            ids = data.get("idGroup", {}).get("rxnormId", [])
            if ids:
                self._cache[drug_name] = ids[0]
                return ids[0]

        # 尝试近似搜索
        data = self._get("approximateTerm.json", {"term": drug_name, "maxEntries": 1})
        if data:
            candidates = data.get("approximateGroup", {}).get("candidate", [])
            if candidates:
                rxcui = candidates[0].get("rxcui")
                self._cache[drug_name] = rxcui
                return rxcui

        return None

    def get_ingredients(self, rxcui: str) -> List[Dict]:
        """获取药品的活性成分"""
        data = self._get(f"rxcui/{rxcui}/allrelated.json")
        ingredients = []
        if data:
            groups = data.get("allRelatedGroup", {}).get("conceptGroup", [])
            for g in groups:
                if g.get("tty") in ("IN", "MIN"):  # Ingredient, Multiple Ingredients
                    for prop in g.get("conceptProperties", []):
                        ingredients.append({
                            "rxcui": prop["rxcui"],
                            "name": prop["name"],
                            "tty": g["tty"],
                        })
        return ingredients

    def get_related_brands(self, rxcui: str) -> List[Dict]:
        """获取品牌药名"""
        data = self._get(f"rxcui/{rxcui}/allrelated.json")
        brands = []
        if data:
            groups = data.get("allRelatedGroup", {}).get("conceptGroup", [])
            for g in groups:
                if g.get("tty") in ("BN", "BPCK"):  # Brand Name
                    for prop in g.get("conceptProperties", []):
                        brands.append({
                            "rxcui": prop["rxcui"],
                            "name": prop["name"],
                        })
        return brands

    def get_drug_interactions(self, rxcui: str) -> List[Dict]:
        """获取药物相互作用（RxNorm interaction API）"""
        data = self._get(f"interaction/interaction.json",
                         {"rxcui": rxcui, "sources": "DrugBank"})
        interactions = []
        if data:
            groups = data.get("interactionTypeGroup", [])
            for group in groups:
                for itype in group.get("interactionType", []):
                    for pair in itype.get("interactionPair", []):
                        concepts = pair.get("interactionConcept", [])
                        if len(concepts) >= 2:
                            other = None
                            for c in concepts:
                                if c["minConceptItem"]["rxcui"] != rxcui:
                                    other = c["minConceptItem"]
                                    break
                            if other:
                                interactions.append({
                                    "other_rxcui": other["rxcui"],
                                    "other_name": other["name"],
                                    "description": pair.get("description", ""),
                                    "severity": pair.get("severity", "N/A"),
                                })
        return interactions

    def get_ndc_properties(self, rxcui: str) -> List[Dict]:
        """获取 NDC（National Drug Code）信息 — 含生产商"""
        data = self._get(f"rxcui/{rxcui}/ndcs.json")
        ndcs = []
        if data:
            ndc_list = data.get("ndcGroup", {}).get("ndcList", {}).get("ndc", [])
            for ndc in ndc_list[:10]:  # 限制数量
                prop_data = self._get(f"ndcproperties.json", {"id": ndc})
                if prop_data:
                    props_list = prop_data.get("ndcPropertyList", {}).get("ndcProperty", [])
                    for p in props_list:
                        ndcs.append({
                            "ndc": ndc,
                            "manufacturer": p.get("propertyValue", "")
                            if p.get("propertyName") == "LABELER" else None,
                            "packaging": p.get("packagingList", {}).get("packaging", []),
                        })
        return ndcs

    def fetch_all_for_drugs(self, drug_names: List[str]) -> Dict:
        """批量获取所有药品数据"""
        results = {}
        total = len(drug_names)

        for i, name in enumerate(drug_names, 1):
            print(f"  [{i}/{total}] {name}...", end=" ")

            rxcui = self.get_rxcui(name)
            if not rxcui:
                print("✗ 未找到")
                continue

            drug_data = {"rxcui": rxcui}

            # 成分
            ingredients = self.get_ingredients(rxcui)
            if ingredients:
                drug_data["ingredients"] = ingredients
                print(f"✓rxcui={rxcui}", end=" ")
                print(f"成分({len(ingredients)})", end=" ")

            # 相互作用
            interactions = self.get_drug_interactions(rxcui)
            if interactions:
                drug_data["interactions"] = interactions
                print(f"交互({len(interactions)})", end=" ")

            # 品牌名
            brands = self.get_related_brands(rxcui)
            if brands:
                drug_data["brands"] = brands[:5]  # 最多5个品牌

            results[name] = drug_data
            print()
            time.sleep(0.3)  # 尊重 rate limit

        return results

    def save_data(self, data: Dict, filepath: str = None):
        """保存到 JSON"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "rxnorm_data.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ RxNorm 数据已保存: {filepath}")

    def load_data(self, filepath: str = None) -> Dict:
        """从 JSON 加载"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "rxnorm_data.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
