"""
GraphRAG CLI — 交互式问答入口
=============================
用法:
  python -m pharma_graphrag.main                    # 交互模式
  python -m pharma_graphrag.main --query "..."      # 单次查询
  python -m pharma_graphrag.main --test              # 运行测试查询
  python -m pharma_graphrag.main --stats             # 查看系统统计
"""

import argparse
import sys
import time
import json
from pathlib import Path

from .config import GraphRAGConfig
from .retriever import GraphRAGRetriever
from .llm_client import DeepSeekClient


# ============================================================
#  GraphRAG 问答引擎
# ============================================================

class GraphRAGEngine:
    """GraphRAG 问答引擎 — 封装检索器 + LLM"""

    def __init__(self, config: GraphRAGConfig = None):
        self.config = config or GraphRAGConfig()
        self.retriever = GraphRAGRetriever(self.config)
        self.llm = DeepSeekClient(self.config.llm)

    def initialize(self):
        """初始化所有组件"""
        print("╔═══════════════════════════════════════════════════╗")
        print("║  Pharma Supply Chain GraphRAG System              ║")
        print("║  3-Stage: Bottom-Up → Top-Down → Graph Walk       ║")
        print("╚═══════════════════════════════════════════════════╝\n")
        print("Initializing components...")
        self.retriever.initialize()

    def ask(self, query: str, verbose: bool = True) -> str:
        """
        完整问答流程:
          1. 3-Stage 检索
          2. 组装上下文
          3. LLM 生成回答

        Args:
            query: 用户问题
            verbose: 是否打印检索过程

        Returns:
            LLM 生成的回答
        """
        if verbose:
            print(f"\n{'─' * 55}")
            print(f"  Query: {query}")
            print(f"{'─' * 55}\n")
            print("  [Retrieving...]")

        # 检索
        t0 = time.time()
        result = self.retriever.retrieve(query)
        retrieval_time = time.time() - t0

        if verbose:
            print(f"\n  Retrieval Summary ({retrieval_time:.2f}s):")
            print(result.summary())

        # 构建上下文
        context = result.to_context()

        if verbose:
            ctx_len = len(context)
            print(f"\n  Context length: {ctx_len} chars")
            print(f"\n  [Generating answer...]")

        # LLM 生成
        t0 = time.time()
        answer = self.llm.generate_answer(query, context)
        gen_time = time.time() - t0

        if verbose:
            print(f"  Generation time: {gen_time:.2f}s")
            print(f"\n{'═' * 55}")
            print(f"  ANSWER")
            print(f"{'═' * 55}\n")
            print(answer)
            print(f"\n{'═' * 55}")

            # 来源引用
            print(f"\n  [DOC] Sources:")
            doc_ids = set()
            for c in result.chunks:
                doc_ids.add(c.doc_id)
            for did in sorted(doc_ids):
                print(f"     - {did}")

            if result.entities:
                print(f"  [KG] KG Entities: ", end="")
                print(", ".join(
                    f"{e.name}({e.label})" for e in result.entities[:8]
                ))

            if result.risk_paths:
                print(f"  [!] Risk Paths: {len(result.risk_paths)}")
                for rp in result.risk_paths[:3]:
                    print(f"     {rp.to_str()}")

        return answer

    def close(self):
        self.retriever.close()


# ============================================================
#  测试查询
# ============================================================

TEST_QUERIES = [
    "What happens if Aurobindo Pharma stops producing Amoxicillin Trihydrate?",
    "What are the GMP requirements for API manufacturing according to ICH Q7?",
    "Which drugs have single-source API supply risk?",
    "What is the risk propagation if Heparin supply from China is disrupted?",
    "How does ICH Q9 recommend managing quality risks in pharmaceutical supply chains?",
]


# ============================================================
#  CLI 入口
# ============================================================

def show_stats(config: GraphRAGConfig):
    """显示系统统计信息"""
    from neo4j import GraphDatabase
    import faiss

    print("\n╔═══════════════════════════════════════╗")
    print("║  System Statistics                     ║")
    print("╚═══════════════════════════════════════╝\n")

    # Neo4j
    driver = GraphDatabase.driver(
        config.neo4j.uri,
        auth=(config.neo4j.user, config.neo4j.password)
    )
    with driver.session() as s:
        r = s.run("MATCH (n) RETURN labels(n)[0] AS lbl, count(*) AS cnt "
                   "ORDER BY cnt DESC")
        print("  Neo4j Nodes:")
        total_nodes = 0
        for rec in r:
            print(f"    {rec['lbl']:20s} {rec['cnt']:5d}")
            total_nodes += rec['cnt']
        print(f"    {'TOTAL':20s} {total_nodes:5d}")

        r = s.run("MATCH ()-[r]->() RETURN type(r) AS rel, count(*) AS cnt "
                   "ORDER BY cnt DESC")
        print("\n  Neo4j Edges:")
        total_edges = 0
        for rec in r:
            print(f"    {rec['rel']:20s} {rec['cnt']:5d}")
            total_edges += rec['cnt']
        print(f"    {'TOTAL':20s} {total_edges:5d}")
    driver.close()

    # FAISS
    vectors_dir = Path("data/vectors")
    index_path = vectors_dir / "pharma_docs.faiss"
    if index_path.exists():
        idx = faiss.read_index(str(index_path))
        print(f"\n  FAISS Index:")
        print(f"    Vectors: {idx.ntotal}")
        print(f"    Dimension: {idx.d}")

    # Chunks
    chunks_dir = Path("data/chunks")
    enriched = list(chunks_dir.glob("*_enriched.json"))
    total_chunks = 0
    for ef in enriched:
        with open(ef, "r", encoding="utf-8") as f:
            total_chunks += len(json.load(f))
    print(f"\n  Document Chunks: {total_chunks}")
    print(f"  Enriched Files: {len(enriched)}")


def run_interactive(engine: GraphRAGEngine):
    """交互式问答循环"""
    print("\n  Enter your question (type 'quit' to exit, 'test' for test queries):\n")
    while True:
        try:
            query = input("  📝 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye!")
            break

        if not query:
            continue
        if query.lower() in ("quit", "exit", "q"):
            print("  Bye!")
            break
        if query.lower() == "test":
            for i, tq in enumerate(TEST_QUERIES, 1):
                print(f"\n  Test {i}/{len(TEST_QUERIES)}")
                engine.ask(tq)
            continue

        engine.ask(query)


def main():
    parser = argparse.ArgumentParser(
        description="Pharma Supply Chain GraphRAG System"
    )
    parser.add_argument("--query", "-q", type=str, help="单次查询")
    parser.add_argument("--test", action="store_true", help="运行测试查询")
    parser.add_argument("--stats", action="store_true", help="查看系统统计")
    parser.add_argument("--no-llm", action="store_true",
                        help="仅检索，不调用 LLM 生成回答")
    args = parser.parse_args()

    config = GraphRAGConfig()

    if args.stats:
        show_stats(config)
        return

    engine = GraphRAGEngine(config)
    engine.initialize()

    try:
        if args.query:
            if args.no_llm:
                # 仅检索模式
                result = engine.retriever.retrieve(args.query)
                print(f"\n{result.summary()}")
                print(f"\n--- Context ---\n{result.to_context()}")
            else:
                engine.ask(args.query)
        elif args.test:
            for i, tq in enumerate(TEST_QUERIES, 1):
                print(f"\n{'#' * 55}")
                print(f"  Test {i}/{len(TEST_QUERIES)}")
                print(f"{'#' * 55}")
                engine.ask(tq)
        else:
            run_interactive(engine)
    finally:
        engine.close()


if __name__ == "__main__":
    main()
