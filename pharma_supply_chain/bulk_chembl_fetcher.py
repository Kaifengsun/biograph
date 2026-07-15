"""
ChEMBL 批量获取器 — 大规模扩展药品知识图谱
============================================
通过 ChEMBL REST API 的分页端点，批量获取全部已批准药物、
作用机制和适应症数据。

策略:
  1) molecule.json?max_phase=4  → 获取所有上市药物 (~4500)
  2) mechanism.json             → 获取所有机制 → drug→target
  3) drug_indication.json       → 获取所有适应症 → drug→indication
  4) target.json (按需)          → 获取靶点详情

API 文档: https://chembl.gitbook.io/chembl-interface-documentation
无需 API Key / 完全免费 / 速率: ~10 req/s (我们保守发 3 req/s)
"""

import json
import os
import time
import requests
from typing import Dict, List, Optional, Set

from . import config


class BulkChEMBLFetcher:
    """ChEMBL REST API 批量客户端"""

    BASE_URL = "https://www.ebi.ac.uk/chembl/api/data"
    PAGE_SIZE = 1000  # ChEMBL 最大单页

    def __init__(self):
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({"Accept": "application/json"})

    # ─── 通用分页器 ────────────────────────────────────────────
    def _paginate(self, endpoint: str, params: dict = None,
                  max_records: int = 0, label: str = "") -> List[dict]:
        """
        分页获取某个端点的全部记录。
        max_records=0 表示取全部。
        """
        if params is None:
            params = {}
        params["format"] = "json"
        params["limit"] = self.PAGE_SIZE
        params["offset"] = 0

        all_results = []
        total = "?"

        while True:
            url = f"{self.BASE_URL}/{endpoint}"
            for attempt in range(4):
                try:
                    r = self.session.get(url, params=params, timeout=30)
                    if r.status_code == 200:
                        break
                    elif r.status_code == 429:
                        time.sleep(5)
                    else:
                        time.sleep(2)
                except requests.exceptions.RequestException:
                    time.sleep(3)
            else:
                print(f"\n  ✗ 请求失败: {endpoint} offset={params['offset']}")
                break

            data = r.json()
            page_meta = data.get("page_meta", {})
            total = page_meta.get("total_count", "?")
            results = data.get(endpoint.split(".")[0] + "s", [])
            # ChEMBL 的 endpoint key 规则: molecule.json -> molecules
            if not results:
                # 有些端点用不同 key
                for key in data:
                    if key != "page_meta" and isinstance(data[key], list):
                        results = data[key]
                        break

            if not results:
                break

            all_results.extend(results)

            got = len(all_results)
            print(f"\r  {label}: {got}/{total} 条", end="", flush=True)

            if max_records and got >= max_records:
                all_results = all_results[:max_records]
                break

            next_url = page_meta.get("next")
            if not next_url:
                break

            # 更新 offset
            params["offset"] += self.PAGE_SIZE
            time.sleep(0.35)  # 尊重 rate limit

        print(f"\r  {label}: {len(all_results)}/{total} 条 ✓")
        return all_results

    # ─── Step 1: 获取所有已批准药物 ──────────────────────────
    def fetch_approved_molecules(self, max_records: int = 0) -> List[dict]:
        """
        获取所有 max_phase >= 4 (已上市) 的分子。
        返回精简字段列表。
        """
        print("\n[ 步骤 1 ] 批量获取已批准药物...")
        raw = self._paginate(
            "molecule.json",
            params={"max_phase": 4},
            max_records=max_records,
            label="已批准药物",
        )

        molecules = []
        seen_ids = set()
        for mol in raw:
            chembl_id = mol.get("molecule_chembl_id", "")
            if not chembl_id or chembl_id in seen_ids:
                continue
            seen_ids.add(chembl_id)

            # 提取关键字段
            props = mol.get("molecule_properties") or {}
            structs = mol.get("molecule_structures") or {}
            name = mol.get("pref_name") or ""
            if not name:
                continue  # 无名分子跳过

            molecules.append({
                "chembl_id": chembl_id,
                "name": name,
                "molecule_type": mol.get("molecule_type", ""),
                "max_phase": mol.get("max_phase"),
                "first_approval": mol.get("first_approval"),
                "oral": mol.get("oral", False),
                "parenteral": mol.get("parenteral", False),
                "topical": mol.get("topical", False),
                "atc_classifications": mol.get("atc_classifications") or [],
                "mw_freebase": props.get("mw_freebase"),
                "alogp": props.get("alogp"),
                "hba": props.get("hba"),
                "hbd": props.get("hbd"),
                "canonical_smiles": structs.get("canonical_smiles", ""),
            })

        print(f"  → 有效已批准分子: {len(molecules)}")
        return molecules

    # ─── Step 2: 批量获取作用机制 ──────────────────────────────
    def fetch_all_mechanisms(self) -> Dict[str, List[dict]]:
        """
        获取 ChEMBL 全部 drug-mechanism-target 记录。
        返回 {chembl_id: [mechanism_records...]}
        """
        print("\n[ 步骤 2 ] 批量获取作用机制...")
        raw = self._paginate(
            "mechanism.json",
            label="作用机制",
        )

        by_drug: Dict[str, List[dict]] = {}
        for mech in raw:
            cid = mech.get("molecule_chembl_id", "")
            if not cid:
                continue
            rec = {
                "target_chembl_id": mech.get("target_chembl_id", ""),
                "mechanism_of_action": mech.get("mechanism_of_action", ""),
                "action_type": mech.get("action_type", ""),
            }
            by_drug.setdefault(cid, []).append(rec)

        print(f"  → 覆盖 {len(by_drug)} 个药物")
        return by_drug

    # ─── Step 3: 批量获取适应症 ────────────────────────────────
    def fetch_all_indications(self, max_records: int = 0) -> Dict[str, List[dict]]:
        """
        获取 ChEMBL 全部 drug_indication 记录。
        返回 {chembl_id: [indication_records...]}
        """
        print("\n[ 步骤 3 ] 批量获取适应症...")
        raw = self._paginate(
            "drug_indication.json",
            max_records=max_records,
            label="适应症",
        )

        by_drug: Dict[str, List[dict]] = {}
        for ind in raw:
            cid = ind.get("molecule_chembl_id", "")
            if not cid:
                continue
            rec = {
                "mesh_heading": ind.get("mesh_heading", ""),
                "mesh_id": ind.get("mesh_id", ""),
                "efo_term": ind.get("efo_term", ""),
                "max_phase_for_ind": ind.get("max_phase_for_ind"),
            }
            by_drug.setdefault(cid, []).append(rec)

        print(f"  → 覆盖 {len(by_drug)} 个药物")
        return by_drug

    # ─── Step 4: 批量获取靶点详情 ──────────────────────────────
    def fetch_targets_batch(self, target_ids: Set[str]) -> Dict[str, dict]:
        """
        批量获取靶点信息（分页 + 过滤）。
        返回 {target_chembl_id: {name, type, organism}}
        """
        print(f"\n[ 步骤 4 ] 获取靶点详情 ({len(target_ids)} 个)...")

        # ChEMBL 支持在 URL 中传递 target_chembl_id__in，但列表太长时需分批
        targets = {}
        id_list = sorted(target_ids)
        batch_size = 50

        for i in range(0, len(id_list), batch_size):
            batch = id_list[i:i + batch_size]
            ids_str = ",".join(batch)
            url = f"{self.BASE_URL}/target.json"
            params = {
                "target_chembl_id__in": ids_str,
                "format": "json",
                "limit": batch_size,
            }

            for attempt in range(3):
                try:
                    r = self.session.get(url, params=params, timeout=30)
                    if r.status_code == 200:
                        break
                    time.sleep(2)
                except requests.exceptions.RequestException:
                    time.sleep(2)
            else:
                continue

            data = r.json()
            for t in data.get("targets", []):
                tid = t.get("target_chembl_id", "")
                if tid:
                    targets[tid] = {
                        "pref_name": t.get("pref_name", ""),
                        "target_type": t.get("target_type", ""),
                        "organism": t.get("organism", ""),
                    }

            print(f"\r  靶点: {len(targets)}/{len(target_ids)}", end="", flush=True)
            time.sleep(0.3)

        print(f"\r  靶点: {len(targets)}/{len(target_ids)} ✓")
        return targets

    # ─── 汇总: 完整批量流程 ──────────────────────────────────
    def fetch_all(self, max_drugs: int = 0,
                  max_indications: int = 0) -> dict:
        """
        执行完整的批量获取流程。

        Args:
            max_drugs: 最大药物数 (0=全部, 约4500)
            max_indications: 最大适应症记录数 (0=全部, 约60000+)

        Returns:
            {
                "molecules": [...],
                "mechanisms": {chembl_id: [...]},
                "indications": {chembl_id: [...]},
                "targets": {target_chembl_id: {...}},
            }
        """
        print("=" * 60)
        print("  ChEMBL 批量数据获取")
        print("=" * 60)

        # 1. 药物
        molecules = self.fetch_approved_molecules(max_records=max_drugs)

        # 2. 机制
        mechanisms = self.fetch_all_mechanisms()

        # 3. 适应症
        indications = self.fetch_all_indications(max_records=max_indications)

        # 4. 靶点 ID 汇总
        target_ids = set()
        for mechs in mechanisms.values():
            for m in mechs:
                tid = m.get("target_chembl_id")
                if tid:
                    target_ids.add(tid)

        targets = self.fetch_targets_batch(target_ids)

        result = {
            "molecules": molecules,
            "mechanisms": mechanisms,
            "indications": indications,
            "targets": targets,
        }

        print(f"\n{'=' * 60}")
        print(f"  批量获取完成!")
        print(f"  药物: {len(molecules)}")
        print(f"  有机制的药物: {len(mechanisms)}")
        print(f"  有适应症的药物: {len(indications)}")
        print(f"  靶点: {len(targets)}")
        print(f"{'=' * 60}")

        return result

    # ─── 保存 / 加载 ──────────────────────────────────────────
    def save_data(self, data: dict, filepath: str = None):
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "chembl_bulk_data.json")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✓ 批量数据已保存: {filepath}")

    def load_data(self, filepath: str = None) -> Optional[dict]:
        if filepath is None:
            filepath = os.path.join(config.DATA_DIR, "chembl_bulk_data.json")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return None
