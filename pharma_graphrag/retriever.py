"""
3-Stage GraphRAG 检索器 (增强版)
================================
Stage 1: Bottom-Up  — 三路并行召回 (chunk向量 + 实体向量 + 关键词匹配)
                      + 上下文回溯 + 同级兄弟补充
Stage 2: Top-Down   — 智能路由触发, KG 实体邻居展开 + 整章阅读
Stage 3: Graph Walk — 元路径受限扩散, 风险传播追踪

增强点 (相比原版):
  ① 实体 FAISS 向量检索 (pharma_entities.faiss)
  ② 同级兄弟 chunk 补充 (短 chunk 自动拉取前后兄弟)
  ③ 策略路由 (根据 query 特征智能选择执行哪些 Stage)
  ④ 上下文回溯 (自动拼接 Document + Section 来源信息)
  ⑤ Top-Down 整章阅读 (当 chunks 集中于某文档时)
"""

import json
import re
import time
import numpy as np
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

from .config import GraphRAGConfig, VECTORS_DIR, CHUNKS_DIR


# ============================================================
#  数据结构
# ============================================================

@dataclass
class ChunkResult:
    """检索到的文档 chunk"""
    chunk_id: str
    doc_id: str
    heading: str
    content: str
    summary: str = ""
    parents_context: str = ""
    level: int = 0
    score: float = 0.0
    source: str = ""  # "faiss" | "top_down" | "sibling" | "chapter_read"
    table_summaries: List[str] = field(default_factory=list)  # HAS_TABLE 关联表格摘要

    def to_context_str(self) -> str:
        """转换为 LLM 上下文字符串 (含来源回溯 + 关联表格摘要)"""
        header = f"[{self.doc_id}] {self.parents_context} > {self.heading}"
        body = self.summary if self.summary else self.content[:800]
        source_tag = f"[{self.source}]" if self.source else ""
        result = f"### {header} {source_tag}\n{body}"
        if self.table_summaries:
            tbl_lines = "\n".join(f"  - {s}" for s in self.table_summaries)
            result += f"\n**Related Tables:**\n{tbl_lines}"
        return result


@dataclass
class KGEntity:
    """知识图谱实体"""
    name: str
    label: str  # Drug, API, Manufacturer, etc.
    properties: Dict = field(default_factory=dict)
    source: str = ""  # "mentions" | "walk" | "query_match" | "faiss_entity"


@dataclass
class KGRelation:
    """知识图谱关系"""
    source_name: str
    source_label: str
    relation: str
    target_name: str
    target_label: str
    properties: Dict = field(default_factory=dict)


@dataclass
class RiskPath:
    """风险传播路径"""
    nodes: List[str]       # 节点名序列
    labels: List[str]      # 节点类型序列
    edges: List[str]       # 边类型序列
    depth: int = 0
    risk_score: float = 0.0

    def to_str(self) -> str:
        parts = []
        for i, (node, label) in enumerate(zip(self.nodes, self.labels)):
            parts.append(f"({label}:{node})")
            if i < len(self.edges):
                parts.append(f"-[{self.edges[i]}]->")
        return " ".join(parts)


@dataclass
class RetrievalResult:
    """三阶段检索的聚合结果"""
    query: str
    chunks: List[ChunkResult] = field(default_factory=list)
    entities: List[KGEntity] = field(default_factory=list)
    relations: List[KGRelation] = field(default_factory=list)
    risk_paths: List[RiskPath] = field(default_factory=list)
    strategies_used: List[str] = field(default_factory=list)
    timings: Dict[str, float] = field(default_factory=dict)

    def to_context(self) -> str:
        """将所有检索结果合并为 LLM 上下文"""
        sections = []

        # 1. Document Evidence
        if self.chunks:
            sections.append("## Document Evidence\n")
            seen_ids = set()
            for c in self.chunks:
                if c.chunk_id not in seen_ids:
                    sections.append(c.to_context_str())
                    seen_ids.add(c.chunk_id)

        # 2. Knowledge Graph Facts
        if self.relations:
            sections.append("\n## Knowledge Graph Facts\n")
            for r in self.relations:
                sections.append(
                    f"- ({r.source_label}:{r.source_name}) "
                    f"-[{r.relation}]-> "
                    f"({r.target_label}:{r.target_name})"
                )

        # 3. Risk Propagation Paths
        if self.risk_paths:
            sections.append("\n## Risk Propagation Paths\n")
            for i, rp in enumerate(self.risk_paths, 1):
                score_str = f" [risk={rp.risk_score:.2f}]" if rp.risk_score else ""
                sections.append(f"{i}. {rp.to_str()}{score_str}")

        # 4. Entity Summary
        if self.entities:
            sections.append("\n## Identified Entities\n")
            by_label = {}
            for e in self.entities:
                by_label.setdefault(e.label, []).append(e.name)
            for label, names in by_label.items():
                sections.append(f"- **{label}**: {', '.join(set(names))}")

        return "\n".join(sections)

    def summary(self) -> str:
        """打印检索统计"""
        lines = [
            f"  Chunks: {len(self.chunks)}",
            f"  Entities: {len(self.entities)}",
            f"  Relations: {len(self.relations)}",
            f"  Risk Paths: {len(self.risk_paths)}",
            f"  Strategies: {', '.join(self.strategies_used)}",
        ]
        for stage, t in self.timings.items():
            lines.append(f"  {stage}: {t:.2f}s")
        return "\n".join(lines)


# ============================================================
#  核心检索器 (增强版)
# ============================================================

class GraphRAGRetriever:
    """
    3-Stage GraphRAG 检索器 (增强版)

    增强点:
      ① 实体 FAISS 向量检索 — 用 query 向量直接检索 KG 实体
      ② 同级兄弟补充 — 短 chunk 自动拉取前后兄弟
      ③ 策略路由 — 根据 query 特征智能选择 Stage
      ④ 上下文回溯 — ChunkResult 自动拼接完整来源路径
      ⑤ Top-Down 整章阅读 — chunks 集中于某文档时批量加载

    使用方法:
        retriever = GraphRAGRetriever(config)
        result = retriever.retrieve("What happens if Aurobindo stops production?")
        context = result.to_context()
    """

    def __init__(self, config: GraphRAGConfig = None):
        self.config = config or GraphRAGConfig()
        self._faiss_index = None
        self._faiss_meta = None
        self._entity_faiss_index = None  # 新增: 实体 FAISS
        self._entity_faiss_meta = None
        self._embedding_model = None
        self._neo4j_driver = None
        self._chunk_store = {}  # chunk_id → full chunk data
        self._entity_name_index = {}  # lowercase name → (label, name)

    # ─────────── 惰性加载 ───────────

    @property
    def embedding_model(self):
        if self._embedding_model is None:
            import torch
            from sentence_transformers import SentenceTransformer
            print("  Loading embedding model (FP16)...", flush=True)
            self._embedding_model = SentenceTransformer(
                self.config.retriever.embedding_model,
                device="cuda",
                trust_remote_code=True,
                model_kwargs={
                    "trust_remote_code": True,
                    "torch_dtype": torch.float16,
                },
            )
            self._embedding_model.half()
            print("  [OK] Embedding model ready (FP16, CUDA)")
        return self._embedding_model

    @property
    def faiss_index(self):
        if self._faiss_index is None:
            import faiss
            index_path = VECTORS_DIR / "pharma_docs.faiss"
            meta_path = VECTORS_DIR / "pharma_docs.meta.json"
            if not index_path.exists():
                raise FileNotFoundError(f"FAISS index not found: {index_path}")
            self._faiss_index = faiss.read_index(str(index_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                self._faiss_meta = json.load(f)
            print(f"  FAISS (docs): {self._faiss_index.ntotal} vectors loaded")
        return self._faiss_index

    @property
    def faiss_meta(self):
        if self._faiss_meta is None:
            _ = self.faiss_index  # trigger load
        return self._faiss_meta

    @property
    def entity_faiss_index(self):
        """新增: 实体 FAISS 索引"""
        if self._entity_faiss_index is None:
            import faiss
            index_path = VECTORS_DIR / "pharma_entities.faiss"
            meta_path = VECTORS_DIR / "pharma_entities.meta.json"
            if not index_path.exists():
                print(f"  ⚠ Entity FAISS not found: {index_path}")
                return None
            self._entity_faiss_index = faiss.read_index(str(index_path))
            with open(meta_path, "r", encoding="utf-8") as f:
                self._entity_faiss_meta = json.load(f)
            print(f"  FAISS (entities): {self._entity_faiss_index.ntotal} vectors loaded")
        return self._entity_faiss_index

    @property
    def entity_faiss_meta(self):
        if self._entity_faiss_meta is None:
            _ = self.entity_faiss_index  # trigger load
        return self._entity_faiss_meta

    @property
    def neo4j_driver(self):
        if self._neo4j_driver is None:
            from neo4j import GraphDatabase
            self._neo4j_driver = GraphDatabase.driver(
                self.config.neo4j.uri,
                auth=(self.config.neo4j.user, self.config.neo4j.password)
            )
            self._neo4j_driver.verify_connectivity()
            print("  Neo4j: connected")
        return self._neo4j_driver

    def _load_chunk_store(self):
        """加载所有 enriched chunks 到内存"""
        if self._chunk_store:
            return
        for ef in sorted(CHUNKS_DIR.glob("*_enriched.json")):
            with open(ef, "r", encoding="utf-8") as f:
                records = json.load(f)
            for r in records:
                cid = r.get("chunk_id", "")
                if cid:
                    self._chunk_store[cid] = r
        print(f"  Chunk store: {len(self._chunk_store)} chunks loaded")

    def _load_entity_index(self):
        """从 Neo4j 加载实体名索引用于快速匹配"""
        if self._entity_name_index:
            return
        with self.neo4j_driver.session() as session:
            for label in ["Drug", "API", "Manufacturer", "Country",
                          "TherapeuticArea", "Regulation", "ShortageEvent"]:
                result = session.run(
                    f"MATCH (n:{label}) RETURN n.name AS name"
                )
                for rec in result:
                    name = rec["name"]
                    if name and len(name) >= 2:
                        self._entity_name_index[name.lower()] = (label, name)
        print(f"  Entity index: {len(self._entity_name_index)} entities")

    def initialize(self):
        """预加载所有资源"""
        _ = self.faiss_index
        _ = self.entity_faiss_index  # 新增
        _ = self.neo4j_driver
        self._load_chunk_store()
        self._load_entity_index()
        print("  [OK] GraphRAG Retriever initialized\n")

    def close(self):
        """关闭连接"""
        if self._neo4j_driver:
            self._neo4j_driver.close()

    # ============================================================
    #  策略路由 (新增)
    # ============================================================

    def _route_strategies(self, query: str, chunks: List[ChunkResult],
                          entities: List[KGEntity]) -> List[str]:
        """
        智能策略路由: 根据 query 特征和 Stage 1 结果决定后续执行哪些 Stage。
        
        路由规则:
          - bottom_up: 永远执行 (Stage 1 已完成)
          - top_down:  碎片触发 — 某文档命中 >= N chunks 时启动整章阅读
          - graph_walk: 只要存在可游走的 KG 实体 (Drug/API/Manufacturer/
                        ShortageEvent/Regulation/Country) 就触发，让 LLM
                        自行判断路径是否有价值。额外检查风险关键词兜底。
        """
        cfg = self.config.retriever
        strategies = ["bottom_up"]

        # ── 图游走触发 (宽松版) ──
        # 条件1: 存在可游走的实体类型 (医药 KG 关系丰富，只要有实体就值得游走)
        walkable_labels = {"Drug", "API", "Manufacturer",
                           "ShortageEvent", "Regulation", "Country"}
        has_walkable_entity = any(e.label in walkable_labels for e in entities)

        # 条件2: query 含风险/推理/跨文档关键词
        query_lower = query.lower()
        risk_match = any(kw in query_lower for kw in cfg.risk_keywords)

        if has_walkable_entity or risk_match:
            strategies.append("graph_walk")

        # ── 整章阅读触发 ──
        doc_counts = Counter(c.doc_id for c in chunks)
        if any(count >= cfg.top_down_doc_threshold for count in doc_counts.values()):
            strategies.append("top_down")

        # ── 兜底: 完全没命中 chunk, 也启动 top_down ──
        if len(chunks) == 0 and entities:
            strategies.append("top_down")

        return strategies

    # ============================================================
    #  Stage 1: Bottom-Up (增强版: 三路召回 + 同级补充)
    # ============================================================

    def stage1_bottom_up(self, query: str) -> Tuple[List[ChunkResult], List[KGEntity]]:
        """
        五路并行召回 (对应化工版 S1 + S1.5):
          1a. FAISS chunk 向量检索
          1b. FAISS 实体向量检索
          1c. query 文本中实体名直接匹配
          1d. 通过 MENTIONS 边从 chunks 找 KG 实体
          1e. 关键词匹配 (补充向量盲区: 标准号、条款号精确命中)
        + 同级兄弟 chunk 补充 (对应化工版 S1.5)
        """
        import faiss
        cfg = self.config.retriever

        # ── 1a. FAISS chunk 向量检索 ──
        query_emb = self.embedding_model.encode([query])
        query_emb = np.array(query_emb, dtype=np.float32)
        faiss.normalize_L2(query_emb)
        scores, indices = self.faiss_index.search(query_emb, cfg.faiss_top_k)

        # 去重: 同一个 chunk_id 可能有多个向量 (content + hyde)
        seen_chunks = {}
        for score, idx in zip(scores[0], indices[0]):
            if idx < 0 or idx >= len(self.faiss_meta):
                continue
            meta = self.faiss_meta[idx]
            cid = meta["chunk_id"]
            if score < cfg.chunk_score_threshold:
                continue
            if cid not in seen_chunks or score > seen_chunks[cid]:
                seen_chunks[cid] = float(score)

        # 构建 ChunkResult
        chunks = []
        for cid, score in sorted(seen_chunks.items(), key=lambda x: -x[1]):
            full = self._chunk_store.get(cid, {})
            chunks.append(ChunkResult(
                chunk_id=cid,
                doc_id=full.get("doc_id", ""),
                heading=full.get("heading", ""),
                content=full.get("content", ""),
                summary=full.get("summary", ""),
                parents_context=full.get("parents_context", ""),
                level=full.get("level", 0),
                score=score,
                source="faiss",
            ))

        # ── 1b. FAISS 实体向量检索 (新增) ──
        entities = []
        if self.entity_faiss_index is not None and self.entity_faiss_meta is not None:
            e_scores, e_indices = self.entity_faiss_index.search(
                query_emb, cfg.entity_faiss_top_k
            )
            for score, idx in zip(e_scores[0], e_indices[0]):
                if idx < 0 or idx >= len(self.entity_faiss_meta):
                    continue
                if score < cfg.entity_score_threshold:
                    continue
                meta = self.entity_faiss_meta[idx]
                entities.append(KGEntity(
                    name=meta["name"],
                    label=meta["label"],
                    properties={"entity_id": meta.get("entity_id", "")},
                    source="faiss_entity",
                ))

        # ── 1c. query 文本中实体名直接匹配 ──
        query_lower = query.lower()
        query_words = set(re.findall(r"[a-zA-Z\u4e00-\u9fff]{2,}", query_lower))
        for entity_key, (label, entity_name) in self._entity_name_index.items():
            matched = False
            # 精确子串匹配
            if entity_key in query_lower:
                matched = True
            # 反向匹配 (长词)
            elif any(w in entity_key for w in query_words if len(w) >= 4):
                matched = True
            if matched:
                entities.append(KGEntity(
                    name=entity_name, label=label, source="query_match"
                ))

        # ── 1d. 通过 MENTIONS 边从 chunks 找 KG 实体 ──
        with self.neo4j_driver.session() as session:
            chunk_ids = [c.chunk_id for c in chunks]
            if chunk_ids:
                result = session.run(
                    "UNWIND $chunk_ids AS cid "
                    "MATCH (c:DocChunk {chunk_id: cid})-[:MENTIONS]->(e) "
                    "RETURN DISTINCT e.name AS name, labels(e)[0] AS label",
                    chunk_ids=chunk_ids
                )
                for rec in result:
                    entities.append(KGEntity(
                        name=rec["name"], label=rec["label"],
                        source="mentions"
                    ))

        # ── 同级兄弟 chunk 补充 (新增) ──
        sibling_chunks = self._expand_siblings(chunks)
        chunks.extend(sibling_chunks)

        # ── 1e. 关键词匹配 (化工版 S1 补充) ──
        # 提取 query 中的关键词（字母数字2字以上 + 标准号如 ICH Q9、21 CFR）
        keyword_chunks = self._keyword_search_stage1(query, {c.chunk_id for c in chunks})
        chunks.extend(keyword_chunks)

        # ── 去重实体 ──
        seen = set()
        unique_entities = []
        for e in entities:
            key = (e.label, e.name)
            if key not in seen:
                seen.add(key)
                unique_entities.append(e)

        return chunks, unique_entities

    # ── 同级兄弟 chunk 补充 ──

    def _expand_siblings(self, chunks: List[ChunkResult]) -> List[ChunkResult]:
        """
        新增: 对短 chunk 或枚举项, 自动拉取前后兄弟 chunks 补充上下文。
        
        触发条件:
          - char_count < sibling_trigger_chars (默认 200)
          - 或内容以数字/字母编号开头 (枚举项)
        """
        cfg = self.config.retriever
        siblings = []
        existing_ids = {c.chunk_id for c in chunks}

        for chunk in chunks:
            full = self._chunk_store.get(chunk.chunk_id, {})
            char_count = full.get("char_count", len(chunk.content))

            # 判断是否需要补充
            is_short = char_count < cfg.sibling_trigger_chars
            is_enum = bool(re.match(r'^[\d]+[.)]\s|^[a-zA-Z][.)]\s', chunk.content.strip()))

            if not (is_short or is_enum):
                continue

            # 拉取前后兄弟
            for direction in ["prev_chunk_id", "next_chunk_id"]:
                current_id = full.get(direction)
                for _ in range(cfg.sibling_expand_count):
                    if not current_id or current_id in existing_ids:
                        break
                    sibling_data = self._chunk_store.get(current_id, {})
                    if not sibling_data:
                        break

                    siblings.append(ChunkResult(
                        chunk_id=current_id,
                        doc_id=sibling_data.get("doc_id", ""),
                        heading=sibling_data.get("heading", ""),
                        content=sibling_data.get("content", ""),
                        summary=sibling_data.get("summary", ""),
                        parents_context=sibling_data.get("parents_context", ""),
                        level=sibling_data.get("level", 0),
                        score=chunk.score * 0.7,  # 衰减分数
                        source="sibling",
                    ))
                    existing_ids.add(current_id)

                    # 继续沿同方向延伸
                    current_id = sibling_data.get(direction)

        return siblings

    def _keyword_search_stage1(self, query: str, exclude_ids: Set[str],
                                limit: int = 8) -> List[ChunkResult]:
        """
        S1 关键词匹配 (补充向量检索的盲区):
          - 对 query 中的关键词（包含标准号如 ICH Q9、21 CFR 210）做文本匹配
          - 匹配 chunk 的 content / heading / summary / search_text
          - 返回命中关键词最多的 Top-K chunks

        解决向量检索的盲区: 具体标准号/条款号 (Annex 11, 21 CFR 210.3) 向量
        相似度可能较低，但关键词精确匹配能直接命中。
        """
        # 提取关键词: 标准号（ICH Q9、21 CFR 210、Annex 11）+ 普通词
        # 先提取标准号模式（大写字母+数字组合），再提取普通英文/中文词
        std_codes = re.findall(r"[A-Z]{1,5}\s*[A-Za-z]?\d+[A-Za-z]?(?:\.\d+)?", query)
        plain_words = re.findall(r"\b[a-zA-Z\u4e00-\u9fff]{3,}\b", query)
        stopwords = {"what", "when", "where", "which", "how", "why", "does", "with",
                     "that", "this", "from", "into", "have", "been", "their", "also",
                     "for", "the", "and", "are", "can", "not", "its", "any", "all",
                     "under", "apply", "between", "should", "used", "within",
                     "principles", "requirements", "system", "systems", "process"}
        keywords = list(dict.fromkeys(  # 去重保序
            [c.strip().lower() for c in std_codes if len(c.strip()) >= 2] +
            [w.lower() for w in plain_words if w.lower() not in stopwords]
        ))
        if not keywords:
            return []

        results = []
        for cid, data in self._chunk_store.items():
            if cid in exclude_ids:
                continue
            search_text = (
                (data.get("search_text") or "") + " " +
                (data.get("heading") or "") + " " +
                (data.get("summary") or "")
            ).lower()
            hit_count = sum(1 for kw in keywords if kw in search_text)
            if hit_count >= 2:  # 至少命中2个关键词才收录
                results.append((cid, data, hit_count))

        results.sort(key=lambda x: -x[2])
        chunks = []
        for cid, data, hit in results[:limit]:
            chunks.append(ChunkResult(
                chunk_id=cid,
                doc_id=data.get("doc_id", ""),
                heading=data.get("heading", ""),
                content=data.get("content", ""),
                summary=data.get("summary", ""),
                parents_context=data.get("parents_context", ""),
                level=data.get("level", 0),
                score=0.35 + 0.05 * min(hit, 5),  # 关键词数越多分越高，上限0.6
                source="keyword",
            ))
            exclude_ids.add(cid)
        return chunks
    # ============================================================

    def stage2_top_down(self, entities: List[KGEntity],
                        existing_chunk_ids: Set[str],
                        chunks_stage1: List[ChunkResult] = None
                        ) -> Tuple[List[ChunkResult], List[KGRelation]]:
        """
        从 KG 实体出发:
          a) 展开邻居关系获取 KG 结构化知识
          b) 反向 MENTIONS 查找补充文档证据
          c) 整章阅读: 当 chunks 集中于某文档时, 批量加载相关章节 (新增)
        """
        cfg = self.config.retriever
        relations = []
        supporting_chunks = []
        entity_names = [e.name for e in entities]

        if not entity_names:
            return supporting_chunks, relations

        with self.neo4j_driver.session() as session:
            # 2a. 展开实体的直接邻居关系
            result = session.run(
                "UNWIND $names AS ename "
                "MATCH (a {name: ename})-[r]->(b) "
                "WHERE NOT b:DocChunk AND NOT b:Document "
                "RETURN a.name AS src_name, labels(a)[0] AS src_label, "
                "       type(r) AS rel, b.name AS tgt_name, labels(b)[0] AS tgt_label "
                "LIMIT 100",
                names=entity_names
            )
            for rec in result:
                relations.append(KGRelation(
                    source_name=rec["src_name"],
                    source_label=rec["src_label"],
                    relation=rec["rel"],
                    target_name=rec["tgt_name"],
                    target_label=rec["tgt_label"],
                ))

            # 也获取反向关系
            result = session.run(
                "UNWIND $names AS ename "
                "MATCH (b)-[r]->(a {name: ename}) "
                "WHERE NOT b:DocChunk AND NOT b:Document "
                "RETURN b.name AS src_name, labels(b)[0] AS src_label, "
                "       type(r) AS rel, a.name AS tgt_name, labels(a)[0] AS tgt_label "
                "LIMIT 100",
                names=entity_names
            )
            for rec in result:
                relations.append(KGRelation(
                    source_name=rec["src_name"],
                    source_label=rec["src_label"],
                    relation=rec["rel"],
                    target_name=rec["tgt_name"],
                    target_label=rec["tgt_label"],
                ))

            # 收集所有出现的新实体名（用于反向 MENTIONS 查找）
            all_entity_names = set(entity_names)
            for r in relations:
                all_entity_names.add(r.source_name)
                all_entity_names.add(r.target_name)

            # 2b. 反向 MENTIONS: 实体 → DocChunk
            result = session.run(
                "UNWIND $names AS ename "
                "MATCH (c:DocChunk)-[:MENTIONS]->(e {name: ename}) "
                "RETURN DISTINCT c.chunk_id AS chunk_id "
                "LIMIT $limit",
                names=list(all_entity_names),
                limit=cfg.max_supporting_chunks * 2
            )
            for rec in result:
                cid = rec["chunk_id"]
                if cid not in existing_chunk_ids:
                    full = self._chunk_store.get(cid, {})
                    if full:
                        supporting_chunks.append(ChunkResult(
                            chunk_id=cid,
                            doc_id=full.get("doc_id", ""),
                            heading=full.get("heading", ""),
                            content=full.get("content", ""),
                            summary=full.get("summary", ""),
                            parents_context=full.get("parents_context", ""),
                            level=full.get("level", 0),
                            score=0.5,
                            source="top_down",
                        ))
                        existing_chunk_ids.add(cid)

        # 2c. 整章阅读 (新增) — 当 Stage 1 的 chunks 集中于某文档时
        if chunks_stage1:
            chapter_chunks = self._chapter_read(chunks_stage1, existing_chunk_ids)
            supporting_chunks.extend(chapter_chunks)

        # 2d. 文本搜索补充
        if len(supporting_chunks) < cfg.max_supporting_chunks:
            needed = cfg.max_supporting_chunks - len(supporting_chunks)
            text_matched = self._text_search_chunks(
                entity_names, existing_chunk_ids, limit=needed
            )
            supporting_chunks.extend(text_matched)

        # 去重关系
        seen = set()
        unique_relations = []
        for r in relations:
            key = (r.source_name, r.relation, r.target_name)
            if key not in seen:
                seen.add(key)
                unique_relations.append(r)

        return supporting_chunks[:cfg.max_supporting_chunks * 2], unique_relations

    def _chapter_read(self, chunks_stage1: List[ChunkResult],
                      existing_ids: Set[str]) -> List[ChunkResult]:
        """
        新增: 整章阅读 — 当 chunks 高度集中于某文档时, 加载该文档同一章节的所有 chunks。
        
        逻辑 (借鉴化工项目 Top-Down):
          1. 找到命中 chunks 最集中的文档
          2. 找到最常出现的章节 (level=1 heading)
          3. 加载该章节下所有 chunks
        """
        cfg = self.config.retriever

        # 找集中度最高的文档
        doc_counts = Counter(c.doc_id for c in chunks_stage1)
        if not doc_counts:
            return []
        top_doc, top_count = doc_counts.most_common(1)[0]
        if top_count < cfg.top_down_doc_threshold:
            return []

        # 找该文档中命中最多的父级章节
        section_counts = Counter()
        for c in chunks_stage1:
            if c.doc_id == top_doc and c.parents_context:
                # 取第一级 (e.g., "ICH Q7 > 4. BUILDINGS" → "4. BUILDINGS")
                parts = c.parents_context.split(" > ")
                section = parts[0] if parts else c.heading
                section_counts[section] += 1

        if not section_counts:
            return []
        top_section = section_counts.most_common(1)[0][0]

        # 加载该章节的所有 chunks
        chapter_chunks = []
        for cid, data in self._chunk_store.items():
            if cid in existing_ids:
                continue
            if (data.get("doc_id") == top_doc and
                    top_section in (data.get("parents_context", "") or "")):
                chapter_chunks.append(ChunkResult(
                    chunk_id=cid,
                    doc_id=data.get("doc_id", ""),
                    heading=data.get("heading", ""),
                    content=data.get("content", ""),
                    summary=data.get("summary", ""),
                    parents_context=data.get("parents_context", ""),
                    level=data.get("level", 0),
                    score=0.4,
                    source="chapter_read",
                ))
                existing_ids.add(cid)

        return chapter_chunks[:10]  # 最多补充 10 个

    def _text_search_chunks(self, entity_names: List[str],
                            exclude_ids: Set[str],
                            limit: int = 5) -> List[ChunkResult]:
        """在 chunk store 中基于实体名做文本搜索"""
        results = []
        for cid, data in self._chunk_store.items():
            if cid in exclude_ids:
                continue
            content_lower = (data.get("search_text", "") or data.get("content", "")).lower()
            match_count = 0
            for name in entity_names:
                if name.lower() in content_lower:
                    match_count += 1
            if match_count > 0:
                results.append((cid, data, match_count))

        results.sort(key=lambda x: -x[2])
        chunks = []
        for cid, data, _ in results[:limit]:
            chunks.append(ChunkResult(
                chunk_id=cid,
                doc_id=data.get("doc_id", ""),
                heading=data.get("heading", ""),
                content=data.get("content", ""),
                summary=data.get("summary", ""),
                parents_context=data.get("parents_context", ""),
                level=data.get("level", 0),
                score=0.3,
                source="text_search",
            ))
            exclude_ids.add(cid)
        return chunks

    # ============================================================
    #  Stage 3: Graph Walk (风险传播)
    # ============================================================

    def stage3_graph_walk(self, entities: List[KGEntity]) -> List[RiskPath]:
        """
        从实体出发，沿供应链边做 BFS，追踪风险传播路径。
        
        典型路径:
          Manufacturer → SUPPLIED_BY(反) → API → CONTAINS_API(反) → Drug → BELONGS_TO_AREA → TherapeuticArea
          Drug → HAD_SHORTAGE → ShortageEvent
        """
        cfg = self.config.retriever

        # 只对关键实体类型做 graph walk
        walk_entities = [
            e for e in entities
            if e.label in ("Drug", "API", "Manufacturer", "Country", "ShortageEvent")
        ]

        if not walk_entities:
            return []

        all_paths = []

        with self.neo4j_driver.session() as session:
            for entity in walk_entities[:5]:  # 限制入口实体数
                depth_literal = int(cfg.max_walk_depth)
                cypher = (
                    f"MATCH (start {{name: $name}}) "
                    f"MATCH path = (start)-[*1..{depth_literal}]-(end) "
                    f"WHERE NONE(n IN nodes(path) WHERE n:DocChunk OR n:Document) "
                    f"  AND ALL(r IN relationships(path) WHERE type(r) IN $edge_types) "
                    f"WITH path, length(path) AS depth "
                    f"ORDER BY depth "
                    f"LIMIT $limit "
                    f"RETURN [n IN nodes(path) | n.name] AS node_names, "
                    f"       [n IN nodes(path) | labels(n)[0]] AS node_labels, "
                    f"       [r IN relationships(path) | type(r)] AS edge_types, "
                    f"       depth"
                )
                result = session.run(
                    cypher,
                    name=entity.name,
                    edge_types=cfg.risk_edge_types,
                    limit=cfg.max_walk_paths
                )

                for rec in result:
                    node_names = rec["node_names"]
                    node_labels = rec["node_labels"]
                    edge_types = rec["edge_types"]
                    depth = rec["depth"]

                    if len(node_names) < 2:
                        continue

                    risk_score = self._calculate_risk_score(
                        node_labels, edge_types
                    )

                    all_paths.append(RiskPath(
                        nodes=node_names,
                        labels=node_labels,
                        edges=edge_types,
                        depth=depth,
                        risk_score=risk_score,
                    ))

        # 去重并按风险评分排序
        seen = set()
        unique_paths = []
        for p in all_paths:
            key = tuple(p.nodes)
            if key not in seen:
                seen.add(key)
                unique_paths.append(p)

        unique_paths.sort(key=lambda x: -x.risk_score)
        return unique_paths[:cfg.max_walk_paths]

    # ============================================================
    #  Stage 3 (增强): LLM 引导图游走
    # ============================================================

    def _get_kg_neighbors(self, session, node_name: str) -> List[tuple]:
        """获取节点的 1-hop KG 邻居（双向，排除文档类节点）"""
        result = session.run(
            "MATCH (n {name: $name})-[r]-(nb) "
            "WHERE NOT nb:DocChunk AND NOT nb:Document AND nb.name IS NOT NULL "
            "RETURN type(r) AS edge, nb.name AS name, labels(nb)[0] AS label "
            "LIMIT 20",
            name=node_name,
        )
        return [(rec["edge"], rec["name"], rec["label"]) for rec in result]

    def _llm_select_next_hop(
        self,
        query: str,
        current_node: str,
        current_label: str,
        path_so_far: List[tuple],   # [(name, label), ...]
        candidates: List[tuple],    # [(edge, name, label), ...]
    ) -> List[tuple]:
        """调用 LLM 从候选邻居中选择最相关的下一跳节点"""
        from .llm_client import DeepSeekClient
        llm = DeepSeekClient(self.config.llm)
        cand_lines = "\n".join(
            f"  [{i+1}] -[{e}]-> ({lbl}: {nm})"
            for i, (e, nm, lbl) in enumerate(candidates)
        )
        path_str = " -> ".join(f"({lbl}:{nm})" for nm, lbl in path_so_far)
        prompt = (
            "You are navigating a pharmaceutical supply-chain knowledge graph.\n"
            f"Query: {query}\n\n"
            f"Current node: ({current_label}: {current_node})\n"
            f"Path so far: {path_str or '(start)'}\n\n"
            f"Available next hops:\n{cand_lines}\n\n"
            "Select the 1-2 indices most relevant to answering the query. "
            "Prefer nodes like ShortageEvent, Drug, Manufacturer, or Regulation "
            "that are semantically related to the query topic. "
            "Reply with ONLY a JSON array, e.g. [1] or [2,4]."
        )
        try:
            response = llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=16,
            )
            indices = [
                int(n) - 1 for n in re.findall(r"\d+", response)
                if 0 <= int(n) - 1 < len(candidates)
            ]
            return [candidates[i] for i in indices[:2]]
        except Exception:
            return candidates[:1]

    def stage3_llm_guided_walk(
        self,
        query: str,
        entities: List[KGEntity],
        max_depth: int = 3,
    ) -> Tuple[List[RiskPath], List[ChunkResult]]:
        """
        LLM 引导图游走 (Variant D 核心): 每步由 LLM 选择最相关的下一跳。

        与 stage3_graph_walk (BFS) 的关键区别:
          - BFS: 枚举 depth 内所有路径，取评分最高者
          - LLM 引导: 每步询问 LLM 哪个邻居与 query 最相关，定向前进

        返回: (RiskPath 列表, 由走过节点 MENTIONS 边找到的支撑 DocChunk 列表)
        """
        cfg = self.config.retriever
        walk_entities = [
            e for e in entities
            if e.label in ("Drug", "API", "Manufacturer",
                           "ShortageEvent", "Regulation", "Country")
        ]
        if not walk_entities:
            return [], []

        all_paths: List[RiskPath] = []
        walked_names: Set[str] = set()

        with self.neo4j_driver.session() as session:
            for start in walk_entities[:3]:
                path_nodes = [start.name]
                path_labels = [start.label]
                path_edges: List[str] = []
                current_node = start.name
                current_label = start.label
                visited: Set[str] = {current_node}
                walked_names.add(current_node)

                for _step in range(max_depth):
                    neighbors = self._get_kg_neighbors(session, current_node)
                    candidates = [
                        (edge, nm, lbl)
                        for edge, nm, lbl in neighbors
                        if nm not in visited
                    ]
                    if not candidates:
                        break
                    chosen = self._llm_select_next_hop(
                        query=query,
                        current_node=current_node,
                        current_label=current_label,
                        path_so_far=list(zip(path_nodes, path_labels)),
                        candidates=candidates[:8],
                    )
                    if not chosen:
                        break
                    edge, next_node, next_label = chosen[0]
                    path_nodes.append(next_node)
                    path_labels.append(next_label)
                    path_edges.append(edge)
                    visited.add(next_node)
                    walked_names.add(next_node)
                    current_node = next_node
                    current_label = next_label

                if len(path_nodes) >= 2:
                    all_paths.append(RiskPath(
                        nodes=path_nodes,
                        labels=path_labels,
                        edges=path_edges,
                        depth=len(path_edges),
                        risk_score=self._calculate_risk_score(path_labels, path_edges),
                    ))

            # 将走过的实体名通过 MENTIONS 边映射回支撑 DocChunks
            supporting_chunks: List[ChunkResult] = []
            if walked_names:
                result = session.run(
                    "UNWIND $names AS nm "
                    "MATCH (c:DocChunk)-[:MENTIONS]->(e {name: nm}) "
                    "RETURN DISTINCT c.chunk_id AS chunk_id "
                    "LIMIT 15",
                    names=list(walked_names),
                )
                for rec in result:
                    cid = rec["chunk_id"]
                    full = self._chunk_store.get(cid, {})
                    if full:
                        supporting_chunks.append(ChunkResult(
                            chunk_id=cid,
                            doc_id=full.get("doc_id", ""),
                            heading=full.get("heading", ""),
                            content=full.get("content", ""),
                            summary=full.get("summary", ""),
                            parents_context=full.get("parents_context", ""),
                            level=full.get("level", 0),
                            score=0.45,
                            source="llm_walk",
                        ))

        all_paths.sort(key=lambda x: -x.risk_score)
        return all_paths[:cfg.max_walk_paths], supporting_chunks

    def _calculate_risk_score(self, node_labels: List[str],
                              edge_types: List[str]) -> float:
        """
        基于路径特征计算风险评分 (0-1)。
        
        风险信号:
          - 路径经过 ShortageEvent → +0.3
          - 路径经过 HAD_SHORTAGE/WAS_RECALLED 边 → +0.3
          - 路径经过 SUPPLIED_BY (供应链依赖) → +0.1
          - 路径经过 Country → +0.1 (地理风险)
          - 路径经过 INTERACTS_WITH → +0.1
        """
        score = 0.0

        if "ShortageEvent" in node_labels or "RecallEvent" in node_labels:
            score += 0.3
        if "HAD_SHORTAGE" in edge_types or "WAS_RECALLED" in edge_types:
            score += 0.3
        if "SUPPLIED_BY" in edge_types:
            score += 0.1
        if "Country" in node_labels:
            score += 0.1
        if "INTERACTS_WITH" in edge_types:
            score += 0.1

        # 路径长度惩罚
        path_len = len(edge_types)
        if path_len > 2:
            score *= (1.0 - 0.1 * (path_len - 2))

        return min(max(score, 0.0), 1.0)

    # ============================================================
    #  综合检索入口 (增强版: 策略路由)
    # ============================================================

    def retrieve(self, query: str) -> RetrievalResult:
        """
        执行 3 阶段 GraphRAG 检索 (增强版)。

        流程:
          1. Stage 1: Bottom-Up (三路召回 + 同级补充)
          2. 策略路由: 根据 query 和 Stage 1 结果智能决定后续 Stage
          3. Stage 2: Top-Down (如果触发)
          4. Stage 3: Graph Walk (如果触发)

        Args:
            query: 用户问题

        Returns:
            RetrievalResult 聚合所有检索结果
        """
        result = RetrievalResult(query=query)

        # ── Stage 1: Bottom-Up (永远执行) ──
        t0 = time.time()
        chunks_s1, entities_s1 = self.stage1_bottom_up(query)
        result.timings["stage1_bottom_up"] = time.time() - t0
        result.chunks.extend(chunks_s1)
        result.entities.extend(entities_s1)

        # 统计同级补充
        sibling_count = sum(1 for c in chunks_s1 if c.source == "sibling")
        entity_faiss_count = sum(1 for e in entities_s1 if e.source == "faiss_entity")
        print(f"  Stage 1 (Bottom-Up): {len(chunks_s1)} chunks "
              f"(+{sibling_count} siblings), "
              f"{len(entities_s1)} entities "
              f"(+{entity_faiss_count} from FAISS) "
              f"[{result.timings['stage1_bottom_up']:.2f}s]")

        # ── 策略路由 ──
        strategies = self._route_strategies(query, chunks_s1, entities_s1)
        result.strategies_used = strategies
        print(f"  Strategy Router: {' + '.join(strategies)}")

        # ── Stage 2: Top-Down (如果触发) ──
        if "top_down" in strategies:
            t0 = time.time()
            existing_ids = {c.chunk_id for c in result.chunks}
            chunks_s2, relations = self.stage2_top_down(
                result.entities, existing_ids,
                chunks_stage1=chunks_s1  # 传入 Stage 1 结果用于整章阅读
            )
            result.timings["stage2_top_down"] = time.time() - t0
            result.chunks.extend(chunks_s2)
            result.relations.extend(relations)

            chapter_count = sum(1 for c in chunks_s2 if c.source == "chapter_read")
            print(f"  Stage 2 (Top-Down): +{len(chunks_s2)} chunks "
                  f"(+{chapter_count} chapter), "
                  f"{len(relations)} relations "
                  f"[{result.timings['stage2_top_down']:.2f}s]")
        else:
            # 即使没有整章阅读, 仍然执行基本的实体展开 + MENTIONS
            t0 = time.time()
            existing_ids = {c.chunk_id for c in result.chunks}
            chunks_s2, relations = self.stage2_top_down(
                result.entities, existing_ids
            )
            result.timings["stage2_top_down"] = time.time() - t0
            result.chunks.extend(chunks_s2)
            result.relations.extend(relations)

            print(f"  Stage 2 (Lite): +{len(chunks_s2)} chunks, "
                  f"{len(relations)} relations "
                  f"[{result.timings['stage2_top_down']:.2f}s]")

        # ── Stage 3: LLM 引导图游走 (如果触发) ──
        if "graph_walk" in strategies:
            t0 = time.time()
            risk_paths, walk_chunks = self.stage3_llm_guided_walk(query, result.entities)
            result.timings["stage3_llm_walk"] = time.time() - t0
            result.risk_paths.extend(risk_paths)
            # 将游走发现的支撑 chunks 加入结果（去重）
            existing_ids = {c.chunk_id for c in result.chunks}
            added = 0
            for c in walk_chunks:
                if c.chunk_id not in existing_ids:
                    result.chunks.append(c)
                    existing_ids.add(c.chunk_id)
                    added += 1
            print(f"  Stage 3 (LLM Walk): {len(risk_paths)} paths, "
                  f"+{added} new chunks "
                  f"[{result.timings['stage3_llm_walk']:.2f}s]")
        else:
            print(f"  Stage 3 (LLM Walk): skipped (no risk trigger)")

        # ── RRF 融合排序 (借鉴化工版) ──
        result.chunks = self._rrf_rerank(result.chunks)

        # ── 附加关联表格摘要 (HAS_TABLE) ──
        if self._driver:
            with self._driver.session() as session:
                self._enrich_chunks_with_tables(session, result.chunks)

        return result

    def _enrich_chunks_with_tables(self, session, chunks: List[ChunkResult]) -> None:
        """
        对每个 ChunkResult 查询 Neo4j 的 HAS_TABLE 边，
        将 TableChunk.summary 附加到 chunk.table_summaries。
        批量查询以减少往返次数。
        """
        if not chunks:
            return
        chunk_ids = [c.chunk_id for c in chunks]
        rows = list(session.run(
            """
            UNWIND $ids AS cid
            MATCH (c:DocChunk {chunk_id: cid})-[:HAS_TABLE]->(t:TableChunk)
            RETURN cid, t.summary AS summary, t.table_index AS idx
            ORDER BY cid, idx
            """,
            ids=chunk_ids,
        ))
        # 建立 chunk_id → [summary, ...] 映射
        from collections import defaultdict
        mapping: Dict[str, List[str]] = defaultdict(list)
        for r in rows:
            s = r["summary"]
            if s:
                mapping[r["cid"]].append(s)
        # 写回
        for c in chunks:
            if c.chunk_id in mapping:
                c.table_summaries = mapping[c.chunk_id]

    def _rrf_rerank(self, chunks: List[ChunkResult], k: int = 60) -> List[ChunkResult]:
        """
        Reciprocal Rank Fusion (RRF) 融合多路检索结果。

        化工版用 RRF 合并 S1+S2；医药版多出 sibling/keyword/chapter_read/
        llm_walk 等路径，RRF 能公平权衡各路径贡献、压制单路径高分偏差。

        公式: score(d) = sum_i( 1 / (k + rank_i(d)) )
              其中 i 遍历每个 source 组的排名。
        """
        if not chunks:
            return chunks

        # 按 source 分组，每组内按分数降序排列
        source_groups: Dict[str, List[ChunkResult]] = {}
        for c in chunks:
            source_groups.setdefault(c.source, []).append(c)
        for grp in source_groups.values():
            grp.sort(key=lambda x: -x.score)

        # 计算 RRF 分数
        rrf_scores: Dict[str, float] = {}
        for source, grp in source_groups.items():
            for rank, chunk in enumerate(grp):
                rrf_scores[chunk.chunk_id] = (
                    rrf_scores.get(chunk.chunk_id, 0.0) + 1.0 / (k + rank + 1)
                )

        # 去重（保留第一次出现的 ChunkResult 对象），按 RRF 分数降序
        seen: Set[str] = set()
        unique: List[ChunkResult] = []
        for c in chunks:
            if c.chunk_id not in seen:
                seen.add(c.chunk_id)
                unique.append(c)

        unique.sort(key=lambda c: -rrf_scores.get(c.chunk_id, 0.0))

        # 将 RRF 分数写回 score 字段（方便下游使用）
        rrf_lookup = {c.chunk_id: rrf_scores.get(c.chunk_id, 0.0) for c in unique}
        for c in unique:
            c.score = rrf_lookup[c.chunk_id]

        return unique
