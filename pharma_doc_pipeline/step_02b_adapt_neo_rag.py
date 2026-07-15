"""
步骤 02b: Neo_StandardExtracter RAG JSON → 标准 ChunkNode 格式适配器
=====================================================================
将 Neo_StandardExtracter 输出的 *_rag.json (RAGDocument 列表)
转换为 pharma_graphrag/retriever.py 和 step_04_vectorize.py 所需的
*_enriched.json (ChunkNode 格式) 文件。

输入:  Neo_StandardExtracter/output/*_rag.json
输出:  data/chunks/*_enriched.json

RAGDocument 字段:
  doc_id, standard_id, title, original_title, level, path,
  section_number, parent_id, children, content, tables,
  summary (bool), keywords, entities, section_type

ChunkNode 字段 (retriever.py 所需):
  chunk_id, doc_id, level, heading, parents_context,
  content, search_text, summary, prev_chunk_id, next_chunk_id,
  has_table, table_refs, char_count, keywords, entities,
  section_number, section_type, hyde_questions

用法:
  python pharma_doc_pipeline/step_02b_adapt_neo_rag.py
  python pharma_doc_pipeline/step_02b_adapt_neo_rag.py --input Neo_StandardExtracter/output --output data/chunks
"""

import json
import re
import argparse
import pathlib
import sys

BASE_DIR = pathlib.Path(__file__).parent.parent
DEFAULT_INPUT  = BASE_DIR / "Neo_StandardExtracter" / "output"
DEFAULT_OUTPUT = BASE_DIR / "data" / "chunks"


# ─────────────────────────────────────────────
#  ID 规范化工具
# ─────────────────────────────────────────────

def normalize_id(raw: str) -> str:
    """将 RAGDocument.doc_id / standard_id 转换为安全的 snake_case ID。

    示例:
      "ICH Q10_1_introduction" → "ich_q10_1_introduction"
      "ICH Q10"               → "ich_q10"
      "FDA CFR 21 Part 211"   → "fda_cfr_21_part_211"
    """
    s = raw.lower()
    s = re.sub(r"[\s\-/]+", "_", s)     # 空白/连字符 → 下划线
    s = re.sub(r"[^\w]", "_", s)        # 非字母数字 → 下划线
    s = re.sub(r"_+", "_", s)           # 合并连续下划线
    s = s.strip("_")
    return s


def build_doc_id(standard_id: str) -> str:
    """从 standard_id 构建文档级 doc_id。"""
    return normalize_id(standard_id)


# ─────────────────────────────────────────────
#  父链路径构建
# ─────────────────────────────────────────────

def build_parents_context(rag_doc: dict, id_map: dict) -> str:
    """沿 parent_id 链向上收集父节点标题，构建 " > " 分隔的面包屑路径。

    例如: "ICH Q10 > 4 Continual Improvement > 4.1 Process Performance"
         对应 level=3 的子节点
    """
    ancestors = []
    current = rag_doc
    visited = set()
    while current.get("parent_id"):
        pid = current["parent_id"]
        if pid in visited:
            break  # 检测到循环引用，终止
        visited.add(pid)
        parent = id_map.get(pid)
        if parent is None:
            break
        ancestors.append(parent.get("original_title") or parent.get("title") or "")
        current = parent

    # ancestors 现在是从直接父到根（倒序），翻转后是从根到直接父
    ancestors.reverse()
    return " > ".join(a for a in ancestors if a)


# ─────────────────────────────────────────────
#  单文件转换
# ─────────────────────────────────────────────

def convert_rag_file(rag_path: pathlib.Path, output_dir: pathlib.Path) -> int:
    """转换单个 *_rag.json 文件，返回生成的 chunk 数量。"""
    with open(rag_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # data 可能是 list[RAGDocument dict] 或 {"documents": [...], "metadata": {...}}
    if isinstance(data, dict):
        rag_docs = data.get("documents", [])
    elif isinstance(data, list):
        rag_docs = data
    else:
        print(f"  [WARN] {rag_path.name}: 未知格式，跳过")
        return 0

    if not rag_docs:
        print(f"  [WARN] {rag_path.name}: 空文档列表，跳过")
        return 0

    # 确定 doc_id（取第一个条目的 standard_id，或从文件名推断）
    first = rag_docs[0]
    standard_id = first.get("standard_id", "")
    if standard_id:
        file_doc_id = build_doc_id(standard_id)
    else:
        # 从文件名推断，去掉 _rag 后缀
        stem = rag_path.stem
        if stem.endswith("_rag"):
            stem = stem[:-4]
        file_doc_id = normalize_id(stem)

    # 构建 doc_id → RAGDocument 的快速查找表
    id_map: dict = {}
    for rd in rag_docs:
        raw_id = rd.get("doc_id", "")
        id_map[raw_id] = rd

    # ── 转换每个 RAGDocument → ChunkNode ──
    chunks = []
    for rd in rag_docs:
        raw_id   = rd.get("doc_id", "")
        chunk_id = normalize_id(raw_id) if raw_id else f"{file_doc_id}_unknown"

        doc_id_for_chunk = file_doc_id

        heading = rd.get("original_title") or rd.get("title") or ""
        level   = rd.get("level", 1)

        parents_ctx = build_parents_context(rd, id_map)

        content = rd.get("content", "")
        was_summarized = rd.get("summary", False)  # bool

        # search_text: 面包屑 + 标题 + 正文（用于向量化）
        search_parts = []
        if parents_ctx:
            search_parts.append(parents_ctx)
        if heading:
            search_parts.append(heading)
        if content:
            search_parts.append(content)
        search_text = "\n".join(search_parts)

        tables      = rd.get("tables", [])
        has_table   = len(tables) > 0

        keywords    = rd.get("keywords", [])
        entities    = rd.get("entities", [])

        chunk = {
            "chunk_id":        chunk_id,
            "doc_id":          doc_id_for_chunk,
            "level":           level,
            "heading":         heading,
            "parents_context": parents_ctx,
            "content":         content,
            "search_text":     search_text,
            # 若 LLM 摘要过，summary 字段存摘要文本（供 retriever 展示）
            # 否则为空字符串
            "summary":         content if was_summarized else "",
            "was_summarized":  was_summarized,
            # 链接关系 — 下面的第二遍扫描会填充
            "prev_chunk_id":   None,
            "next_chunk_id":   None,
            # 表格
            "has_table":       has_table,
            "table_refs":      tables,
            # 统计
            "char_count":      len(content),
            # 丰富元数据
            "keywords":        keywords,
            "entities":        entities,
            "section_number":  rd.get("section_number", ""),
            "section_type":    rd.get("section_type", "normal"),
            # 父子关系（保留供高级检索使用）
            "parent_chunk_id": normalize_id(rd["parent_id"]) if rd.get("parent_id") else None,
            "children_ids":    [normalize_id(c) for c in rd.get("children", [])],
            # HyDE 问题留空（可选：后续运行 step_03 生成）
            "hyde_questions":  [],
        }
        chunks.append(chunk)

    # ── 第二遍：按顺序分配 prev/next 链接 ──
    for i, chunk in enumerate(chunks):
        if i > 0:
            chunk["prev_chunk_id"] = chunks[i - 1]["chunk_id"]
        if i < len(chunks) - 1:
            chunk["next_chunk_id"] = chunks[i + 1]["chunk_id"]

    # ── 写出 *_enriched.json ──
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"{file_doc_id}_enriched.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"  OK  {rag_path.name} → {out_path.name}  ({len(chunks)} chunks)")
    return len(chunks)


# ─────────────────────────────────────────────
#  主流程
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="将 Neo_StandardExtracter RAG JSON 转换为 ChunkNode 格式"
    )
    parser.add_argument("--input",  "-i", default=str(DEFAULT_INPUT),
                        help=f"RAG JSON 输入目录 (默认: {DEFAULT_INPUT})")
    parser.add_argument("--output", "-o", default=str(DEFAULT_OUTPUT),
                        help=f"ChunkNode 输出目录 (默认: {DEFAULT_OUTPUT})")
    args = parser.parse_args()

    input_dir  = pathlib.Path(args.input)
    output_dir = pathlib.Path(args.output)

    if not input_dir.exists():
        print(f"[ERROR] 输入目录不存在: {input_dir}")
        sys.exit(1)

    # 递归搜索所有 *_rag.json（包括 intermediate/ 子目录）
    rag_files = sorted(input_dir.rglob("*_rag.json"))
    if not rag_files:
        print(f"[WARN] 在 {input_dir} 中未找到 *_rag.json 文件")
        sys.exit(0)

    print(f"\n=== Neo_StandardExtracter RAG JSON → ChunkNode 适配器 ===")
    print(f"输入: {input_dir}  ({len(rag_files)} 文件)")
    print(f"输出: {output_dir}\n")

    total_chunks = 0
    errors = []
    for rag_path in rag_files:
        try:
            n = convert_rag_file(rag_path, output_dir)
            total_chunks += n
        except Exception as e:
            print(f"  [ERROR] {rag_path.name}: {e}")
            errors.append((rag_path.name, str(e)))

    print(f"\n=== 完成 ===")
    print(f"  文件: {len(rag_files) - len(errors)} 成功 / {len(errors)} 失败")
    print(f"  总 chunks: {total_chunks}")

    if errors:
        print("\n失败文件:")
        for name, err in errors:
            print(f"  {name}: {err}")

    # 写出汇总
    summary_path = output_dir / "_chunks_summary.json"
    summary = {
        "total_files":  len(rag_files) - len(errors),
        "total_chunks": total_chunks,
        "errors":       errors,
        "source":       "Neo_StandardExtracter",
    }
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"\n汇总已写入: {summary_path}")


if __name__ == "__main__":
    main()
