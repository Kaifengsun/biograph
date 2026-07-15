#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_qapairs.py — 为每个 DocChunk 生成假设性问答对，写入 Neo4j QAPair 节点

设计：
  (:DocChunk)-[:HAS_QUESTION]->(:QAPair {
      qa_id, chunk_id, doc_id,
      question,               # 问题文本（用于向量检索）
      answer,                 # 与 chunk 内容一致
      embedding,              # question 的向量（2048 dim，Youtu-Embedding）
      strategy,               # "C1"（内容丰富 >500c）| "C2"（简短）
      source,                 # "auto_generated" | "user_query"
      created_at
  })

可扩展：用户点赞/修正的问答对可直接 MERGE 新 QAPair 节点（source="user_query"），
        无需重新跑整个 pipeline。

检索流程（替换 FAISS）：
  query → embed → db.index.vector.queryNodes('qapair_embedding_index') →
  QAPair 节点 → [:HAS_QUESTION]<- DocChunk → GraphRAG 扩展

用法：
  python build_qapairs.py                    # 处理全部文档
  python build_qapairs.py --doc ich_q9       # 只处理 ich_q9
  python build_qapairs.py --dry-run          # 不写 Neo4j，只打印
  python build_qapairs.py --force            # 忽略断点，重新生成
  python build_qapairs.py --no-embed         # 跳过向量化（只生成问题文本）
"""

import os
import re
import json
import time
import argparse
import hashlib
from pathlib import Path
from typing import List, Dict, Optional

import requests
from neo4j import GraphDatabase

# ── 配置 ───────────────────────────────────────────────────────
NEO4J_URI      = "bolt://localhost:7687"
NEO4J_AUTH     = ("neo4j", "Nb87891882")
CHUNKS_DIR     = Path("data/chunks")
CHECKPOINT_FILE = Path("data/pipeline_cache/qapairs_checkpoint.json")

MOONSHOT_API_BASE = os.getenv("MOONSHOT_API_BASE_URL", "https://api.moonshot.cn/v1")
MOONSHOT_API_KEY  = os.getenv("MOONSHOT_API_KEY", "")
MOONSHOT_MODEL    = os.getenv("MOONSHOT_MODEL", "kimi-k2-5")

EMBED_API_BASE = os.getenv(
    "EMBED_API_BASE",
    "https://api.moonshot.cn/v1"          # 兼容 OpenAI 的 Embedding 端点
)
EMBED_MODEL    = os.getenv("EMBED_MODEL", "text-embedding-3-small")
EMBED_DIM      = 2048                      # Youtu-Embedding 维度（本地模型）

# C1: 内容 > 500 字符 → 生成 3 个问题
# C2: 内容 ≤ 500 字符 → 生成 1 个问题
C1_THRESHOLD  = 500
C1_QUESTIONS  = 3
C2_QUESTIONS  = 1

# ── Neo4j Cypher ──────────────────────────────────────────────

CREATE_VECTOR_INDEX = """
CREATE VECTOR INDEX qapair_embedding_index IF NOT EXISTS
FOR (qa:QAPair) ON (qa.embedding)
OPTIONS {
    indexConfig: {
        `vector.dimensions`: 2048,
        `vector.similarity_function`: 'cosine'
    }
}
"""

CREATE_FULLTEXT_INDEX = """
CREATE FULLTEXT INDEX qapair_question_fulltext IF NOT EXISTS
FOR (qa:QAPair) ON EACH [qa.question, qa.answer]
"""

CREATE_QA_CONSTRAINT = """
CREATE CONSTRAINT qapair_id_unique IF NOT EXISTS
FOR (qa:QAPair) REQUIRE qa.qa_id IS UNIQUE
"""

MERGE_QAPAIR_BATCH = """
UNWIND $rows AS row
MATCH (chunk:DocChunk {chunk_id: row.chunk_id})
MERGE (qa:QAPair {qa_id: row.qa_id})
SET qa.chunk_id   = row.chunk_id,
    qa.doc_id     = row.doc_id,
    qa.question   = row.question,
    qa.answer     = row.answer,
    qa.strategy   = row.strategy,
    qa.source     = row.source,
    qa.embedding  = row.embedding,
    qa.created_at = datetime()
MERGE (chunk)-[:HAS_QUESTION]->(qa)
"""

# 向量检索（供 retriever 使用，这里仅作参考文档）
VECTOR_SEARCH_CYPHER = """
CALL db.index.vector.queryNodes('qapair_embedding_index', $top_k, $query_vector)
YIELD node AS qa, score
MATCH (chunk:DocChunk)-[:HAS_QUESTION]->(qa)
RETURN qa.qa_id AS qa_id,
       qa.question AS question,
       chunk.chunk_id AS chunk_id,
       chunk.content AS content,
       chunk.doc_id AS doc_id,
       chunk.heading AS heading,
       score
ORDER BY score DESC
"""


# ── LLM 客户端 ─────────────────────────────────────────────────

def _call_moonshot(prompt: str, system: str, max_tokens: int = 512) -> str:
    """调用 Moonshot API 生成文本"""
    if not MOONSHOT_API_KEY:
        raise RuntimeError("MOONSHOT_API_KEY 未设置")

    url = f"{MOONSHOT_API_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MOONSHOT_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        "temperature": 0.8,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


# ── 问题生成 ──────────────────────────────────────────────────

SYSTEM_PROMPT = """你是一位制药行业质量管理和法规合规领域的专业顾问。
你的任务是：根据给定的 ICH/FDA/WHO 指南文本，生成研究人员或监管审查员
在实际工作中会提出的具体问题。

要求：
1. 问题应具体、可操作，能够通过该文本内容直接回答
2. 覆盖不同角度：定义/原则/操作步骤/数值限量/例外情况
3. 避免宽泛的"是什么"，用"如何"、"为什么"、"在什么条件下"等引导词
4. 每行一个问题，不加序号或前缀
5. 使用中文提问（内容为英文时也用中文）"""


def generate_questions(chunk: Dict, n: int) -> List[str]:
    """为 chunk 生成 n 个问题"""
    content = chunk.get("content", "")
    heading = chunk.get("heading", "").lstrip("#").strip()
    doc_id  = chunk.get("doc_id", "")

    prompt = f"""文档 ID：{doc_id}
章节标题：{heading}

内容：
{content[:2000]}

请为上述内容生成 {n} 个问题："""

    raw = _call_moonshot(prompt, SYSTEM_PROMPT, max_tokens=300)
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    # 去除可能的序号前缀（"1. " "- " "• " 等）
    cleaned = [re.sub(r'^[\d\-•*]+[.、\)]\s*', '', l) for l in lines]
    return [q for q in cleaned if len(q) > 5][:n]


# ── Embedding ─────────────────────────────────────────────────

_embed_model = None  # 缓存本地模型

def embed_texts(texts: List[str], use_local: bool = True) -> List[List[float]]:
    """
    批量 embed 文本。
    use_local=True: 使用本地 Youtu-Embedding 模型
    use_local=False: 使用 API
    """
    if not texts:
        return []

    if use_local:
        return _embed_local(texts)
    else:
        return _embed_api(texts)


def _embed_local(texts: List[str]) -> List[List[float]]:
    global _embed_model
    if _embed_model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        print("  [embed] 加载本地 Youtu-Embedding 模型...")
        _embed_model = SentenceTransformer(
            "tencent/Youtu-Embedding",
            trust_remote_code=True,
            model_kwargs={"trust_remote_code": True},
        )
    vecs = _embed_model.encode(texts, normalize_embeddings=True, batch_size=32)
    return vecs.tolist()


def _embed_api(texts: List[str]) -> List[List[float]]:
    """OpenAI 兼容 API Embedding"""
    api_key = os.getenv("MOONSHOT_API_KEY", "")
    url = f"{EMBED_API_BASE}/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    results = []
    BATCH = 20
    for i in range(0, len(texts), BATCH):
        batch = texts[i:i + BATCH]
        r = requests.post(url, json={"model": EMBED_MODEL, "input": batch},
                          headers=headers, timeout=60)
        r.raise_for_status()
        results.extend([d["embedding"] for d in r.json()["data"]])
    return results


# ── 断点续传 ──────────────────────────────────────────────────

def load_checkpoint() -> Dict[str, bool]:
    if CHECKPOINT_FILE.exists():
        return json.load(open(CHECKPOINT_FILE, encoding="utf-8"))
    return {}


def save_checkpoint(done: Dict[str, bool]):
    CHECKPOINT_FILE.parent.mkdir(parents=True, exist_ok=True)
    json.dump(done, open(CHECKPOINT_FILE, "w", encoding="utf-8"), ensure_ascii=False)


# ── 核心流程 ──────────────────────────────────────────────────

def setup_neo4j_indexes(session):
    """创建向量索引、全文索引、唯一约束"""
    for cypher in [CREATE_QA_CONSTRAINT, CREATE_VECTOR_INDEX, CREATE_FULLTEXT_INDEX]:
        try:
            session.run(cypher)
        except Exception as e:
            if "already exists" not in str(e).lower():
                print(f"  [WARN] 索引创建: {e}")


def chunk_has_qapairs(session, chunk_id: str) -> bool:
    r = session.run(
        "MATCH (:DocChunk {chunk_id: $cid})-[:HAS_QUESTION]->(:QAPair) RETURN count(*) AS n",
        cid=chunk_id
    ).single()
    return r["n"] > 0


def process_doc(session, doc_id: str, chunks: List[Dict],
                dry_run: bool, force: bool, use_embed: bool,
                checkpoint: Dict[str, bool]) -> int:
    """处理一个文档的所有 chunk，返回生成的 QAPair 数量"""
    total = 0
    batch_rows = []

    for chunk in chunks:
        chunk_id = chunk.get("chunk_id", "")
        content  = chunk.get("content", "").strip()

        if not content or not chunk_id:
            continue

        ck_key = f"{doc_id}::{chunk_id}"

        # 已处理且不强制重跑则跳过
        if not force and checkpoint.get(ck_key):
            continue

        # Neo4j 中已有则跳过（除非 force）
        if not force and not dry_run and chunk_has_qapairs(session, chunk_id):
            checkpoint[ck_key] = True
            continue

        # 策略
        strategy = "C1" if len(content) >= C1_THRESHOLD else "C2"
        n_q      = C1_QUESTIONS if strategy == "C1" else C2_QUESTIONS

        # 生成问题
        try:
            questions = generate_questions(chunk, n_q)
            time.sleep(0.3)  # 限速
        except Exception as e:
            print(f"    [WARN] {chunk_id} 问题生成失败: {e}")
            continue

        # Embedding
        embeddings = []
        if use_embed and questions:
            try:
                embeddings = embed_texts(questions, use_local=True)
            except Exception as e:
                print(f"    [WARN] {chunk_id} embedding 失败: {e}")
                embeddings = [[0.0] * EMBED_DIM] * len(questions)

        # 构造 rows
        for i, q in enumerate(questions):
            qa_id = f"{chunk_id}_qa_{hashlib.md5(q.encode()).hexdigest()[:8]}"
            row = {
                "qa_id":    qa_id,
                "chunk_id": chunk_id,
                "doc_id":   doc_id,
                "question": q,
                "answer":   content[:2000],   # 截断防止超限
                "strategy": strategy,
                "source":   "auto_generated",
                "embedding": embeddings[i] if i < len(embeddings) else [0.0] * EMBED_DIM,
            }
            batch_rows.append(row)
            total += 1

        checkpoint[ck_key] = True

        if dry_run:
            print(f"    [DRY] {chunk_id} ({strategy}) → {len(questions)} 个问题")
            for q in questions:
                print(f"      • {q}")

    # 批量写入 Neo4j
    if batch_rows and not dry_run:
        BATCH_SIZE = 50
        for i in range(0, len(batch_rows), BATCH_SIZE):
            session.run(MERGE_QAPAIR_BATCH, rows=batch_rows[i:i + BATCH_SIZE])

    return total


# ── 主函数 ────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="生成 QAPair 节点写入 Neo4j")
    parser.add_argument("--doc",      help="只处理指定 doc_id")
    parser.add_argument("--dry-run",  action="store_true", help="不写入 Neo4j")
    parser.add_argument("--force",    action="store_true", help="忽略断点重新生成")
    parser.add_argument("--no-embed", action="store_true", help="跳过向量化")
    args = parser.parse_args()

    use_embed = not args.no_embed

    if not MOONSHOT_API_KEY:
        print("[ERROR] 请设置环境变量 MOONSHOT_API_KEY")
        return

    checkpoint = load_checkpoint()
    driver     = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    with driver.session() as session:
        if not args.dry_run:
            print("[1/3] 创建 Neo4j 向量索引 / 约束...")
            setup_neo4j_indexes(session)

        # 统计 Neo4j 已有 QAPair
        existing = session.run("MATCH (:QAPair) RETURN count(*) AS n").single()["n"]
        print(f"[2/3] 当前 Neo4j QAPair 数量: {existing}")

        print("[3/3] 开始生成问答对...\n")
        grand_total = 0

        json_files = sorted(CHUNKS_DIR.glob("*_enriched.json"))
        if args.doc:
            json_files = [f for f in json_files
                          if f.stem.replace("_enriched", "") == args.doc]
            if not json_files:
                print(f"[ERROR] 找不到文档 {args.doc}")
                return

        for json_file in json_files:
            doc_id = json_file.stem.replace("_enriched", "")
            data   = json.load(open(json_file, encoding="utf-8"))
            valid  = [c for c in data if c.get("content", "").strip()]

            if not valid:
                print(f"  {doc_id:<35} 跳过（JSON 无有效 chunk）")
                continue

            print(f"  {doc_id} ({len(valid)} chunks)...")
            count = process_doc(
                session=session,
                doc_id=doc_id,
                chunks=valid,
                dry_run=args.dry_run,
                force=args.force,
                use_embed=use_embed,
                checkpoint=checkpoint,
            )
            print(f"    → 生成 {count} 个 QAPair")
            grand_total += count

            if not args.dry_run:
                save_checkpoint(checkpoint)

    driver.close()

    # ── 最终统计 ────────────────────────────────────────
    driver2 = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)
    with driver2.session() as s:
        total_qa = s.run("MATCH (:QAPair) RETURN count(*) AS n").single()["n"]
        total_hq = s.run("MATCH ()-[:HAS_QUESTION]->() RETURN count(*) AS n").single()["n"]
        print(f"\n[DONE] 本次新增: {grand_total} 个 QAPair")
        print(f"  QAPair 节点总计:   {total_qa}")
        print(f"  HAS_QUESTION 边:   {total_hq}")
    driver2.close()


if __name__ == "__main__":
    main()
