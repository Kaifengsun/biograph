"""
Step 2: 层级分块器 (Hierarchical Chunker) — v2 重构版
====================================================
重构重点 (修复三大问题):
  1. 智能清洗: 自动检测并移除页眉/页脚/孤立页码
  2. 语义切分: 永远不在单词中间切断, 递归分隔符优先级
  3. 动态标题: 正则检测 ICH 文档的 **N.** **TITLE** 格式

保留全部后处理结构:
  - parents_context (面包屑路径)
  - prev/next_chunk_id (链表导航)
  - search_text (parents + content 拼接, 供 embedding)
  - 表格压缩为外部引用
  - HyDE 假设性问题 (step_03)
"""

import re
import json
import hashlib
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field, asdict
from collections import Counter

from .config import (MD_DIR, CHUNKS_DIR, CACHE_DIR,
                     PipelineSettings, ChunkingConfig)


# ═══════════════════════════════════════════════════════════════
#  数据结构 (与 v1 完全兼容)
# ═══════════════════════════════════════════════════════════════

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
    table_refs: List[str] = field(default_factory=list)
    char_count: int = 0
    line_count: int = 0
    children_count: int = 0
    metadata: Dict = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
#  正则表达式 (预编译)
# ═══════════════════════════════════════════════════════════════

# Markdown 标题 (# ~ ######)
_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

# 页码注释 <!-- Page N -->
_PAGE_RE = re.compile(r'<!--\s*Page\s+(\d+)\s*-->')

# Markdown 表格
_TABLE_RE = re.compile(
    r'(\|[^\n]+\|\n(?:\|[-:| ]+\|\n)?(?:\|[^\n]+\|\n?)*)',
    re.MULTILINE
)

# MinerU 输出的 HTML 表格 (<html><body><table>...</table></body></html>)
_HTML_TABLE_RE = re.compile(
    r'<html>.*?</html>',
    re.DOTALL | re.IGNORECASE
)

# ICH 风格编号标题 (出现在 bold 中或裸文本中)
# 匹配: **1.** **TITLE TEXT**
#        **4.1.**  Title Text
#        **ANNEX I: TITLE**
#        4.1 Title Text  (裸编号)
_ICH_HEADING_PATTERNS = [
    # Pattern 1: **N.** **TITLE** 或 **N.N.** **TITLE** (ICH 最常见)
    re.compile(
        r'^(\*{2}\d+(?:\.\d+)*\.?\*{2})\s+(\*{2}.+?\*{2})\s*$',
        re.MULTILINE
    ),
    # Pattern 2: **N. TITLE** (标题和编号在同一个 bold block)
    re.compile(
        r'^\*{2}(\d+(?:\.\d+)*\.?)\s+([A-Z][A-Z\s,/()&:*-]+)\*{2}\s*$',
        re.MULTILINE
    ),
    # Pattern 3: **ANNEX/APPENDIX ...: TITLE**
    re.compile(
        r'^\*{2}((?:ANNEX|APPENDIX)\s+[IVX\d]+[A-Z]?(?:\s*:)?)\s+(.+?)\*{2}\s*$',
        re.MULTILINE
    ),
    # Pattern 4: 裸编号行 — "4.1 Title Text" 或 "4.1. Title Text"
    # 注意: 需要配合 _is_likely_heading_text() 验证, 避免误抓编号正文段落
    re.compile(
        r'^(\d+\.\d+(?:\.\d+)?\.?)\s+([A-Z][A-Za-z\s,/()&:-]{3,}?)\s*$',
        re.MULTILINE
    ),
]

# 孤立页码 (只有一个数字或罗马数字的行)
_ISOLATED_PAGE_NUM_RE = re.compile(
    r'^\s*([ivxlcdm]+|\d{1,3})\s*$',
    re.IGNORECASE
)


# ═══════════════════════════════════════════════════════════════
#  Step A: 智能数据清洗 (Markdown 预处理)
# ═══════════════════════════════════════════════════════════════

def _detect_repeating_patterns(text: str, min_occurrences: int = 3) -> List[str]:
    """
    自动检测 Markdown 中重复出现 >= min_occurrences 次的"脏行"。
    这些通常是页眉 (如 "ICH Q9(R1) Guideline") 或页脚。
    
    算法: 统计所有非空行(去掉 # / ** / _ 装饰后)出现频率,
    如果某行 > min_occurrences 且字数 <= 10, 极可能是页眉/页脚。
    """
    lines = text.split('\n')
    normalized_counter = Counter()
    norm_to_raw = {}
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 跳过 Markdown 标题行 (# 开头) — 这些是真正的标题, 不是页眉/页脚
        if stripped.startswith('#'):
            continue
        # 去除 markdown 粗体/斜体标记进行比较
        norm = re.sub(r'[\*_#`]+', '', stripped).strip()
        if not norm or len(norm) < 3:
            continue
        # 忽略表格行和纯标点
        if norm.startswith('|') or norm.startswith('---'):
            continue
        normalized_counter[norm] += 1
        if norm not in norm_to_raw:
            norm_to_raw[norm] = stripped
    
    # 筛选: 出现 >= min_occurrences 次, 字数 2~12 (页眉/页脚通常是短语)
    # word_count >= 2 排除单词行末残留 ("appropriate.", "use." 等)
    patterns = []
    for norm, count in normalized_counter.items():
        if count >= min_occurrences:
            word_count = len(norm.split())
            if 2 <= word_count <= 12:
                patterns.append(norm_to_raw[norm])
    
    return patterns


def _strip_toc_section(text: str) -> str:
    """
    检测并移除 TABLE OF CONTENTS 段落。
    TOC 中的编号条目会干扰后续的标题检测。

    改进策略: 使用"重复标题锚点"定位 TOC 结束边界。
    TOC 通常在正文开始前，而正文会重复文档标题或第1节标题。
    在 TOC 内收集所有 # 标题的纯文本（去掉点号/页码），
    然后找这些标题在 TOC 之后的首次重复出现，即为 TOC 结束处。
    """
    toc_patterns = [
        r'\*{2}TABLE OF CONTENTS\*{2}',
        r'TABLE OF CONTENTS',
    ]

    # 清洗标题行的 TOC 装饰 (点号序列、页码): "SECTION .. . 12" → "SECTION"
    def _clean_toc_heading(h: str) -> str:
        h = re.sub(r'[\*_#]+', '', h).strip()
        # 去掉末尾的点号序列+可选页码: " ... 12", " . . 34", " ...." (无页码)
        # \d* 而非 \d+, 使页码变为可选
        h = re.sub(r'[\s.]+\d*\s*$', '', h).strip()
        return h.lower()

    for pat in toc_patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            toc_start = text.rfind('\n', 0, m.start())
            if toc_start == -1:
                toc_start = 0

            # ── 策略1: 在 TOC 之后找到同一个 # 标题的第二次出现 ──
            # 先收集 TOC 之后直到某个合理位置内出现的 # 标题 (代表 TOC 条目)
            toc_region_text = text[m.end():]
            toc_headings_raw = re.findall(r'^#\s+(.+)$', toc_region_text, re.MULTILINE)

            # 对每个 TOC 标题, 寻找其在 TOC 起始点之后的第二次出现
            # (即去掉 TOC 注释后仍相同的标题)
            toc_end = None
            for raw_h in toc_headings_raw[:30]:  # 只看前30个候选
                cleaned = _clean_toc_heading(raw_h)
                if len(cleaned) < 5:  # 太短的标题忽略
                    continue
                # 在 TOC 起始点之后找同名标题的出现
                # 用原始文本搜索, 逐段匹配
                # 在 toc_region_text 中找此 clean 标题的第2次出现
                # (第1次是在 TOC 里, 第2次是在正文里)
                escaped = re.escape(cleaned)
                # 先找第1次 (TOC 条目)
                first = re.search(
                    r'^#\s+' + escaped + r'[\s.]*\d*\s*$',
                    toc_region_text, re.MULTILINE | re.IGNORECASE
                )
                if not first:
                    continue
                # 再找第2次 (正文标题, 精确匹配无点号)
                after_first = toc_region_text[first.end():]
                second = re.search(
                    r'^#\s+' + escaped + r'\s*$',
                    after_first, re.MULTILINE | re.IGNORECASE
                )
                if second:
                    candidate_end = m.end() + first.end() + second.start()
                    # 回退到这一行的开头 (找前一个 \n)
                    candidate_end = text.rfind('\n', 0, candidate_end)
                    if candidate_end != -1:
                        toc_end = candidate_end
                        break

            # ── 策略2 (降级): 原始逐行检测 ──
            if toc_end is None:
                lines_after = text[m.end():].split('\n')
                toc_end = m.end()
                for line in lines_after:
                    toc_end += len(line) + 1
                    stripped = line.strip()
                    if not stripped:
                        continue
                    is_toc_line = (
                        '...' in stripped or
                        bool(re.search(r'\.\s+\.', stripped) and re.search(r'\d+\s*$', stripped)) or
                        bool(re.match(r'^[\*]*[\dIVX]+\.?[\s\*]', stripped) and re.search(r'\d+[\*]*\s*$', stripped))
                    )
                    if not is_toc_line and len(stripped) > 20:
                        toc_end -= len(line) + 1
                        break

            removed = text[toc_start:toc_end]
            entry_count = len([l for l in removed.split('\n') if l.strip()])
            print(f"    🧹 移除 TABLE OF CONTENTS 段落 ({entry_count} 行)")
            text = text[:toc_start] + '\n\n' + text[toc_end:]
            break

    return text


def _strip_orphan_toc_lines(text: str) -> str:
    """
    移除未标记的 TOC 残留行 (无 'TABLE OF CONTENTS' 标题的散落目录条目)。
    
    检测逻辑: 连续 3+ 行 (忽略空行) 符合 TOC 特征:
      - 含连续点号 '...'
      - 或形如 '**N. TITLE ......... N**' (粗体编号 + 页码)
      - 或形如 '6 SECTION TITLE  20' (编号 + 标题 + 页码，无点号)
    """
    lines = text.split('\n')
    # 增强正则: 除了 ... 模式，还匹配 "编号 标题  页码" 模式 (3+空格隔开)
    toc_line_re = re.compile(
        r'^\s*[\*_]*[\dIVX]*\.?\s*.+\.{3,}\s*\d*[\*_]*\s*$'
        r'|'
        r'^\s*[\*_]*\d+(?:\.\d+)*\.?\s+[A-Z][A-Z\s,/()&:-]+\s{3,}\d+[\*_]*\s*$'
    )
    
    # 扫描连续 TOC 行簇
    i = 0
    regions_to_remove = []  # [(start, end)] 行号范围
    while i < len(lines):
        if toc_line_re.match(lines[i].strip()):
            cluster_start = i
            j = i + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if not stripped:  # 空行继续
                    j += 1
                    continue
                if toc_line_re.match(stripped):
                    j += 1
                else:
                    break
            cluster_end = j
            # 簇中实际 TOC 行数
            actual_toc = sum(
                1 for k in range(cluster_start, cluster_end)
                if lines[k].strip() and toc_line_re.match(lines[k].strip())
            )
            if actual_toc >= 3:
                regions_to_remove.append((cluster_start, cluster_end))
            i = cluster_end
        else:
            i += 1
    
    if regions_to_remove:
        total_removed = sum(e - s for s, e in regions_to_remove)
        print(f"    🧹 移除 {len(regions_to_remove)} 个散落 TOC 片段 ({total_removed} 行)")
        # 从后往前删除避免索引偏移
        for start, end in reversed(regions_to_remove):
            lines[start:end] = ['']
    
    return '\n'.join(lines)


def _strip_inline_toc_lines(text: str) -> str:
    """
    移除分散的单行 TOC 残留 (无需 3+ 行簇)。
    
    特征: 一行中同时满足:
      1. 含 3+ 连续点号 (...)
      2. 末尾有页码数字
      3. 可能被 ** 或 _ 包裹
    
    这种模式几乎不可能出现在正文中。
    """
    inline_toc_re = re.compile(
        r'^\s*[\*_]*[^\n]*\.{3,}\s*\d+[\*_]*\s*$',
        re.MULTILINE
    )
    cleaned = inline_toc_re.sub('', text)
    return cleaned


def _collapse_excessive_newlines(text: str) -> str:
    """
    折叠过多连续换行: >2 个连续 \\n 压缩为 \\n\\n。
    
    PDF 解析器对图表/图片区域往往输出大量空行，这些空行浪费 chunk 空间
    且在向量库中产生无意义的嵌入噪声。
    """
    # 将 3+ 连续换行折叠为 2 个 (保留段落分隔语义)
    collapsed = re.sub(r'\n{3,}', '\n\n', text)
    return collapsed


def _add_figure_placeholders(text: str) -> str:
    """
    为文档中引用的 Figure/图表添加占位标记。
    
    pymupdf4llm 无法提取嵌入式图片中的文字，流程图/架构图的内容
    会丢失为空行。此函数检测 Figure 引用标题行并确保它们带有标准占位符，
    方便下游检索器识别。
    
    处理模式:
      - "Figure 1: Title"  → "[图: Figure 1: Title]"
      - "Figure 1. Title"  → "[图: Figure 1. Title]"
    
    仅对独立的 Figure 标题行生效（不处理内联引用如 "see Figure 1"）。
    """
    def _replace_figure(m):
        full_line = m.group(0).strip()
        # 去除可能的 markdown 装饰
        clean = re.sub(r'[\*_]+', '', full_line).strip()
        return f'[图: {clean}]'
    
    # 匹配独占一行的 Figure/Fig. 标题 (可能带粗体/斜体)
    figure_re = re.compile(
        r'^\s*[\*_]*(?:Figure|Fig\.?)\s+\d+[\*_]*[\s.:–—-]+[\*_]*[^\n]+[\*_]*\s*$',
        re.MULTILINE | re.IGNORECASE
    )
    text = figure_re.sub(_replace_figure, text)
    return text


def _clean_markdown(text: str, doc_id: str = "") -> str:
    """
    综合清洗 Markdown 文本:
    0. 移除 TABLE OF CONTENTS 段落
    0b. 移除散落 TOC 残留行
    0c. 折叠连续换行 + 图表占位
    1. 检测并移除重复页眉/页脚
    2. 移除孤立页码
    3. 修复跨页断句 (把被页眉/页码打断的句子重新连接)
    """
    # ── 第-1步: Unicode NFKC 归一化 (ﬁ→fi, ﬂ→fl 等 ligature) ──
    text = unicodedata.normalize('NFKC', text)
    # ── 第0步: 移除标记的目录段落 ──
    text = _strip_toc_section(text)
    # ── 第0b步: 移除散落 TOC 行 (无标记但含 '...' 模式) ──
    text = _strip_orphan_toc_lines(text)
    # ── 第0c步: 折叠连续换行 (>2 → 2) + 图表标题占位 ──
    text = _collapse_excessive_newlines(text)
    text = _add_figure_placeholders(text)
    # ── 第1步: 检测重复模式 ──
    repeating = _detect_repeating_patterns(text, min_occurrences=3)
    
    if repeating:
        print(f"    🧹 检测到 {len(repeating)} 个页眉/页脚模式:")
        for p in repeating[:5]:
            print(f"       → \"{p}\"")
    
    lines = text.split('\n')
    cleaned_lines = []
    skip_count = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        
        # ── 跳过: 重复页眉/页脚 (但绝不删除 # 标题行) ──
        is_repeating = False
        if not stripped.startswith('#'):  # 保护 Markdown 标题
            for pattern in repeating:
                norm_line = re.sub(r'[\*_#`]+', '', stripped).strip()
                norm_pattern = re.sub(r'[\*_#`]+', '', pattern).strip()
                if norm_line == norm_pattern:
                    is_repeating = True
                    break
        if is_repeating:
            skip_count += 1
            continue
        
        # ── 跳过: 孤立页码 ──
        if _ISOLATED_PAGE_NUM_RE.match(stripped):
            prev_empty = (i == 0) or (lines[i - 1].strip() == '')
            next_empty = (i == len(lines) - 1) or (lines[i + 1].strip() == '')
            if prev_empty or next_empty:
                skip_count += 1
                continue
        
        cleaned_lines.append(line)
    
    if skip_count > 0:
        print(f"    🧹 移除 {skip_count} 行脏数据 (页眉/页脚/页码)")
    
    # ── 第2步: 修复跨页断句 ──
    # 如果某行以小写字母开头, 且上一个非空行不以句号/冒号/标题结尾,
    # 说明这是被页分隔打断的句子 → 合并它们
    result_lines = []
    for i, line in enumerate(cleaned_lines):
        stripped = line.strip()
        if not stripped:
            result_lines.append(line)
            continue
        
        # 检测是否是被打断的句子片段
        if (stripped and stripped[0].islower() and 
            not stripped.startswith('http') and
            not stripped.startswith('e.g.') and
            not stripped.startswith('i.e.')):
            # 往回找最后一个非空行
            j = len(result_lines) - 1
            while j >= 0 and result_lines[j].strip() == '':
                j -= 1
            if j >= 0:
                prev_stripped = result_lines[j].strip()
                # 上一行不是标题, 不以句号结尾, 不是表格 → 合并
                if (prev_stripped and 
                    not prev_stripped.startswith('#') and
                    not prev_stripped.endswith(('.', ':', ';', '!', '?', ')')) and
                    not prev_stripped.startswith('|') and
                    not prev_stripped.endswith('|') and
                    not prev_stripped.startswith('---')):
                    # 合并: 删掉中间的空行, 用空格连接
                    while len(result_lines) > j + 1:
                        result_lines.pop()
                    result_lines[j] = result_lines[j].rstrip() + ' ' + stripped
                    continue
        
        result_lines.append(line)
    
    text = '\n'.join(result_lines)
    
    # ── 第3步: 最终换行折叠 (前面删页眉/页脚可能再次产生连续空行) ──
    text = _collapse_excessive_newlines(text)
    
    # ── 第4步: 移除内联 TOC 残留行 ──
    # 处理单独出现的 "**TITLE ........... N**" 格式行
    text = _strip_inline_toc_lines(text)
    
    return text


# ═══════════════════════════════════════════════════════════════
#  Step B: ICH 标题检测 & Heading 规范化
# ═══════════════════════════════════════════════════════════════

def _detect_ich_heading_level(text: str) -> int:
    """
    根据编号深度推断标题级别:
      "1." → 1  (对应 #)
      "1.1" 或 "1.1." → 2  (对应 ##)
      "1.1.1" → 3  (对应 ###)
      "ANNEX" → 1
    """
    num_match = re.match(r'[\*]*(\d+(?:\.\d+)*)\.?[\*]*', text.strip())
    if num_match:
        parts = num_match.group(1).split('.')
        return min(len(parts), 3)
    if re.match(r'[\*]*(ANNEX|APPENDIX)', text.strip(), re.IGNORECASE):
        return 1
    return 1


def _is_likely_heading_text(text: str) -> bool:
    """
    判断裸编号行后的文本是否像标题 (而非正文段落)。
    
    真标题特征:
      - 较短 (通常 < 60 字符)
      - Title Case 或 ALL CAPS (多数词首字母大写)
      - 不以句号/冒号/分号结尾
      - 不含典型正文动词 (should, must, can, may 等)
    
    假阳性 (正文段落) 特征:
      - 较长 (80+ 字符)
      - 只首词大写, 其余小写
      - 含 "should", "must", "include" 等
      - 以 ":" 或 "." 结尾 (列举引导语)
    """
    text = text.strip()
    if not text:
        return False
    
    # 条件 1: 长度 — 标题通常短于 60 字符
    if len(text) > 60:
        return False
    
    # 条件 2: 不以正文标点结尾
    if text.rstrip().endswith((':', '.', ';', '?', '!')):
        return False
    
    # 条件 3: 不含典型正文/规范性动词
    sentence_words = {
        'should', 'shall', 'must', 'can', 'may', 'will', 'would', 'could',
        'include', 'including', 'unless', 'where', 'when', 'however',
        'although', 'maintained', 'performed', 'stored', 'conducted',
        'documented', 'established', 'appropriate', 'acceptable',
    }
    words = text.lower().split()
    if any(w.rstrip('.,;:') in sentence_words for w in words):
        return False
    
    # 条件 4: 大多数词首字母大写 (Title Case / ALL CAPS)
    # 允许小的连接词 (and, of, for...) 为小写
    small_words = {
        'and', 'of', 'for', 'the', 'in', 'to', 'or', 'a', 'an',
        'on', 'at', 'by', 'with', 'from',
    }
    if len(words) > 1:
        cap_count = sum(
            1 for w in words
            if w[0].isupper() or w.lower() in small_words
        )
        if cap_count / len(words) < 0.7:
            return False
    
    return True


def _clean_heading_text(text: str) -> str:
    """
    清洗标题文本:
    - 移除 Markdown 装饰 (**, _, #)
    - 移除 TOC 样式的点号序列和页码 ("SECTION .. . 12", "TITLE ...... 25")
    - 移除尾部孤立数字 (页码残留)

    MinerU TOC 点号格式可能是非连续的 (如 ".. . 12", ".... . 16"),
    所以同时处理连续和非连续点号。
    """
    # 去掉 markdown 装饰
    cleaned = re.sub(r'[\*_]+', '', text).strip()
    # 去掉 TOC 点号序列 + 可选页码: 匹配 "至少一个空格 + 点号/空格混合 + 可选数字"
    # 例如: " ...... 1", " .. . 12", " .... . 16", " .. ..20"
    cleaned = re.sub(r'\s+[. ]+\d*\s*$', '', cleaned).strip()
    # 去掉尾部孤立页码: "SCOPE  2" (前面有多个空格)
    cleaned = re.sub(r'\s{3,}\d+\s*$', '', cleaned).strip()
    return cleaned


def _fix_mineru_flat_headings(text: str) -> str:
    """
    MinerU 输出的 Markdown 中，所有标题都被渲染为 # (H1)，丢失了层级信息。
    本函数根据 ICH/学术文档的编号模式重新推断正确的标题深度：

      # 1. INTRODUCTION         → 保持 # (H1, level=1)
      # 1.1 Objective           → ## 1.1 Objective    (H2, level=2)
      # 1.1.1 Sub-section       → ### 1.1.1 Sub-section (H3, level=3)
      # ANNEX I: TOOLS          → 保持 # (无编号 → H1)
      # Some heading without num→ 保持 # (无编号 → H1)

    只处理当前为 H1 的标题，已经有深度的 (##, ###) 不动。
    """
    def _rewrite_level(m: re.Match) -> str:
        hashes = m.group(1)
        heading_text = m.group(2).strip()

        # 只处理 H1 — 已经分层的保持不变
        if len(hashes) > 1:
            return m.group(0)

        # 检测 ICH/标准文档编号格式: "1.", "1.1", "1.1.1", "11.", "A.1" 等
        num_match = re.match(r'^(\d+(?:\.\d+)+)[\.\s]', heading_text)
        if num_match:
            parts = num_match.group(1).split('.')
            level = min(len(parts), 3)
            return '#' * level + ' ' + heading_text

        # 单层编号 "1. TITLE" → 保持 H1
        # 无编号标题 → 保持 H1
        return m.group(0)

    return re.sub(r'^(#{1,6})\s+(.+)$', _rewrite_level, text, flags=re.MULTILINE)


def _normalize_headings(text: str) -> str:
    """
    将 ICH 风格的粗体编号标题转为标准 Markdown # 标题。
    
    例如:
      **1.** **PREAMBLE**  →  # 1. PREAMBLE
      **4.1.**  Risk Control  →  ## 4.1. Risk Control
      **ANNEX I: TOOLS**  →  # ANNEX I: TOOLS
    """
    result = text
    
    for pat_idx, pattern in enumerate(_ICH_HEADING_PATTERNS):
        def _replace(m, _idx=pat_idx):
            full_match = m.group(0)
            if m.lastindex and m.lastindex >= 2:
                num_part = re.sub(r'[\*]+', '', m.group(1)).strip()
                title_part = re.sub(r'[\*]+', '', m.group(2)).strip()
                heading_text = f"{num_part} {title_part}"
                level = _detect_ich_heading_level(num_part)
            else:
                heading_text = re.sub(r'[\*]+', '', full_match).strip()
                level = _detect_ich_heading_level(heading_text)
                title_part = heading_text
            
            # Pattern 4 (裸编号): 额外验证是否真的是标题
            # 避免将 ICH Q7 的编号正文段落 (4.30, 4.31...) 误判为标题
            if _idx == 3:
                if not _is_likely_heading_text(title_part):
                    return full_match  # 不是标题, 保持原样
            
            # 清洗可能残留的 TOC 点号和页码
            heading_text = _clean_heading_text(heading_text)
            
            prefix = '#' * level
            return f"{prefix} {heading_text}"
        
        result = pattern.sub(_replace, result)
    
    return result


# ═══════════════════════════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════════════════════════

def _make_chunk_id(doc_id: str, seq: int, text: str) -> str:
    """生成 chunk ID: doc_id + 序号 + 内容前64字节hash"""
    h = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
    return f"{doc_id}_C{seq:04d}_{h}"


def _detect_page(text: str) -> Optional[int]:
    """从 <!-- Page N --> 注释中提取页码"""
    m = _PAGE_RE.search(text)
    return int(m.group(1)) if m else None


def _clean_table_header(table_text: str) -> str:
    """
    修复表头越界: 如果表格第一行是章节编号 (如 |2.1.7.1. General|case|...),
    将其移除, 以真正的数据行作为列名。
    
    检测: 第一个 cell 匹配 N.N.N 格式 → 不是真正的表头, 是章节标题渗透。
    """
    lines = table_text.strip().split('\n')
    if len(lines) < 3:
        return table_text
    
    first_row = lines[0]
    cells = [c.strip() for c in first_row.split('|') if c.strip()]
    if not cells:
        return table_text
    
    # 检测第一个 cell 是否为章节编号 (如 "2.1.7.1. General")
    if re.match(r'\d+\.\d+(?:\.\d+)+\.?\s', cells[0]):
        # 确认下一行是分隔符 (|---|---|---| 格式)
        if len(lines) >= 2 and '---' in lines[1]:
            # 第一行是假表头 — 跳过它和分隔符
            # 如果之后有真正的数据行, 尝试重建
            if len(lines) >= 3:
                # 检查第三行是否像真表头 (有列名)
                third_cells = [c.strip() for c in lines[2].split('|') if c.strip()]
                if third_cells and not re.match(r'\d+\.\d+', third_cells[0]):
                    # 用第三行作为表头, 生成新分隔符
                    sep = '|' + '|'.join(['---'] * len(third_cells)) + '|'
                    return '\n'.join([lines[2], sep] + lines[3:])
            # 否则直接跳过第一行
            return '\n'.join(lines[2:])
    
    return table_text


def _compress_tables(text: str) -> Tuple[str, List[str]]:
    """
    将 Markdown 表格和 MinerU HTML 表格压缩为 [表: ...] 引用，
    返回 (压缩后文本, 表格引用列表)。
    
    额外处理:
    - 修复表头越界 (章节标题渗透到表头行)
    - 检测并跳过幽灵列名 (Col3, Col4 等由 pymupdf4llm 伪造的列名)
    - 支持 MinerU HTML 表格 (<html><body><table>...</html>)
    """
    table_refs = []
    # 幽灵列名正则: ColN 格式 (pymupdf4llm 在无法解析合并单元格时生成)
    _phantom_col_re = re.compile(r'^Col\d+$', re.IGNORECASE)

    def _replace_md(match):
        table_text = match.group(0)
        # 修复表头越界
        table_text = _clean_table_header(table_text)
        first_line = table_text.strip().split('\n')[0]
        cols = [c.strip() for c in first_line.split('|') if c.strip()]
        # 过滤掉幽灵列名 (Col3, Col4, Col5...)
        real_cols = [c for c in cols if not _phantom_col_re.match(c)]
        if not real_cols:
            real_cols = cols  # 如果全是幽灵列名则保留原样
        caption = ', '.join(real_cols[:5])
        if len(real_cols) > 5:
            caption += '...'
        ref = f"[表: {caption}]"
        table_refs.append(table_text)
        return ref

    def _replace_html(match):
        """处理 MinerU 输出的 HTML 表格"""
        html_text = match.group(0)
        # 从 <th> 或第一行 <td> 中提取列名
        th_re = re.compile(r'<th[^>]*>(.*?)</th>', re.IGNORECASE | re.DOTALL)
        td_re = re.compile(r'<td[^>]*>(.*?)</td>', re.IGNORECASE | re.DOTALL)
        # 清洗 HTML 标签
        def clean_cell(s):
            return re.sub(r'<[^>]+>', '', s).strip()

        header_cells = th_re.findall(html_text)
        if header_cells:
            cols = [clean_cell(c) for c in header_cells[:5]]
        else:
            # 取第一行的 td
            all_tds = td_re.findall(html_text)
            cols = [clean_cell(c) for c in all_tds[:5]]

        real_cols = [c for c in cols if c and not _phantom_col_re.match(c)]
        if not real_cols:
            real_cols = cols[:3] if cols else ['table']
        caption = ', '.join(real_cols[:5])
        if len(real_cols) > 5:
            caption += '...'
        ref = f"[表: {caption}]"
        table_refs.append(html_text)
        return ref

    # 先处理 Markdown 表格
    compressed = _TABLE_RE.sub(_replace_md, text)
    # 再处理 MinerU HTML 表格
    compressed = _HTML_TABLE_RE.sub(_replace_html, compressed)
    return compressed, table_refs


def _split_by_headings(md_text: str, max_depth: int = 3) -> List[Dict]:
    """
    用正则将 Markdown 按标题切分成段落列表。
    返回 [{level, heading, content, start_pos, end_pos}, ...]
    """
    segments = []

    headings = []
    for m in _HEADING_RE.finditer(md_text):
        level = min(len(m.group(1)), max_depth)
        headings.append({
            "level": level,
            "heading": m.group(2).strip(),
            "start": m.start(),
            "end": m.end(),
        })

    if not headings:
        return [{
            "level": 0,
            "heading": "",
            "content": md_text.strip(),
            "start_pos": 0,
            "end_pos": len(md_text),
        }]

    # 标题前的前言
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


# ═══════════════════════════════════════════════════════════════
#  Step C: 语义安全切分 (绝不在单词中间切断)
# ═══════════════════════════════════════════════════════════════

def _split_long_content(content: str, max_chars: int,
                        overlap: int) -> List[str]:
    """
    递归字符文本切分 (RecursiveCharacterTextSplitter 风格):
    
    分隔符优先级: 段落 → 换行 → 句号 → 空格
    
    关键保证:
    1. 永远不在单词中间切断
    2. overlap 对齐到最近的空格/句号边界
    3. 每个 chunk 都是语义完整的
    """
    if len(content) <= max_chars:
        return [content]
    
    # 分隔符优先级 (从粗到细)
    separators = ['\n\n', '\n', '. ', '; ', ', ', ' ']
    
    return _recursive_split(content, separators, max_chars, overlap)


def _recursive_split(text: str, separators: List[str],
                     max_chars: int, overlap: int) -> List[str]:
    """递归切分实现"""
    if len(text) <= max_chars:
        return [text.strip()] if text.strip() else []
    
    # 找到能用于切分的最粗分隔符
    best_sep = None
    for sep in separators:
        if sep in text:
            best_sep = sep
            break
    
    # 没有任何分隔符 → 在 max_chars 处强制切 (但保护单词边界)
    if best_sep is None:
        return _force_split_at_word_boundary(text, max_chars, overlap)
    
    # 按分隔符拆分
    parts = text.split(best_sep)
    
    chunks = []
    current = ""
    
    for i, part in enumerate(parts):
        candidate = current + best_sep + part if current else part
        
        if len(candidate) <= max_chars:
            current = candidate
        else:
            # 当前累积已满 → 输出
            if current.strip():
                chunks.append(current.strip())
            
            # 如果单个 part 超长 → 递归用更细的分隔符
            if len(part) > max_chars:
                remaining_seps = separators[separators.index(best_sep) + 1:]
                if remaining_seps:
                    sub_chunks = _recursive_split(part, remaining_seps, max_chars, overlap)
                    if sub_chunks:
                        chunks.extend(sub_chunks[:-1])
                        current = sub_chunks[-1]
                    else:
                        current = part
                else:
                    sub_chunks = _force_split_at_word_boundary(part, max_chars, overlap)
                    chunks.extend(sub_chunks[:-1])
                    current = sub_chunks[-1] if sub_chunks else ""
            else:
                current = part
    
    if current.strip():
        chunks.append(current.strip())
    
    # ── 添加 overlap ──
    if overlap > 0 and len(chunks) > 1:
        chunks = _add_overlap(chunks, overlap)
    
    return [c for c in chunks if c.strip()]


def _force_split_at_word_boundary(text: str, max_chars: int,
                                   overlap: int) -> List[str]:
    """
    最后手段: 在 max_chars 附近的空格处强制切分。
    绝对保证: 不在字母序列中间切断。
    """
    chunks = []
    start = 0
    
    while start < len(text):
        if start + max_chars >= len(text):
            chunks.append(text[start:].strip())
            break
        
        # 从 max_chars 位置往回找最近的空格
        end = start + max_chars
        while end > start and text[end] not in (' ', '\n', '\t'):
            end -= 1
        
        # 极端情况: 整段无空格 (不太可能, 但兜底)
        if end == start:
            end = start + max_chars
        
        chunks.append(text[start:end].strip())
        start = end
    
    return [c for c in chunks if c.strip()]


def _add_overlap(chunks: List[str], overlap: int) -> List[str]:
    """
    在 chunk 之间添加重叠, 对齐到完整句子边界。
    保证: overlap 前缀以完整句子开头 (首字母大写)。
    """
    if len(chunks) <= 1:
        return chunks
    
    result = [chunks[0]]
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i - 1]
        current = chunks[i]
        
        if len(prev_chunk) <= overlap:
            prefix = prev_chunk
        else:
            raw_overlap = prev_chunk[-overlap:]
            prefix = _find_sentence_start_overlap(raw_overlap)
        
        if prefix.strip():
            result.append(prefix.strip() + '\n\n' + current)
        else:
            result.append(current)
    
    return result


def _find_sentence_start_overlap(raw_overlap: str) -> str:
    """
    从 overlap 区间中找到最佳前缀: 尽量从完整句子开头开始。
    
    搜索优先级:
    0. 列表序号起始 (\n1. / \n- / \na) 等) → 保完整列表项
    1. 句末标记 ('. ' / '.\n') + 大写字母 → 完美句子开头
    2. 段落分隔 '\\n\\n' → 新段落 (即使小写也是新的语义单元)
    3. 任意句末标记 ('. ' / '.\n') → 至少从完整句子后开始
    4. 换行 + 大写字母 → 行级边界
    5. 回退: 空格对齐 (至少不切断单词)
    """
    min_remaining = 20  # 确保剩余内容有意义
    
    # ── 策略0: 列表序号起始 (换行后跟编号/bullet) ──
    # 匹配: \n1. / \n(a) / \n- / \n• / \n* 等
    list_re = re.compile(r'\n(\d+\.\s|[a-z]\)\s|[\-\*•]\s|\([a-z]\)\s|\(\d+\)\s)')
    for m in list_re.finditer(raw_overlap):
        start_pos = m.start() + 1  # 跳过 \n
        remaining = raw_overlap[start_pos:]
        if len(remaining) >= min_remaining:
            return remaining
    
    # ── 策略1: 句末 + 大写字母 (最佳) ──
    sentence_ends = ['. ', '.\n', '? ', '?\n', '! ', '!\n', ';\n']
    positions: List[int] = []
    for pattern in sentence_ends:
        start = 0
        while True:
            pos = raw_overlap.find(pattern, start)
            if pos == -1:
                break
            positions.append(pos + len(pattern))
            start = pos + 1
    positions.sort()
    
    for pos in positions:
        p = pos
        while p < len(raw_overlap) and raw_overlap[p] in (' ', '\n', '\t'):
            p += 1
        if p < len(raw_overlap) and raw_overlap[p].isupper():
            remaining = raw_overlap[p:]
            if len(remaining) >= min_remaining:
                return remaining
    
    # ── 策略2: 段落分隔 (\n\n) ──
    para_pos = raw_overlap.find('\n\n')
    if para_pos != -1:
        after = raw_overlap[para_pos + 2:].lstrip()
        if len(after) >= min_remaining:
            return after
    
    # ── 策略3: 任意句末标记 (不要求大写) ──
    for pos in positions:
        p = pos
        while p < len(raw_overlap) and raw_overlap[p] in (' ', '\n', '\t'):
            p += 1
        if p < len(raw_overlap):
            remaining = raw_overlap[p:]
            if len(remaining) >= min_remaining:
                return remaining
    
    # ── 策略4: 换行 + 大写字母 ──
    nl_pos = 0
    while True:
        nl_pos = raw_overlap.find('\n', nl_pos)
        if nl_pos == -1:
            break
        p = nl_pos + 1
        while p < len(raw_overlap) and raw_overlap[p] in (' ', '\t'):
            p += 1
        if p < len(raw_overlap) and raw_overlap[p].isupper():
            remaining = raw_overlap[p:]
            if len(remaining) >= min_remaining:
                return remaining
        nl_pos += 1
    
    # ── 策略5: 空格对齐 (保底) ──
    space_pos = raw_overlap.find(' ')
    if space_pos != -1 and space_pos < len(raw_overlap) - 5:
        return raw_overlap[space_pos + 1:]
    
    return raw_overlap


# ═══════════════════════════════════════════════════════════════
#  核心分块器
# ═══════════════════════════════════════════════════════════════

class HierarchicalChunker:
    """
    层级分块器 v2: Markdown → Tree-structured Chunks
    
    流水线:
      Markdown → 清洗 (页眉/页脚/页码) → 标题规范化 (ICH格式→#)
               → 按标题切分 → 超长内容递归拆分 → 链表连接
    """

    def __init__(self, config: ChunkingConfig = None):
        self.config = config or ChunkingConfig()

    def chunk_document(self, md_path: Path, doc_id: str = None) -> List[ChunkNode]:
        """将一个 Markdown 文件分块"""
        md_text = md_path.read_text(encoding='utf-8')
        doc_id = doc_id or md_path.stem

        # ── Phase 1: 智能清洗 ──
        md_text = _clean_markdown(md_text, doc_id)

        # ── Phase 2: ICH 标题规范化 ──
        md_text = _normalize_headings(md_text)

        # ── Phase 2b: 修正 MinerU 扁平 H1 标题层级 ──
        # MinerU 把所有标题都输出为 # (H1), 此步根据编号模式还原深度
        md_text = _fix_mineru_flat_headings(md_text)

        # ── Phase 3: 按标题分段 ──
        segments = _split_by_headings(md_text, self.config.max_depth)

        # ── Phase 4: 构造 chunk 树 ──
        chunks: List[ChunkNode] = []
        heading_stack: List[str] = []
        level_stack: List[int] = []
        seq = 0

        for seg in segments:
            level = seg["level"]
            heading = seg["heading"]
            content = seg["content"]

            # 清洗 heading 中残留的 Markdown 装饰 + TOC 点号
            clean_heading = _clean_heading_text(heading)
            if not clean_heading:
                clean_heading = heading

            # 更新面包屑栈
            while level_stack and level_stack[-1] >= level:
                level_stack.pop()
                heading_stack.pop()

            if clean_heading and clean_heading != "(Preamble)":
                heading_stack.append(clean_heading)
                level_stack.append(level)

            parents_ctx = _build_parents_context(
                heading_stack[:-1]) if len(heading_stack) > 1 else ""

            # 表格压缩
            compressed_content, table_refs = _compress_tables(content)

            # 超长内容拆分 (递归语义切分)
            sub_contents = _split_long_content(
                compressed_content,
                self.config.max_chunk_chars,
                self.config.overlap_chars
            )

            # ── 表格 ref 按实际占位符分配到各 sub-chunk ──
            table_ref_idx = 0

            for i, sub_content in enumerate(sub_contents):
                if not sub_content.strip():
                    continue
                    
                seq += 1

                # 统计本 sub-chunk 中的 [表: ...] 占位符数量
                placeholder_count = sub_content.count('[表:')
                sub_table_refs = table_refs[table_ref_idx:table_ref_idx + placeholder_count]
                table_ref_idx += placeholder_count

                # 生成 search_text
                search_parts = []
                if parents_ctx:
                    search_parts.append(parents_ctx)
                if clean_heading:
                    search_parts.append(clean_heading)
                search_parts.append(sub_content)
                search_text = "\n".join(search_parts)
                # 移除学术引用 [N] (保留 content 原文)
                search_text = re.sub(r'\[\d+\]', '', search_text)

                # 子分块后缀
                sub_heading = clean_heading
                if len(sub_contents) > 1:
                    sub_heading = f"{clean_heading} (Part {i+1}/{len(sub_contents)})"

                chunk = ChunkNode(
                    chunk_id=_make_chunk_id(doc_id, seq, sub_content),
                    doc_id=doc_id,
                    level=level,
                    heading=sub_heading,
                    parents_context=parents_ctx,
                    content=sub_content,
                    search_text=search_text,
                    page_hint=_detect_page(content),
                    has_table=bool(sub_table_refs),
                    table_refs=sub_table_refs,
                    char_count=len(sub_content),
                    line_count=sub_content.count('\n') + 1,
                )
                chunks.append(chunk)

        # ── Phase 5: 链表连接 ──
        for i, chunk in enumerate(chunks):
            if i > 0:
                chunk.prev_chunk_id = chunks[i - 1].chunk_id
            if i < len(chunks) - 1:
                chunk.next_chunk_id = chunks[i + 1].chunk_id

        # ── Phase 6: 统计子节点数 ──
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

        for md_file in sorted(md_dir.rglob("*.md")):
            md_files.append(md_file)

        if not md_files:
            print("  ⚠ 无 Markdown 文件可分块")
            return {}

        print(f"╔{'═' * 50}╗")
        print(f"║  层级分块 v2 (语义安全切分)")
        print(f"║  共 {len(md_files)} 个文件 / 最大深度: L{self.config.max_depth}")
        print(f"║  清洗: 页眉/页脚/页码自动移除")
        print(f"║  切分: 递归分隔符优先级, 永不断词")
        print(f"╚{'═' * 50}╝\n")

        all_results = {}
        total_chunks = 0
        total_broken = 0

        for md_file in md_files:
            doc_id = md_file.stem
            print(f"  📄 {doc_id}...", flush=True)

            chunks = self.chunk_document(md_file, doc_id)
            all_results[doc_id] = chunks
            total_chunks += len(chunks)

            # 统计层级分布
            level_dist = {}
            for c in chunks:
                level_dist[c.level] = level_dist.get(c.level, 0) + 1
            dist_str = " ".join(f"L{k}:{v}" for k, v in sorted(level_dist.items()))
            
            # 质量检查: 是否有被截断的单词
            common_lower_starts = frozenset([
                'a', 'an', 'as', 'at', 'be', 'by', 'do', 'go', 'if', 'in', 'is',
                'it', 'no', 'of', 'on', 'or', 'so', 'to', 'up', 'we', 'and', 'are',
                'but', 'can', 'for', 'had', 'has', 'may', 'not', 'the', 'was', 'all',
                'any', 'its', 'new', 'now', 'old', 'our', 'own', 'one', 'per', 'she',
                'too', 'two', 'who', 'why', 'also', 'been', 'each', 'from', 'have',
                'more', 'most', 'much', 'only', 'such', 'than', 'that', 'them', 'then',
                'they', 'this', 'were', 'what', 'when', 'will', 'with', 'e.g.', 'i.e.',
                'etc.', 'vs.', 'where', 'which', 'while', 'should', 'could', 'would',
                'these', 'those', 'their', 'other', 'after', 'before', 'about',
            ])
            broken_words = 0
            for c in chunks:
                stripped = c.content.lstrip()
                if stripped and stripped[0].islower():
                    first_word = stripped.split()[0] if stripped.split() else ''
                    if len(first_word) <= 4 and first_word not in common_lower_starts:
                        broken_words += 1
            
            total_broken += broken_words
            quality = "✅" if broken_words == 0 else f"⚠️ {broken_words} 疑似断词"
            print(f"     → {len(chunks)} chunks ({dist_str}) {quality}")

        if total_broken == 0:
            print(f"\n✅ 分块完成: {total_chunks} chunks / {len(md_files)} docs — 零断词 ✓")
        else:
            print(f"\n✅ 分块完成: {total_chunks} chunks / {len(md_files)} docs (⚠️ {total_broken} 疑似断词)")
        return all_results


# ═══════════════════════════════════════════════════════════════
#  输出写入
# ═══════════════════════════════════════════════════════════════

def save_chunks(all_chunks: Dict[str, List[ChunkNode]],
                output_dir: Path = None):
    """将 chunks 保存为 JSON"""
    output_dir = output_dir or CHUNKS_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    for doc_id, chunks in all_chunks.items():
        out_file = output_dir / f"{doc_id}_chunks.json"
        
        # 清空该文档的旧表格文件
        tables_file = output_dir / f"{doc_id}_tables.json"
        all_tables = []
        
        records = []
        for c in chunks:
            d = asdict(c)
            if c.table_refs:
                all_tables.extend([{
                    "chunk_id": c.chunk_id,
                    "table": t
                } for t in c.table_refs])
                d["table_refs"] = [f"[表 ref: {doc_id}_tables.json]"]
            records.append(d)

        # ── 去重 + 过滤空 chunk（防御：保留 content 最长的版本）──
        seen: Dict[str, dict] = {}
        for d in records:
            cid = d.get("chunk_id", "")
            prev = seen.get(cid)
            if prev is None or len(d.get("content", "")) > len(prev.get("content", "")):
                seen[cid] = d
        records = [d for d in seen.values() if d.get("content", "").strip()]

        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

        # 写表格文件
        if all_tables:
            with open(tables_file, 'w', encoding='utf-8') as f:
                json.dump(all_tables, f, ensure_ascii=False, indent=2)

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
