"""
build_kg_enhancements.py
=========================
对现有 Neo4j 知识图谱进行两项增强：

1. 建立 Regulation 节点之间的 REFERENCES 边（跨标准引用关系）
   - ICH Q9 ↔ ICH Q10 ↔ ICH Q7 三角核心引用
   - EMA GMP → ICH Q7/Q9 / PIC/S 互认
   - FDA cGMP → ICH Q7 / 内部体系引用
   - 国家 GMP (NMPA / PMDA) → ICH Q7
   - WHO PQ → ICH Q7

2. 建立 DocChunk 父子层级边 (PARENT_CHUNK / CHILD_CHUNK)
   - 从 _enriched.json 中读取 parent_chunk_id / children_ids
   - 在 Neo4j 中 MERGE (parent)-[:PARENT_CHUNK_OF]->(child)

运行方式（Windows，激活项目 venv）：
    & "d:\\Projects\\financial knowledge graph\\Neo_StandardExtracter\\.venv\\Scripts\\python.exe" build_kg_enhancements.py

或命令行参数控制：
    --skip-refs          跳过 REFERENCES 边
    --skip-hierarchy     跳过 DocChunk 父子边
"""

import json
import argparse
import os
from pathlib import Path

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASS = os.getenv("NEO4J_PASSWORD", "")
CHUNKS_DIR = Path("data/chunks")


# ─────────────────────────────────────────────────────────────
# 1. 规管标准 REFERENCES 关系定义
# ─────────────────────────────────────────────────────────────

REFERENCES_EDGES = [
    # ICH 内部三角
    ("REG_ich_q9",  "REG_ich_q10", "harmonized_pair",
     "Q10 PQS explicitly requires integration with Q9 QRM framework"),
    ("REG_ich_q10", "REG_ich_q9",  "harmonized_pair",
     "Q10 Pharmaceutical Quality System is implemented via Q9 risk management"),
    ("REG_ich_q7",  "REG_ich_q9",  "applies_framework",
     "ICH Q7 API GMP applies QRM principles from Q9 throughout manufacturing lifecycle"),
    ("REG_ich_q9",  "REG_ich_q7",  "applies_framework",
     "Q9 risk tools (FMEA, fault tree) apply to API manufacturing governed by Q7"),
    ("REG_ich_q7",  "REG_ich_q10", "superseded_by_framework",
     "Q10 PQS provides the overarching quality system within which Q7 GMP operates"),
    ("REG_ich_q10", "REG_ich_q7",  "encompasses",
     "Q10 PQS integration covers API stages as defined in ICH Q7"),

    # EMA GMP ↔ ICH
    ("REG_ema_gmp", "REG_ich_q7",  "adopted_from",
     "EMA GMP EudraLex Vol.4 Part II for APIs is adopted from ICH Q7"),
    ("REG_ich_q7",  "REG_ema_gmp", "adopted_as",
     "ICH Q7 is incorporated as EMA GMP Part II in the EU regulatory framework"),
    ("REG_ema_gmp", "REG_ich_q9",  "implements",
     "EMA GMP Annex 20 Quality Risk Management implements ICH Q9 framework"),

    # EMA ↔ PIC/S 互认
    ("REG_ema_gmp",  "REG_pics_gmp", "mutual_recognition",
     "EMA and PIC/S mutually recognize GMP standards; EudraLex aligned with PIC/S PE009"),
    ("REG_pics_gmp", "REG_ema_gmp",  "mutual_recognition",
     "PIC/S PE009 GMP Guide maintained in alignment with EMA EudraLex Vol.4"),

    # FDA cGMP ↔ ICH Q7
    ("REG_fda_cgmp", "REG_ich_q7",  "aligned_with",
     "FDA 21 CFR 210/211 cGMP aligned with ICH Q7; FDA endorses Q7 for APIs"),
    ("REG_ich_q7",   "REG_fda_cgmp", "harmonizes",
     "ICH Q7 harmonizes US FDA 21 CFR 210/211 requirements for API manufacturing"),

    # FDA 内部体系
    ("REG_fda_drug_shortage", "REG_fda_cgmp", "governed_by",
     "Drug shortage reporting (21 CFR 314.81) embedded in cGMP compliance framework"),
    ("REG_fda_import_alert",  "REG_fda_cgmp", "enforces",
     "Import alerts (e.g., Import Alert 66-40) triggered by cGMP violations at foreign API sites"),
    ("REG_fda_import_alert",  "REG_fda_dmf",  "triggers_review",
     "Import alerts may trigger FDA review and suspension of associated Drug Master Files"),
    ("REG_fda_dmf",           "REG_fda_cgmp", "requires_compliance",
     "FDA Type II Drug Master File must document cGMP compliance for API manufacturing"),
    ("REG_fda_dmf",           "REG_ich_q7",   "structured_per",
     "FDA Type II DMF for APIs is structured per ICH Q7 API GMP guidelines"),
    ("REG_dea_schedule",      "REG_fda_cgmp", "co_regulated_by",
     "DEA-registered manufacturing of controlled substances must comply with FDA cGMP"),

    # USP → FDA
    ("REG_usp_monograph", "REG_fda_cgmp", "enforced_by",
     "USP monograph standards are legally enforceable quality standards under FDA cGMP"),

    # 国家 GMP → ICH Q7/Q10
    ("REG_nmpa_gmp", "REG_ich_q7",  "based_on",
     "China NMPA 2010 GMP is revised based on ICH Q7 API GMP and WHO GMP guidelines"),
    ("REG_nmpa_gmp", "REG_ich_q10", "incorporates",
     "NMPA GMP revisions incorporate ICH Q10 Pharmaceutical Quality System requirements"),
    ("REG_pmda_gmp", "REG_ich_q7",  "aligned_with",
     "Japan PMDA GMP Enforcement Regulation aligned with ICH Q7 for API manufacturing"),

    # PIC/S → ICH
    ("REG_pics_gmp", "REG_ich_q7",  "adopted_from",
     "PIC/S PE009 Part II adopted directly from ICH Q7 for API GMP inspections"),
    ("REG_pics_gmp", "REG_ich_q9",  "based_on",
     "PIC/S PE010 Quality Risk Management guidance based on ICH Q9 framework"),

    # WHO → ICH Q7
    ("REG_who_prequalification", "REG_ich_q7", "requires_compliance",
     "WHO Prequalification requires API suppliers to comply with ICH Q7 GMP"),
    ("REG_who_pq",               "REG_ich_q7", "requires_compliance",
     "WHO PQ Programme API inspections assess compliance with ICH Q7 GMP"),

    # WHO 内部两个节点
    ("REG_who_prequalification", "REG_who_pq",               "implemented_by",
     "WHO Prequalification is implemented through the WHO Prequalification Programme"),
    ("REG_who_pq",               "REG_who_prequalification",  "implements",
     "WHO PQ Programme is the mechanism for WHO Prequalification assessment"),
]


# ─────────────────────────────────────────────────────────────
# 2. 建立 REFERENCES 边
# ─────────────────────────────────────────────────────────────

def build_regulation_references(session):
    """创建所有 Regulation → REFERENCES → Regulation 边"""
    created = 0
    skipped = 0
    for src_id, tgt_id, rel_type, context in REFERENCES_EDGES:
        result = session.run(
            """
            MATCH (a:Regulation {id: $src_id})
            MATCH (b:Regulation {id: $tgt_id})
            MERGE (a)-[r:REFERENCES {relation_type: $rel_type}]->(b)
            ON CREATE SET r.context = $context
            RETURN r, a.name AS a_name, b.name AS b_name
            """,
            src_id=src_id, tgt_id=tgt_id,
            rel_type=rel_type, context=context,
        )
        record = result.single()
        if record:
            created += 1
            print(f"  ✓ {record['a_name']}  --[REFERENCES]-->  {record['b_name']}")
        else:
            skipped += 1
            print(f"  ⚠ 跳过 ({src_id} or {tgt_id} 节点不存在)")
    print(f"\n  REFERENCES 边: {created} 创建/确认, {skipped} 跳过")
    return created


# ─────────────────────────────────────────────────────────────
# 3. 建立 DocChunk 父子层级边
# ─────────────────────────────────────────────────────────────

def build_chunk_hierarchy(session):
    """
    从 _enriched.json 读取 parent_chunk_id，
    在 Neo4j 中建立 (parent)-[:PARENT_CHUNK_OF]->(child) 边
    """
    enriched_files = sorted(CHUNKS_DIR.glob("*_enriched.json"))
    if not enriched_files:
        enriched_files = sorted(CHUNKS_DIR.glob("*_chunks.json"))
    if not enriched_files:
        print("  ⚠ 无 chunk 文件，跳过层级边构建")
        return 0

    parent_child_pairs = []
    for ef in enriched_files:
        with open(ef, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        for c in chunks:
            pid = c.get("parent_chunk_id")
            cid = c.get("chunk_id")
            if pid and cid:
                parent_child_pairs.append({"parent_id": pid, "child_id": cid})

    if not parent_child_pairs:
        print("  ℹ 所有 chunk 的 parent_chunk_id 为 null，无层级关系需建立")
        return 0

    print(f"  发现 {len(parent_child_pairs)} 条父子关系")

    # 批量写入，每批 500 条
    batch_size = 500
    total = 0
    for i in range(0, len(parent_child_pairs), batch_size):
        batch = parent_child_pairs[i:i + batch_size]
        result = session.run(
            """
            UNWIND $batch AS pair
            MATCH (p:DocChunk {chunk_id: pair.parent_id})
            MATCH (c:DocChunk {chunk_id: pair.child_id})
            MERGE (p)-[:PARENT_CHUNK_OF]->(c)
            RETURN count(*) AS cnt
            """,
            batch=batch,
        )
        cnt = result.single()["cnt"]
        total += cnt
        print(f"  批次 {i // batch_size + 1}: {cnt} 条父子边")

    print(f"  DocChunk PARENT_CHUNK_OF 边: {total} 条")
    return total


# ─────────────────────────────────────────────────────────────
# 4. 创建缺失的 Regulation 节点（chunk 文件对应的 ICH 指南）
# ─────────────────────────────────────────────────────────────

MISSING_REGULATIONS = [
    # 这些 ICH 文件有 chunk 数据但 KG 中无 Regulation 节点
    ("REG_ich_q1",   "ICH Q1 Stability Testing",                "ICH", "原料药和制剂的稳定性测试指南"),
    ("REG_ich_q2",   "ICH Q2 Analytical Validation",            "ICH", "分析方法验证指南"),
    ("REG_ich_q3a",  "ICH Q3A Impurities in New Drug Substances","ICH", "新药物质中的杂质控制"),
    ("REG_ich_q3b",  "ICH Q3B Impurities in New Drug Products",  "ICH", "新药制剂中的杂质控制"),
    ("REG_ich_q3c",  "ICH Q3C Residual Solvents",               "ICH", "残留溶剂限度指南"),
    ("REG_ich_q3d",  "ICH Q3D Elemental Impurities",            "ICH", "元素杂质控制指南"),
    ("REG_ich_q4b",  "ICH Q4B Regulatory Acceptance of Pharmacopoeial Procedures","ICH","药典方法监管互认"),
    ("REG_ich_q5a",  "ICH Q5A Viral Safety of Biotechnology Products","ICH","生物技术产品病毒安全性"),
    ("REG_ich_q5b",  "ICH Q5B Quality of Biotechnology Products","ICH","生物技术产品表达构建体分析"),
    ("REG_ich_q5c",  "ICH Q5C Stability Testing of Biotechnological Products","ICH","生物技术产品稳定性测试"),
    ("REG_ich_q5d",  "ICH Q5D Derivation of Cell Substrates",   "ICH", "细胞基质衍生和鉴定"),
    ("REG_ich_q5e",  "ICH Q5E Comparability of Biotechnology Products","ICH","生物技术产品变更可比性"),
    ("REG_ich_q6a",  "ICH Q6A Specifications for New Drug Substances","ICH","新药物质规格测试程序"),
    ("REG_ich_q6b",  "ICH Q6B Specifications for Biotechnological Products","ICH","生物技术产品规格"),
    ("REG_who_eml",  "WHO Essential Medicines List",            "WHO", "WHO基本药物目录，指导各国药品选择"),
]

def create_missing_regulation_nodes(session):
    """创建 chunk 文件对应但 KG 中缺失的 Regulation 节点"""
    created = 0
    for reg_id, name, authority, description in MISSING_REGULATIONS:
        result = session.run(
            """
            MERGE (r:Regulation {id: $id})
            ON CREATE SET
                r.name = $name,
                r.authority = $authority,
                r.description = $description,
                r.label = 'Regulation'
            ON MATCH SET r.authority = $authority
            RETURN r, (r.name = $name) AS is_new
            """,
            id=reg_id, name=name, authority=authority, description=description
        )
        rec = result.single()
        if rec and rec["is_new"]:
            created += 1
            print(f"  ✚ 新增 Regulation: {name}")
        else:
            print(f"  ~ 已存在: {name}")
    print(f"\n  Regulation 节点: {created} 新增")
    return created


def link_documents_to_regulations(session):
    """
    将 Document 节点链接到对应的 Regulation 节点
    规则: Document.doc_id 以 reg_id 的后缀部分匹配
    例: Document{doc_id:'ich_q9'} → Regulation{id:'REG_ich_q9'}
    """
    result = session.run("MATCH (d:Document) RETURN d.doc_id AS doc_id")
    doc_ids = [rec["doc_id"] for rec in result]

    linked = 0
    for doc_id in doc_ids:
        # 尝试 REG_{doc_id} 格式
        reg_id = f"REG_{doc_id}"
        r = session.run(
            """
            MATCH (d:Document {doc_id: $doc_id})
            MATCH (r:Regulation {id: $reg_id})
            MERGE (d)-[:DESCRIBES]->(r)
            RETURN count(*) AS cnt
            """,
            doc_id=doc_id, reg_id=reg_id
        )
        cnt = r.single()["cnt"]
        if cnt:
            linked += 1
            print(f"  ↗ Document '{doc_id}' -[:DESCRIBES]-> Regulation '{reg_id}'")

    print(f"\n  Document-[:DESCRIBES]->Regulation: {linked} 条")
    return linked


# ─────────────────────────────────────────────────────────────
# 5. 主流程
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="增强 Neo4j 知识图谱")
    parser.add_argument("--skip-refs",       action="store_true", help="跳过 REFERENCES 边")
    parser.add_argument("--skip-hierarchy",  action="store_true", help="跳过 DocChunk 父子边")
    parser.add_argument("--skip-new-nodes",  action="store_true", help="跳过新增 Regulation 节点")
    parser.add_argument("--skip-doc-links",  action="store_true", help="跳过 Document-DESCRIBES-Regulation 边")
    args = parser.parse_args()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("❌ 未安装 neo4j 包。请运行: pip install neo4j")
        return

    print(f"🔌 连接 Neo4j: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    try:
        with driver.session() as session:
            # 0. 基本统计
            r = session.run("MATCH (n) RETURN labels(n)[0] AS lbl, count(n) AS cnt ORDER BY cnt DESC")
            print("\n── 当前节点分布 ──")
            for rec in r:
                print(f"  {rec['lbl']}: {rec['cnt']}")

            # 1. 新增缺失 Regulation 节点
            if not args.skip_new_nodes:
                print("\n── 步骤1: 新增缺失 Regulation 节点 ──")
                create_missing_regulation_nodes(session)

            # 2. 建立 REFERENCES 边
            if not args.skip_refs:
                print("\n── 步骤2: 建立 Regulation REFERENCES 边 ──")
                build_regulation_references(session)

            # 3. Document → Regulation 链接
            if not args.skip_doc_links:
                print("\n── 步骤3: Document -[:DESCRIBES]-> Regulation ──")
                link_documents_to_regulations(session)

            # 4. DocChunk 父子层级
            if not args.skip_hierarchy:
                print("\n── 步骤4: DocChunk 父子层级边 ──")
                build_chunk_hierarchy(session)

            # 5. 最终统计
            print("\n── 最终图谱统计 ──")
            r = session.run("MATCH ()-[rel]->() RETURN type(rel) AS t, count(rel) AS cnt ORDER BY cnt DESC LIMIT 25")
            for rec in r:
                print(f"  {rec['t']}: {rec['cnt']}")

        print("\n✅ 全部增强完成！")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
