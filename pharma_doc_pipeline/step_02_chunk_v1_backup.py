"""
Step 2: 层级分块器 (Hierarchical Chunker)
==========================================
将 Markdown 文档按标题层级切分成树状 chunk，保留:
  - parents_context (面包屑路径)
  - prev/next_chunk_id (链表导航)
  - search_text (parents + content 拼接, 供 embedding 使用)
  - chunk_id (doc_key + seq + hash)

参考 StandardExtracter-hichunk 的输出格式，
但用正则做 rule-based 切分而非 LLM 预测。
"""

import re
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict

from .config import (MD_DIR, CHUNKS_DIR, CACHE_DIR,
                     PipelineSettings, ChunkingConfig)


# ─────────────────── 数据结构 ───────────────────

@dataclass
class ChunkNode:
    """单个 chunk 节点"""
    chunk_id: str = ""
    doc_id: str = ""
    level: int = 0                          # 0=文档根, 1=#, 2=##, 3=###
    heading: str = ""                       # 本级标题
    parents_context: str = ""               # 面包屑: "L1标题 > L2标题"
    content: str = ""                       # 正文内容 (不含标题)
    search_text: str = ""                   # parents_context + heading + content
    prev_chunk_id: Optional[str] = None
    next_chunk_id: Optional[str] = None
    page_hint: Optional[int] = None         # 来自 <!-- Page N --> 注释
    has_table: bool = False
    table_refs: List[str] = field(default_factory=list)  # 表格压缩引用
    char_count: int = 0
    line_count: int = 0
    children_count: int = 0
    metadata: Dict = field(default_factory=dict)


# ─────────────────── 辅助函数 ───────────────────

_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
_PAGE_RE = re.compile(r'<!--\s*Page\s+(\d+)\s*-->')
_TABLE_RE = re.compile(
    r'(\|[^\n]+\|\n(?:\|[-:| ]+\|\n)?(?:\|[^\n]+\|\n?)*)',
    re.MULTILINE
)


def _make_chunk_id(doc_id: str, seq: int, text: str) -> str:
    """生成 chunk ID: doc_id + 序号 + 内容前64字节hash"""
    h = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    return f"{doc_id}_C{seq:04d}_{h}"


def _detect_page(text: str) -> Optional[int]:
    """从 <!-- Page N --> 注释中提取页码"""
    m = _PAGE_RE.search(text)
    return int(m.group(1)) if m else None


def _compress_tables(text: str) -> Tuple[str, List[str]]:
    """
    将 Markdown 表格压缩为 [表: ...] 引用，
    返回 (压缩后文本, 表格引用列表)。
    灵感来自 hichunk 的 table compression。
    """
    table_refs = []

    def _replace(match):
        table_text = match.group(0)
        # 取第一行做摘要
        first_line = table_text.strip().split('\n')[0]
        # 提取列名
        cols = [c.strip() for c in first_line.split('|') if c.strip()]
        caption = ', '.join(cols[:5])
        if len(cols) > 5:
            caption += '...'
        ref = f"[表: {caption}]"
        table_refs.append(table_text)  # 保留原始表格
        return ref

    compressed = _TABLE_RE.sub(_replace, text)
    return compressed, table_refs


def _split_by_headings(md_text: str, max_depth: int = 3) -> List[Dict]:
    """
    用正则将 Markdown 按标题切分成段落列表。
    返回 [{level, heading, content, start_pos, end_pos}, ...]
    """
    segments = []
    last_end = 0

    # 找所有标题
    headings = []
    for m in _HEADING_RE.finditer(md_text):
        level = min(len(m.group(1)), max_depth)
        headings.append({
            "level": level,
            "heading": m.group(2).strip(),
            "start": m.start(),
            "end": m.end(),
        })

    # 如果没有任何标题，整个文档一个 chunk
    if not headings:
        return [{
            "level": 0,
            "heading": "",
            "content": md_text.strip(),
            "start_pos": 0,
            "end_pos": len(md_text),
        }]

    # 标题前的前言内容
    if headings[0]["start"] > 0:
        preamble = md_text[:headings[0]["start"]].strip()
        if preamble:
            segments.append({
                "level": 0,
                "heading": "(Preamble)",
                "content": preamble,
                "start_pos": 0,
                "end_pos": headings[0]["start"],
            })

    # 每个标题到下一个相同或更高级标题之间的内容
    for i, h in enumerate(headings):
        content_start = h["end"]
        if i + 1 < len(headings):
            content_end = headings[i + 1]["start"]
        else:
            content_end = len(md_text)

        content = md_text[content_start:content_end].strip()

        segments.append({
            "level": h["level"],
            "heading": h["heading"],
            "content": content,
            "start_pos": h["start"],
            "end_pos": content_end,
        })

    return segments


def _build_parents_context(heading_stack: List[str]) -> str:
    """生成面包屑"""
    return " > ".join(heading_stack) if heading_stack else ""


def _split_long_content(content: str, max_chars: int,
                        overlap: int) -> List[str]:
    """超长内容按段落边界拆分"""
    if len(content) <= max_chars:
        return [content]

    chunks = []
    paragraphs = content.split('\n\n')
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 > max_chars and current:
            chunks.append(current.strip())
            # 保留 overlap
            if overlap > 0 and len(current) > overlap:
                current = current[-overlap:] + "\n\n" + para
            else:
                current = para
        else:
            current = current + "\n\n" + para if current else para

    if current.strip():
        chunks.append(current.strip())

    return chunks if chunks else [content]


# ─────────────────── 核心分块器 ───────────────────

class HierarchicalChunker:
    """
    层级分块器: Markdown → Tree-structured Chunks
    
    三层结构:
      L0: 文档根 (保存全局 metadata)
      L1: 主章节 (#)
      L2: 子章节 (##)
      L3: 段落/条款 (###)
    
    每个 chunk 携带:
      - parents_context: 上级标题面包屑
      - search_text: 面包屑 + 正文 (用于 embedding)
      - prev/next: 链表导航
    """

    def __init__(self, config: ChunkingConfig = None):
        self.config = config or ChunkingConfig()

    def chunk_document(self, md_path: Path, doc_id: str = None) -> List[ChunkNode]:
        """将一个 Markdown 文件分块"""
        md_text = md_path.read_text(encoding='utf-8')
        doc_id = doc_id or md_path.stem

        # 1. 按标题分段
        segments = _split_by_headings(md_text, self.config.max_depth)

        # 2. 构造 chunk 树
        chunks: List[ChunkNode] = []
        heading_stack: List[str] = []  # 面包屑栈
        level_stack: List[int] = []    # 对应级别栈
        seq = 0

        for seg in segments:
            level = seg["level"]
            heading = seg["heading"]
            content = seg["content"]

            # 更新面包屑栈
            while level_stack and level_stack[-1] >= level:
                level_stack.pop()
                heading_stack.pop()

            if heading and heading != "(Preamble)":
                heading_stack.append(heading)
                level_stack.append(level)

            parents_ctx = _build_parents_context(heading_stack[:-1]) if len(heading_stack) > 1 else ""

            # 表格压缩
            compressed_content, table_refs = _compress_tables(content)

            # 超长内容拆分
            sub_contents = _split_long_content(
                compressed_content,
                self.config.max_chunk_chars,
                self.config.overlap_chars
            )

            for i, sub_content in enumerate(sub_contents):
                seq += 1

                # 生成 search_text
                search_parts = []
                if parents_ctx:
                    search_parts.append(parents_ctx)
                if heading:
                    search_parts.append(heading)
                search_parts.append(sub_content)
                search_text = "\n".join(search_parts)

                # 子分块后缀
                sub_heading = heading
                if len(sub_contents) > 1:
                    sub_heading = f"{heading} (Part {i+1}/{len(sub_contents)})"

                chunk = ChunkNode(
                    chunk_id=_make_chunk_id(doc_id, seq, sub_content),
                    doc_id=doc_id,
                    level=level,
                    heading=sub_heading,
                    parents_context=parents_ctx,
                    content=sub_content,
                    search_text=search_text,
                    page_hint=_detect_page(content),
                    has_table=bool(table_refs),
                    table_refs=table_refs if i == 0 else [],
                    char_count=len(sub_content),
                    line_count=sub_content.count('\n') + 1,
                )
                chunks.append(chunk)

        # 3. 链表连接
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.prev_chunk_id = chunks[i - 1].chunk_id
            if i < len(chunks) - 1:
                chunk.next_chunk_id = chunks[i + 1].chunk_id

        # 4. 统计子节点数
        self._count_children(chunks)

        return chunks

    def _count_children(self, chunks: List[ChunkNode]):
        """计算每个 chunk 的子节点数"""
        for i, chunk in enumerate(chunks):
            count = 0
            for j in range(i + 1, len(chunks)):
                if chunks[j].level <= chunk.level:
                    break
                if chunks[j].level == chunk.level + 1:
                    count += 1
            chunk.children_count = count

    def chunk_all(self, md_dir: Path = None) -> Dict[str, List[ChunkNode]]:
        """批量分块所有 markdown 文件"""
        md_dir = md_dir or MD_DIR
        md_files = []

        # 支持子目录结构 (MinerU: md_dir/doc_name/doc_name.md)
        for md_file in sorted(md_dir.rglob("*.md")):
            md_files.append(md_file)

        if not md_files:
            print("  ⚠ 无 Markdown 文件可分块")
            return {}

        print(f"╔{'═' * 50}╗")
        print(f"║  层级分块 — 共 {len(md_files)} 个文件")
        print(f"║  最大深度: L{self.config.max_depth}")
        print(f"╚{'═' * 50}╝\n")

        all_results = {}
        total_chunks = 0

        for md_file in md_files:
            doc_id = md_file.stem
            print(f"  📄 {doc_id}...", end=" ", flush=True)

            chunks = self.chunk_document(md_file, doc_id)
            all_results[doc_id] = chunks
            total_chunks += len(chunks)

            # 统计层级分布
            level_dist = {}
            for c in chunks:
                level_dist[c.level] = level_dist.get(c.level, 0) + 1
            dist_str = " ".join(f"L{k}:{v}" for k, v in sorted(level_dist.items()))
            print(f"{len(chunks)} chunks ({dist_str})")

        print(f"\n✅ 分块完成: {total_chunks} chunks / {len(md_files)} docs")
        return all_results


# ─────────────────── 输出写入 ───────────────────

def save_chunks(all_chunks: Dict[str, List[ChunkNode]],
                output_dir: Path = None):
    """将 chunks 保存为 JSON"""
    output_dir = output_dir or CHUNKS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    for doc_id, chunks in all_chunks.items():
        out_file = output_dir / f"{doc_id}_chunks.json"
        records = []
        for c in chunks:
            d = asdict(c)
            # table_refs 单独存
            if c.table_refs:
                tables_file = output_dir / f"{doc_id}_tables.json"
                # 追加到表格文件
                existing_tables = []
                if tables_file.exists():
                    with open(tables_file, 'r', encoding='utf-8') as f:
                        existing_tables = json.load(f)
                existing_tables.extend([{
                    "chunk_id": c.chunk_id,
                    "table": t
                } for t in c.table_refs])
                with open(tables_file, 'w', encoding='utf-8') as f:
                    json.dump(existing_tables, f, ensure_ascii=False, indent=2)
                d["table_refs"] = [f"[表 ref: {doc_id}_tables.json]"]

            records.append(d)

        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        print(f"  💾 {out_file.name}: {len(records)} chunks")

    # 汇总统计
    summary = {
        "total_documents": len(all_chunks),
        "total_chunks": sum(len(v) for v in all_chunks.values()),
        "documents": {
            doc_id: {
                "chunks": len(chunks),
                "levels": dict(sorted({
                    c.level: sum(1 for x in chunks if x.level == c.level)
                    for c in chunks
                }.items()))
            }
            for doc_id, chunks in all_chunks.items()
        }
    }
    summary_path = output_dir / "_chunks_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def run(**kwargs) -> Dict[str, List[ChunkNode]]:
    """Step 2 入口"""
    settings = kwargs.get("settings", PipelineSettings())
    chunker = HierarchicalChunker(config=settings.chunking)

    md_dir = kwargs.get("md_dir", MD_DIR)
    all_chunks = chunker.chunk_all(md_dir=md_dir)

    save_chunks(all_chunks)
    return all_chunks
