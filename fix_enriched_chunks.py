"""
fix_enriched_chunks.py
========================
一次性快速修脚本:
  1. 清洗所有 *_enriched.json:
       - 去重 (同 chunk_id 保留 content 最长的那份)
       - 过滤空 content
  2. 更新 Neo4j:
       - 用清洗后内容 MERGE DocChunk (更新 content/heading/parents_context)
       - 删除清洗后消失的孤儿空 DocChunk 节点
  3. 补建 PARENT_CHUNK_OF 边 (基于清洗后 JSON 的 parents_context)

不需要任何 LLM / embedding API, 几分钟内完成。
FAISS 不动 (空向量不会被检索命中, 不影响效果)。

运行:
    python fix_enriched_chunks.py
    python fix_enriched_chunks.py --dry-run   # 只统计, 不写
    python fix_enriched_chunks.py --doc ich_q9  # 只修一个文档
"""

import json
import argparse
from pathlib import Path
from collections import defaultdict

NEO4J_URI  = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "Nb87891882"
CHUNKS_DIR = Path("data/chunks")


# ════════════════════════════════════════════════════════════════
# 1. 清洗 enriched JSON
# ════════════════════════════════════════════════════════════════

def clean_enriched_file(path: Path, dry_run: bool = False):
    """
    返回 (cleaned_list, removed_ids_set)
    - cleaned_list: 去重 + 过滤后的 chunk 列表
    - removed_ids:  原 JSON 中有, 清洗后消失的 chunk_id 集合
    """
    data = json.load(open(path, encoding="utf-8"))
    original_ids = {c.get("chunk_id") for c in data}

    # 去重: 同 chunk_id 保留 content 最长的
    seen = {}
    for c in data:
        cid = c.get("chunk_id", "")
        prev = seen.get(cid)
        if prev is None or len(c.get("content", "")) > len(prev.get("content", "")):
            seen[cid] = c

    # 过滤空 content
    cleaned = [c for c in seen.values() if c.get("content", "").strip()]
    cleaned_ids = {c["chunk_id"] for c in cleaned}
    removed_ids = original_ids - cleaned_ids

    n_before = len(data)
    n_after  = len(cleaned)
    n_dup    = len(data) - len(seen)         # 重复记录数 (原始行数 - 去重后数)
    n_empty  = len(seen) - len(cleaned)      # 去重后仍为空的 chunk 数

    if n_dup > 0 or n_empty > 0:
        print(f"  {path.name}: {n_before} → {n_after} "
              f"(去重 -{n_dup}, 空 chunk -{n_empty})")
        if not dry_run:
            # 保留原始字段顺序 / 不改变已有的 summary 等字段
            json.dump(cleaned, open(path, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
    else:
        print(f"  {path.name}: OK (无需修改)")

    return cleaned, removed_ids


# ════════════════════════════════════════════════════════════════
# 2. 更新 Neo4j
# ════════════════════════════════════════════════════════════════

def update_neo4j_chunks(session, cleaned: list, removed_ids: set) -> dict:
    """
    a) 对清洗后保留的每个 chunk, MERGE 并 SET 正确字段
    b) 删除孤儿空 DocChunk 节点 (removed_ids 中的)
    返回统计 {updated, deleted}
    """
    updated = 0
    # 批量更新 (100条/批)
    batch = []
    for c in cleaned:
        batch.append({
            "chunk_id":       c.get("chunk_id", ""),
            "heading":        c.get("heading", ""),
            "content":        c.get("content", ""),
            "parents_context": c.get("parents_context", ""),
            "level":          c.get("level", 1),
            "summary":        c.get("summary", ""),
        })
        if len(batch) >= 100:
            r = session.run(
                """
                UNWIND $batch AS row
                MATCH (c:DocChunk {chunk_id: row.chunk_id})
                SET c.heading         = row.heading,
                    c.content         = row.content,
                    c.parents_context = row.parents_context,
                    c.level           = row.level,
                    c.summary         = row.summary
                """,
                batch=batch
            )
            updated += r.consume().counters.properties_set // 6
            batch = []
    if batch:
        r = session.run(
            """
            UNWIND $batch AS row
            MATCH (c:DocChunk {chunk_id: row.chunk_id})
            SET c.heading         = row.heading,
                c.content         = row.content,
                c.parents_context = row.parents_context,
                c.level           = row.level,
                c.summary         = row.summary
            """,
            batch=batch
        )
        updated += r.consume().counters.properties_set // 6

    # 删除孤儿空节点
    deleted = 0
    if removed_ids:
        r = session.run(
            """
            UNWIND $ids AS cid
            MATCH (c:DocChunk {chunk_id: cid})
            WHERE c.content IS NULL OR c.content = ''
            DETACH DELETE c
            """,
            ids=list(removed_ids)
        )
        deleted = r.consume().counters.nodes_deleted

    return {"updated": updated, "deleted": deleted}


# ════════════════════════════════════════════════════════════════
# 3. 补建 PARENT_CHUNK_OF 边
# ════════════════════════════════════════════════════════════════

def rebuild_parent_chunk_of(session, doc_id: str, cleaned: list) -> int:
    """
    用 parents_context 字段反查父 chunk_id, 建立 PARENT_CHUNK_OF 边。

    parents_context 是面包屑字符串, 如 "4. GENERAL... > 4.1. Resp..."
    父级标题 = 面包屑最后一段
    通过 (doc_id + heading like '%父级标题%') 找父 chunk
    """
    # 先加载该文档所有 chunk 的 heading → chunk_id 映射
    rows = list(session.run(
        "MATCH (c:DocChunk {doc_id: $doc_id}) "
        "RETURN c.chunk_id AS cid, c.heading AS h",
        doc_id=doc_id
    ))
    # heading → chunk_id (取第一个匹配)
    heading_map = {}
    for r in rows:
        h = (r["h"] or "").strip().lstrip("#").strip().lower()
        if h and h not in heading_map:
            heading_map[h] = r["cid"]

    def find_parent_cid(parents_context: str) -> str:
        """从面包屑中取最后一级标题, 在 heading_map 里查找"""
        if not parents_context:
            return ""
        parts = [p.strip() for p in parents_context.split(">")]
        # 尝试从最后一级往前找
        for part in reversed(parts):
            key = part.lstrip("#").strip().lower()
            if key in heading_map:
                return heading_map[key]
        return ""

    created = 0
    for c in cleaned:
        ctx = c.get("parents_context", "").strip()
        if not ctx:
            continue
        child_id  = c.get("chunk_id", "")
        parent_id = find_parent_cid(ctx)
        if not parent_id or parent_id == child_id:
            continue

        r = session.run(
            """
            MATCH (parent:DocChunk {chunk_id: $pid})
            MATCH (child:DocChunk  {chunk_id: $cid})
            MERGE (parent)-[:PARENT_CHUNK_OF]->(child)
            RETURN count(*) AS cnt
            """,
            pid=parent_id, cid=child_id
        )
        row = r.single()
        if row and row["cnt"] > 0:
            created += 1

    return created


# ════════════════════════════════════════════════════════════════
# 4. 主流程
# ════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--doc", type=str, default="",
                        help="只处理指定 doc_id 的 enriched JSON")
    args = parser.parse_args()

    # 找到所有 enriched JSON
    if args.doc:
        paths = list(CHUNKS_DIR.glob(f"{args.doc}_enriched.json"))
    else:
        paths = sorted(CHUNKS_DIR.glob("*_enriched.json"))

    if not paths:
        print("[WARN] 未找到 enriched JSON 文件")
        return

    # ── Step 1: 清洗 JSON ──
    print("=== Step 1: 清洗 enriched JSON ===")
    doc_results = {}  # doc_id → (cleaned_list, removed_ids)
    total_removed = 0
    for p in paths:
        doc_id = p.stem.replace("_enriched", "")
        cleaned, removed = clean_enriched_file(p, dry_run=args.dry_run)
        doc_results[doc_id] = (cleaned, removed)
        total_removed += len(removed)

    print(f"\n共删除 {total_removed} 个重复/空 chunk")

    if args.dry_run:
        print("[DRY RUN] 跳过 Neo4j 更新")
        return

    # ── Step 2 & 3: 更新 Neo4j ──
    print("\n=== Step 2: 更新 Neo4j ===")
    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        return

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))
    total_updated = 0
    total_deleted = 0
    total_edges   = 0

    try:
        with driver.session() as session:
            for doc_id, (cleaned, removed) in doc_results.items():
                if not cleaned:
                    continue

                # 更新内容 + 删孤儿
                stats = update_neo4j_chunks(session, cleaned, removed)
                total_updated += stats["updated"]
                total_deleted += stats["deleted"]

                # 补建 PARENT_CHUNK_OF 边
                edges = rebuild_parent_chunk_of(session, doc_id, cleaned)
                total_edges += edges

                if stats["deleted"] > 0 or edges > 0:
                    print(f"  {doc_id}: "
                          f"updated={stats['updated']} "
                          f"deleted={stats['deleted']} "
                          f"new_PARENT_edges={edges}")

            # 最终统计
            r1 = session.run("MATCH (c:DocChunk) RETURN count(c) AS n").single()
            r2 = session.run("MATCH ()-[:PARENT_CHUNK_OF]->() RETURN count(*) AS n").single()
            print(f"\n-- 最终状态 --")
            print(f"  DocChunk 节点: {r1['n']}")
            print(f"  PARENT_CHUNK_OF 边: {r2['n']}")
            print(f"  本次 更新={total_updated} 删除={total_deleted} 新建边={total_edges}")
    finally:
        driver.close()

    print("\n[DONE]")


if __name__ == "__main__":
    main()
