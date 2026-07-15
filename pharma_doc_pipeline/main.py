"""
制药供应链文档处理 Pipeline — 主入口
=====================================
5 步流水线:
  Step 0: 下载 PDF 文档 (ICH / FDA / WHO)
  Step 1: PDF → Markdown (MinerU / pymupdf4llm)
  Step 2: 层级分块 (Heading-based Hierarchical Chunking)
  Step 3: 内容富化 (LLM 清洗 + 摘要 + HyDE)
  Step 4: 向量化 + 存储 (FAISS + Neo4j 可选)

用法:
  python -m pharma_doc_pipeline.main --all           # 运行全部步骤
  python -m pharma_doc_pipeline.main --step 0        # 只下载文档
  python -m pharma_doc_pipeline.main --step 1        # 只转换 PDF
  python -m pharma_doc_pipeline.main --step 2        # 只分块
  python -m pharma_doc_pipeline.main --step 3        # 只做内容富化
  python -m pharma_doc_pipeline.main --step 4        # 只向量化
  python -m pharma_doc_pipeline.main --step 4 --neo4j  # 向量化+导入 Neo4j
"""

import argparse
import time
import sys
from pathlib import Path

from .config import PipelineSettings


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="制药供应链文档处理 Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--all", action="store_true",
        help="运行全部步骤 (0→4)"
    )
    parser.add_argument(
        "--step", type=int, choices=[0, 1, 2, 3, 4],
        help="运行指定步骤"
    )
    parser.add_argument(
        "--priority", type=int, default=1,
        help="文档下载优先级筛选 (1=核心, 2=扩展, 3=可选)"
    )
    parser.add_argument(
        "--backend", type=str, default=None,
        choices=["mineru", "pymupdf4llm", "raw"],
        help="PDF 解析后端"
    )
    parser.add_argument(
        "--llm", type=str, default=None,
        choices=["ollama", "deepseek", "moonshot", "openai"],
        help="LLM 后端"
    )
    parser.add_argument(
        "--no-hyde", action="store_true",
        help="禁用 HyDE 假设性问题生成"
    )
    parser.add_argument(
        "--neo4j", action="store_true",
        help="将文档 chunks 导入 Neo4j 并链接到 KG"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="显示 pipeline 状态"
    )
    return parser


def show_status():
    """显示 pipeline 各步骤的当前状态"""
    from .config import PDF_DIR, MD_DIR, CHUNKS_DIR, VECTORS_DIR

    print(f"\n{'=' * 55}")
    print(f"  制药文档 Pipeline 状态")
    print(f"{'=' * 55}\n")

    # Step 0: PDFs
    pdfs = list(PDF_DIR.glob("*.pdf"))
    print(f"  Step 0 [PDFs]:      {len(pdfs)} files in {PDF_DIR}")
    for p in pdfs[:5]:
        print(f"    - {p.name} ({p.stat().st_size / 1024:.0f} KB)")
    if len(pdfs) > 5:
        print(f"    ... +{len(pdfs)-5} more")

    # Step 1: Markdown
    mds = list(MD_DIR.rglob("*.md"))
    print(f"\n  Step 1 [Markdown]:  {len(mds)} files in {MD_DIR}")
    for m in mds[:5]:
        chars = m.stat().st_size
        print(f"    - {m.stem} ({chars:,} chars)")

    # Step 2: Chunks
    chunk_files = list(CHUNKS_DIR.glob("*_chunks.json"))
    total_chunks = 0
    for cf in chunk_files:
        import json
        with open(cf, 'r', encoding='utf-8') as f:
            total_chunks += len(json.load(f))
    print(f"\n  Step 2 [Chunks]:    {total_chunks} chunks in {len(chunk_files)} files")

    # Step 3: Enriched
    enriched = list(CHUNKS_DIR.glob("*_enriched.json"))
    print(f"  Step 3 [Enriched]:  {len(enriched)} enriched files")

    # Step 4: Vectors
    faiss_file = VECTORS_DIR / "pharma_docs.faiss"
    if faiss_file.exists():
        size_mb = faiss_file.stat().st_size / 1024 / 1024
        meta_file = VECTORS_DIR / "pharma_docs.meta.json"
        vec_count = 0
        if meta_file.exists():
            import json
            with open(meta_file, 'r', encoding='utf-8') as f:
                vec_count = len(json.load(f))
        print(f"  Step 4 [Vectors]:   {vec_count} vectors ({size_mb:.1f} MB)")
    else:
        print(f"  Step 4 [Vectors]:   (无索引)")

    print()


def run_pipeline(args):
    """执行 pipeline"""
    settings = PipelineSettings()

    # 覆盖配置
    if args.backend:
        settings.parser.backend = args.backend
    if args.llm:
        settings.llm.backend = args.llm
    if args.no_hyde:
        settings.chunking.enable_hyde = False

    start = time.time()

    steps_to_run = []
    if args.all:
        steps_to_run = [0, 1, 2, 3, 4]
    elif args.step is not None:
        steps_to_run = [args.step]
    else:
        print("请指定 --all 或 --step N")
        return

    print(f"\n{'═' * 55}")
    print(f"  制药文档 Pipeline — 执行步骤: {steps_to_run}")
    print(f"{'═' * 55}\n")

    for step in steps_to_run:
        step_start = time.time()
        print(f"\n{'─' * 50}")
        print(f"  STEP {step}")
        print(f"{'─' * 50}\n")

        try:
            if step == 0:
                from . import step_00_download
                step_00_download.run(priority=args.priority)

            elif step == 1:
                from . import step_01_convert
                step_01_convert.run(settings=settings)

            elif step == 2:
                from . import step_02_chunk
                step_02_chunk.run(settings=settings)

            elif step == 3:
                from . import step_03_enrich
                step_03_enrich.run(settings=settings)

            elif step == 4:
                from . import step_04_vectorize
                step_04_vectorize.run(settings=settings, neo4j=args.neo4j)

            elapsed = time.time() - step_start
            print(f"\n  ⏱ Step {step} 耗时: {elapsed:.1f}s")

        except Exception as e:
            print(f"\n  ✗ Step {step} 失败: {e}")
            import traceback
            traceback.print_exc()
            if not args.all:
                sys.exit(1)
            print("  → 继续执行后续步骤...")

    total = time.time() - start
    print(f"\n{'═' * 55}")
    print(f"  Pipeline 完成 — 总耗时: {total:.1f}s")
    print(f"{'═' * 55}\n")


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    if not args.all and args.step is None:
        parser.print_help()
        return

    run_pipeline(args)


if __name__ == "__main__":
    main()
