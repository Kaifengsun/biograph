"""
ChEMBL API 数据获取器
=====================
从 EMBL-EBI ChEMBL API 获取:
  - 药物的 ChEMBL ID / 分子属性
  - 药物靶点 (Target) 及作用机制 (Mechanism of Action)
  - 药物适应症 (Indication) 数据
  - 靶点-蛋白质关联

API 文档: https://chembl.gitbook.io/chembl-interface-documentation/web-services/chembl-data-web-services
无需注册 / 无需 API Key / 完全免费
"""

import time
import json
import os
import requests
from typing import Dict, List, Optional

from . import config


class ChEMBLFetcher:
    """ChEMBL REST API 客户端"""

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({
            "Accept": "application/json",
        })
        self._cache: Dict[str, str] = {}  # name -> chembl_id

    def _get(self, endpoint: str, params: dict = None) -> Optional[dict]:
        """发起 GET 请求"""
        url = f"{self.BASE_URL}/{endpoint}"
        if params is None:
            params = {}
        params["format"] = "json"

        for attempt in range(3):
            try:
                r = self.session.get(url, params=params, timeout=20)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code == 429:
                    time.sleep(3)
                    continue
                elif r.status_code == 404:
                    return None
            except requests.exceptions.RequestException:
                time.sleep(1)
        return None

    def search_molecule(self, drug_name: str) -> Optional[Dict]:
        """搜索药物分子，返回 ChEMBL ID 和基本信息"""
        if drug_name in self._cache:
            return {"molecule_chembl_id": self._cache[drug_name]}

        data = self._get("molecule/search.json", {"q": drug_name, "limit": 5})
        if data and data.get("molecules"):
            for mol in data["molecules"]:
                pref_name = (mol.get("pref_name") or "").lower()
                if drug_name.lower() in pref_name or pref_name in drug_name.lower():
                    chembl_id = mol["molecule_chembl_id"]
                    self._cache[drug_name] = chembl_id
                    return {
                        "molecule_chembl_id": chembl_id,
                        "pref_name": mol.get("pref_name"),
                        "max_phase": mol.get("max_phase"),
                        "molecule_type": mol.get("molecule_type"),
                        "first_approval": mol.get("first_approval"),
                        "oral": mol.get("oral"),
                        "parenteral": mol.get("parenteral"),
                        "topical": mol.get("topical"),
                    }
            # 如果没有精确匹配，取第一个
            mol = data["molecules"][0]
            chembl_id = mol["molecule_chembl_id"]
            self._cache[drug_name] = chembl_id
            return {
                "molecule_chembl_id": chembl_id,
                "pref_name": mol.get("pref_name"),
                "max_phase": mol.get("max_phase"),
                "molecule_type": mol.get("molecule_type"),
                "first_approval": mol.get("first_approval"),
            }
        return None

    def get_mechanisms(self, chembl_id: str) -> List[Dict]:
        """获取药物作用机制（靶点 + 作用类型）"""
        data = self._get("mechanism.json", {
            "molecule_chembl_id": chembl_id,
            "limit": 20,
        })
        mechanisms = []
        if data and data.get("mechanisms"):
            for mech in data["mechanisms"]:
                mechanisms.append({
                    "mechanism_of_action": mech.get("mechanism_of_action"),
                    "action_type": mech.get("action_type"),
                    "target_chembl_id": mech.get("target_chembl_id"),
                    "target_name": None,  # 后续填充
                })
        return mechanisms

    def get_target_info(self, target_chembl_id: str) -> Optional[Dict]:
        """获取靶点详情"""
        data = self._get(f"target/{target_chembl_id}.json")
        if data:
            return {
                "target_chembl_id": data.get("target_chembl_id"),
                "pref_name": data.get("pref_name"),
                "target_type": data.get("target_type"),
                "organism": data.get("organism"),
                "target_components": [
                    {
                        "component_id": tc.get("component_id"),
                        "component_type": tc.get("component_type"),
                        "accession": tc.get("accession"),
                    }
                    for tc in (data.get("target_components") or [])
                ],
            }
        return None

    def get_indications(self, chembl_id: str) -> List[Dict]:
        """获取药物适应症"""
        data = self._get("drug_indication.json", {
            "molecule_chembl_id": chembl_id,
            "limit": 30,
        })
        indications = []
        if data and data.get("drug_indications"):
            seen = set()
            for ind in data["drug_indications"]:
                mesh_heading = ind.get("mesh_heading", "")
                if mesh_heading and mesh_heading not in seen:
                    seen.add(mesh_heading)
                    indications.append({
                        "mesh_heading": mesh_heading,
                        "mesh_id": ind.get("mesh_id", ""),
                        "efo_term": ind.get("efo_term", ""),
                        "max_phase_for_ind": ind.get("max_phase_for_ind"),
                    })
        return indications

    def fetch_all_for_drugs(self, drug_names: List[str]) -> Dict:
        """批量获取所有药品数据"""
        results = {}
        total = len(drug_names)

        for i, name in enumerate(drug_names, 1):
            print(f"  [{i}/{total}] {name}...", end=" ")

            mol = self.search_molecule(name)
            if not mol:
                print("✗ 未找到")
                continue

            chembl_id = mol["molecule_chembl_id"]
            drug_data = {"molecule": mol}
            print(f"✓ {chembl_id}", end=" ")

            # 作用机制 + 靶点
            mechanisms = self.get_mechanisms(chembl_id)
            if mechanisms:
                # 填充靶点名称
                for mech in mechanisms:
                    tid = mech.get("target_chembl_id")
                    if tid:
                        tinfo = self.get_target_info(tid)
                        if tinfo:
                            mech["target_name"] = tinfo.get("pref_name")
                            mech["target_type"] = tinfo.get("target_type")
                            mech["organism"] = tinfo.get("organism")
                        time.sleep(0.15)
                drug_data["mechanisms"] = mechanisms
                print(f"靶点({len(mechanisms)})", end=" ")

            # 适应症
            indications = self.get_indications(chembl_id)
            if indications:
                drug_data["indications"] = indications
                print(f"适应症({len(indications)})", end=" ")

            results[name] = drug_data
            print()
            time.sleep(0.25)

        return results

    def save_data(self, data: Dict, filepath: str = None):
        """保存到 JSON"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "chembl_data.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ ChEMBL 数据已保存: {filepath}")

    def load_data(self, filepath: str = None) -> Dict:
        """从 JSON 加载"""
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "chembl_data.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
