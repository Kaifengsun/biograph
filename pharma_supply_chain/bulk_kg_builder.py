"""
大规模知识图谱构建器
====================
在原有 PharmaKGBuilder (core_data 128 药品) 基础上，
融合 ChEMBL 批量数据 (4000+ 已批准药物)，
构建包含全球药物、靶点、适应症、供应链的超大图谱。

构建策略:
  Stage 1: 核心供应链图（来自 core_data + FDA/RxNorm/ChEMBL）
  Stage 2: 扩展药物层（来自 ChEMBL 批量数据）
           → 新增 Drug 节点 + Target 节点 + Indication 节点
           → 药物→靶点 ACTS_ON 边
           → 药物→适应症 TREATS 边
  Stage 3: ATC 分类层 → 药物的 ATC 治疗领域分类
  Stage 4: 薄弱链接推断
           → 同靶点药物互联 (SHARES_TARGET)
           → 同适应症药物互联 (TREATS_SAME)
           → 这些 \"推断边\" 大幅增加图密度
"""

import json
import os
import re
import time
from collections import Counter, defaultdict
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from . import config
from .kg_builder import PharmaKGBuilder
from .core_data import DRUGS


# ─── ATC 第一级分类 (用于自动分类药物) ───────────────────────
ATC_LEVEL1 = {
    "A": "消化和代谢 (Alimentary Tract)",
    "B": "血液和造血 (Blood)",
    "C": "心血管 (Cardiovascular)",
    "D": "皮肤 (Dermatologicals)",
    "G": "泌尿生殖和性激素 (Genito-Urinary)",
    "H": "全身性激素 (Systemic Hormonal)",
    "J": "全身性抗感染 (Anti-Infectives)",
    "L": "抗肿瘤和免疫 (Antineoplastic & Immunomodulating)",
    "M": "肌肉骨骼 (Musculo-Skeletal)",
    "N": "神经系统 (Nervous System)",
    "P": "抗寄生虫 (Antiparasitic)",
    "R": "呼吸系统 (Respiratory)",
    "S": "感觉器官 (Sensory Organs)",
    "V": "其他 (Various)",
}


class BulkKGBuilder:
    """
    大规模知识图谱构建器。

    使用方法:
        builder = BulkKGBuilder()
        nodes_df, edges_df = builder.build(
            fda_data=..., rxnorm_data=..., chembl_data=...,
            bulk_chembl_data=...
        )
    """

    def __init__(self):
        # 内部使用现有的 PharmaKGBuilder 处理 Stage 1
        self._core_builder = PharmaKGBuilder()
        # Stage 2+ 直接操作这些列表
        self._extra_nodes: List[dict] = []
        self._extra_edges: List[dict] = []
        self._node_ids: Set[str] = set()
        self._edge_keys: Set[Tuple] = set()

    # ─── 辅助 ────────────────────────────────────────────────
    def _safe_id(self, text: str) -> str:
        """将任意文本转为安全的节点 ID"""
        return re.sub(r"[^A-Za-z0-9_]", "_", text)[:60]

    def _add_node(self, node_id: str, name: str, label: str, **props):
        if node_id not in self._node_ids:
            node = {"id": node_id, "name": name, "label": label}
            node.update(props)
            self._extra_nodes.append(node)
            self._node_ids.add(node_id)

    def _add_edge(self, source: str, target: str, relation: str, **props):
        key = (source, target, relation)
        if key not in self._edge_keys:
            edge = {"source": source, "target": target, "relation": relation}
            edge.update(props)
            self._extra_edges.append(edge)
            self._edge_keys.add(key)

    # ─── Stage 1: 核心图 ────────────────────────────────────
    def _build_core(self, fda_data, rxnorm_data, chembl_data):
        """构建核心供应链图 (128 药品 + API + 厂商 + 国家)"""
        print("\n" + "=" * 60)
        print("  Stage 1: 构建核心供应链图")
        print("=" * 60)
        nodes_df, edges_df = self._core_builder.build_full_graph(
            fda_data=fda_data,
            rxnorm_data=rxnorm_data,
            chembl_data=chembl_data,
        )
        # 同步已有 ID 到自己的集合
        for n in self._core_builder.nodes:
            self._node_ids.add(n["id"])
        for e in self._core_builder.edges:
            self._edge_keys.add((e["source"], e["target"], e["relation"]))

        return nodes_df, edges_df

    # ─── Stage 2: 扩展药物 ──────────────────────────────────
    def _build_expanded_drugs(self, bulk_data: dict):
        """
        从 ChEMBL 批量数据扩展药物、靶点、适应症。
        """
        print("\n" + "=" * 60)
        print("  Stage 2: 扩展全球药物数据 (ChEMBL Bulk)")
        print("=" * 60)

        molecules = bulk_data.get("molecules", [])
        mechanisms = bulk_data.get("mechanisms", {})
        indications = bulk_data.get("indications", {})
        targets_info = bulk_data.get("targets", {})

        # ---- 已有 core_data 的 chembl_id 映射 ----
        existing_chembl_ids = set()
        for node in self._core_builder.nodes:
            cid = node.get("chembl_id")
            if cid:
                existing_chembl_ids.add(cid)

        print(f"  核心图已有 ChEMBL ID: {len(existing_chembl_ids)}")
        print(f"  批量数据药物总数: {len(molecules)}")

        new_drug_count = 0
        new_target_count = 0
        new_indication_count = 0
        drug_target_edges = 0
        drug_indication_edges = 0

        for mol in molecules:
            chembl_id = mol["chembl_id"]

            # 跳过已在核心图中的
            if chembl_id in existing_chembl_ids:
                continue

            drug_id = f"DRUG_{self._safe_id(chembl_id)}"
            drug_name = mol["name"]

            # --- 药物节点 ---
            atc_codes = mol.get("atc_classifications") or []
            category = "other"
            if atc_codes:
                first_letter = atc_codes[0][0] if atc_codes[0] else ""
                category = ATC_LEVEL1.get(first_letter, "other")

            self._add_node(
                drug_id, drug_name, "Drug",
                chembl_id=chembl_id,
                molecule_type=mol.get("molecule_type", ""),
                max_phase=mol.get("max_phase"),
                first_approval=mol.get("first_approval"),
                category=category,
                atc_codes="|".join(atc_codes) if atc_codes else "",
                source="chembl_bulk",
            )
            new_drug_count += 1

            # --- 机制 → 靶点 ---
            for mech in mechanisms.get(chembl_id, []):
                target_chembl = mech.get("target_chembl_id", "")
                if not target_chembl:
                    continue

                target_id = f"TGT_{target_chembl}"
                if target_id not in self._node_ids:
                    tinfo = targets_info.get(target_chembl, {})
                    self._add_node(
                        target_id,
                        tinfo.get("pref_name", target_chembl),
                        "Target",
                        chembl_id=target_chembl,
                        target_type=tinfo.get("target_type", ""),
                        organism=tinfo.get("organism", ""),
                    )
                    new_target_count += 1

                self._add_edge(
                    drug_id, target_id, "ACTS_ON",
                    action_type=mech.get("action_type", ""),
                    mechanism=mech.get("mechanism_of_action", ""),
                )
                drug_target_edges += 1

            # --- 适应症 ---
            seen_ind = set()
            for ind in indications.get(chembl_id, []):
                mesh_heading = ind.get("mesh_heading", "")
                mesh_id = ind.get("mesh_id", "")
                if not mesh_heading or mesh_heading in seen_ind:
                    continue
                seen_ind.add(mesh_heading)

                ind_id = f"IND_{mesh_id}" if mesh_id else f"IND_{self._safe_id(mesh_heading)}"
                if ind_id not in self._node_ids:
                    self._add_node(
                        ind_id, mesh_heading, "Indication",
                        mesh_id=mesh_id,
                        efo_term=ind.get("efo_term", ""),
                    )
                    new_indication_count += 1

                self._add_edge(
                    drug_id, ind_id, "TREATS",
                    max_phase=ind.get("max_phase_for_ind"),
                )
                drug_indication_edges += 1

        print(f"  新增药物节点: {new_drug_count}")
        print(f"  新增靶点节点: {new_target_count}")
        print(f"  新增适应症节点: {new_indication_count}")
        print(f"  新增 ACTS_ON 边: {drug_target_edges}")
        print(f"  新增 TREATS 边: {drug_indication_edges}")

    # ─── Stage 3: ATC 分类层 ────────────────────────────────
    def _build_atc_layer(self, bulk_data: dict):
        """将 ATC 一级分类添加为 TherapeuticArea 节点"""
        print("\n" + "=" * 60)
        print("  Stage 3: ATC 治疗领域分类")
        print("=" * 60)

        # 收集所有 ATC 一级分类
        added = 0
        for code, area_name in ATC_LEVEL1.items():
            atc_area_id = f"ATC_{code}"
            self._add_node(atc_area_id, area_name, "ATCClass", atc_code=code)

        # 为扩展药物添加 BELONGS_TO_ATC 边
        for node in self._extra_nodes:
            if node["label"] == "Drug" and node.get("atc_codes"):
                codes = node["atc_codes"].split("|")
                for code in codes:
                    if code:
                        first_letter = code[0]
                        atc_area_id = f"ATC_{first_letter}"
                        if atc_area_id in self._node_ids:
                            self._add_edge(node["id"], atc_area_id, "BELONGS_TO_ATC")
                            added += 1

        print(f"  新增 ATC 分类节点: {len(ATC_LEVEL1)}")
        print(f"  新增 BELONGS_TO_ATC 边: {added}")

    # ─── Stage 4: 推断边 ────────────────────────────────────
    def _build_inferred_edges(self):
        """
        推断 "薄弱链接":
        - 同靶点药物 → SHARES_TARGET
        - 同适应症药物 → TREATS_SAME
        限制只为核心 128 药品建立推断边 (否则太多)
        """
        print("\n" + "=" * 60)
        print("  Stage 4: 推断药物关联边")
        print("=" * 60)

        # 收集所有 ACTS_ON 和 TREATS 边
        all_edges = list(self._core_builder.edges) + list(self._extra_edges)

        # 按 Target 聚合药物
        target_to_drugs: Dict[str, Set[str]] = defaultdict(set)
        # 按 Indication 聚合药物
        indication_to_drugs: Dict[str, Set[str]] = defaultdict(set)

        for e in all_edges:
            if e["relation"] == "ACTS_ON":
                target_to_drugs[e["target"]].add(e["source"])
            elif e["relation"] == "TREATS":
                indication_to_drugs[e["target"]].add(e["source"])

        # 核心药品 ID 集合 (用于限制推断边的一端必须是核心药品)
        core_drug_ids = {d["id"] for d in DRUGS}

        shares_target_count = 0
        treats_same_count = 0

        # SHARES_TARGET: 如果两个药物作用于同一靶点
        for target_id, drug_set in target_to_drugs.items():
            if len(drug_set) < 2:
                continue
            drug_list = sorted(drug_set)
            for i in range(len(drug_list)):
                for j in range(i + 1, len(drug_list)):
                    d1, d2 = drug_list[i], drug_list[j]
                    # 至少一端是核心药品
                    if d1 not in core_drug_ids and d2 not in core_drug_ids:
                        continue
                    self._add_edge(d1, d2, "SHARES_TARGET", shared_target=target_id)
                    shares_target_count += 1

        # TREATS_SAME: 同适应症的药物 (只取窄适应症, 且限制每个核心药品的边数)
        core_treats_same: Dict[str, int] = defaultdict(int)  # drug_id -> count
        MAX_TREATS_SAME_PER_DRUG = 15

        for ind_id, drug_set in indication_to_drugs.items():
            # 只保留 2-20 个药物的适应症 (太广泛的没意义)
            if len(drug_set) < 2 or len(drug_set) > 20:
                continue
            drug_list = sorted(drug_set)
            for i in range(len(drug_list)):
                for j in range(i + 1, len(drug_list)):
                    d1, d2 = drug_list[i], drug_list[j]
                    if d1 not in core_drug_ids and d2 not in core_drug_ids:
                        continue
                    # 限制每个核心药品的 TREATS_SAME 边数
                    d_core = d1 if d1 in core_drug_ids else d2
                    if core_treats_same[d_core] >= MAX_TREATS_SAME_PER_DRUG:
                        continue
                    self._add_edge(d1, d2, "TREATS_SAME", shared_indication=ind_id)
                    core_treats_same[d_core] += 1
                    treats_same_count += 1

        print(f"  SHARES_TARGET 边: {shares_target_count}")
        print(f"  TREATS_SAME 边: {treats_same_count}")

    # ─── 完整构建 ──────────────────────────────────────────
    def build(self, fda_data=None, rxnorm_data=None,
              chembl_data=None, bulk_chembl_data=None) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        构建完整的大规模知识图谱。

        Returns:
            (nodes_df, edges_df)
        """
        # Stage 1: 核心供应链图
        core_nodes_df, core_edges_df = self._build_core(
            fda_data, rxnorm_data, chembl_data
        )

        # Stage 2: 扩展药物
        if bulk_chembl_data:
            self._build_expanded_drugs(bulk_chembl_data)

            # Stage 3: ATC 分类
            self._build_atc_layer(bulk_chembl_data)

            # Stage 4: 推断边
            self._build_inferred_edges()

        # 合并
        all_nodes = list(self._core_builder.nodes) + self._extra_nodes
        all_edges = list(self._core_builder.edges) + self._extra_edges

        nodes_df = pd.DataFrame(all_nodes)
        edges_df = pd.DataFrame(all_edges)

        # 统计
        print("\n" + "=" * 60)
        print("  大规模知识图谱构建完成!")
        print("=" * 60)
        print(f"  总节点: {len(nodes_df)}")
        print(f"  总边:   {len(edges_df)}")

        if "label" in nodes_df.columns:
            print(f"\n  节点类型分布:")
            for nt, c in nodes_df["label"].value_counts().items():
                print(f"    {nt}: {c}")

        if "relation" in edges_df.columns:
            print(f"\n  边类型分布:")
            for et, c in edges_df["relation"].value_counts().items():
                print(f"    {et}: {c}")

        return nodes_df, edges_df
