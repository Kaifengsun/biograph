import os
import csv
from pathlib import Path
from neo4j import GraphDatabase
from pharma_doc_pipeline.step_04_vectorize import link_chunks_to_neo4j

def import_kg_to_neo4j(
    nodes_csv: str = "output/pharma_kg_nodes.csv",
    edges_csv: str = "output/pharma_kg_edges.csv",
    neo4j_uri: str = "bolt://localhost:7687",
    neo4j_user: str = "neo4j",
    neo4j_pass: str = "Nb87891882"
):
    print("🚀 开始导入初始知识图谱 (KG)...")
    driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pass))
    
    with driver.session() as session:
        # 清空数据库 (确保是新库)
        print("清理现有数据库内容...")
        session.run("MATCH (n) DETACH DELETE n")
        
        # 建立索引
        print("建立约束和索引...")
        session.run("CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)")
        
        # 导入节点
        print("导入节点...")
        with open(nodes_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            nodes = list(reader)
            
            # 使用 UNWIND 批量导入
            query = """
            UNWIND $batch AS row
            CALL apoc.create.node([row.label, 'Entity'], {
                id: row.id,
                name: row.name,
                description: row.description,
                status: row.status,
                country: row.country,
                route: row.route,
                dosage_form: row.dosage_form,
                atc_code: row.atc_code,
                mechanism: row.mechanism,
                event_date: row.event_date,
                reason: row.reason,
                impact: row.impact,
                region: row.region,
                severity: row.severity
            }) YIELD node RETURN count(*)
            """
            
            # 由于部分属性可能不存在，Neo4j 会保留 null，我们可以用更安全的设置方式
            # 或者直接按标签归类
            # 为了避免缺少 APOC 插件，使用纯 Cypher:
            query_safe = """
            UNWIND $batch as row
            MERGE (n:Entity {id: row.id})
            SET n += row
            """
            session.run(query_safe, batch=nodes)

            
            # 为实体设置动态标签
            for row in nodes:
                if row.get("label"):
                    label = row["label"]
                    session.run(f"MATCH (n:Entity {{id: $id}}) SET n:{label}", id=row["id"])
                    
        print(f"成功导入 {len(nodes)} 个实体节点")
        
        # 导入关系边
        print("导入关系边...")
        with open(edges_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            edges = list(reader)
            
            # 批量导入边
            query_edge = """
            UNWIND $batch AS row
            MATCH (s:Entity {id: row.source})
            MATCH (t:Entity {id: row.target})
            CALL apoc.create.relationship(s, row.type, {
                weight: toFloat(row.weight),
                source_doc: row.source_doc,
                context: row.context,
                shared_target: row.shared_target,
                shared_indication: row.shared_indication
            }, t) YIELD rel RETURN count(*)
            """
            # 不用 APOC 的安全导入 (Neo4j 动态关系类型必须使用 APOC。如果没有 APOC 可以用 Python 循环分拨执行)
            
        # 安全处理边：按类型分组导入
        edges_by_type = {}
        for edge in edges:
            etype = edge["relation"]
            edges_by_type.setdefault(etype, []).append(edge)
            
        for etype, batch in edges_by_type.items():
            query_edges_safe = f"""
            UNWIND $batch AS row
            MATCH (s:Entity {{id: row.source}})
            MATCH (t:Entity {{id: row.target}})
            MERGE (s)-[r:{etype}]->(t)
            SET r += row
            """
            session.run(query_edges_safe, batch=batch)
            
        print(f"成功导入 {len(edges)} 条关系边")
        
    driver.close()
    
    print("\n🚀 开始将文档 Chunks 链接到 Neo4j...")
    link_chunks_to_neo4j(neo4j_uri=neo4j_uri, neo4j_auth=(neo4j_user, neo4j_pass))
    print("\n✅ 所有数据导入完毕！现在可以运行端对端测试了。")

if __name__ == "__main__":
    import_kg_to_neo4j()
