"""
build_table_chunks.py
======================
从各文档 Markdown 中提取 HTML 表格，生成自然语言摘要，
在 Neo4j 中创建 TableChunk 节点并与父 DocChunk 连接。

设计意图:
  (DocChunk) -[:HAS_TABLE]-> (TableChunk {summary, raw_html, col_headers})

  检索时:
    FAISS 返回 DocChunk → retriever 顺带取出 HAS_TABLE 的 TableChunk
    OR (可选) 将 table summary 也加入 FAISS，独立命中后反查 TableChunk

运行:
    python build_table_chunks.py                    # 处理全部文档, 纯解析摘要
    python build_table_chunks.py --llm              # 用 LLM (Moonshot) 生成摘要
    python build_table_chunks.py --doc ich_q3d_r2   # 只处理指定文档
    python build_table_chunks.py --dry-run          # 只统计, 不写 Neo4j
"""

import re
import json
import hashlib
import argparse
from pathlib import Path

NEO4J_URI  = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASS = "Nb87891882"

MARKDOWN_DIR = Path("data/markdown")
CHUNKS_DIR   = Path("data/chunks")

# ─── 与 step_02_chunk.py 相同的 HTML 表格正则 ─────────────────────
_HTML_TABLE_RE = re.compile(r"<html>.*?</html>", re.DOTALL | re.IGNORECASE)
_HEADING_RE    = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)


# ════════════════════════════════════════════════════════════════
# 1. 从 Markdown 文件提取表格（附位置信息）
# ════════════════════════════════════════════════════════════════

def extract_tables_from_markdown(md_path: Path) -> list:
    """
    返回 [{"html": str, "char_pos": int, "table_index": int}]
    """
    text = md_path.read_text(encoding="utf-8", errors="replace")
    results = []
    for i, m in enumerate(_HTML_TABLE_RE.finditer(text)):
        results.append({
            "html": m.group(0),
            "char_pos": m.start(),
            "table_index": i,
        })
    return results


def get_section_at_pos(md_text: str, char_pos: int) -> str:
    """
    在 markdown 文本中找到 char_pos 位置之前最近的标题，
    返回标题文本（用于匹配 DocChunk.heading）。
    """
    best_heading = ""
    for m in _HEADING_RE.finditer(md_text):
        if m.start() > char_pos:
            break
        best_heading = m.group(2).strip()
    return best_heading


# ════════════════════════════════════════════════════════════════
# 2. 从 HTML 生成表格摘要（纯解析版，无 LLM）
# ════════════════════════════════════════════════════════════════

def html_table_to_parsed_summary(html: str, heading: str = "") -> dict:
    """
    解析 HTML 表格，返回:
      {
        "col_headers": ["Col1", "Col2", ...],
        "row_count": int,
        "summary": "natural language summary (rule-based)"
      }
    """
    th_re = re.compile(r"<th[^>]*>(.*?)</th>", re.IGNORECASE | re.DOTALL)
    td_re = re.compile(r"<td[^>]*>(.*?)</td>", re.IGNORECASE | re.DOTALL)
    tr_re = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)

    def clean_cell(s: str) -> str:
        s = re.sub(r"<[^>]+>", "", s).strip()
        s = re.sub(r"\s+", " ", s)
        return s[:80]

    # 列标题
    headers = [clean_cell(c) for c in th_re.findall(html)]
    if not headers:
        trs = tr_re.findall(html)
        if trs:
            first_row_cells = td_re.findall(trs[0])
            headers = [clean_cell(c) for c in first_row_cells]

    # 去空
    headers = [h for h in headers if h][:8]

    # 行数 (排除表头行)
    all_trs = tr_re.findall(html)
    row_count = max(0, len(all_trs) - (1 if th_re.search(html) else 0))

    # 规则生成摘要
    context = f"in section '{heading}'" if heading else ""
    if headers:
        col_str = ", ".join(f'"{h}"' for h in headers[:5])
        extra = f"and {len(headers)-5} more columns" if len(headers) > 5 else ""
        summary = (
            f"Table {context} with {row_count} rows and columns: "
            f"{col_str}{(' ' + extra) if extra else ''}."
        )
    else:
        summary = f"Table {context} with {row_count} rows (column headers not detected)."

    return {"col_headers": headers, "row_count": row_count, "summary": summary}


# ════════════════════════════════════════════════════════════════
# 3. LLM 摘要（可选）
# ════════════════════════════════════════════════════════════════

LLM_PROMPT = """Summarize the following HTML table from a pharmaceutical regulatory document in 2-3 sentences.
Focus on: what data this table presents, key parameters/thresholds, and its regulatory significance.
Write in English. Return only the summary text, nothing else.

Section heading: {heading}

Table HTML:
{html}"""

def llm_table_summary(html: str, heading: str = "", api_key: str = "") -> str:
    """
    用 Moonshot Kimi 生成表格摘要（可选）。
    若 API key 为空则回退到规则摘要。
    """
    if not api_key:
        return ""
    try:
        import requests
        url = "https://api.moonshot.cn/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        # 截断过长的 HTML
        html_trunc = html[:4000]
        payload = {
            "model": "moonshot-v1-8k",
            "messages": [
                {"role": "user", "content": LLM_PROMPT.format(
                    heading=heading, html=html_trunc)}
            ],
            "max_tokens": 200,
            "temperature": 0.0,
        }
        r = requests.post(url, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"    ⚠ LLM 摘要失败: {e}")
        return ""


# ════════════════════════════════════════════════════════════════
# 4. 写入 Neo4j
# ════════════════════════════════════════════════════════════════

def write_table_chunks_to_neo4j(session, table_records: list) -> int:
    """
    table_records: [{
        table_id, doc_id, parent_chunk_id, heading,
        table_index, col_headers (list), summary, raw_html
    }]
    """
    # 创建约束
    try:
        session.run(
            "CREATE CONSTRAINT IF NOT EXISTS "
            "FOR (t:TableChunk) REQUIRE t.table_id IS UNIQUE"
        )
    except Exception:
        pass

    created = 0
    for rec in table_records:
        result = session.run(
            """
            MERGE (t:TableChunk {table_id: $table_id})
            SET t.doc_id          = $doc_id,
                t.parent_chunk_id = $parent_chunk_id,
                t.heading         = $heading,
                t.table_index     = $table_index,
                t.col_headers     = $col_headers,
                t.summary         = $summary,
                t.raw_html        = $raw_html
            WITH t
            MATCH (c:DocChunk {chunk_id: $parent_chunk_id})
            MERGE (c)-[:HAS_TABLE]->(t)
            RETURN t.table_id AS tid
            """,
            table_id=rec["table_id"],
            doc_id=rec["doc_id"],
            parent_chunk_id=rec["parent_chunk_id"],
            heading=rec["heading"],
            table_index=rec["table_index"],
            col_headers=rec["col_headers"],
            summary=rec["summary"],
            raw_html=rec["raw_html"][:8000],  # Neo4j 字段限制
        )
        row = result.single()
        if row:
            created += 1
    return created


# ════════════════════════════════════════════════════════════════
# 5. 为文档找父 DocChunk（从 Neo4j 按 heading 匹配）
# ════════════════════════════════════════════════════════════════

def load_chunk_headings(session, doc_id: str) -> list:
    """
    返回 [{chunk_id, heading, level, content_prefix}]
    供后续最近标题匹配使用
    """
    rows = list(session.run(
        "MATCH (c:DocChunk {doc_id: $doc_id}) "
        "RETURN c.chunk_id AS cid, c.heading AS h, c.level AS lvl "
        "ORDER BY c.level, c.heading",
        doc_id=doc_id
    ))
    return [{"chunk_id": r["cid"], "heading": r["h"], "level": r["lvl"]} for r in rows]


def find_best_chunk(section_heading: str, chunks: list, doc_id: str) -> str:
    """
    通过最近标题 fuzzy 匹配找 chunk_id。
    优先完全匹配，其次子串匹配，最后按 doc_id 取 level=1 的第一个。
    """
    if not section_heading:
        # 无标题 → 取 level=0 或 level=1 的第一个 chunk
        for c in chunks:
            if c["level"] in (0, 1):
                return c["chunk_id"]
        return chunks[0]["chunk_id"] if chunks else ""

    sh = section_heading.lower().strip()

    # 1. 完全匹配（忽略 #）
    for c in chunks:
        h = re.sub(r"^#+\s*", "", c["heading"]).lower().strip()
        if h == sh:
            return c["chunk_id"]

    # 2. 子串匹配
    for c in chunks:
        h = re.sub(r"^#+\s*", "", c["heading"]).lower().strip()
        if h in sh or sh in h:
            return c["chunk_id"]

    # 3. 取 level=1 的第一个
    for c in chunks:
        if c["level"] == 1:
            return c["chunk_id"]

    return chunks[0]["chunk_id"] if chunks else ""


# ════════════════════════════════════════════════════════════════
# 6. 主流程
# ════════════════════════════════════════════════════════════════

def process_document(session, doc_id: str, md_file: Path,
                     use_llm: bool = False, api_key: str = "",
                     dry_run: bool = False) -> int:
    """处理单个文档，返回写入的 TableChunk 数量"""

    # 读取 markdown
    md_text = md_file.read_text(encoding="utf-8", errors="replace")

    # 提取 HTML 表格
    table_list = extract_tables_from_markdown(md_file)
    if not table_list:
        return 0

    print(f"  {doc_id}: 发现 {len(table_list)} 个 HTML 表格")

    # 加载该文档的 DocChunk 标题列表（用于匹配父节点）
    chunk_meta = load_chunk_headings(session, doc_id)
    if not chunk_meta:
        print(f"    [WARN] Neo4j 中无 doc_id={doc_id} 的 DocChunk，跳过")
        return 0

    table_records = []
    for tbl in table_list:
        html      = tbl["html"]
        pos       = tbl["char_pos"]
        idx       = tbl["table_index"]

        # 找到表格所在的 section 标题
        section_heading = get_section_at_pos(md_text, pos)

        # 在 Neo4j chunks 中匹配最佳父 chunk
        parent_chunk_id = find_best_chunk(section_heading, chunk_meta, doc_id)

        # 生成摘要
        parsed = html_table_to_parsed_summary(html, heading=section_heading)
        if use_llm and api_key:
            lsummary = llm_table_summary(html, heading=section_heading, api_key=api_key)
            summary = lsummary if lsummary else parsed["summary"]
        else:
            summary = parsed["summary"]

        # 生成唯一 table_id
        h = hashlib.md5(f"{doc_id}_{idx}_{html[:100]}".encode()).hexdigest()[:8]
        table_id = f"{doc_id}_t{idx:03d}_{h}"

        table_records.append({
            "table_id": table_id,
            "doc_id": doc_id,
            "parent_chunk_id": parent_chunk_id,
            "heading": section_heading,
            "table_index": idx,
            "col_headers": parsed["col_headers"],
            "summary": summary,
            "raw_html": html,
        })

        print(f"    [{idx:03d}] section='{section_heading[:50]}' → "
              f"chunk={parent_chunk_id[:30]} | cols={parsed['col_headers'][:3]}")

    if dry_run:
        print(f"  [DRY RUN] 将写入 {len(table_records)} 个 TableChunk")
        return len(table_records)

    created = write_table_chunks_to_neo4j(session, table_records)
    print(f"  [OK] 写入 {created}/{len(table_records)} 个 TableChunk 节点")
    return created


def main():
    parser = argparse.ArgumentParser(description="从 Markdown 提取表格，写入 Neo4j")
    parser.add_argument("--doc",     type=str, default="",
                        help="只处理指定 doc_id（如 ich_q3d_r2）")
    parser.add_argument("--llm",     action="store_true",
                        help="用 Moonshot LLM 生成摘要（需 MOONSHOT_API_KEY）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只统计，不写 Neo4j")
    args = parser.parse_args()

    # Moonshot API key
    api_key = ""
    if args.llm:
        import os
        api_key = os.environ.get("MOONSHOT_API_KEY", "")
        if not api_key:
            print("⚠ --llm 需要 MOONSHOT_API_KEY 环境变量，回退到规则摘要")

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("[ERROR] pip install neo4j")
        return

    print(f"[INFO] 连接 Neo4j: {NEO4J_URI}")
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASS))

    total_tables = 0

    try:
        with driver.session() as session:
            # 发现所有 doc_id（markdown 目录名 = doc_id）
            if args.doc:
                doc_dirs = [MARKDOWN_DIR / args.doc]
            else:
                doc_dirs = sorted(d for d in MARKDOWN_DIR.iterdir() if d.is_dir())

            for doc_dir in doc_dirs:
                doc_id = doc_dir.name
                # 找 .md 文件
                md_files = sorted(doc_dir.glob("*.md"))
                if not md_files:
                    continue
                md_file = md_files[0]  # 取第一个（通常只有一个）
                cnt = process_document(
                    session, doc_id, md_file,
                    use_llm=args.llm, api_key=api_key,
                    dry_run=args.dry_run
                )
                total_tables += cnt

            if not args.dry_run:
                # 最终统计
                r = session.run(
                    "MATCH (t:TableChunk) RETURN count(t) AS cnt"
                ).single()
                r2 = session.run(
                    "MATCH ()-[r:HAS_TABLE]->() RETURN count(r) AS cnt"
                ).single()
                print(f"\n── 最终统计 ──")
                print(f"  TableChunk 节点: {r['cnt']}")
                print(f"  HAS_TABLE 边:   {r2['cnt']}")

    finally:
        driver.close()

    print(f"\n[DONE] 共处理 {total_tables} 个表格")


if __name__ == "__main__":
    main()
