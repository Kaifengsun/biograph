"""Locked evaluation for BM25, corpus enrichment, hybrid, and adaptive retrieval."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import faiss
import numpy as np
from scipy.stats import binomtest, wilcoxon
from statsmodels.stats.multitest import multipletests

from adaptive_text_first import AdaptiveParameters, adaptive_rank
from pharma_doc_pipeline.config import EmbeddingConfig, PipelineSettings
from pharma_doc_pipeline.step_04_vectorize import EmbeddingClient


METHODS = ("BM25_raw", "R1_raw", "R2_summary", "R3_hyde", "R4_table", "BM25_R4_RRF", "Adaptive_text_first")
VARIANTS = {"R1_raw": "R1_raw", "R2_summary": "R2_summary", "R3_hyde": "R3_hyde", "R4_table": "R4_table"}
TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tokenize(text: str) -> list[str]:
    return TOKEN_PATTERN.findall(str(text).casefold())


def source_text(row: dict[str, Any]) -> str:
    return "\n".join(str(row.get(key, "")).strip() for key in ("parents_context", "heading", "content") if str(row.get(key, "")).strip())


@dataclass
class BM25Index:
    ids: list[str]
    term_frequencies: list[Counter[str]]
    document_lengths: np.ndarray
    document_frequency: Counter[str]
    average_length: float
    k1: float = 1.2
    b: float = 0.75

    @classmethod
    def build(cls, records: list[dict[str, Any]], k1: float = 1.2, b: float = 0.75) -> "BM25Index":
        ids, frequencies, lengths, document_frequency = [], [], [], Counter()
        for row in records:
            tokens = tokenize(source_text(row))
            ids.append(str(row["chunk_id"]))
            tf = Counter(tokens)
            frequencies.append(tf)
            lengths.append(len(tokens))
            document_frequency.update(tf.keys())
        values = np.asarray(lengths, dtype=np.float64)
        return cls(ids, frequencies, values, document_frequency, float(values.mean()), k1, b)

    def rank(self, query: str, limit: int = 100) -> list[str]:
        query_terms = Counter(tokenize(query))
        scores = np.zeros(len(self.ids), dtype=np.float64)
        n_docs = len(self.ids)
        for term, query_weight in query_terms.items():
            df = self.document_frequency.get(term, 0)
            if not df:
                continue
            idf = math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
            for index, tf in enumerate(self.term_frequencies):
                frequency = tf.get(term, 0)
                if not frequency:
                    continue
                norm = frequency + self.k1 * (1.0 - self.b + self.b * self.document_lengths[index] / self.average_length)
                scores[index] += query_weight * idf * frequency * (self.k1 + 1.0) / norm
        ranked = sorted(range(n_docs), key=lambda index: (-scores[index], index))
        return [self.ids[index] for index in ranked[:limit] if scores[index] > 0.0]


def dedupe_source_ranking(indices: Iterable[int], metadata: list[dict[str, Any]], limit: int = 100) -> list[str]:
    result, seen = [], set()
    for index in indices:
        if index < 0 or index >= len(metadata):
            continue
        chunk_id = str(metadata[index].get("chunk_id", ""))
        if chunk_id and chunk_id not in seen:
            seen.add(chunk_id)
            result.append(chunk_id)
            if len(result) >= limit:
                break
    return result


def rrf_rank(rankings: list[list[str]], k: int = 60, limit: int = 100) -> list[str]:
    scores: dict[str, float] = {}
    first_seen: dict[str, tuple[int, int]] = {}
    for list_index, ranking in enumerate(rankings):
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            first_seen.setdefault(chunk_id, (list_index, rank))
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], first_seen[chunk_id], chunk_id))[:limit]


def metric_row(ranking: list[str], gold: set[str]) -> dict[str, float]:
    unique = list(dict.fromkeys(ranking))
    first = next((rank for rank, chunk_id in enumerate(unique, 1) if chunk_id in gold), None)
    relevance = [int(chunk_id in gold) for chunk_id in unique[:5]]
    dcg = sum(hit / math.log2(rank + 1) for rank, hit in enumerate(relevance, 1))
    ideal = sum(1.0 / math.log2(rank + 1) for rank in range(1, min(len(gold), 5) + 1))
    return {
        "hit_at_1": float(any(chunk_id in gold for chunk_id in unique[:1])),
        "hit_at_3": float(any(chunk_id in gold for chunk_id in unique[:3])),
        "hit_at_5": float(any(chunk_id in gold for chunk_id in unique[:5])),
        "mrr": 0.0 if first is None else 1.0 / first,
        "ndcg_at_5": 0.0 if not ideal else dcg / ideal,
    }


def aggregate(rows: list[dict[str, float]]) -> dict[str, float]:
    return {metric: float(np.mean([row[metric] for row in rows])) for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")}


def bootstrap_mean_ci(values: list[float], iterations: int, seed: int, label: str) -> dict[str, float]:
    rng = random.Random(f"{seed}:{label}")
    n = len(values)
    samples = [sum(values[rng.randrange(n)] for _ in range(n)) / n for _ in range(iterations)]
    samples.sort()
    return {"mean": float(np.mean(values)), "ci_95_low": samples[int(iterations * 0.025)], "ci_95_high": samples[min(iterations - 1, int(iterations * 0.975))]}


def paired_comparison(treatment: list[float], baseline: list[float], metric: str, iterations: int, seed: int, label: str) -> dict[str, Any]:
    differences = [a - b for a, b in zip(treatment, baseline, strict=True)]
    ci = bootstrap_mean_ci(differences, iterations, seed, label)
    if metric == "hit_at_5":
        discordant = [(a, b) for a, b in zip(treatment, baseline, strict=True) if a != b]
        wins = sum(a > b for a, b in discordant)
        p_value = 1.0 if not discordant else float(binomtest(wins, len(discordant), 0.5).pvalue)
        test = "exact_paired_mcnemar_binomial"
    else:
        p_value = 1.0 if all(abs(value) < 1e-15 for value in differences) else float(wilcoxon(differences, zero_method="wilcox", alternative="two-sided").pvalue)
        test = "paired_wilcoxon_signed_rank"
    return {"treatment_mean": float(np.mean(treatment)), "baseline_mean": float(np.mean(baseline)), "delta_mean": ci["mean"], "delta_ci_95_low": ci["ci_95_low"], "delta_ci_95_high": ci["ci_95_high"], "test": test, "p_value_raw": p_value}


def adjust_holm(comparisons: dict[str, dict[str, Any]]) -> None:
    rejected, adjusted, _, _ = multipletests([row["p_value_raw"] for row in comparisons.values()], alpha=0.05, method="holm")
    for row, adjusted_p, rejected_flag in zip(comparisons.values(), adjusted, rejected, strict=True):
        row["p_value_holm"] = float(adjusted_p)
        row["significant_after_holm_0_05"] = bool(rejected_flag)


def load_corpus(corpus_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for file_path in sorted(corpus_dir.glob("*_enriched.json")):
        rows.extend(read_json(file_path))
    if len(rows) != 2478:
        raise ValueError(f"expected 2478 frozen chunks, found {len(rows)}")
    return rows


def load_adaptive_retrieval(path: Path) -> dict[str, dict[str, Any]]:
    records = read_json(path)
    result = {str(row.get("query_id", "")): row["retrieval"] for row in records}
    if len(result) != len(records):
        raise ValueError("duplicate adaptive retrieval query IDs")
    return result


def markdown_report(report: dict[str, Any]) -> str:
    lines = ["# BM25 Baseline and Corpus-Enrichment Ablation", "", f"Queries: {report['query_count']}", "", "| Method | Hit@1 | Hit@3 | Hit@5 | MRR | nDCG@5 |", "|---|---:|---:|---:|---:|---:|"]
    for method in METHODS:
        row = report["aggregate"][method]
        lines.append(f"| {method} | {row['hit_at_1']:.3f} | {row['hit_at_3']:.3f} | {row['hit_at_5']:.3f} | {row['mrr']:.3f} | {row['ndcg_at_5']:.3f} |")
    lines.extend(["", "## Preregistered paired comparisons", ""])
    for family, metrics in report["paired_comparisons"].items():
        lines.append(f"### {family}")
        for metric, row in metrics.items():
            lines.append(f"- {metric}: delta {row['delta_mean']:.4f}, 95% CI [{row['delta_ci_95_low']:.4f}, {row['delta_ci_95_high']:.4f}], Holm p={row['p_value_holm']:.4g}.")
        lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack", required=True)
    parser.add_argument("--adaptive-retrieval", required=True)
    parser.add_argument("--adaptive-lock", default="outputs/adaptive_text_first_development_2026-07-15-v3/method_lock_manifest.json")
    parser.add_argument("--corpus", default="data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4")
    parser.add_argument("--index-root", default="artifacts/retrieval_ablation/deepseek-v4-pro-v4")
    parser.add_argument("--output", required=True)
    parser.add_argument("--search-depth", type=int, default=100)
    parser.add_argument("--bootstrap-iterations", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20260715)
    args = parser.parse_args()

    output = Path(args.output)
    per_query_path = output.with_name(output.stem + "-per-query.json")
    markdown_path = output.with_suffix(".md")
    csv_path = output.with_name(output.stem + "-per-query.csv")
    if any(path.exists() for path in (output, per_query_path, markdown_path, csv_path)):
        raise RuntimeError(f"refusing to overwrite formal output: {output}")
    pack = read_json(Path(args.pack))
    if not pack.get("formal_metrics_ready") or pack.get("retrieval_execution_prohibited"):
        raise ValueError("held-out pack is not activated for a single formal run")
    queries = pack.get("queries", [])
    if len(queries) != 30:
        raise ValueError("formal pack must contain exactly 30 queries")
    corpus = load_corpus(Path(args.corpus))
    bm25 = BM25Index.build(corpus, k1=1.2, b=0.75)
    adaptive_retrieval = load_adaptive_retrieval(Path(args.adaptive_retrieval))
    if set(adaptive_retrieval) != {str(row["annotation_id"]) for row in queries}:
        raise ValueError("adaptive retrieval IDs do not match frozen held-out IDs")

    settings = PipelineSettings()
    settings.embedding = EmbeddingConfig(backend="local", local_model=settings.embedding.local_model, dimension=settings.embedding.dimension)
    embedder = EmbeddingClient(settings.embedding)
    query_vectors = embedder.embed([row["query"] for row in queries], batch_size=8)
    faiss.normalize_L2(query_vectors)
    index_root = Path(args.index_root)
    dense_rankings: dict[str, list[list[str]]] = {}
    for method, directory in VARIANTS.items():
        index_path = index_root / directory / "pharma_docs.faiss"
        metadata = read_json(index_path.with_suffix(".meta.json"))
        index = faiss.read_index(str(index_path))
        search_depth = min(args.search_depth, index.ntotal)
        _, indices = index.search(query_vectors, search_depth)
        dense_rankings[method] = [dedupe_source_ranking(row, metadata, args.search_depth) for row in indices]

    adaptive_parameters = AdaptiveParameters(**read_json(Path(args.adaptive_lock))["selected_parameters"])
    per_query = []
    for position, row in enumerate(queries):
        bm25_ranking = bm25.rank(row["query"], args.search_depth)
        r4 = dense_rankings["R4_table"][position]
        adaptive = adaptive_rank(adaptive_retrieval[str(row["annotation_id"])], adaptive_parameters, top_k=5)
        rankings = {
            "BM25_raw": bm25_ranking,
            "R1_raw": dense_rankings["R1_raw"][position],
            "R2_summary": dense_rankings["R2_summary"][position],
            "R3_hyde": dense_rankings["R3_hyde"][position],
            "R4_table": r4,
            "BM25_R4_RRF": rrf_rank([bm25_ranking, r4], k=60, limit=args.search_depth),
            "Adaptive_text_first": adaptive["ranking"],
        }
        gold = set(row["gold_evidence_chunk_ids"])
        per_query.append({
            "annotation_id": row["annotation_id"], "query_slice": row["query_slice"], "query": row["query"], "gold_evidence_chunk_ids": row["gold_evidence_chunk_ids"],
            "metrics": {method: metric_row(rankings[method], gold) for method in METHODS}, "rankings": rankings,
            "adaptive_audit": adaptive["audit"],
        })
    aggregate_metrics = {method: aggregate([row["metrics"][method] for row in per_query]) for method in METHODS}
    by_slice = {query_slice: {method: aggregate([row["metrics"][method] for row in per_query if row["query_slice"] == query_slice]) for method in METHODS} for query_slice in sorted({row["query_slice"] for row in per_query})}
    uncertainty = {method: {metric: bootstrap_mean_ci([row["metrics"][method][metric] for row in per_query], args.bootstrap_iterations, args.seed, f"{method}:{metric}") for metric in ("hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5")} for method in METHODS}
    families = {
        "R2_vs_R1": ("R2_summary", "R1_raw"), "R3_vs_R2": ("R3_hyde", "R2_summary"), "R4_vs_R3": ("R4_table", "R3_hyde"),
        "Adaptive_vs_BM25": ("Adaptive_text_first", "BM25_raw"), "Adaptive_vs_BM25_R4_RRF": ("Adaptive_text_first", "BM25_R4_RRF"),
    }
    paired = {}
    for family, (treatment, baseline) in families.items():
        comparisons = {metric: paired_comparison([row["metrics"][treatment][metric] for row in per_query], [row["metrics"][baseline][metric] for row in per_query], metric, args.bootstrap_iterations, args.seed, f"{family}:{metric}") for metric in ("hit_at_5", "mrr", "ndcg_at_5")}
        adjust_holm(comparisons)
        paired[family] = comparisons
    report = {
        "schema_version": "1.0", "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(), "formal_metrics": True, "query_count": len(per_query), "methods": list(METHODS),
        "locked_parameters": {"bm25_k1": 1.2, "bm25_b": 0.75, "tokenization": "lowercase_alphanumeric", "dense_search_depth": args.search_depth, "rrf_k": 60, "bootstrap_iterations": args.bootstrap_iterations, "seed": args.seed},
        "aggregate": aggregate_metrics, "uncertainty": uncertainty, "by_slice": by_slice, "paired_comparisons": paired,
        "input_hashes": {"pack": sha256_file(Path(args.pack)), "adaptive_retrieval": sha256_file(Path(args.adaptive_retrieval)), "adaptive_lock": sha256_file(Path(args.adaptive_lock)), "evaluation_code": sha256_file(Path(__file__))},
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    per_query_path.write_text(json.dumps(per_query, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["annotation_id", "query_slice", "method", "hit_at_1", "hit_at_3", "hit_at_5", "mrr", "ndcg_at_5"])
        for row in per_query:
            for method in METHODS:
                metric = row["metrics"][method]
                writer.writerow([row["annotation_id"], row["query_slice"], method, metric["hit_at_1"], metric["hit_at_3"], metric["hit_at_5"], metric["mrr"], metric["ndcg_at_5"]])
    print(json.dumps({"output": str(output), "query_count": len(per_query), "aggregate": aggregate_metrics}, indent=2))


if __name__ == "__main__":
    main()
