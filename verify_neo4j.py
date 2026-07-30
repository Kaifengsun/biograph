"""快速验证 Neo4j 中的图谱数据"""
import os

from neo4j import GraphDatabase

password = os.getenv("NEO4J_PASSWORD", "")
if not password:
    raise RuntimeError("NEO4J_PASSWORD is not set")
d = GraphDatabase.driver(
    os.getenv("NEO4J_URI", "bolt://localhost:7687"),
    auth=(os.getenv("NEO4J_USER", "neo4j"), password),
)
with d.session() as s:
    # 节点统计
    r = s.run("MATCH (n) RETURN labels(n)[0] AS type, count(*) AS cnt ORDER BY cnt DESC")
    print("=== 节点统计 ===")
    for rec in r:
        print(f"  {rec['type']}: {rec['cnt']}")

    # 边统计
    r = s.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt ORDER BY cnt DESC")
    print("\n=== 边统计 ===")
    for rec in r:
        print(f"  {rec['rel']}: {rec['cnt']}")

    # 供应链路径示例：Heparin
    print("\n=== Heparin 供应链 ===")
    r = s.run(
        "MATCH (d:Drug)-[:CONTAINS_API]->(a:API)"
        "-[:SUPPLIED_BY]->(m:Manufacturer)-[:LOCATED_IN]->(c:Country) "
        "WHERE d.name CONTAINS 'Heparin' "
        "RETURN d.name AS drug, a.name AS api, m.name AS mfg, c.name AS country"
    )
    for rec in r:
        print(f"  {rec['drug']} -> {rec['api']} -> {rec['mfg']} ({rec['country']})")
    
    # 多跳路径: 从 Cisplatin 出发
    print("\n=== Cisplatin 多跳路径 (Drug->API->Manufacturer->Country) ===")
    r = s.run(
        "MATCH (d:Drug)-[:CONTAINS_API]->(a:API)"
        "-[:SUPPLIED_BY]->(m:Manufacturer)-[:LOCATED_IN]->(c:Country) "
        "WHERE d.name CONTAINS 'Cisplatin' "
        "RETURN d.name AS drug, a.name AS api, m.name AS mfg, c.name AS country"
    )
    for rec in r:
        print(f"  {rec['drug']} -> {rec['api']} -> {rec['mfg']} ({rec['country']})")

    # 单源风险 API
    print("\n=== ⚠ 单一来源 API (高风险) ===")
    r = s.run(
        "MATCH (a:API)-[:SUPPLIED_BY]->(m:Manufacturer) "
        "WITH a, collect(m.name) AS suppliers, count(m) AS cnt "
        "WHERE cnt = 1 RETURN a.name AS api, suppliers[0] AS sole_supplier"
    )
    for rec in r:
        print(f"  {rec['api']} -> 唯一供应商: {rec['sole_supplier']}")

    # 连通子图
    print("\n=== 图谱连通性 ===")
    r = s.run("MATCH (n) WHERE NOT (n)--() RETURN count(n) AS isolated")
    iso = r.single()["isolated"]
    print(f"  孤立节点数: {iso}")

d.close()
print("\n✅ 验证完成！浏览器访问 http://localhost:7474 查看可视化")
