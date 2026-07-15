"""
Retrieval Evaluation Script for PharmGraphRAG
Computes Hit@K, MRR, NDCG@K against eval_queries.json ground truth.

Usage:
    python eval_retrieval.py                      # evaluate all methods
    python eval_retrieval.py --method graphrag     # single method
    python eval_retrieval.py --k 1 5 10 20        # custom K values
    python eval_retrieval.py --queries-only        # just show annotated queries
"""
import json
import argparse
import math
import time
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────
# Retrieval backends
# ─────────────────────────────────────────────

def load_faiss_chunk_ids(faiss_index_path: str) -> list[str]:
    """Load vector-position to chunk-id mapping from current or legacy artifacts."""
    index_path = Path(faiss_index_path)
    meta_path = index_path.with_suffix(".meta.json")
    legacy_ids_path = index_path.with_name(f"{index_path.stem}_ids.json")

    mapping_path = meta_path if meta_path.exists() else legacy_ids_path
    with open(mapping_path, encoding="utf-8") as f:
        metadata = json.load(f)

    if not isinstance(metadata, list):
        raise ValueError(f"Expected list metadata in {mapping_path}")

    chunk_ids = []
    for row in metadata:
        chunk_id = row.get("chunk_id") if isinstance(row, dict) else row
        if not chunk_id:
            raise ValueError(f"Missing chunk_id in {mapping_path}")
        chunk_ids.append(str(chunk_id))
    return chunk_ids


def retrieve_faiss(query: str, k: int, faiss_index_path: str, chunks_dir: str) -> list[str]:
    """Naive dense retrieval via FAISS + Youtu-Embedding."""
    import faiss
    import numpy as np
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(
        "tencent/Youtu-Embedding",
        trust_remote_code=True,
    )
    vec = model.encode([query], normalize_embeddings=True).astype("float32")

    index = faiss.read_index(faiss_index_path)
    id_map = load_faiss_chunk_ids(faiss_index_path)

    search_k = min(max(k * 4, k), index.ntotal)
    distances, indices = index.search(vec, search_k)
    ranked_ids = [id_map[i] for i in indices[0] if 0 <= i < len(id_map)]
    return _dedupe_ranked_ids(ranked_ids)[:k]


def retrieve_graphrag(query: str, k: int) -> list[str]:
    """PharmGraphRAG graph-enhanced retrieval."""
    from pharma_graphrag.main import GraphRAGEngine

    engine = GraphRAGEngine()
    engine.initialize()
    try:
        results = engine.retrieve(query, top_k=k)
        # Results should be list of dicts with "chunk_id" or "doc_id"
        chunk_ids = []
        for r in results:
            cid = r.get("chunk_id") or r.get("doc_id") or r.get("id")
            if cid:
                chunk_ids.append(str(cid))
        return chunk_ids[:k]
    finally:
        engine.close()


def retrieve_neo4j_bm25(query: str, k: int) -> list[str]:
    """BM25 full-text search via Neo4j fulltext index."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(
        "bolt://localhost:7687", auth=("neo4j", "Nb87891882")
    )
    try:
        with driver.session() as session:
            result = session.run(
                """
                CALL db.index.fulltext.queryNodes('chunk_fulltext', $query, {limit: $k})
                YIELD node, score
                RETURN node.chunk_id AS chunk_id, score
                ORDER BY score DESC
                LIMIT $k
                """,
                query=query, k=k
            )
            return [rec["chunk_id"] for rec in result if rec["chunk_id"]]
    finally:
        driver.close()


# ─────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────

def hit_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """1 if any relevant doc in top-k, else 0."""
    return float(any(r in relevant for r in retrieved[:k]))


def mrr(retrieved: list[str], relevant: list[str]) -> float:
    """Mean Reciprocal Rank."""
    for i, r in enumerate(_dedupe_ranked_ids(retrieved), 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def ndcg_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    """Normalized Discounted Cumulative Gain @ k."""
    def dcg(hits: list[int]) -> float:
        return sum(h / math.log2(i + 2) for i, h in enumerate(hits))

    relevance = _binary_relevance(retrieved, relevant, k)
    ideal = [1] * min(len(set(relevant)), k)
    dcg_val = dcg(relevance)
    idcg_val = dcg(ideal)
    return dcg_val / idcg_val if idcg_val > 0 else 0.0


def precision_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    return sum(_binary_relevance(retrieved, relevant, k)) / k


def recall_at_k(retrieved: list[str], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    return sum(_binary_relevance(retrieved, relevant, k)) / len(set(relevant))


def _binary_relevance(retrieved: list[str], relevant: list[str], k: int) -> list[int]:
    """Return binary relevance while preventing duplicate retrieval credit."""
    relevant_ids = set(relevant)
    credited = set()
    hits = []
    for chunk_id in retrieved[:k]:
        is_new_hit = chunk_id in relevant_ids and chunk_id not in credited
        hits.append(int(is_new_hit))
        if is_new_hit:
            credited.add(chunk_id)
    return hits


def _dedupe_ranked_ids(chunk_ids: list[str]) -> list[str]:
    """Preserve rank order while returning each chunk at most once."""
    return list(dict.fromkeys(chunk_ids))


# ─────────────────────────────────────────────
# Evaluation runner
# ─────────────────────────────────────────────

def evaluate_method(
    queries: list[dict],
    retrieve_fn,
    k_values: list[int],
    method_name: str,
    max_k: int,
) -> dict:
    """Run all queries through retrieve_fn, compute metrics."""
    results = {f"Hit@{k}": [] for k in k_values}
    results["MRR"] = []
    results["NDCG@10"] = []
    results["P@10"] = []
    results["R@10"] = []

    per_query = []
    skipped = 0

    for q in queries:
        if q.get("status") != "annotated":
            skipped += 1
            continue

        relevant = set(q.get("relevant_chunk_ids", []))
        if not relevant:
            skipped += 1
            continue

        try:
            t0 = time.time()
            retrieved = retrieve_fn(q["query"], max_k)
            latency = time.time() - t0
        except Exception as e:
            print(f"  [WARN] Query {q['query_id']} failed: {e}")
            retrieved = []
            latency = 0.0

        qr = {
            "query_id": q["query_id"],
            "query": q["query"][:60],
            "category": q.get("category"),
            "difficulty": q.get("difficulty"),
            "relevant": list(relevant),
            "retrieved_top5": retrieved[:5],
            "latency_s": round(latency, 2),
        }

        for k in k_values:
            h = hit_at_k(retrieved, relevant, k)
            results[f"Hit@{k}"].append(h)
            qr[f"Hit@{k}"] = h

        mrr_val = mrr(retrieved, relevant)
        results["MRR"].append(mrr_val)
        results["NDCG@10"].append(ndcg_at_k(retrieved, relevant, 10))
        results["P@10"].append(precision_at_k(retrieved, relevant, 10))
        results["R@10"].append(recall_at_k(retrieved, relevant, 10))
        qr["MRR"] = round(mrr_val, 4)

        per_query.append(qr)

    n = len(per_query)
    if n == 0:
        print(f"  [WARN] No annotated queries evaluated for {method_name}")
        return {}

    aggregated = {
        "method": method_name,
        "n_queries": n,
        "n_skipped": skipped,
    }
    for metric, values in results.items():
        if values:
            aggregated[metric] = round(sum(values) / len(values), 4)

    # By category
    categories = set(q.get("category") for q in per_query)
    aggregated["by_category"] = {}
    for cat in sorted(categories):
        cat_q = [q for q in per_query if q.get("category") == cat]
        if cat_q:
            aggregated["by_category"][cat] = {
                "n": len(cat_q),
                "Hit@5": round(sum(q.get("Hit@5", 0) for q in cat_q) / len(cat_q), 4),
                "MRR": round(sum(q.get("MRR", 0) for q in cat_q) / len(cat_q), 4),
            }

    aggregated["per_query"] = per_query
    return aggregated


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PharmGraphRAG Retrieval Evaluation")
    parser.add_argument("--method", choices=["faiss", "graphrag", "bm25", "all"],
                        default="faiss", help="Retrieval method to evaluate")
    parser.add_argument("--k", nargs="+", type=int, default=[1, 5, 10, 20],
                        help="K values for Hit@K metrics")
    parser.add_argument("--queries", default="data/eval_queries.json",
                        help="Evaluation query set path")
    parser.add_argument("--faiss-index", default="data/vectors/pharma_docs.faiss",
                        help="FAISS index file path")
    parser.add_argument("--chunks-dir", default="data/chunks",
                        help="Enriched chunk JSON directory")
    parser.add_argument("--output", default="data/eval_results.json",
                        help="Output results JSON path")
    parser.add_argument("--queries-only", action="store_true",
                        help="Just print annotated query statistics and exit")
    args = parser.parse_args()

    # Load queries
    with open(args.queries, encoding="utf-8") as f:
        queries = json.load(f)

    if args.queries_only:
        from collections import Counter
        cats = Counter(q["category"] for q in queries if q.get("status") == "annotated")
        diffs = Counter(q["difficulty"] for q in queries if q.get("status") == "annotated")
        annotated = [q for q in queries if q.get("status") == "annotated"]
        print(f"\nTotal queries: {len(queries)}")
        print(f"Annotated:     {len(annotated)}")
        print(f"Categories:    {dict(cats)}")
        print(f"Difficulty:    {dict(diffs)}")
        return

    max_k = max(args.k)
    all_results = {}

    methods_to_run = ["faiss", "graphrag", "bm25"] if args.method == "all" else [args.method]

    for method in methods_to_run:
        print(f"\n{'='*60}")
        print(f"  Evaluating: {method.upper()}")
        print(f"{'='*60}")

        if method == "faiss":
            if not Path(args.faiss_index).exists():
                print(f"  [SKIP] FAISS index not found: {args.faiss_index}")
                print("  Run step_04_vectorize.py first.")
                continue
            fn = lambda q, k: retrieve_faiss(q, k, args.faiss_index, args.chunks_dir)

        elif method == "graphrag":
            fn = lambda q, k: retrieve_graphrag(q, k)

        elif method == "bm25":
            fn = lambda q, k: retrieve_neo4j_bm25(q, k)

        result = evaluate_method(queries, fn, args.k, method, max_k)
        if result:
            all_results[method] = result
            print(f"\n  Results ({method}):")
            for k in args.k:
                print(f"    Hit@{k}:  {result.get(f'Hit@{k}', 0):.4f}")
            print(f"    MRR:    {result.get('MRR', 0):.4f}")
            print(f"    NDCG@10:{result.get('NDCG@10', 0):.4f}")
            if "by_category" in result:
                print(f"\n  By category:")
                for cat, stats in result["by_category"].items():
                    print(f"    {cat:20s}: Hit@5={stats['Hit@5']:.3f}  MRR={stats['MRR']:.3f}  (n={stats['n']})")

    if all_results:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(all_results, f, ensure_ascii=False, indent=2)
        print(f"\n  Saved: {out_path}")

        # Print comparison table if multiple methods
        if len(all_results) > 1:
            print(f"\n{'='*60}")
            print("  COMPARISON TABLE")
            print(f"{'='*60}")
            header = f"  {'Method':<12}" + "".join(f"  Hit@{k}" for k in args.k) + "     MRR  NDCG@10"
            print(header)
            print("  " + "-" * (len(header) - 2))
            for method, res in all_results.items():
                row = f"  {method:<12}"
                for k in args.k:
                    row += f"  {res.get(f'Hit@{k}', 0):6.4f}"
                row += f"  {res.get('MRR', 0):6.4f}  {res.get('NDCG@10', 0):7.4f}"
                print(row)


if __name__ == "__main__":
    main()
