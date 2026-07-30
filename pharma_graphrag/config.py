"""
GraphRAG 配置
"""

import os
import pathlib
from dataclasses import dataclass, field

# ============================================================
#  网络设置（禁用代理）
# ============================================================
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"
for _v in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(_v, None)

os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

# ============================================================
#  路径
# ============================================================
BASE_DIR = pathlib.Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
VECTORS_DIR = DATA_DIR / "vectors"
CHUNKS_DIR = DATA_DIR / "chunks"

# ============================================================
#  配置类
# ============================================================

@dataclass
class Neo4jConfig:
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))


@dataclass
class LLMConfig:
    api_base_url: str = "https://api.deepseek.com/v1"
    api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    model: str = "deepseek-v4-pro"
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 120


@dataclass
class RetrieverConfig:
    # Stage 1: Bottom-Up
    faiss_top_k: int = 15           # FAISS 检索 chunk 的 top-k
    entity_faiss_top_k: int = 5     # FAISS 检索实体的 top-k
    chunk_score_threshold: float = 0.3  # chunk 最低相似度阈值
    entity_score_threshold: float = 0.35  # 实体最低相似度阈值

    # 同级兄弟 chunk 补充
    sibling_expand_count: int = 2   # 前后各拉取的兄弟 chunk 数
    sibling_trigger_chars: int = 200  # 短于此字符数时触发同级补充

    # Stage 2: Top-Down
    entity_expand_hops: int = 1     # 从实体展开的跳数
    max_supporting_chunks: int = 5  # 最多补充的支撑文档数
    top_down_doc_threshold: int = 3  # 某文档命中 >=N chunks 时触发整章阅读

    # Stage 3: Graph Walk
    max_walk_depth: int = 3         # BFS 最大深度
    max_walk_paths: int = 10        # 返回的影响路径数
    risk_edge_types: list = field(default_factory=lambda: [
        "SUPPLIED_BY", "CONTAINS_API", "MANUFACTURED_BY",
        "LOCATED_IN", "HAD_SHORTAGE", "WAS_RECALLED",
        "INTERACTS_WITH", "SUBSTITUTE_OF",
        "REFERENCES",         # 跨文档监管引用 (ICH Q9 → ICH Q10 等)
        "REGULATED_BY",       # Drug/Manufacturer 受哪个 Regulation 约束
        "SUBJECT_TO",         # 与 REGULATED_BY 同义的变体
    ])

    # 策略路由关键词 (触发 Graph Walk)
    risk_keywords: list = field(default_factory=lambda: [
        "risk", "impact", "affect", "consequence", "disrupt", "shortage",
        "recall", "fail", "stop", "halt", "ban", "withdraw",
        "supply chain", "manufacturer", "sourcing", "alternative",
        "multi-hop", "cross", "integrate", "connect", "relate",
        "how do", "what requirements", "which regulation",
        "风险", "影响", "后果", "中断", "短缺", "召回", "停产",
        "供应链", "制造商", "合规",
    ])

    # Embedding
    embedding_model: str = "tencent/Youtu-Embedding"
    embedding_dim: int = 2048


@dataclass
class GraphRAGConfig:
    neo4j: Neo4jConfig = field(default_factory=Neo4jConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    retriever: RetrieverConfig = field(default_factory=RetrieverConfig)
