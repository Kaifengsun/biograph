"""诊断图谱数据密度，找出需要补充的地方"""
from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "Nb87891882"))
with d.session() as s:

    print("=" * 60)
    print("  制药供应链知识图谱 — 数据密度诊断报告")
    print("=" * 60)

    # 1. 没有 API 的药品（Drug→API 边缺失）
    r = s.run(
        "MATCH (d:Drug) WHERE NOT (d)-[:CONTAINS_API]->() "
        "RETURN d.name AS drug ORDER BY drug"
    )
    rows = list(r)
    print(f"\n❌ 无 API 关联的药品 ({len(rows)} 个):")
    for rec in rows: print(f"   - {rec['drug']}")

    # 2. 没有供应商的 API
    r = s.run(
        "MATCH (a:API) WHERE NOT (a)-[:SUPPLIED_BY]->() "
        "RETURN a.name AS api ORDER BY api"
    )
    rows = list(r)
    print(f"\n❌ 无供应商的 API ({len(rows)} 个):")
    for rec in rows: print(f"   - {rec['api']}")

    # 3. 只有 1 个供应商的 API（单一来源风险）
    r = s.run(
        "MATCH (a:API)-[:SUPPLIED_BY]->(m:Manufacturer) "
        "WITH a, count(m) AS cnt WHERE cnt = 1 "
        "RETURN a.name AS api, cnt ORDER BY api"
    )
    rows = list(r)
    print(f"\n⚠️  单一来源 API ({len(rows)} 个) — 供应链风险高:")
    for rec in rows: print(f"   - {rec['api']}")

    # 4. 无药物相互作用记录的药品
    r = s.run(
        "MATCH (d:Drug) WHERE NOT (d)-[:INTERACTS_WITH]-() "
        "RETURN d.name AS drug ORDER BY drug"
    )
    rows = list(r)
    print(f"\n⚠️  无药物相互作用记录的药品 ({len(rows)} 个):")
    for rec in rows: print(f"   - {rec['drug']}")

    # 5. 无短缺事件记录的药品
    r = s.run(
        "MATCH (d:Drug) WHERE NOT (d)-[:HAD_SHORTAGE]->() "
        "RETURN d.name AS drug ORDER BY drug"
    )
    rows = list(r)
    print(f"\n📊 无短缺事件记录的药品 ({len(rows)} 个 / 共47):")
    for rec in rows: print(f"   - {rec['drug']}")

    # 6. 度数最高的节点（图中枢纽）
    r = s.run(
        "MATCH (n)-[r]-() "
        "RETURN n.name AS name, labels(n)[0] AS type, count(r) AS degree "
        "ORDER BY degree DESC LIMIT 15"
    )
    print(f"\n🔗 图中度数最高的节点 (Top 15 枢纽):")
    for rec in r:
        print(f"   [{rec['type']:15}] {rec['name']:<40} 度={rec['degree']}")

    # 7. 国家视角：各国制造商数 vs API 供应量
    r = s.run(
        "MATCH (m:Manufacturer)-[:LOCATED_IN]->(c:Country) "
        "OPTIONAL MATCH (a:API)-[:SUPPLIED_BY]->(m) "
        "RETURN c.name AS country, count(DISTINCT m) AS manufacturers, "
        "count(DISTINCT a) AS apis_supplied "
        "ORDER BY apis_supplied DESC"
    )
    print(f"\n🌍 各国制造商 vs API 供应量:")
    print(f"   {'国家':<25} {'制造商数':>8} {'供应API数':>10}")
    print(f"   {'-'*45}")
    for rec in r:
        print(f"   {rec['country']:<25} {rec['manufacturers']:>8} {rec['apis_supplied']:>10}")

    # 8. 总结建议
    r1 = s.run("MATCH (d:Drug) WHERE NOT (d)-[:CONTAINS_API]->() RETURN count(*) AS n").single()["n"]
    r2 = s.run("MATCH (a:API) WHERE NOT (a)-[:SUPPLIED_BY]->() RETURN count(*) AS n").single()["n"]
    r3 = s.run("MATCH (d:Drug) WHERE NOT (d)-[:INTERACTS_WITH]-() RETURN count(*) AS n").single()["n"]

    print(f"\n{'=' * 60}")
    print("  💡 数据补充优先级建议")
    print(f"{'=' * 60}")
    print(f"  优先级 1 — {r1} 个药品缺少 API 关联 → 补充 CONTAINS_API 边")
    print(f"  优先级 2 — {r2} 个 API 缺少供应商 → 补充 SUPPLIED_BY 边")
    print(f"  优先级 3 — {r3} 个药品无相互作用记录 → 从 DrugBank 导入交互数据")
    print(f"  优先级 4 — 所有药品缺 price/stock_level 属性 → 对接 FDA shortage DB")
    print(f"  优先级 5 — 缺少 Distributor（经销商）节点类型 → 补充分销层级")

d.close()
