"""
将知识图谱数据通过 Python Driver 直接导入 Neo4j
================================================
用法:
    python -m pharma_supply_chain.neo4j_import
    python -m pharma_supply_chain.neo4j_import --clear   # 先清空再导入
"""

import argparse
import csv
import os
import time
from collections import defaultdict

from neo4j import GraphDatabase

from . import config

# ============================================================
#  连接配置
# ============================================================
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def load_csv(filepath):
    """读取 CSV 文件为字典列表"""
    with open(filepath, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def import_to_neo4j(clear_first=False):
    """将 CSV 导入 Neo4j"""
    if not NEO4J_PASSWORD:
        raise RuntimeError("NEO4J_PASSWORD is not set")

    print("╔" + "═" * 58 + "╗")
    print("║  制药供应链知识图谱 → Neo4j 导入工具                    ║")
    print("╚" + "═" * 58 + "╝")

    # 1. 连接
    print(f"\n连接 Neo4j: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    driver.verify_connectivity()
    print("✓ 连接成功")

    # 2. 读取 CSV
    print(f"\n读取节点: {config.NODES_CSV}")
    nodes = load_csv(config.NODES_CSV)
    print(f"  → {len(nodes)} 个节点")

    print(f"读取边: {config.EDGES_CSV}")
    edges = load_csv(config.EDGES_CSV)
    print(f"  → {len(edges)} 条边")

    start = time.time()

    with driver.session() as session:
        # 3. 清空（可选）
        if clear_first:
            print("\n⚠ 清空现有数据...")
            session.run("MATCH (n) DETACH DELETE n")
            print("  ✓ 已清空")

        # 4. 创建索引（加速后续 MERGE）
        print("\n创建索引...")
        labels = set(row["label"] for row in nodes)
        for label in labels:
            try:
                session.run(
                    f"CREATE INDEX IF NOT EXISTS FOR (n:`{label}`) ON (n.id)"
                )
            except Exception:
                pass  # 索引可能已存在
        print(f"  ✓ 为 {len(labels)} 个节点类型创建索引")

        # 5. 导入节点（按类型批量）
        print("\n导入节点...")
        nodes_by_label = defaultdict(list)
        for row in nodes:
            nodes_by_label[row["label"]].append(row)

        total_nodes = 0
        for label, rows in nodes_by_label.items():
            # 获取该类型所有属性列
            prop_keys = [k for k in rows[0].keys() if k not in ("label",)]

            # 构建 SET 子句
            set_parts = ", ".join(
                f"n.`{k}` = row.`{k}`" for k in prop_keys if k != "id"
            )
            cypher = (
                f"UNWIND $rows AS row "
                f"MERGE (n:`{label}` {{id: row.id}}) "
                f"SET {set_parts}"
            )
            # 分批导入节点 (每批 500)
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                session.run(cypher, rows=[{k: r.get(k, "") for k in prop_keys} for r in batch])
            total_nodes += len(rows)
            print(f"  ✓ {label}: {len(rows)} 个")

        # 6. 导入边（按关系类型批量）
        print("\n导入边...")
        edges_by_rel = defaultdict(list)
        for row in edges:
            edges_by_rel[row["relation"]].append(row)

        total_edges = 0
        for relation, rows in edges_by_rel.items():
            # 额外属性
            extra_keys = [k for k in rows[0].keys() if k not in ("source", "target", "relation")]
            set_clause = ""
            if extra_keys:
                set_parts = ", ".join(f"r.`{k}` = row.`{k}`" for k in extra_keys)
                set_clause = f"SET {set_parts}"

            cypher = (
                f"UNWIND $rows AS row "
                f"MATCH (a {{id: row.source}}) "
                f"MATCH (b {{id: row.target}}) "
                f"MERGE (a)-[r:`{relation}`]->(b) "
                f"{set_clause}"
            )
            # 分批导入边 (每批 500)
            batch_size = 500
            for i in range(0, len(rows), batch_size):
                batch = rows[i:i + batch_size]
                session.run(
                    cypher,
                    rows=[
                        {k: r.get(k, "") for k in ["source", "target"] + extra_keys}
                        for r in batch
                    ],
                )
            total_edges += len(rows)
            desc = config.EDGE_TYPES.get(relation, relation)
            print(f"  ✓ {relation} ({desc}): {len(rows)} 条")

    elapsed = time.time() - start
    driver.close()

    print(f"\n{'=' * 60}")
    print(f"✅ 导入完成！耗时 {elapsed:.1f}s")
    print(f"   节点: {total_nodes} | 边: {total_edges}")
    print(f"\n🌐 打开 Neo4j Browser: http://localhost:7474")
    print(f"   用户名: {NEO4J_USER}")
    print(f"\n📝 试试这些 Cypher 查询:")
    print(f'   MATCH (n) RETURN labels(n)[0] AS type, count(*) ORDER BY count(*) DESC')
    print(f'   MATCH (d:Drug)-[:CONTAINS_API]->(a:API)-[:SUPPLIED_BY]->(m:Manufacturer) RETURN d,a,m LIMIT 50')
    print(f'   MATCH p=(d:Drug)-[*1..3]-(x) WHERE d.name="Heparin" RETURN p')
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description="Neo4j 导入工具")
    parser.add_argument("--clear", action="store_true", help="导入前清空数据库")
    args = parser.parse_args()
    import_to_neo4j(clear_first=args.clear)


if __name__ == "__main__":
    main()
