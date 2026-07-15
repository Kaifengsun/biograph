"""
retrieval_ablation.py — 3阶段 GraphRAG 消融实验
=================================================
4 变体:
  A: Stage 1 only (HyDE + 向量检索)
  B: Stage 1 + Stage 2 (加入自顶向下结构探索)
  C: Stage 1 + Stage 2 + Stage 3 随机游走
  D: 完整流水线 (Stage 1+2+3 含 LLM 引导游走)

指标: Recall@5, Recall@10, MRR
"""
import json
import time
import random
import re
import sys
import os
import numpy as np
from pathlib import Path
from typing import List, Dict, Optional, Set

sys.path.insert(0, str(Path(__file__).parent))

# ─────────────────────────────────────────────
#  配置 & 依赖
# ─────────────────────────────────────────────
from pharma_graphrag.config import GraphRAGConfig
from pharma_graphrag.retriever import GraphRAGRetriever, ChunkResult, RetrievalResult

# ─────────────────────────────────────────────
#  工具：doc_id 规范化映射
# ─────────────────────────────────────────────
DOC_ID_MAP = {
    # eval_queries.json  →  Neo4j doc_id
    "EMA GMP Annex 11":      ["ema_gmp_annex11", "ema_gmp_annex_11"],
    "EMA GMP Annex11":       ["ema_gmp_annex11", "ema_gmp_annex_11"],
    "ICH M7 R2":             ["ich_m7_r2"],
    "ICH Q10":               ["ich_q10"],
    "ICH Q11":               ["ich_q11"],
    "ICH Q12":               ["ich_q12"],
    "ICH Q13":               ["ich_q13"],
    "ICH Q14":               ["ich_q14"],
    "ICH Q1A":               ["ich_q1a"],
    "ICH Q1B":               ["ich_q1b"],
    "ICH Q1C":               ["ich_q1c"],
    "ICH Q1D":               ["ich_q1d"],
    "ICH Q1E":               ["ich_q1e"],
    "ICH Q2R2":              ["ich_q2r2"],
    "ICH Q3A":               ["ich_q3a_r2"],
    "ICH Q3B":               ["ich_q3b_r2"],
    "ICH Q3C":               ["ich_q3c_r9"],
    "ICH Q3D":               ["ich_q3d_r2"],
    "ICH Q3E":               ["ich_q3e_draft"],
    "ICH Q4B":               ["ich_q4b"],
    "ICH Q6A":               ["ich_q6a"],
    "ICH Q6B":               ["ich_q6b"],
    "ICH Q7":                ["ich_q7"],
    "ICH Q9":                ["ich_q9"],
    "FDA CGMP Guidance":     ["fda_cgmp_guidance"],
    "WHO EML":               ["who_eml_2023"],
    "WHO Stability Q1F":     ["who_stability_q1f"],
}

def normalize_doc_id_to_store(doc_name: str) -> List[str]:
    """将 doc 名称映射到 chunk store doc_id (lowercase + underscore 格式)"""
    clean = doc_name.strip()
    # Direct map
    if clean in DOC_ID_MAP:
        return DOC_ID_MAP[clean]
    # Partial match
    for k, v in DOC_ID_MAP.items():
        if k.lower() in clean.lower() or clean.lower() in k.lower():
            return v
    # Fallback
    return [re.sub(r'\s+', '_', clean.lower())]


def normalize_doc_ids(relevant_docs: List[str]) -> List[str]:
    """将 eval_queries 中的 doc 名称映射到 chunk store doc_ids"""
    out = []
    for rd in relevant_docs:
        out.extend(normalize_doc_id_to_store(rd))
    return list(set(out))


def convert_eval_chunk_id(old_id: str) -> str:
    """
    将 eval_queries.json 中的 chunk_id 转为 chunk store 格式。
    例: 'EMA GMP Annex 11_1' → 'ema_gmp_annex_11_1'
         'ICH M7 R2_7'       → 'ich_m7_r2_7'
    """
    return re.sub(r'\s+', '_', old_id.strip().lower())


def dedupe_ranked_ids(chunk_ids: List[str]) -> List[str]:
    """Preserve first occurrence while removing duplicate retrieval credit."""
    seen = set()
    ranked = []
    for chunk_id in chunk_ids:
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            ranked.append(chunk_id)
    return ranked


def weighted_reciprocal_rank_fusion(
    ranked_lists: List[List[str]],
    weights: Optional[List[float]] = None,
    rank_constant: int = 10,
) -> List[str]:
    """Fuse retrieval channels so graph evidence can compete for top-k ranks."""
    if weights is None:
        weights = [1.0] * len(ranked_lists)
    if len(weights) != len(ranked_lists):
        raise ValueError("weights must match ranked_lists")

    scores: Dict[str, float] = {}
    first_seen: Dict[str, tuple] = {}
    for list_index, (chunk_ids, weight) in enumerate(zip(ranked_lists, weights)):
        for rank, chunk_id in enumerate(dedupe_ranked_ids(chunk_ids), 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + (
                weight / (rank_constant + rank)
            )
            first_seen.setdefault(chunk_id, (list_index, rank))

    return sorted(
        scores,
        key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id]),
    )


# ─────────────────────────────────────────────
#  Ground Truth 构建器
# ─────────────────────────────────────────────
class GroundTruthBuilder:
    """
    为每个查询构建 ground truth chunk_id 集合 (chunk store 格式)。
    
    策略:
      1. 优先用 eval_queries.json 中已标注的 relevant_chunk_ids
         (format 'EMA GMP Annex 11_1' → 'ema_gmp_annex_11_1')
      2. 如无标注，在 relevant_docs 对应的 chunk store 文件中做关键词搜索
    """
    def __init__(
        self,
        chunks_dir: Path = Path("data/chunks"),
        allow_keyword_fallback: bool = False,
    ):
        self.chunks_dir = chunks_dir
        self.allow_keyword_fallback = allow_keyword_fallback
        self._chunk_store: Optional[Dict] = None  # lazy
        self.last_source = "none"

    def _load_store(self):
        """加载所有 chunk JSON 文件，建立 chunk_id → content 索引"""
        if self._chunk_store is not None:
            return
        store = {}
        for jf in self.chunks_dir.glob("*_enriched.json"):
            try:
                with open(jf, encoding="utf-8") as f:
                    items = json.load(f)
                if isinstance(items, list):
                    for it in items:
                        cid = it.get("chunk_id", it.get("id", ""))
                        if cid:
                            store[cid] = it
                elif isinstance(items, dict):
                    for cid, it in items.items():
                        store[cid] = it
            except Exception:
                pass
        self._chunk_store = store
        print(f"  GroundTruthBuilder: loaded {len(store)} chunks from store")

    def build_for_query(self, query: dict) -> Set[str]:
        """返回 ground-truth chunk_id 集合 (chunk store 格式)"""
        self._load_store()
        self.last_source = "none"
        q_text = query.get("query", "")
        relevant_docs = query.get("relevant_docs", [])

        # 1. 已有人工标注的 chunk_ids → 直接转换格式
        annotated = query.get("relevant_chunk_ids", [])
        if annotated:
            resolved = set()
            for cid in annotated:
                converted = convert_eval_chunk_id(cid)
                if converted in self._chunk_store:
                    resolved.add(converted)
            if resolved:
                self.last_source = "manual_annotation"
                return resolved

        # Keyword-derived labels are debugging-only and must be explicitly enabled.
        if not self.allow_keyword_fallback:
            return set()

        # 2. 关键词搜索 + doc 过滤
        doc_ids = normalize_doc_ids(relevant_docs)
        if not doc_ids:
            return set()
        result = self._keyword_search(q_text, doc_ids, top_k=10)
        if result:
            self.last_source = "keyword_fallback_debug_only"
        return result

    def _keyword_search(self, query_text: str, doc_ids: List[str], top_k: int = 10) -> Set[str]:
        """在 doc_ids 对应的 chunk store 文件中用关键词搜索"""
        stopwords = {"what", "how", "are", "the", "a", "an", "and", "or", "of", "in",
                     "for", "to", "is", "do", "does", "when", "which", "that", "with",
                     "by", "from", "at", "on", "be", "been", "being", "have", "has"}
        words = re.findall(r'\b[a-zA-Z]{3,}\b', query_text.lower())
        keywords = [w for w in words if w not in stopwords][:6]

        found = set()
        for cid, chunk in self._chunk_store.items():
            # Check if this chunk belongs to one of relevant docs
            cdoc = chunk.get("doc_id", cid.rsplit("_", 1)[0] if "_" in cid else cid)
            if not any(did in cdoc or cdoc in did for did in doc_ids):
                continue
            content = (chunk.get("content", "") + " " +
                       chunk.get("heading", "") + " " +
                       chunk.get("summary", "")).lower()
            hits = sum(1 for kw in keywords if kw in content)
            if hits >= 2:
                found.add(cid)
                if len(found) >= top_k:
                    break
        return found


# ─────────────────────────────────────────────
#  变体 A: Stage 1 Only
# ─────────────────────────────────────────────
def retrieve_variant_a(retriever: GraphRAGRetriever, query: str) -> List[str]:
    """Stage 1 only: HyDE + FAISS 向量检索，不走 Stage 2/3"""
    # 直接调用 stage1_bottom_up
    chunks, _ = retriever.stage1_bottom_up(query)
    # 按 score 排序
    chunks.sort(key=lambda c: c.score, reverse=True)
    return dedupe_ranked_ids([c.chunk_id for c in chunks])


# ─────────────────────────────────────────────
#  变体 B: Stage 1 + Stage 2
# ─────────────────────────────────────────────
def retrieve_variant_b(retriever: GraphRAGRetriever, query: str) -> List[str]:
    """Stage 1 + Stage 2 (自顶向下结构探索)，跳过 Stage 3"""
    chunks_s1, entities_s1 = retriever.stage1_bottom_up(query)
    existing_ids = {c.chunk_id for c in chunks_s1}
    chunks_s2, relations = retriever.stage2_top_down(entities_s1, existing_ids,
                                                      chunks_stage1=chunks_s1)
    ranked_s1 = [
        c.chunk_id for c in sorted(chunks_s1, key=lambda c: c.score, reverse=True)
    ]
    ranked_s2 = [
        c.chunk_id for c in sorted(chunks_s2, key=lambda c: c.score, reverse=True)
    ]
    # 按 score 排序，Stage 2 chunks 默认 score=1.0（来源权重较低）
    # 给 Stage 2 chunks 降权
    # Weighted RRF lets supplementary graph evidence compete for top-k ranks.
    # 去重
    return weighted_reciprocal_rank_fusion(
        [ranked_s1, ranked_s2],
        weights=[1.0, 0.85],
    )


# ─────────────────────────────────────────────
#  变体 C: Stage 1 + Stage 2 + Stage 3 随机游走
# ─────────────────────────────────────────────
def retrieve_variant_c(retriever: GraphRAGRetriever, query: str,
                        max_walk_depth: int = 3) -> List[str]:
    """Stage 1+2 + KG 真实随机游走 (沿图结构随机选边，非 LLM 引导)"""
    chunks_s1, entities_s1 = retriever.stage1_bottom_up(query)
    existing_ids = {c.chunk_id for c in chunks_s1}
    chunks_s2, relations = retriever.stage2_top_down(entities_s1, existing_ids,
                                                      chunks_stage1=chunks_s1)
    existing_ids |= {c.chunk_id for c in chunks_s2}

    # KG 随机游走: 与 LLM 引导版本相同结构，但随机选边 (区别于 Variant D)
    walk_entities = [
        e for e in entities_s1
        if e.label in ("Drug", "API", "Manufacturer",
                       "ShortageEvent", "Regulation", "Country")
    ]
    extra_chunk_ids: List[str] = []
    if walk_entities:
        with retriever.neo4j_driver.session() as session:
            for entity in walk_entities[:3]:
                current = entity.name
                visited: Set[str] = {current}
                for _step in range(max_walk_depth):
                    neighbors = retriever._get_kg_neighbors(session, current)
                    candidates = [
                        (e, nm, lbl) for e, nm, lbl in neighbors
                        if nm not in visited
                    ]
                    if not candidates:
                        break
                    # 随机选择下一跳 (与 LLM 引导的核心区别)
                    _edge, next_node, _lbl = random.choice(candidates)
                    visited.add(next_node)
                    current = next_node
                    # 收集该节点被 MENTIONS 的 DocChunks
                    mresult = session.run(
                        "MATCH (c:DocChunk)-[:MENTIONS]->(e {name: $nm}) "
                        "RETURN c.chunk_id AS chunk_id LIMIT 3",
                        nm=next_node,
                    )
                    for rec in mresult:
                        cid = rec["chunk_id"]
                        if cid not in existing_ids:
                            extra_chunk_ids.append(cid)
                            existing_ids.add(cid)

    ranked_s1 = [
        c.chunk_id for c in sorted(chunks_s1, key=lambda c: c.score, reverse=True)
    ]
    ranked_s2 = [
        c.chunk_id for c in sorted(chunks_s2, key=lambda c: c.score, reverse=True)
    ]
    return weighted_reciprocal_rank_fusion(
        [ranked_s1, ranked_s2, extra_chunk_ids],
        weights=[1.0, 0.85, 0.75],
    )


# ─────────────────────────────────────────────
#  变体 D: 完整流水线 (LLM 引导游走)
# ─────────────────────────────────────────────
def retrieve_variant_d(retriever: GraphRAGRetriever, query: str) -> List[str]:
    """完整 3 阶段流水线: Stage 1+2 + LLM 引导图游走 (每步 LLM 决策)"""
    chunks_s1, entities_s1 = retriever.stage1_bottom_up(query)
    existing_ids = {c.chunk_id for c in chunks_s1}
    chunks_s2, relations = retriever.stage2_top_down(entities_s1, existing_ids,
                                                      chunks_stage1=chunks_s1)
    existing_ids |= {c.chunk_id for c in chunks_s2}

    # LLM 引导游走 (核心差异: 每步 LLM 决策 vs 随机)
    _paths, walk_chunks = retriever.stage3_llm_guided_walk(query, entities_s1)

    # 合并所有 chunks，按分数排序
    ranked_s1 = [
        c.chunk_id for c in sorted(chunks_s1, key=lambda c: c.score, reverse=True)
    ]
    ranked_s2 = [
        c.chunk_id for c in sorted(chunks_s2, key=lambda c: c.score, reverse=True)
    ]
    # LLM 游走补充的 chunks 追加在后
    ranked_walk = [
        c.chunk_id for c in sorted(walk_chunks, key=lambda c: c.score, reverse=True)
    ]
    return weighted_reciprocal_rank_fusion(
        [ranked_s1, ranked_s2, ranked_walk],
        weights=[1.0, 0.85, 0.9],
    )


# ─────────────────────────────────────────────
#  指标计算
# ─────────────────────────────────────────────
def recall_at_k(retrieved: List[str], relevant: Set[str], k: int) -> float:
    if not relevant:
        return 0.0
    top_k = dedupe_ranked_ids(retrieved)[:k]
    hits = sum(1 for cid in top_k if cid in relevant)
    return hits / len(relevant)


def mrr(retrieved: List[str], relevant: Set[str]) -> float:
    for rank, cid in enumerate(dedupe_ranked_ids(retrieved), 1):
        if cid in relevant:
            return 1.0 / rank
    return 0.0


# ─────────────────────────────────────────────
#  主实验函数
# ─────────────────────────────────────────────
def run_ablation(
    eval_path: str = "data/eval_queries_entity_anchor.json",
    output_path: str = "data/ablation_results.json",
    n_queries: int = 40,
    skip_variant_d: bool = False,  # D 最慢，可选跳过
    seed: int = 42,
    allow_keyword_ground_truth: bool = False,
):
    random.seed(seed)
    np.random.seed(seed)

    print("=" * 60)
    print("PharmGraphRAG 消融实验")
    print("=" * 60)

    # 加载查询集
    with open(eval_path, encoding="utf-8") as f:
        all_queries = json.load(f)

    # 选取查询 (各类别均衡)
    cats = {}
    for q in all_queries:
        c = q.get("category", q.get("type", "other"))
        cats.setdefault(c, []).append(q)

    selected = []
    n_per_cat = max(1, n_queries // max(len(cats), 1))
    for cat, qs in cats.items():
        random.shuffle(qs)
        selected.extend(qs[:n_per_cat])
    selected = selected[:n_queries]
    print(f"Selected {len(selected)} queries from {len(cats)} categories")

    # 初始化检索器
    config = GraphRAGConfig()
    retriever = GraphRAGRetriever(config)
    print("Retriever loaded.\n")

    # 构建 ground truth (使用 chunk store 格式)
    gt_builder = GroundTruthBuilder(
        chunks_dir=Path("data/chunks"),
        allow_keyword_fallback=allow_keyword_ground_truth,
    )

    results = {
        "metadata": {
            "keyword_ground_truth_enabled": allow_keyword_ground_truth,
            "keyword_ground_truth_policy": (
                "debug_only" if allow_keyword_ground_truth else "disabled"
            ),
            "ranking": "weighted_reciprocal_rank_fusion",
            "rrf_rank_constant": 10,
        },
        "queries": [],
        "aggregate": {}
    }

    variant_scores = {
        "A": {"recall5": [], "recall10": [], "mrr": [], "valid": 0},
        "B": {"recall5": [], "recall10": [], "mrr": [], "valid": 0},
        "C": {"recall5": [], "recall10": [], "mrr": [], "valid": 0},
        "D": {"recall5": [], "recall10": [], "mrr": [], "valid": 0},
    }

    for i, q in enumerate(selected):
        qid = q.get("query_id", q.get("qid", f"Q{i+1:02d}"))
        query_text = q["query"]
        category = q.get("category", q.get("type", "other"))

        print(f"\n[{i+1}/{len(selected)}] {qid} ({category})")
        print(f"  Query: {query_text[:70]}...")

        # 构建 ground truth
        gt = gt_builder.build_for_query(q)
        if not gt:
            print(f"  WARNING: No ground truth found, skipping.")
            continue
        print(f"  Ground truth: {len(gt)} chunks")

        q_result = {
            "qid": qid,
            "query": query_text,
            "category": category,
            "ground_truth_size": len(gt),
            "ground_truth_source": gt_builder.last_source,
            "variants": {}
        }

        # ── Variant A ──
        t0 = time.time()
        try:
            ret_a = retrieve_variant_a(retriever, query_text)
            ta = time.time() - t0
            r5a = recall_at_k(ret_a, gt, 5)
            r10a = recall_at_k(ret_a, gt, 10)
            mrra = mrr(ret_a, gt)
            variant_scores["A"]["recall5"].append(r5a)
            variant_scores["A"]["recall10"].append(r10a)
            variant_scores["A"]["mrr"].append(mrra)
            variant_scores["A"]["valid"] += 1
            q_result["variants"]["A"] = {"recall5": r5a, "recall10": r10a, "mrr": mrra,
                                          "retrieved": ret_a[:10], "time": ta}
            print(f"  A (Stage1): R@5={r5a:.3f} R@10={r10a:.3f} MRR={mrra:.3f} [{ta:.1f}s]")
        except Exception as e:
            print(f"  A ERROR: {e}")
            q_result["variants"]["A"] = {"error": str(e)}

        # ── Variant B ──
        t0 = time.time()
        try:
            ret_b = retrieve_variant_b(retriever, query_text)
            tb = time.time() - t0
            r5b = recall_at_k(ret_b, gt, 5)
            r10b = recall_at_k(ret_b, gt, 10)
            mrrb = mrr(ret_b, gt)
            variant_scores["B"]["recall5"].append(r5b)
            variant_scores["B"]["recall10"].append(r10b)
            variant_scores["B"]["mrr"].append(mrrb)
            variant_scores["B"]["valid"] += 1
            q_result["variants"]["B"] = {"recall5": r5b, "recall10": r10b, "mrr": mrrb,
                                          "retrieved": ret_b[:10], "time": tb}
            print(f"  B (S1+S2): R@5={r5b:.3f} R@10={r10b:.3f} MRR={mrrb:.3f} [{tb:.1f}s]")
        except Exception as e:
            print(f"  B ERROR: {e}")
            q_result["variants"]["B"] = {"error": str(e)}

        # ── Variant C ──
        t0 = time.time()
        try:
            ret_c = retrieve_variant_c(retriever, query_text)
            tc = time.time() - t0
            r5c = recall_at_k(ret_c, gt, 5)
            r10c = recall_at_k(ret_c, gt, 10)
            mrrc = mrr(ret_c, gt)
            variant_scores["C"]["recall5"].append(r5c)
            variant_scores["C"]["recall10"].append(r10c)
            variant_scores["C"]["mrr"].append(mrrc)
            variant_scores["C"]["valid"] += 1
            q_result["variants"]["C"] = {"recall5": r5c, "recall10": r10c, "mrr": mrrc,
                                          "retrieved": ret_c[:10], "time": tc}
            print(f"  C (S1+S2+Rand): R@5={r5c:.3f} R@10={r10c:.3f} MRR={mrrc:.3f} [{tc:.1f}s]")
        except Exception as e:
            print(f"  C ERROR: {e}")
            q_result["variants"]["C"] = {"error": str(e)}

        # ── Variant D (optional, slowest) ──
        if not skip_variant_d:
            t0 = time.time()
            try:
                ret_d = retrieve_variant_d(retriever, query_text)
                td = time.time() - t0
                r5d = recall_at_k(ret_d, gt, 5)
                r10d = recall_at_k(ret_d, gt, 10)
                mrrd = mrr(ret_d, gt)
                variant_scores["D"]["recall5"].append(r5d)
                variant_scores["D"]["recall10"].append(r10d)
                variant_scores["D"]["mrr"].append(mrrd)
                variant_scores["D"]["valid"] += 1
                q_result["variants"]["D"] = {"recall5": r5d, "recall10": r10d, "mrr": mrrd,
                                              "retrieved": ret_d[:10], "time": td}
                print(f"  D (Full): R@5={r5d:.3f} R@10={r10d:.3f} MRR={mrrd:.3f} [{td:.1f}s]")
            except Exception as e:
                print(f"  D ERROR: {e}")
                q_result["variants"]["D"] = {"error": str(e)}
        else:
            q_result["variants"]["D"] = {"skipped": True}

        results["queries"].append(q_result)

        # 中间保存
        if (i + 1) % 5 == 0:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"  [Checkpoint saved: {i+1} queries done]")

    # ── 聚合结果 ──
    print("\n" + "=" * 60)
    print("AGGREGATE RESULTS")
    print("=" * 60)
    agg = {}
    for v in ["A", "B", "C", "D"]:
        s = variant_scores[v]
        n = s["valid"]
        if n == 0:
            continue
        r5 = np.mean(s["recall5"])
        r10 = np.mean(s["recall10"])
        m = np.mean(s["mrr"])
        r5_std = np.std(s["recall5"])
        r10_std = np.std(s["recall10"])
        agg[v] = {
            "n_queries": n,
            "recall5_mean": round(r5, 4),
            "recall5_std": round(r5_std, 4),
            "recall10_mean": round(r10, 4),
            "recall10_std": round(r10_std, 4),
            "mrr_mean": round(m, 4),
        }
        print(f"Variant {v}: R@5={r5:.3f}±{r5_std:.3f}  R@10={r10:.3f}±{r10_std:.3f}  MRR={m:.3f}  (n={n})")

    # 计算 delta D vs A and D vs C
    if "A" in agg and "D" in agg:
        delta_da_r5 = agg["D"]["recall5_mean"] - agg["A"]["recall5_mean"]
        delta_da_r10 = agg["D"]["recall10_mean"] - agg["A"]["recall10_mean"]
        delta_da_mrr = agg["D"]["mrr_mean"] - agg["A"]["mrr_mean"]
        agg["delta_D_vs_A"] = {
            "recall5_pp": round(delta_da_r5 * 100, 2),
            "recall10_pp": round(delta_da_r10 * 100, 2),
            "mrr": round(delta_da_mrr, 4)
        }
        print(f"\nΔ(D) vs (A): R@5={delta_da_r5*100:+.1f}pp  R@10={delta_da_r10*100:+.1f}pp  MRR={delta_da_mrr:+.4f}")

    if "C" in agg and "D" in agg:
        delta_dc_r5 = agg["D"]["recall5_mean"] - agg["C"]["recall5_mean"]
        delta_dc_r10 = agg["D"]["recall10_mean"] - agg["C"]["recall10_mean"]
        delta_dc_mrr = agg["D"]["mrr_mean"] - agg["C"]["mrr_mean"]
        agg["delta_D_vs_C"] = {
            "recall5_pp": round(delta_dc_r5 * 100, 2),
            "recall10_pp": round(delta_dc_r10 * 100, 2),
            "mrr": round(delta_dc_mrr, 4)
        }
        print(f"Δ(D) vs (C): R@5={delta_dc_r5*100:+.1f}pp  R@10={delta_dc_r10*100:+.1f}pp  MRR={delta_dc_mrr:+.4f}")

    results["aggregate"] = agg

    # 保存最终结果
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nResults saved to {output_path}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=30, help="Number of queries to evaluate")
    parser.add_argument("--skip_d", action="store_true", help="Skip Variant D (slowest)")
    parser.add_argument("--output", default="data/ablation_results.json")
    parser.add_argument(
        "--allow-keyword-ground-truth",
        action="store_true",
        help="Debug only: auto-construct missing ground truth with keyword search",
    )
    args = parser.parse_args()

    run_ablation(
        n_queries=args.n,
        output_path=args.output,
        skip_variant_d=args.skip_d,
        allow_keyword_ground_truth=args.allow_keyword_ground_truth,
    )
