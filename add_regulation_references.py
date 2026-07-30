"""
添加 Regulation-to-Regulation 跨标准关系到 KG。

根据官方 ICH 文档及各监管机构公开的相互引用关系建立以下边类型：
  REFERENCES     - A 文件正文引用/依赖 B 文件
  HARMONIZED_WITH - A 与 B 互相协调等效（双向）

运行后会：
1. 追加边到 output/pharma_kg_edges.csv
2. 生成 output/patch_regulation_refs.cypher（可直接在 Neo4j Browser 执行）
"""

import csv
import os

BASE = os.path.dirname(os.path.abspath(__file__))
EDGES_CSV  = os.path.join(BASE, "output", "pharma_kg_edges.csv")
PATCH_CQL  = os.path.join(BASE, "output", "patch_regulation_refs.cypher")

# ──────────────────────────────────────────────────────────────────────────────
# 跨标准关系定义（来源：ICH 官方文档 + FDA/EMA 指南 + WHO PQ 要求）
# 格式: (source_id, target_id, relation_type, evidence_note)
# ──────────────────────────────────────────────────────────────────────────────
REGULATION_EDGES = [
    # ── ICH Q 系列内部互引 ──────────────────────────────────────────────────
    # ICH Q10 Section 1.1 明确写道"应按 ICH Q9 中的说明使用质量风险管理"
    ("REG_ich_q10", "REG_ich_q9",  "REFERENCES",
     "ICH Q10 Sec1.1: 'quality risk management as described in ICH Q9 should be utilized'"),
    # ICH Q10 Appendix 1: Q10 与 Q7 合用，Q10 补充而非替代 Q7
    ("REG_ich_q10", "REG_ich_q7",  "REFERENCES",
     "ICH Q10 Appendix 1: Q10 applies in addition to ICH Q7 for API lifecycle"),
    # ICH Q9 Step 4 文件 Section 1 引用了质量体系框架 (Q10 predecessor)
    ("REG_ich_q9",  "REG_ich_q10", "REFERENCES",
     "ICH Q9 Section 1: risk management integrated into pharmaceutical quality system (Q10)"),
    # ICH Q7 Section 13 讨论风险分析，与 Q9 一脉相承
    ("REG_ich_q7",  "REG_ich_q9",  "REFERENCES",
     "ICH Q7 Sec13: risk analysis principles aligned with ICH Q9 framework"),

    # ── EMA GMP 跨 ICH 标准引用 ─────────────────────────────────────────────
    # EMA GMP Annex 11 Section 1 第一段明确引用 ICH Q9 作为风险管理基础
    ("REG_ema_gmp", "REG_ich_q9",  "REFERENCES",
     "EMA GMP Annex 11 Sec1: risk management principles as per ICH Q9"),
    # EMA GMP Part I Chapter 1 引用 ICH Q10 作为药品质量体系标准
    ("REG_ema_gmp", "REG_ich_q10", "REFERENCES",
     "EMA GMP Part I Ch1: pharmaceutical quality system per ICH Q10"),
    # EMA GMP Part II 完全基于 ICH Q7（等同采用）
    ("REG_ema_gmp", "REG_ich_q7",  "REFERENCES",
     "EMA GMP Part II = ICH Q7 (EU explicitly adopted ICH Q7 for API GMP)"),

    # ── FDA cGMP 跨 ICH 标准引用 ────────────────────────────────────────────
    # FDA 于 2016 年正式采纳 ICH Q7 作为 API GMP 指导性文件
    ("REG_fda_cgmp", "REG_ich_q7",  "REFERENCES",
     "FDA adopted ICH Q7 Guidance for Active Pharmaceutical Ingredient (2016)"),
    # FDA 多份指南文件（PQRI, PACMP 等）采用 ICH Q9 风险框架
    ("REG_fda_cgmp", "REG_ich_q9",  "REFERENCES",
     "FDA risk-based inspection framework aligned with ICH Q9"),
    # FDA 2011 Process Validation 指南采用 ICH Q10 生命周期方法
    ("REG_fda_cgmp", "REG_ich_q10", "REFERENCES",
     "FDA Process Validation Guidance 2011: product lifecycle approach aligned with ICH Q10"),

    # ── PIC/S 与 EMA GMP 协调 ───────────────────────────────────────────────
    # PIC/S PE 009 与 EMA GMP EudraLex Vol.4 互相协调（官方声明等效）
    ("REG_pics_gmp", "REG_ema_gmp", "HARMONIZED_WITH",
     "PIC/S PE 009 harmonized with EMA GMP EudraLex Vol.4 (official joint statement)"),
    ("REG_ema_gmp",  "REG_pics_gmp", "HARMONIZED_WITH",
     "EMA GMP EudraLex Vol.4 harmonized with PIC/S PE 009 (official joint statement)"),

    # ── WHO PQ 引用 ICH Q7 ──────────────────────────────────────────────────
    # WHO PQ 技术报告 TRS 902 要求 API 供应商符合 ICH Q7
    ("REG_who_pq",             "REG_ich_q7", "REFERENCES",
     "WHO PQ TRS 902: API manufacturers must comply with ICH Q7"),
    ("REG_who_prequalification", "REG_ich_q7", "REFERENCES",
     "WHO Prequalification Programme requires ICH Q7 compliance for API suppliers"),
    # WHO PQ 与 WHO Prequalification 互为引用（两套 WHO 计划相互链接）
    ("REG_who_pq", "REG_who_prequalification", "REFERENCES",
     "WHO PQ Programme references WHO Prequalification as overarching framework"),

    # ── 国家 GMP 引用 ICH 国际标准 ─────────────────────────────────────────
    # NMPA（中国）2010 GMP 修订版对 API 部分采纳 ICH Q7
    ("REG_nmpa_gmp", "REG_ich_q7", "REFERENCES",
     "NMPA GMP 2010 revision: API chapter harmonized with ICH Q7"),
    # NMPA GMP 整体框架参照 EU GMP
    ("REG_nmpa_gmp", "REG_ema_gmp", "REFERENCES",
     "NMPA GMP 2010 overall framework modeled on EU GMP EudraLex Vol.4"),
    # PMDA（日本）GMP 遵循 ICH Q7 API 标准
    ("REG_pmda_gmp", "REG_ich_q7", "REFERENCES",
     "PMDA GMP follows ICH Q7 for API manufacturing (Japan PIC/S member)"),

    # ── FDA 内部监管文件间引用 ──────────────────────────────────────────────
    # FDA 短缺政策通过 cGMP 违规触发
    ("REG_fda_drug_shortage", "REG_fda_cgmp", "REFERENCES",
     "FDA Drug Shortage Policy (FDASIA 2012 Sec506C): shortage often traced to cGMP failures"),
    # Import Alert 由 cGMP 不合规引发
    ("REG_fda_import_alert",  "REG_fda_cgmp", "REFERENCES",
     "FDA Import Alert 66-40: triggered by cGMP non-compliance at foreign API manufacturers"),
    # DMF 属于 cGMP 文件体系
    ("REG_fda_dmf", "REG_fda_cgmp", "REFERENCES",
     "FDA Drug Master File (DMF) is part of the cGMP documentation system (21 CFR 314.420)"),
]


def edges_already_exist(existing_rows: list[dict]) -> set[tuple]:
    """返回已存在的 (source, target, relation) 三元组集合"""
    return {(r["source"], r["target"], r["relation"]) for r in existing_rows}


def main():
    # ── 1. 读取现有边 ──────────────────────────────────────────────────────
    with open(EDGES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        existing = list(reader)

    existing_set = edges_already_exist(existing)
    new_edges = []

    for src, tgt, rel, _note in REGULATION_EDGES:
        if (src, tgt, rel) not in existing_set:
            new_edges.append({"source": src, "target": tgt, "relation": rel,
                               **{fn: "" for fn in fieldnames if fn not in ("source","target","relation")}})

    if not new_edges:
        print("所有跨标准关系已存在，无需重复添加。")
        return

    # ── 2. 追加到 CSV ──────────────────────────────────────────────────────
    with open(EDGES_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writerows(new_edges)

    print(f"已向 {EDGES_CSV} 追加 {len(new_edges)} 条跨标准关系。")

    # ── 3. 生成增量 Cypher 补丁 ──────────────────────────────────────────
    lines = [
        "// ============================================================",
        "// 增量补丁：Regulation 节点之间的 REFERENCES / HARMONIZED_WITH 关系",
        "// 生成于 add_regulation_references.py",
        "// 可直接在 Neo4j Browser 中执行，或通过 cypher-shell 导入",
        "// ============================================================",
        "",
    ]

    for src, tgt, rel, note in REGULATION_EDGES:
        lines += [
            f"// {note}",
            f"MATCH (a:Regulation {{id: '{src}'}}), (b:Regulation {{id: '{tgt}'}})",
            f"MERGE (a)-[:{rel}]->(b);",
            "",
        ]

    # 补充：若 REFERENCES/HARMONIZED_WITH 尚未在关系导入块里，则追加
    lines += [
        "// 确认关系统计",
        "MATCH ()-[r:REFERENCES]->() RETURN count(r) AS references_count;",
        "MATCH ()-[r:HARMONIZED_WITH]->() RETURN count(r) AS harmonized_count;",
    ]

    with open(PATCH_CQL, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"已生成 Cypher 补丁文件：{PATCH_CQL}")
    print()
    print("=== 新增的跨标准关系 ===")
    for src, tgt, rel, note in REGULATION_EDGES:
        if (src, tgt, rel) not in existing_set:
            print(f"  {src}  --[{rel}]-->  {tgt}")
    print()
    print("下一步：")
    print("  1. 确保 Neo4j 容器正在运行")
    print("  2. 将 output/patch_regulation_refs.cypher 复制到 Neo4j import 目录")
    print("     或直接在 Neo4j Browser 中粘贴执行")
    print("  3. 或使用 cypher-shell：")
    print('     cypher-shell -u neo4j -p "$NEO4J_PASSWORD" '
          "-f output/patch_regulation_refs.cypher")


if __name__ == "__main__":
    main()
