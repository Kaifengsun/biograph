"""Prepare a blinded 60-query dual-annotation evidence pack.

The script creates the frozen machine-readable registry used by the workbook
builder.  Generated questions are grounded in frozen source chunks, while the
candidate pools combine lexical, dense, and hierarchical retrieval routes.
No generated summary, HyDE question, or graph node is admitted as evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import subprocess
import urllib.error
import urllib.request
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from evaluate_bm25_enrichment_ablation import BM25Index, load_corpus
from three_path_retrieval import ThreePathSnapshotRetriever, sha256_file


ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "data/staging/enrichment_full_2026-07-deepseek-v4-pro-v4"
INDEX_ROOT = ROOT / "artifacts/retrieval_ablation/deepseek-v4-pro-v4"
GRAPH = ROOT / "artifacts/regulatory_evidence_graph/deepseek-v4-pro-v4-build5-regulatory-fda"
EVAL_ROOT = ROOT / "data/eval"
OUTPUT = ROOT / "outputs/dual_annotation_60_2026-07-15"
SEED = 20260716
MODEL = "deepseek-v4-pro"

SLICE_COUNTS = {
    "single_clause": 20,
    "table": 15,
    "document_structure": 15,
    "cross_document": 10,
}
BATCH_COUNTS = {
    "01": {"single_clause": 7, "table": 5, "document_structure": 5, "cross_document": 3},
    "02": {"single_clause": 7, "table": 5, "document_structure": 5, "cross_document": 3},
    "03": {"single_clause": 6, "table": 5, "document_structure": 5, "cross_document": 4},
}


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_question(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", str(text).casefold()))


def iter_questions(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"query", "question", "revised_query", "original_query"} and isinstance(child, str):
                yield child
            else:
                yield from iter_questions(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_questions(child)


def historical_questions() -> set[str]:
    result: set[str] = set()
    for path in sorted(EVAL_ROOT.rglob("*.json")):
        try:
            payload = read_json(path)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        result.update(normalize_question(question) for question in iter_questions(payload))
    return {question for question in result if question}


def useful_chunk(row: dict[str, Any]) -> bool:
    content = str(row.get("content", "")).strip()
    heading = str(row.get("heading", "")).strip()
    lowered = f"{heading}\n{content}".casefold()
    blocked = ("table of contents", "legal notice", "copyright", "acknowledgement", "references")
    return 220 <= len(content) <= 2400 and heading and not any(term in lowered for term in blocked)


def spread_by_document(rows: list[dict[str, Any]], count: int, rng: random.Random) -> list[dict[str, Any]]:
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        buckets[str(row.get("doc_id", "unknown"))].append(row)
    docs = sorted(buckets)
    for doc in docs:
        rng.shuffle(buckets[doc])
    selected: list[dict[str, Any]] = []
    while len(selected) < count and docs:
        next_docs = []
        for doc in docs:
            if buckets[doc] and len(selected) < count:
                selected.append(buckets[doc].pop())
            if buckets[doc]:
                next_docs.append(doc)
        docs = next_docs
    if len(selected) != count:
        raise ValueError(f"unable to select {count} diverse chunks; got {len(selected)}")
    return selected


def source_label(row: dict[str, Any]) -> str:
    return str(row.get("doc_id", "")).replace("_", " ").upper()


def select_anchors(corpus: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    eligible = [row for row in corpus if useful_chunk(row)]
    table_rows = [row for row in eligible if row.get("has_table") or "|---" in str(row.get("content", ""))]
    prose_rows = [row for row in eligible if row not in table_rows]
    selected: list[dict[str, Any]] = []

    for index, row in enumerate(spread_by_document(prose_rows, 20, rng), 1):
        selected.append({"query_id": f"DA60-SC{index:02d}", "query_slice": "single_clause", "anchors": [row]})
    for index, row in enumerate(spread_by_document(table_rows, 15, rng), 1):
        selected.append({"query_id": f"DA60-TB{index:02d}", "query_slice": "table", "anchors": [row]})

    structural_pool = [
        row for row in prose_rows
        if str(row.get("parents_context", "")).strip() and len(str(row.get("heading", ""))) >= 5
    ]
    used = {item["anchors"][0]["chunk_id"] for item in selected}
    structural_pool = [row for row in structural_pool if row["chunk_id"] not in used]
    for index, row in enumerate(spread_by_document(structural_pool, 15, rng), 1):
        selected.append({"query_id": f"DA60-DS{index:02d}", "query_slice": "document_structure", "anchors": [row]})

    topics = [
        ("stability", ("stability", "storage", "shelf life")),
        ("quality risk management", ("quality risk", "risk management")),
        ("process validation", ("process validation", "continued process", "validation lifecycle")),
        ("change management", ("change management", "post-approval change", "change control")),
        ("impurity control", ("impurity", "mutagenic", "elemental")),
        ("computerized systems", ("computerised system", "computerized system", "data integrity")),
        ("analytical validation", ("analytical procedure", "validation characteristics", "performance characteristic")),
        ("manufacturing quality", ("manufacturing process", "good manufacturing practice", "commercial manufacturing")),
        ("lifecycle monitoring", ("lifecycle", "continual improvement", "ongoing monitoring")),
        ("specifications and control", ("specification", "control strategy", "acceptance criteria")),
    ]
    for index, (topic, terms) in enumerate(topics, 1):
        ranked = []
        for row in eligible:
            text = f"{row.get('heading', '')} {row.get('content', '')}".casefold()
            score = sum(text.count(term) for term in terms)
            if score:
                ranked.append((score, len(str(row.get("content", ""))), str(row["chunk_id"]), row))
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))
        pair: list[dict[str, Any]] = []
        seen_docs: set[str] = set()
        for _score, _length, _chunk_id, row in ranked:
            doc_id = str(row.get("doc_id", ""))
            if doc_id not in seen_docs:
                pair.append(row)
                seen_docs.add(doc_id)
            if len(pair) == 2:
                break
        if len(pair) != 2:
            raise ValueError(f"unable to find two documents for cross-document topic: {topic}")
        selected.append({"query_id": f"DA60-CD{index:02d}", "query_slice": "cross_document", "topic": topic, "anchors": pair})
    return selected


def api_json(messages: list[dict[str, str]]) -> Any:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set")
    body = json.dumps({
        "model": MODEL,
        "temperature": 0.1,
        "max_tokens": 8000,
        "response_format": {"type": "json_object"},
        "messages": messages,
    }).encode("utf-8")
    last_error: Exception | None = None
    for attempt in range(3):
        request = urllib.request.Request(
            "https://api.deepseek.com/v1/chat/completions",
            data=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                payload = json.loads(response.read().decode("utf-8"))
            content = payload["choices"][0]["message"]["content"]
            return json.loads(content)
        except (json.JSONDecodeError, TimeoutError, urllib.error.URLError) as exc:
            last_error = exc
            time.sleep(2 ** attempt)
    raise RuntimeError("model failed to return complete JSON after three attempts") from last_error


def question_prompt(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    compact = []
    for item in items:
        compact.append({
            "query_id": item["query_id"],
            "query_slice": item["query_slice"],
            "topic": item.get("topic"),
            "sources": [{
                "document": source_label(row),
                "heading": row.get("heading", ""),
                "parents_context": row.get("parents_context", ""),
                "passage": row.get("content", ""),
            } for row in item["anchors"]],
        })
    instructions = """Create one publication-quality English regulatory evidence retrieval question per item.
Return JSON only: {"items":[{"query_id":"...","question":"...","rationale":"..."}]}.
Rules:
1. The question must be answerable completely from the supplied frozen source passage(s), but must not copy a full sentence or reveal the answer.
2. Ask for concrete regulatory evidence, obligations, conditions, comparisons, or table facts. Avoid yes/no and trivia.
3. single_clause: one passage should be sufficient. table: require facts explicitly represented by the table passage. document_structure: ask where the topic is addressed and what that section establishes, so heading plus passage matter. cross_document: require a synthesis in which both supplied documents contribute a necessary component.
4. Preserve technical qualifiers. Do not invent facts, products, agencies, dates, or numerical values absent from the sources.
5. It is acceptable to name the source guidance when doing so makes the task realistic. Do not mention chunk IDs or retrieval systems.
6. Keep each question to at most 45 words."""
    return [
        {"role": "system", "content": instructions},
        {"role": "user", "content": json.dumps({"items": compact}, ensure_ascii=False)},
    ]


def generate_questions(anchors: list[dict[str, Any]], history: set[str]) -> list[dict[str, Any]]:
    generated: dict[str, dict[str, str]] = {}
    for start in range(0, len(anchors), 5):
        batch = anchors[start:start + 5]
        cache_path = OUTPUT / "_generation_cache" / f"questions_{start // 5 + 1:02d}.json"
        if cache_path.exists():
            payload = read_json(cache_path)
        else:
            payload = api_json(question_prompt(batch))
            write_json(cache_path, payload)
        for row in payload.get("items", []):
            generated[str(row["query_id"])] = row
    result = []
    seen = set(history)
    for item in anchors:
        row = generated.get(item["query_id"])
        if not row:
            raise ValueError(f"model omitted {item['query_id']}")
        question = " ".join(str(row.get("question", "")).split())
        normalized = normalize_question(question)
        if not question.endswith("?"):
            raise ValueError(f"question lacks question mark: {item['query_id']}")
        if len(question.split()) > 55:
            raise ValueError(f"question too long: {item['query_id']}")
        if normalized in seen:
            raise ValueError(f"question overlaps historical registry: {item['query_id']}")
        seen.add(normalized)
        result.append({
            **{key: value for key, value in item.items() if key != "anchors"},
            "query": question,
            "generation_rationale": str(row.get("rationale", "")).strip(),
            "source_anchor_chunk_ids": [str(anchor["chunk_id"]) for anchor in item["anchors"]],
        })
    return result


def blind_passage_id(query_id: str, chunk_id: str) -> str:
    digest = hashlib.sha256(f"{SEED}:{query_id}:{chunk_id}".encode("utf-8")).hexdigest()[:8].upper()
    return f"P-{digest}"


def build_candidate_pools(queries: list[dict[str, Any]], corpus: list[dict[str, Any]]) -> None:
    by_id = {str(row["chunk_id"]): row for row in corpus}
    bm25 = BM25Index.build(corpus)
    retriever = ThreePathSnapshotRetriever(graph_dir=GRAPH, corpus_dir=CORPUS, index_root=INDEX_ROOT)
    vectors = retriever.encode_queries([row["query"] for row in queries])
    for query, vector in zip(queries, vectors, strict=True):
        source_ids = list(query["source_anchor_chunk_ids"])
        bm25_ids = bm25.rank(query["query"], limit=3)
        r1_rows = retriever.rank_variant("R1_raw", query["query"], 3, vector.reshape(1, -1))
        r1_ids = [str(row["chunk_id"]) for row in r1_rows]
        top_down = retriever.top_down_from_rankings(
            retriever.rank_variant("R3_hyde", query["query"], 240, vector.reshape(1, -1)),
            retriever.rank_variant("R2_summary", query["query"], 500, vector.reshape(1, -1)),
            k=3,
            document_budget=2,
        )
        top_down_ids = [item.chunk_id for item in top_down["evidence"]]
        methods: dict[str, set[str]] = defaultdict(set)
        for chunk_id in source_ids:
            methods[chunk_id].add("source_anchor")
        for chunk_id in bm25_ids:
            methods[chunk_id].add("bm25_top3")
        for chunk_id in r1_ids:
            methods[chunk_id].add("r1_dense_top3")
        for chunk_id in top_down_ids:
            methods[chunk_id].add("top_down_top3")
        ordered = list(dict.fromkeys(source_ids + bm25_ids + r1_ids + top_down_ids))
        anchor_docs = {str(by_id[chunk_id].get("doc_id", "")) for chunk_id in source_ids}
        negatives = [
            row for row in corpus
            if str(row.get("doc_id", "")) in anchor_docs
            and str(row["chunk_id"]) not in ordered
            and useful_chunk(row)
        ]
        negatives.sort(key=lambda row: (str(row.get("doc_id", "")), str(row["chunk_id"])))
        rng = random.Random(f"{SEED}:{query['query_id']}:negative")
        rng.shuffle(negatives)
        for row in negatives[:2]:
            chunk_id = str(row["chunk_id"])
            ordered.append(chunk_id)
            methods[chunk_id].add("same_document_hard_negative")
        ordered = ordered[:12]
        if len(ordered) < 8:
            raise ValueError(f"candidate pool too small for {query['query_id']}: {len(ordered)}")
        query["candidate_passages"] = [{
            "blind_passage_id": blind_passage_id(query["query_id"], chunk_id),
            "chunk_id": chunk_id,
            "doc_id": str(by_id[chunk_id].get("doc_id", "")),
            "source_document": source_label(by_id[chunk_id]),
            "heading": str(by_id[chunk_id].get("heading", "")),
            "parents_context": str(by_id[chunk_id].get("parents_context", "")),
            "content": str(by_id[chunk_id].get("content", "")),
            "candidate_sources": sorted(methods[chunk_id]),
        } for chunk_id in ordered]


def assign_batches(queries: list[dict[str, Any]]) -> None:
    by_slice: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for query in queries:
        by_slice[query["query_slice"]].append(query)
    rng = random.Random(SEED)
    for rows in by_slice.values():
        rng.shuffle(rows)
    for batch, quotas in BATCH_COUNTS.items():
        for slice_name, count in quotas.items():
            chosen, by_slice[slice_name] = by_slice[slice_name][:count], by_slice[slice_name][count:]
            for query in chosen:
                query["batch"] = batch
    if any(by_slice.values()) or any("batch" not in query for query in queries):
        raise ValueError("batch assignment did not consume every query")


def git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def validate(queries: list[dict[str, Any]]) -> None:
    if len(queries) != 60 or len({row["query_id"] for row in queries}) != 60:
        raise ValueError("pack must contain 60 unique query IDs")
    actual = defaultdict(int)
    batches = defaultdict(int)
    for row in queries:
        actual[row["query_slice"]] += 1
        batches[row["batch"]] += 1
        count = len(row["candidate_passages"])
        if not 8 <= count <= 12:
            raise ValueError(f"{row['query_id']} has {count} passages")
        if not set(row["source_anchor_chunk_ids"]).issubset({p["chunk_id"] for p in row["candidate_passages"]}):
            raise ValueError(f"source anchor absent from candidates: {row['query_id']}")
    if dict(actual) != SLICE_COUNTS or dict(batches) != {"01": 20, "02": 20, "03": 20}:
        raise ValueError(f"quota mismatch: slices={dict(actual)}, batches={dict(batches)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT / "dual_annotation_60_registry.json")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError(f"refusing to overwrite frozen registry: {output}")
    corpus = load_corpus(CORPUS)
    history = historical_questions()
    anchors = select_anchors(corpus)
    queries = generate_questions(anchors, history)
    assign_batches(queries)
    build_candidate_pools(queries, corpus)
    validate(queries)
    payload = {
        "schema_version": "1.0",
        "status": "frozen_pending_independent_dual_annotation",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "question_generation_model": MODEL,
        "annotator_roles": {"A": "author_annotator", "B": "external_domain_annotator"},
        "git_commit_at_generation": git_commit(),
        "historical_normalized_question_count": len(history),
        "input_hashes": {
            "graph_nodes": sha256_file(GRAPH / "nodes.jsonl"),
            "graph_edges": sha256_file(GRAPH / "edges.jsonl"),
            "r1_metadata": sha256_file(INDEX_ROOT / "R1_raw/pharma_docs.meta.json"),
            "r2_metadata": sha256_file(INDEX_ROOT / "R2_summary/pharma_docs.meta.json"),
            "r3_metadata": sha256_file(INDEX_ROOT / "R3_hyde/pharma_docs.meta.json"),
        },
        "slice_counts": SLICE_COUNTS,
        "batch_counts": BATCH_COUNTS,
        "queries": queries,
    }
    write_json(output, payload)
    print(f"wrote {output}")


if __name__ == "__main__":
    main()
