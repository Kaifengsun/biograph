"""
制药供应链知识图谱构建器
========================
将 core_data.py 中的结构化数据 + FDA / RxNorm / ChEMBL 增强数据，
统一构建为知识图谱的节点和边（DataFrame 格式），
然后导出为 Neo4j 可导入的 CSV。
"""

import pandas as pd
import json
import os
from typing import Tuple, Dict, Optional
from collections import Counter

from . import config
from .core_data import (
    DRUGS, APIS, MANUFACTURERS, COUNTRIES,
    THERAPEUTIC_AREAS, REGULATIONS, SHORTAGE_EVENTS,
    DRUG_API_MAP, API_SUPPLIER_MAP, DRUG_INTERACTIONS,
    API_SUBSTITUTES, DRUG_AREA_MAP, COUNTRY_NAME_TO_ID,
)


class PharmaKGBuilder:
    """制药供应链知识图谱构建器"""

    def __init__(self):
        self.nodes = []
        self.edges = []
        self._node_ids = set()
        self._edge_keys = set()

    def _add_node(self, node_id: str, name: str, label: str, **props):
        """添加节点（去重）"""
        if node_id not in self._node_ids:
            node = {"id": node_id, "name": name, "label": label}
            node.update(props)
            self.nodes.append(node)
            self._node_ids.add(node_id)

    def _add_edge(self, source: str, target: str, relation: str, **props):
        """添加边（去重）"""
        key = (source, target, relation)
        if key not in self._edge_keys:
            edge = {"source": source, "target": target, "relation": relation}
            edge.update(props)
            self.edges.append(edge)
            self._edge_keys.add(key)

    # ============================================================
    #  构建各类节点
    # ============================================================

    def build_drug_nodes(self):
        """构建药品节点"""
        print("  构建药品节点...", end=" ")
        for drug in DRUGS:
            self._add_node(
                drug["id"], drug["name"], "Drug",
                category=drug["category"],
                who_essential=drug["who_essential"],
                dosage_form=drug["dosage_form"]
            )
        print(f"✓ {len(DRUGS)} 个")

    def build_api_nodes(self):
        """构建 API 节点"""
        print("  构建 API 节点...", end=" ")
        for api in APIS:
            self._add_node(
                api["id"], api["name"], "API",
                cas_number=api["cas"],
                api_class=api["class"]
            )
        print(f"✓ {len(APIS)} 个")

    def build_manufacturer_nodes(self):
        """构建制造商节点"""
        print("  构建制造商节点...", end=" ")
        for mfg in MANUFACTURERS:
            self._add_node(
                mfg["id"], mfg["name"], "Manufacturer",
                country=mfg["country"],
                mfg_type=mfg["type"],
                tier=mfg["tier"]
            )
        print(f"✓ {len(MANUFACTURERS)} 个")

    def build_country_nodes(self):
        """构建国家节点"""
        print("  构建国家/地区节点...", end=" ")
        for country in COUNTRIES:
            self._add_node(
                country["id"], country["name"], "Country",
                region=country["region"],
                api_share_pct=country["api_share_pct"]
            )
        print(f"✓ {len(COUNTRIES)} 个")

    def build_therapeutic_area_nodes(self):
        """构建治疗领域节点"""
        print("  构建治疗领域节点...", end=" ")
        for area in THERAPEUTIC_AREAS:
            self._add_node(
                area["id"], area["name"], "TherapeuticArea",
                atc_prefix=area["atc_prefix"]
            )
        print(f"✓ {len(THERAPEUTIC_AREAS)} 个")

    def build_shortage_event_nodes(self):
        """构建短缺事件节点"""
        print("  构建短缺事件节点...", end=" ")
        for event in SHORTAGE_EVENTS:
            self._add_node(
                event["id"], f"Shortage: {event['drug_id']} ({event['year']})",
                "ShortageEvent",
                year=event["year"],
                duration_months=event["duration_months"],
                cause=event["cause"],
                severity=event["severity"],
                impact=event["impact"]
            )
        print(f"✓ {len(SHORTAGE_EVENTS)} 个")

    def build_regulation_nodes(self):
        """构建监管法规节点"""
        print("  构建法规节点...", end=" ")
        for reg in REGULATIONS:
            self._add_node(
                reg["id"], reg["name"], "Regulation",
                authority=reg["authority"],
                description=reg["description"]
            )
        print(f"✓ {len(REGULATIONS)} 个")

    # ============================================================
    #  构建各类边
    # ============================================================

    def build_drug_api_edges(self):
        """构建 Drug ─CONTAINS_API─→ API 边"""
        print("  构建 Drug→API 边...", end=" ")
        count = 0
        for drug_id, api_id in DRUG_API_MAP:
            self._add_edge(drug_id, api_id, "CONTAINS_API")
            count += 1
        print(f"✓ {count} 条")

    def build_api_supplier_edges(self):
        """构建 API ←SUPPLIED_BY→ Manufacturer 边"""
        print("  构建 API→Manufacturer 边...", end=" ")
        count = 0
        for api_id, mfg_id in API_SUPPLIER_MAP:
            self._add_edge(api_id, mfg_id, "SUPPLIED_BY")
            count += 1
        print(f"✓ {count} 条")

    def build_manufacturer_country_edges(self):
        """构建 Manufacturer ─LOCATED_IN─→ Country 边"""
        print("  构建 Manufacturer→Country 边...", end=" ")
        count = 0
        for mfg in MANUFACTURERS:
            country_id = COUNTRY_NAME_TO_ID.get(mfg["country"])
            if country_id:
                self._add_edge(mfg["id"], country_id, "LOCATED_IN")
                count += 1
        print(f"✓ {count} 条")

    def build_drug_interaction_edges(self):
        """构建 Drug ─INTERACTS_WITH─→ Drug 边"""
        print("  构建 Drug↔Drug 相互作用边...", end=" ")
        count = 0
        for drug_a, drug_b, severity, mechanism in DRUG_INTERACTIONS:
            self._add_edge(drug_a, drug_b, "INTERACTS_WITH",
                          severity=severity, mechanism=mechanism)
            count += 1
        print(f"✓ {count} 条")

    def build_drug_area_edges(self):
        """构建 Drug ─BELONGS_TO_AREA─→ TherapeuticArea 边"""
        print("  构建 Drug→TherapeuticArea 边...", end=" ")
        count = 0
        for drug in DRUGS:
            area_id = DRUG_AREA_MAP.get(drug["category"])
            if area_id:
                self._add_edge(drug["id"], area_id, "BELONGS_TO_AREA")
                count += 1
        print(f"✓ {count} 条")

    def build_shortage_edges(self):
        """构建 Drug ─HAD_SHORTAGE─→ ShortageEvent 边"""
        print("  构建 Drug→ShortageEvent 边...", end=" ")
        count = 0
        for event in SHORTAGE_EVENTS:
            self._add_edge(event["drug_id"], event["id"], "HAD_SHORTAGE")
            count += 1
        print(f"✓ {count} 条")

    def build_substitute_edges(self):
        """构建 API ─SUBSTITUTE_OF─→ API 边"""
        print("  构建 API↔API 替代关系边...", end=" ")
        count = 0
        for api_a, api_b, sub_type in API_SUBSTITUTES:
            self._add_edge(api_a, api_b, "SUBSTITUTE_OF",
                          substitute_type=sub_type)
            count += 1
        print(f"✓ {count} 条")

    def build_regulation_edges(self):
        """构建 Manufacturer ─REGULATED_BY─→ Regulation 边"""
        print("  构建 Manufacturer→Regulation 边...", end=" ")
        count = 0

        # 按国家分类的监管规则
        us_regs = ["REG_fda_cgmp", "REG_fda_dmf"]
        eu_regs = ["REG_ema_gmp"]
        japan_regs = ["REG_pmda_gmp"] if any(r["id"] == "REG_pmda_gmp" for r in REGULATIONS) else []
        china_regs = ["REG_nmpa_gmp"] if any(r["id"] == "REG_nmpa_gmp" for r in REGULATIONS) else []

        eu_countries = {"Germany", "Switzerland", "France", "Denmark", "Italy", "Ireland", "UK"}
        export_countries = {"India", "China", "Japan", "South Korea", "Bangladesh", "Indonesia", "Brazil", "South Africa", "Canada"}

        for mfg in MANUFACTURERS:
            # 所有制造商受 ICH Q7 监管
            self._add_edge(mfg["id"], "REG_ich_q7", "REGULATED_BY")
            count += 1

            country = mfg["country"]
            if country == "USA":
                for reg in us_regs:
                    self._add_edge(mfg["id"], reg, "REGULATED_BY")
                    count += 1
            elif country in eu_countries:
                for reg in eu_regs:
                    self._add_edge(mfg["id"], reg, "REGULATED_BY")
                    count += 1
            elif country == "Japan" and japan_regs:
                for reg in japan_regs:
                    self._add_edge(mfg["id"], reg, "REGULATED_BY")
                    count += 1
            elif country == "China" and china_regs:
                for reg in china_regs:
                    self._add_edge(mfg["id"], reg, "REGULATED_BY")
                    count += 1

            # 出口到欧美的供应商也需要 FDA DMF / WHO PQ
            if country in export_countries:
                self._add_edge(mfg["id"], "REG_fda_dmf", "REGULATED_BY")
                self._add_edge(mfg["id"], "REG_fda_import_alert", "REGULATED_BY")
                count += 2
                # WHO 预认证 — 出口到发展中国家的重要厂商
                if any(r["id"] == "REG_who_pq" for r in REGULATIONS):
                    self._add_edge(mfg["id"], "REG_who_pq", "REGULATED_BY")
                    count += 1

        print(f"✓ {count} 条")

    # ============================================================
    #  FDA 增强数据融合
    # ============================================================

    def enrich_with_fda_data(self, fda_data: Dict):
        """融合 FDA API 获取的增强数据"""
        if not fda_data:
            print("  无 FDA 增强数据可用，跳过")
            return

        print("  融合 FDA 增强数据...", end=" ")
        recall_count = 0

        for drug_name, data in fda_data.items():
            # 融合召回事件
            if "enforcement" in data:
                for recall in data["enforcement"][:3]:
                    recall_id = f"RECALL_{recall.get('recall_number', 'unknown')}"
                    self._add_node(
                        recall_id,
                        f"Recall: {recall.get('reason', '')[:50]}",
                        "RecallEvent",
                        recalling_firm=recall.get("recalling_firm", ""),
                        classification=recall.get("classification", ""),
                        report_date=recall.get("report_date", ""),
                    )

                    # 找到对应的 Drug ID
                    drug_id = self._find_drug_id(drug_name)
                    if drug_id:
                        self._add_edge(drug_id, recall_id, "WAS_RECALLED")
                        recall_count += 1

        print(f"✓ 新增 {recall_count} 条召回关系")

    # ============================================================
    #  RxNorm 增强数据融合
    # ============================================================

    def enrich_with_rxnorm_data(self, rxnorm_data: Dict):
        """融合 RxNorm API 获取的增强数据"""
        if not rxnorm_data:
            print("  无 RxNorm 增强数据可用，跳过")
            return

        print("  融合 RxNorm 增强数据...", end=" ")
        interaction_count = 0

        for drug_name, data in rxnorm_data.items():
            drug_id = self._find_drug_id(drug_name)
            if not drug_id:
                continue

            rxcui = data.get("rxcui")
            if rxcui:
                # 更新已有节点的 rxcui 属性
                for node in self.nodes:
                    if node["id"] == drug_id:
                        node["rxcui"] = rxcui
                        break

            # 融合 RxNorm 交互作用
            for interaction in data.get("interactions", []):
                other_name = interaction.get("other_name", "")
                other_id = self._find_drug_id(other_name)
                if other_id and other_id != drug_id:
                    desc = interaction.get("description", "")[:100]
                    severity = interaction.get("severity", "N/A")
                    self._add_edge(drug_id, other_id, "INTERACTS_WITH",
                                   severity=severity, mechanism=desc,
                                   source="RxNorm")
                    interaction_count += 1

        print(f"✓ 已更新 rxcui 属性, 新增 {interaction_count} 条交互关系")

    # ============================================================
    #  ChEMBL 增强数据融合
    # ============================================================

    def enrich_with_chembl_data(self, chembl_data: Dict):
        """融合 ChEMBL API 获取的增强数据 — 添加 Target + Indication 节点"""
        if not chembl_data:
            print("  无 ChEMBL 增强数据可用，跳过")
            return

        print("  融合 ChEMBL 增强数据...", end=" ")
        target_count = 0
        indication_count = 0

        for drug_name, data in chembl_data.items():
            drug_id = self._find_drug_id(drug_name)
            if not drug_id:
                continue

            mol = data.get("molecule", {})
            chembl_id = mol.get("molecule_chembl_id")

            if chembl_id:
                # 将 chembl_id 附加到已有 Drug 节点
                for node in self.nodes:
                    if node["id"] == drug_id:
                        node["chembl_id"] = chembl_id
                        node["max_phase"] = mol.get("max_phase")
                        node["first_approval"] = mol.get("first_approval")
                        break

            # ---- 靶点 (Target) ----
            for mech in data.get("mechanisms", []):
                target_chembl = mech.get("target_chembl_id")
                target_name = mech.get("target_name")
                if target_chembl and target_name:
                    target_id = f"TGT_{target_chembl}"
                    self._add_node(
                        target_id, target_name, "Target",
                        chembl_id=target_chembl,
                        target_type=mech.get("target_type", ""),
                        organism=mech.get("organism", ""),
                    )
                    action = mech.get("action_type", "unknown")
                    mechanism_text = mech.get("mechanism_of_action", "")
                    self._add_edge(
                        drug_id, target_id, "ACTS_ON",
                        action_type=action,
                        mechanism=mechanism_text,
                    )
                    target_count += 1

            # ---- 适应症 (Indication) ----
            for ind in data.get("indications", []):
                mesh_heading = ind.get("mesh_heading", "")
                mesh_id = ind.get("mesh_id", "")
                if mesh_heading:
                    ind_id = f"IND_{mesh_id}" if mesh_id else f"IND_{mesh_heading.replace(' ', '_')[:30]}"
                    self._add_node(
                        ind_id, mesh_heading, "Indication",
                        mesh_id=mesh_id,
                        efo_term=ind.get("efo_term", ""),
                    )
                    self._add_edge(
                        drug_id, ind_id, "TREATS",
                        max_phase=ind.get("max_phase_for_ind"),
                    )
                    indication_count += 1

        print(f"✓ 新增 {target_count} 条靶点关系 + {indication_count} 条适应症关系")

    def _find_drug_id(self, drug_name: str) -> Optional[str]:
        """根据药品名称查找 Drug ID"""
        name_lower = drug_name.lower()
        for drug in DRUGS:
            if name_lower in drug["name"].lower() or \
               drug["name"].lower().startswith(name_lower):
                return drug["id"]
        return None

    # ============================================================
    #  完整构建流程
    # ============================================================

    def build_full_graph(self, fda_data: Dict = None,
                         rxnorm_data: Dict = None,
                         chembl_data: Dict = None):
        """构建完整的知识图谱"""
        print("\n" + "=" * 60)
        print("  开始构建制药供应链知识图谱")
        print("=" * 60)

        # 1. 构建所有节点
        print("\n[ 第一步：构建节点 ]")
        self.build_drug_nodes()
        self.build_api_nodes()
        self.build_manufacturer_nodes()
        self.build_country_nodes()
        self.build_therapeutic_area_nodes()
        self.build_shortage_event_nodes()
        self.build_regulation_nodes()

        # 2. 构建所有边
        print("\n[ 第二步：构建边 ]")
        self.build_drug_api_edges()
        self.build_api_supplier_edges()
        self.build_manufacturer_country_edges()
        self.build_drug_interaction_edges()
        self.build_drug_area_edges()
        self.build_shortage_edges()
        self.build_substitute_edges()
        self.build_regulation_edges()

        # 3. FDA 增强（可选）
        if fda_data:
            print("\n[ 第三步：FDA 数据增强 ]")
            self.enrich_with_fda_data(fda_data)

        # 4. RxNorm 增强（可选）
        if rxnorm_data:
            print("\n[ 第四步：RxNorm 数据增强 ]")
            self.enrich_with_rxnorm_data(rxnorm_data)

        # 5. ChEMBL 增强（可选）
        if chembl_data:
            print("\n[ 第五步：ChEMBL 数据增强 ]")
            self.enrich_with_chembl_data(chembl_data)

        # 6. 转换为 DataFrame
        nodes_df = pd.DataFrame(self.nodes)
        edges_df = pd.DataFrame(self.edges)

        return nodes_df, edges_df

    # ============================================================
    #  图谱统计分析
    # ============================================================

    def analyze_graph(self, nodes_df: pd.DataFrame, edges_df: pd.DataFrame) -> Dict:
        """分析图谱统计信息"""
        stats = {
            "total_nodes": len(nodes_df),
            "total_edges": len(edges_df),
            "node_types": {},
            "edge_types": {},
            "supply_chain_metrics": {},
        }

        # 节点类型分布
        if "label" in nodes_df.columns:
            for label, count in nodes_df["label"].value_counts().items():
                stats["node_types"][label] = int(count)

        # 边类型分布
        if "relation" in edges_df.columns:
            for relation, count in edges_df["relation"].value_counts().items():
                stats["edge_types"][relation] = int(count)

        # 供应链关键指标
        supply_edges = edges_df[edges_df["relation"] == "SUPPLIED_BY"]
        if not supply_edges.empty:
            # 每个 API 的供应商数量
            api_supplier_counts = supply_edges.groupby("source").size()
            stats["supply_chain_metrics"]["avg_suppliers_per_api"] = round(
                api_supplier_counts.mean(), 2
            )
            stats["supply_chain_metrics"]["single_source_apis"] = int(
                (api_supplier_counts == 1).sum()
            )
            stats["supply_chain_metrics"]["multi_source_apis"] = int(
                (api_supplier_counts > 1).sum()
            )

            # 每个制造商供应的 API 数量
            mfg_api_counts = supply_edges.groupby("target").size()
            stats["supply_chain_metrics"]["top_suppliers"] = (
                mfg_api_counts.sort_values(ascending=False)
                .head(5)
                .to_dict()
            )

        # 单一来源风险药品
        interaction_edges = edges_df[edges_df["relation"] == "INTERACTS_WITH"]
        stats["supply_chain_metrics"]["drug_interaction_count"] = len(interaction_edges)

        # 国家集中度
        country_edges = edges_df[edges_df["relation"] == "LOCATED_IN"]
        if not country_edges.empty:
            country_counts = country_edges["target"].value_counts()
            stats["supply_chain_metrics"]["manufacturer_by_country"] = (
                country_counts.to_dict()
            )

        return stats

    def print_stats(self, stats: Dict):
        """打印图谱统计信息"""
        print("\n" + "=" * 60)
        print("  知识图谱统计报告")
        print("=" * 60)

        print(f"\n📊 总节点数: {stats['total_nodes']}")
        for label, count in stats.get("node_types", {}).items():
            print(f"   - {label}: {count}")

        print(f"\n📊 总边数: {stats['total_edges']}")
        for relation, count in stats.get("edge_types", {}).items():
            desc = config.EDGE_TYPES.get(relation, relation)
            print(f"   - {relation} ({desc}): {count}")

        metrics = stats.get("supply_chain_metrics", {})
        if metrics:
            print(f"\n🔗 供应链分析:")
            print(f"   - 每个 API 平均供应商数: {metrics.get('avg_suppliers_per_api', 'N/A')}")
            print(f"   - ⚠️  单一来源 API 数量: {metrics.get('single_source_apis', 'N/A')}")
            print(f"   - ✓ 多来源 API 数量: {metrics.get('multi_source_apis', 'N/A')}")
            print(f"   - 药物相互作用数: {metrics.get('drug_interaction_count', 'N/A')}")

            top_suppliers = metrics.get("top_suppliers", {})
            if top_suppliers:
                print(f"\n🏭 供应最多 API 的制造商 (Top 5):")
                for mfg_id, count in top_suppliers.items():
                    # 查找名称
                    mfg_name = mfg_id
                    for m in MANUFACTURERS:
                        if m["id"] == mfg_id:
                            mfg_name = m["name"]
                            break
                    print(f"   - {mfg_name}: {count} 个 API")

            country_dist = metrics.get("manufacturer_by_country", {})
            if country_dist:
                print(f"\n🌍 制造商国家分布:")
                for country_id, count in country_dist.items():
                    country_name = country_id
                    for c in COUNTRIES:
                        if c["id"] == country_id:
                            country_name = c["name"]
                            break
                    print(f"   - {country_name}: {count} 家")

        print("\n" + "=" * 60)

    # ============================================================
    #  导出
    # ============================================================

    def export_csv(self, nodes_df: pd.DataFrame, edges_df: pd.DataFrame):
        """导出为 Neo4j 兼容 CSV"""
        # 节点 CSV
        nodes_df.to_csv(config.NODES_CSV, index=False, encoding="utf-8-sig")
        print(f"\n✓ 节点已保存: {config.NODES_CSV}")

        # 边 CSV
        edges_df.to_csv(config.EDGES_CSV, index=False, encoding="utf-8-sig")
        print(f"✓ 边已保存: {config.EDGES_CSV}")

    def export_stats(self, stats: Dict):
        """导出统计信息到 JSON"""
        with open(config.KG_STATS_FILE, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        print(f"✓ 统计报告已保存: {config.KG_STATS_FILE}")

    def export_neo4j_cypher(self, nodes_df: pd.DataFrame, edges_df: pd.DataFrame):
        """生成 Neo4j 导入用的 Cypher 脚本"""
        cypher_file = os.path.join(config.OUTPUT_DIR, "import_neo4j.cypher")

        with open(cypher_file, 'w', encoding='utf-8') as f:
            f.write("// ============================================\n")
            f.write("// 制药供应链知识图谱 - Neo4j 导入脚本\n")
            f.write("// ============================================\n\n")

            f.write("// 0. 创建索引（加速导入）\n")
            for label in nodes_df["label"].unique():
                f.write(f"CREATE INDEX IF NOT EXISTS FOR (n:{label}) ON (n.id);\n")
            f.write("\n")

            f.write("// 1. 导入节点\n")
            f.write("LOAD CSV WITH HEADERS FROM 'file:///pharma_kg_nodes.csv' AS row\n")
            f.write("CALL apoc.merge.node([row.label], {id: row.id}, {name: row.name}) YIELD node\n")
            f.write("RETURN count(node);\n\n")

            f.write("// 或者按类型分别导入：\n")
            for label in nodes_df["label"].unique():
                f.write(f"\n// 导入 {label} 节点\n")
                f.write(f"LOAD CSV WITH HEADERS FROM 'file:///pharma_kg_nodes.csv' AS row\n")
                f.write(f"WITH row WHERE row.label = '{label}'\n")
                f.write(f"MERGE (n:{label} {{id: row.id}})\n")
                f.write(f"SET n.name = row.name;\n")

            f.write("\n// 2. 导入边\n")
            for relation in edges_df["relation"].unique():
                f.write(f"\n// 导入 {relation} 关系\n")
                f.write(f"LOAD CSV WITH HEADERS FROM 'file:///pharma_kg_edges.csv' AS row\n")
                f.write(f"WITH row WHERE row.relation = '{relation}'\n")
                f.write(f"MATCH (a {{id: row.source}})\n")
                f.write(f"MATCH (b {{id: row.target}})\n")
                f.write(f"MERGE (a)-[r:{relation}]->(b);\n")

        print(f"✓ Neo4j Cypher 脚本已保存: {cypher_file}")
