"""
Step 4: 向量化 + 存储
=====================
  - 用 Tencent Youtu-Embedding (dim=2048) 生成向量
  - 文档 chunk 向量化: search_text + HyDE 假设性问题 → pharma_docs.faiss
  - KG 实体向量化: 7,480 节点描述文本 → pharma_entities.faiss
  - 可选: 写入 Neo4j (DocChunk 节点 + MENTIONS 边)

支持 sentence-transformers 本地推理和 OpenAI 兼容 API。
"""

import csv
import json
import os
import time
import re
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .config import (CHUNKS_DIR, VECTORS_DIR, CACHE_DIR, BASE_DIR,
                     PipelineSettings, EmbeddingConfig)

# The reproducible retrieval artifacts use a model already cached locally.
# Avoid a remote metadata check during experiments, which can otherwise make a
# local run depend on mirror availability.
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"


# ═══════════════════════════════════════════════════════════════
#  Embedding 客户端
# ═══════════════════════════════════════════════════════════════

class EmbeddingClient:
    """统一的 Embedding 接口"""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._model = None
        self._session = None

    def _load_local_model(self):
        """惰性加载本地模型 (FP16 半精度)"""
        if self._model is None:
            import torch
            from sentence_transformers import SentenceTransformer
            print(f"  Loading embedding model: {self.config.local_model} (FP16)")
            self._model = SentenceTransformer(
                self.config.local_model,
                device="cuda",
                trust_remote_code=True,
                local_files_only=True,
                model_kwargs={
                    "trust_remote_code": True,
                    "torch_dtype": torch.float16,
                },
            )
            # 确保整个模型在 FP16
            self._model.half()
            print("  Embedding model ready (FP16, CUDA)")
        return self._model

    @property
    def session(self):
        if self._session is None:
            import requests
            self._session = requests.Session()
            self._session.trust_env = False
        return self._session

    def embed(self, texts: List[str], batch_size: int = 8) -> np.ndarray:
        """
        批量生成 embeddings。
        返回 shape=(N, dim) 的 numpy 数组。
        """
        if not texts:
            return np.array([])

        if self.config.backend == "local":
            return self._embed_local(texts, batch_size)
        else:
            return self._embed_api(texts, batch_size)

    def _embed_local(self, texts: List[str], batch_size: int) -> np.ndarray:
        """sentence-transformers 本地推理"""
        model = self._load_local_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=len(texts) > 50,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype=np.float32)

    def _embed_api(self, texts: List[str], batch_size: int) -> np.ndarray:
        """OpenAI 兼容 API embedding"""
        from .config import PipelineSettings
        settings = PipelineSettings()
        api_key = settings.llm.api_key

        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            url = f"{settings.llm.api_base_url}/embeddings"
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": self.config.api_model,
                "input": batch,
            }
            try:
                r = self.session.post(url, json=payload, headers=headers,
                                      timeout=60)
                r.raise_for_status()
                data = r.json()
                batch_emb = [d["embedding"] for d in data["data"]]
                all_embeddings.extend(batch_emb)
            except Exception as e:
                print(f"    ⚠ Embedding API 错误: {e}")
                # 填充零向量
                for _ in batch:
                    all_embeddings.append([0.0] * self.config.dimension)

        return np.array(all_embeddings, dtype=np.float32)

    @property
    def dimension(self) -> int:
        if self.config.backend == "local":
            model = self._load_local_model()
            return model.get_sentence_embedding_dimension()
        return self.config.dimension


# ═══════════════════════════════════════════════════════════════
#  FAISS 索引管理
# ═══════════════════════════════════════════════════════════════

class FAISSIndex:
    """FAISS 向量索引封装"""

    def __init__(self, dimension: int, index_path: Path = None):
        import faiss  # noqa: F401 — lazy import to avoid hard dep
        self.dimension = dimension
        self.index_path = index_path or (VECTORS_DIR / "pharma_docs.faiss")
        self.meta_path = self.index_path.with_suffix('.meta.json')

        # chunk_id → 向量索引 position 映射
        self.metadata: List[Dict] = []

        # 初始化 FAISS index
        self.index = faiss.IndexFlatIP(dimension)  # 内积 (已 normalize)

    def add(self, embeddings: np.ndarray, chunk_metas: List[Dict]):
        """添加向量 + 元数据"""
        import faiss
        if len(embeddings) == 0:
            return
        # 确保 normalize
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings)
        self.metadata.extend(chunk_metas)

    def search(self, query_embedding: np.ndarray, top_k: int = 10) -> List[Tuple[Dict, float]]:
        """检索最相似的 chunks"""
        import faiss
        if self.index.ntotal == 0:
            return []
        q = query_embedding.reshape(1, -1).astype(np.float32)
        faiss.normalize_L2(q)
        scores, indices = self.index.search(q, top_k)
        results = []
        for score, idx in zip(scores[0], indices[0]):
            if idx >= 0 and idx < len(self.metadata):
                results.append((self.metadata[idx], float(score)))
        return results

    def save(self):
        """保存索引和元数据"""
        import faiss
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self.index, str(self.index_path))
        with open(self.meta_path, 'w', encoding='utf-8') as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        print(f"  💾 FAISS 索引: {self.index.ntotal} vectors → {self.index_path.name}")

    def load(self):
        """加载已有索引"""
        import faiss
        if self.index_path.exists() and self.meta_path.exists():
            self.index = faiss.read_index(str(self.index_path))
            with open(self.meta_path, 'r', encoding='utf-8') as f:
                self.metadata = json.load(f)
            print(f"  📂 FAISS 索引: 已加载 {self.index.ntotal} vectors")
            return True
        return False


# ═══════════════════════════════════════════════════════════════
#  文档 chunk 向量化
# ═══════════════════════════════════════════════════════════════

class Vectorizer:
    """文档 chunk 向量化主流程"""

    def __init__(self, settings: PipelineSettings = None):
        self.settings = settings or PipelineSettings()
        self.embed_client = EmbeddingClient(self.settings.embedding)

    def vectorize_all(self, chunks_dir: Path = None,
                      output_dir: Path = None) -> FAISSIndex:
        """
        向量化所有 enriched chunk 文件:
          1. 加载 *_enriched.json (或 *_chunks.json)
          2. 提取 search_text 生成 content embedding
          3. 提取 hyde_questions 生成 HyDE embedding (可选)
          4. 合并入 FAISS 索引
          5. 保存
        """
        chunks_dir = chunks_dir or CHUNKS_DIR
        output_dir = output_dir or VECTORS_DIR
        output_dir.mkdir(parents=True, exist_ok=True)

        # 优先读 enriched 文件
        enriched_files = sorted(chunks_dir.glob("*_enriched.json"))
        if not enriched_files:
            enriched_files = sorted(chunks_dir.glob("*_chunks.json"))

        if not enriched_files:
            print("  ⚠ 无 chunk 文件可向量化")
            return None

        print(f"╔{'═' * 50}╗")
        print(f"║  文档向量化 — 共 {len(enriched_files)} 个文档")
        print(f"║  Embedding: {self.settings.embedding.backend} "
              f"({self.settings.embedding.local_model})")
        print(f"╚{'═' * 50}╝\n")

        dim = self.embed_client.dimension
        faiss_index = FAISSIndex(dimension=dim,
                                 index_path=output_dir / "pharma_docs.faiss")

        all_texts = []
        all_metas = []
        hyde_texts = []
        hyde_metas = []

        # 收集所有 texts
        for ef in enriched_files:
            doc_id = ef.stem.replace("_enriched", "").replace("_chunks", "")
            print(f"  📄 {doc_id}...", flush=True)

            with open(ef, 'r', encoding='utf-8') as f:
                records = json.load(f)

            for r in records:
                # Content embedding
                search_text = r.get("search_text", r.get("content", ""))
                if not search_text.strip():
                    continue

                meta = {
                    "chunk_id": r.get("chunk_id", ""),
                    "doc_id": doc_id,
                    "heading": r.get("heading", ""),
                    "parents_context": r.get("parents_context", ""),
                    "level": r.get("level", 0),
                    "type": "content",
                }
                all_texts.append(search_text[:2000])  # 截断防溢出
                all_metas.append(meta)

                # HyDE embedding
                hyde_qs = r.get("hyde_questions", [])
                for q in hyde_qs:
                    hyde_meta = meta.copy()
                    hyde_meta["type"] = "hyde"
                    hyde_meta["hyde_question"] = q
                    hyde_texts.append(q)
                    hyde_metas.append(hyde_meta)

        print(f"\n  Content: {len(all_texts)} texts")
        print(f"  HyDE:    {len(hyde_texts)} questions")

        # 批量 embedding
        if all_texts:
            print(f"\n  Embedding content...", flush=True)
            content_emb = self.embed_client.embed(all_texts, batch_size=8)
            faiss_index.add(content_emb, all_metas)

        if hyde_texts:
            print(f"  Embedding HyDE questions...", flush=True)
            hyde_emb = self.embed_client.embed(hyde_texts, batch_size=8)
            faiss_index.add(hyde_emb, hyde_metas)

        # 保存
        faiss_index.save()

        # 额外: 保存文本映射 (方便调试)
        mapping_path = output_dir / "text_mapping.json"
        mapping = []
        for text, meta in zip(all_texts, all_metas):
            mapping.append({
                "chunk_id": meta["chunk_id"],
                "doc_id": meta["doc_id"],
                "text_preview": text[:200],
                "type": meta["type"],
            })
        for text, meta in zip(hyde_texts, hyde_metas):
            mapping.append({
                "chunk_id": meta["chunk_id"],
                "doc_id": meta["doc_id"],
                "text_preview": text[:200],
                "type": meta["type"],
            })
        with open(mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 文档向量化完成: {faiss_index.index.ntotal} vectors "
              f"(dim={dim})")
        return faiss_index


# ═══════════════════════════════════════════════════════════════
#  KG 实体向量化 (新增)
# ═══════════════════════════════════════════════════════════════

class EntityVectorizer:
    """
    KG 实体向量化: 读取 pharma_kg_nodes.csv, 为每个实体构建描述文本,
    向量化后存入独立的 FAISS 索引 (pharma_entities.faiss)。
    
    实体与文档 chunks 在同一向量空间 (Youtu-Embedding, dim=2048),
    支持跨模态检索: 用户 query → 同时检索文档 chunks 和 KG 实体。
    """

    # 不同实体类型的文本构建模板
    _TEMPLATES = {
        "Drug": (
            "{name} is a pharmaceutical drug."
            " Category: {category}."
            " Dosage form: {dosage_form}."
            " WHO essential medicine: {who_essential}."
            " ATC codes: {atc_codes}."
            " ChEMBL ID: {chembl_id}."
            " First approval: {first_approval}."
        ),
        "API": (
            "{name} is an active pharmaceutical ingredient (API)."
            " API class: {api_class}."
            " Manufactured in: {country}."
            " CAS number: {cas_number}."
        ),
        "Manufacturer": (
            "{name} is a pharmaceutical manufacturer."
            " Type: {mfg_type}."
            " Located in: {country}, region: {region}."
            " Tier: {tier}."
        ),
        "ShortageEvent": (
            "Drug shortage event: {name}."
            " Cause: {cause}."
            " Severity: {severity}."
            " Duration: {duration_months} months."
            " Impact: {impact}."
        ),
        "RecallEvent": (
            "Drug recall event: {name}."
            " Classification: {classification}."
            " Recalling firm: {recalling_firm}."
            " Report date: {report_date}."
            " Authority: {authority}."
        ),
        "Indication": (
            "Medical indication: {name}."
            " MeSH ID: {mesh_id}."
            " EFO term: {efo_term}."
        ),
        "Target": (
            "Drug target: {name}."
            " Target type: {target_type}."
            " Organism: {organism}."
        ),
        "Country": (
            "Country: {name}."
            " Region: {region}."
        ),
        "TherapeuticArea": (
            "Therapeutic area: {name}."
        ),
        "Regulation": (
            "Pharmaceutical regulation: {name}."
            " Authority: {authority}."
            " Description: {description}."
        ),
        "ATCClass": (
            "ATC classification: {name}."
            " ATC prefix: {atc_prefix}."
        ),
    }

    def __init__(self, embed_client: EmbeddingClient):
        self.embed_client = embed_client

    def _build_entity_text(self, row: dict) -> str:
        """根据实体类型构建描述文本"""
        label = row.get("label", "")
        template = self._TEMPLATES.get(label, "{label}: {name}.")

        # 用 row 中的值填充模板，空值填 "unknown"
        filled = {}
        for key, value in row.items():
            if value and str(value).strip() and str(value).strip().lower() not in ("", "nan", "none"):
                filled[key] = str(value).strip()
            else:
                filled[key] = "unknown"

        try:
            text = template.format(**filled)
        except KeyError:
            # 模板中有 row 里没有的 key，用基础模板
            text = f"{label}: {row.get('name', 'unknown')}."

        # 清理多余的 "unknown" 片段 (让文本更紧凑)
        # 移除含 "unknown" 的子句 (". XXX: unknown." 模式)
        import re
        text = re.sub(r'\s+\w[\w\s]*:\s*unknown\.', '', text)
        # 清理多余空格和句号
        text = re.sub(r'\.\s*\.', '.', text)
        text = re.sub(r'\s{2,}', ' ', text).strip()

        return text

    def vectorize_entities(self, nodes_csv: Path = None,
                           output_dir: Path = None) -> Optional[FAISSIndex]:
        """
        读取 KG 节点 CSV → 构建描述文本 → 向量化 → 存入 pharma_entities.faiss
        """
        nodes_csv = nodes_csv or (BASE_DIR / "output" / "pharma_kg_nodes.csv")
        output_dir = output_dir or VECTORS_DIR

        if not nodes_csv.exists():
            print(f"  ⚠ KG 节点文件不存在: {nodes_csv}")
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        # 读取 CSV
        entities = []
        with open(nodes_csv, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                entities.append(dict(row))

        if not entities:
            print("  ⚠ 无实体数据")
            return None

        # 统计实体类型分布
        from collections import Counter
        label_counts = Counter(e.get("label", "") for e in entities)

        print(f"╔{'═' * 50}╗")
        print(f"║  实体向量化 — 共 {len(entities)} 个实体")
        print(f"║  Embedding: {self.embed_client.config.local_model}")
        for label, count in sorted(label_counts.items(), key=lambda x: -x[1]):
            print(f"║    {label}: {count}")
        print(f"╚{'═' * 50}╝\n")

        # 构建描述文本
        texts = []
        metas = []
        for e in entities:
            text = self._build_entity_text(e)
            entity_id = e.get("id", "")
            name = e.get("name", "")
            label = e.get("label", "")

            texts.append(text)
            metas.append({
                "entity_id": entity_id,
                "name": name,
                "label": label,
                "type": "entity",
            })

        print(f"  构建了 {len(texts)} 个实体描述文本")

        # 打印几个样例
        for i in range(min(3, len(texts))):
            print(f"    示例 [{metas[i]['label']}]: {texts[i][:120]}...")

        # 向量化
        dim = self.embed_client.dimension
        faiss_index = FAISSIndex(
            dimension=dim,
            index_path=output_dir / "pharma_entities.faiss"
        )

        print(f"\n  Embedding {len(texts)} entities...", flush=True)
        entity_emb = self.embed_client.embed(texts, batch_size=8)
        faiss_index.add(entity_emb, metas)

        # 保存
        faiss_index.save()

        # 保存实体文本映射 (调试用)
        entity_mapping_path = output_dir / "entity_text_mapping.json"
        mapping = []
        for text, meta in zip(texts, metas):
            mapping.append({
                "entity_id": meta["entity_id"],
                "name": meta["name"],
                "label": meta["label"],
                "text_preview": text[:300],
            })
        with open(entity_mapping_path, 'w', encoding='utf-8') as f:
            json.dump(mapping, f, ensure_ascii=False, indent=2)

        print(f"\n✅ 实体向量化完成: {faiss_index.index.ntotal} vectors "
              f"(dim={dim})")
        return faiss_index


# ═══════════════════════════════════════════════════════════════
#  Neo4j 向量集成 (可选)
# ═══════════════════════════════════════════════════════════════

def link_chunks_to_neo4j(chunks_dir: Path = None,
                         neo4j_uri: str = "bolt://localhost:7687",
                         neo4j_auth: Tuple = ("neo4j", "Nb87891882")):
    """
    将文档 chunk 节点写入 Neo4j，并与现有 KG 实体建立链接。
    
    创建:
      - (DocChunk) 节点: chunk_id, doc_id, heading, content, level
      - (DocChunk)-[:FROM_DOCUMENT]->(Document) 边
      - (DocChunk)-[:MENTIONS]->(Drug|API|Manufacturer) 边 (文本匹配)
      - (DocChunk)-[:NEXT_CHUNK]->(DocChunk) 链表
    """
    from neo4j import GraphDatabase

    chunks_dir = chunks_dir or CHUNKS_DIR
    enriched_files = sorted(chunks_dir.glob("*_enriched.json"))
    if not enriched_files:
        enriched_files = sorted(chunks_dir.glob("*_chunks.json"))

    if not enriched_files:
        print("  ⚠ 无 chunk 文件")
        return

    driver = GraphDatabase.driver(neo4j_uri, auth=neo4j_auth)

    with driver.session() as session:
        # 创建约束
        try:
            session.run("CREATE CONSTRAINT IF NOT EXISTS "
                        "FOR (d:DocChunk) REQUIRE d.chunk_id IS UNIQUE")
            session.run("CREATE CONSTRAINT IF NOT EXISTS "
                        "FOR (doc:Document) REQUIRE doc.doc_id IS UNIQUE")
        except Exception:
            pass

        total_chunks = 0
        total_links = 0

        # 获取已有实体名 (用于文本匹配)
        def _normalize_text(text: str) -> str:
            text = text.replace("\u3000", " ")
            return " ".join(text.lower().strip().split())

        def _has_cjk(text: str) -> bool:
            return bool(re.search(r"[\u4e00-\u9fff]", text))

        def _extract_aliases(name: str) -> set:
            aliases = set()
            if not name:
                return aliases
            base = name.strip()
            aliases.add(base)

            # Split parentheses, keep both sides
            m = re.match(r"^(.*?)[(（](.*?)[)）]\s*$", base)
            if m:
                left = m.group(1).strip()
                right = m.group(2).strip()
                if left:
                    aliases.add(left)
                if right:
                    aliases.add(right)

            # Split on colon (e.g., "Shortage: DRUG_x")
            if ":" in base:
                after = base.split(":", 1)[1].strip()
                if after:
                    aliases.add(after)

            return aliases

        entity_aliases = []
        labels_to_link = [
            "Drug", "API", "Manufacturer", "Regulation",
            "ShortageEvent", "Country", "RecallEvent",
        ]
        for label in labels_to_link:
            result = session.run(f"MATCH (n:{label}) RETURN n.name AS name")
            for record in result:
                name = record["name"]
                if not name:
                    continue
                for alias in _extract_aliases(name):
                    alias_norm = _normalize_text(alias)
                    if not alias_norm:
                        continue
                    min_len = 2 if _has_cjk(alias_norm) else 4
                    if len(alias_norm) < min_len:
                        continue
                    is_latin = bool(re.fullmatch(r"[a-z0-9 .,/\-()]+", alias_norm))
                    pattern = None
                    if is_latin:
                        pattern = re.compile(rf"\b{re.escape(alias_norm)}\b", re.IGNORECASE)
                    entity_aliases.append((alias_norm, pattern, label, name))

        for ef in enriched_files:
            doc_id = ef.stem.replace("_enriched", "").replace("_chunks", "")
            print(f"  📄 {doc_id}...")

            with open(ef, 'r', encoding='utf-8') as f:
                records = json.load(f)

            # 创建 Document 节点
            session.run(
                "MERGE (d:Document {doc_id: $doc_id}) "
                "SET d.chunk_count = $count",
                doc_id=doc_id, count=len(records)
            )

            for r in records:
                chunk_id = r.get("chunk_id", "")
                if not chunk_id:
                    continue

                # 创建 DocChunk 节点
                session.run(
                    "MERGE (c:DocChunk {chunk_id: $chunk_id}) "
                    "SET c.doc_id = $doc_id, "
                    "c.heading = $heading, "
                    "c.level = $level, "
                    "c.parents_context = $parents_context, "
                    "c.content = $content, "
                    "c.summary = $summary",
                    chunk_id=chunk_id,
                    doc_id=doc_id,
                    heading=r.get("heading", ""),
                    level=r.get("level", 0),
                    parents_context=r.get("parents_context", ""),
                    content=r.get("content", "")[:5000],
                    summary=r.get("summary", ""),
                )

                # DocChunk → Document
                session.run(
                    "MATCH (c:DocChunk {chunk_id: $chunk_id}), "
                    "(d:Document {doc_id: $doc_id}) "
                    "MERGE (c)-[:FROM_DOCUMENT]->(d)",
                    chunk_id=chunk_id, doc_id=doc_id
                )

                # 链表: NEXT_CHUNK
                next_id = r.get("next_chunk_id")
                if next_id:
                    session.run(
                        "MATCH (a:DocChunk {chunk_id: $a_id}) "
                        "MERGE (b:DocChunk {chunk_id: $b_id}) "
                        "MERGE (a)-[:NEXT_CHUNK]->(b)",
                        a_id=chunk_id, b_id=next_id
                    )

                # 实体链接: MENTIONS
                content_norm = _normalize_text(
                    (r.get("search_text", "") or r.get("content", ""))
                )
                matched = set()
                for alias_norm, pattern, label, entity_name in entity_aliases:
                    if pattern:
                        if not pattern.search(content_norm):
                            continue
                    else:
                        if alias_norm not in content_norm:
                            continue
                    key = (label, entity_name)
                    if key in matched:
                        continue
                    matched.add(key)
                    session.run(
                        f"MATCH (c:DocChunk {{chunk_id: $chunk_id}}), "
                        f"(e:{label} {{name: $entity_name}}) "
                        f"MERGE (c)-[:MENTIONS]->(e)",
                        chunk_id=chunk_id, entity_name=entity_name
                    )
                    total_links += 1

                total_chunks += 1

    driver.close()
    print(f"\n✅ Neo4j 导入: {total_chunks} DocChunk 节点, "
          f"{total_links} MENTIONS 边")


# ═══════════════════════════════════════════════════════════════
#  入口
# ═══════════════════════════════════════════════════════════════

def run(**kwargs):
    """Step 4 入口"""
    settings = kwargs.get("settings", PipelineSettings())

    # 1. 文档 chunk 向量化 → pharma_docs.faiss
    vectorizer = Vectorizer(settings=settings)
    faiss_index = vectorizer.vectorize_all()

    # 2. KG 实体向量化 → pharma_entities.faiss
    entity_vectorizer = EntityVectorizer(embed_client=vectorizer.embed_client)
    entity_index = entity_vectorizer.vectorize_entities()

    # 3. 可选: 导入 Neo4j
    if kwargs.get("neo4j", False):
        link_chunks_to_neo4j()

    return faiss_index
