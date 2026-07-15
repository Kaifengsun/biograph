"""
制药供应链文档处理 Pipeline — 配置中心
=====================================
支持 MinerU / HiChunk 两种解析后端
支持 Ollama(本地) / OpenAI API 两种 LLM 后端
"""

import os
import pathlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

# ============================================================
#  网络
# ============================================================
# HuggingFace 国内镜像 (解决模型下载问题)
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

# 禁用代理 (国内 API 直连)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
for _v in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    os.environ.pop(_v, None)

# ============================================================
#  路径
# ============================================================
BASE_DIR = pathlib.Path(__file__).parent.parent  # financial knowledge graph/
PIPELINE_DIR = pathlib.Path(__file__).parent      # pharma_doc_pipeline/

# 数据目录
PDF_DIR      = BASE_DIR / "data" / "pdfs"          # 原始 PDF
MD_DIR       = BASE_DIR / "data" / "markdown"       # MinerU 输出的 Markdown
CHUNKS_DIR   = BASE_DIR / "data" / "chunks"         # 切分后的 JSON
VECTORS_DIR  = BASE_DIR / "data" / "vectors"        # 向量索引
CACHE_DIR    = BASE_DIR / "data" / "pipeline_cache"  # 断点续传缓存

for _d in [PDF_DIR, MD_DIR, CHUNKS_DIR, VECTORS_DIR, CACHE_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# ============================================================
#  PDF 转换后端
# ============================================================
@dataclass
class ParserConfig:
    """PDF → Markdown 解析配置"""
    # "mineru" | "hichunk_server" | "raw_markdown"
    backend: str = "mineru"

    # MinerU 配置
    mineru_device: str = "cuda"  # "cuda" | "cpu"

    # HiChunk 远程服务器配置 (如果用服务器上的 hichunk)
    hichunk_server_url: str = "http://your-server:8000/v1"
    hichunk_model_path: str = "tencent/Youtu-HiChunk"


# ============================================================
#  LLM 配置
# ============================================================
@dataclass
class LLMConfig:
    """LLM 后端配置"""
    # "ollama" | "api" | "openai" | "deepseek" | "moonshot"
    backend: str = "moonshot"

    # Ollama 本地配置 (RTX 5060 可跑 7B)
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"

    # API 配置 (Moonshot / DeepSeek / OpenAI-compat)
    api_base_url: str = os.getenv("MOONSHOT_API_BASE_URL", "https://api.moonshot.cn/v1")
    api_key: str = os.getenv("MOONSHOT_API_KEY", "")
    api_model: str = os.getenv("MOONSHOT_MODEL", "kimi-k2.6")
    api_extra_body: Dict[str, Any] = field(default_factory=dict)

    # 通用参数
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout: int = 120

    @property
    def is_local(self) -> bool:
        return self.backend == "ollama"


# ============================================================
#  Embedding 配置
# ============================================================
@dataclass
class EmbeddingConfig:
    """向量化配置"""
    # "local" | "api"
    backend: str = "local"

    # 本地模型 (RTX 5060 / CPU 均可)
    local_model: str = "tencent/Youtu-Embedding"
    # 或者用中英双语模型:
    # local_model: str = "BAAI/bge-small-en-v1.5"

    # API embedding
    api_model: str = "text-embedding-3-small"

    # 向量维度 (MiniLM=384, bge-small=384, text-embedding-3-small=1536)
    dimension: int = 2048

    # 索引类型
    index_type: str = "faiss"  # "faiss" | "neo4j_vector"


# ============================================================
#  切分配置
# ============================================================
@dataclass
class ChunkingConfig:
    """层级切分配置"""
    # 最大切分深度 (对应 hichunk 的 max_split_depth)
    max_depth: int = 3

    # 触发 LLM 摘要的阈值
    summary_trigger_lines: int = 20
    summary_trigger_chars: int = 1500

    # chunk 最大字符数 (超过则拆分)
    max_chunk_chars: int = 2000

    # chunk 重叠字符数
    overlap_chars: int = 200

    # 是否生成 HyDE 假设性问题
    enable_hyde: bool = True
    hyde_questions_per_chunk: int = 2


# ============================================================
#  HyDE 模板
# ============================================================
HYDE_TEMPLATES = {
    "supply_chain_risk": [
        "What happens if the supply of {entity} is disrupted?",
        "Which drugs are affected if {entity} stops production?",
        "What are the alternative suppliers for {entity}?",
        "What is the single-source risk for {entity}?",
    ],
    "regulatory": [
        "What are the GMP requirements for {entity}?",
        "Under what conditions would FDA issue an import alert for {entity}?",
        "What quality standards must {entity} comply with?",
    ],
    "drug_safety": [
        "What are the contraindications for {entity}?",
        "What interactions occur between {entity} and other drugs?",
        "What adverse events have been reported for {entity}?",
    ],
    "shortage": [
        "What are the root causes of {entity} shortage?",
        "What is the recommended response during shortage of {entity}?",
        "Which therapeutic alternatives exist for {entity}?",
    ],
}


# ============================================================
#  需要下载的文档清单
# ============================================================
DOCUMENT_SOURCES = [
    # --- ICH 指南 (核心监管文档, 均已验证可下载) ---
    {
        "id": "ich_q7",
        "title": "ICH Q7 Good Manufacturing Practice for APIs",
        "url": "https://database.ich.org/sites/default/files/Q7%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q9",
        "title": "ICH Q9(R1) Quality Risk Management",
        "url": "https://database.ich.org/sites/default/files/ICH_Q9%28R1%29_Guideline_Step4_2022_1219.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q10",
        "title": "ICH Q10 Pharmaceutical Quality System",
        "url": "https://database.ich.org/sites/default/files/Q10%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q12",
        "title": "ICH Q12 Lifecycle Management",
        "url": "https://database.ich.org/sites/default/files/Q12_Guideline_Step4_2019_1119.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q1a",
        "title": "ICH Q1A(R2) Stability Testing",
        "url": "https://database.ich.org/sites/default/files/Q1A%28R2%29%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 2,
    },
    # --- ICH 指南 (新增, 已验证可下载) ---
    {
        "id": "ich_q8r2",
        "title": "ICH Q8(R2) Pharmaceutical Development",
        "url": "https://database.ich.org/sites/default/files/Q8_R2_Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q11",
        "title": "ICH Q11 Development and Manufacture of Drug Substances",
        "url": "https://database.ich.org/sites/default/files/Q11_Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 1,
    },
    {
        "id": "ich_q5e",
        "title": "ICH Q5E Comparability of Biotechnological/Biological Products",
        "url": "https://database.ich.org/sites/default/files/Q5E%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 2,
    },
    {
        "id": "ich_q6a",
        "title": "ICH Q6A Specifications: Test Procedures and Acceptance Criteria",
        "url": "https://database.ich.org/sites/default/files/Q6A%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 2,
    },
    {
        "id": "ich_q6b",
        "title": "ICH Q6B Specifications for Biotechnological/Biological Products",
        "url": "https://database.ich.org/sites/default/files/Q6B%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 2,
    },
    {
        "id": "ich_q5c",
        "title": "ICH Q5C Stability Testing of Biotechnological/Biological Products",
        "url": "https://database.ich.org/sites/default/files/Q5C%20Guideline.pdf",
        "doc_type": "regulatory_guideline",
        "authority": "ICH",
        "priority": 2,
    },
    # --- FDA 指南 (fda.gov 有反爬, 需浏览器手动下载) ---
    {
        "id": "fda_drug_shortage",
        "title": "FDA Report to Congress: Drug Shortages",
        "url": None,  # fda.gov 阻止自动下载, 请浏览器访问: https://www.fda.gov/media/172499/download
        "doc_type": "policy_document",
        "authority": "FDA",
        "priority": 1,
    },
    {
        "id": "fda_cgmp_guidance",
        "title": "FDA cGMP Guidance",
        "url": None,  # 请浏览器访问: https://www.fda.gov/media/71023/download
        "doc_type": "regulatory_guideline",
        "authority": "FDA",
        "priority": 2,
    },
    # --- WHO (需要手动下载) ---
    {
        "id": "who_eml_23",
        "title": "WHO Model List of Essential Medicines (23rd List)",
        "url": None,  # iris.who.int 需浏览器下载
        "doc_type": "reference_list",
        "authority": "WHO",
        "priority": 2,
    },
]


# ============================================================
#  全局设置实例
# ============================================================
@dataclass
class PipelineSettings:
    parser: ParserConfig = field(default_factory=ParserConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)

    def summary(self):
        print("=" * 50)
        print("  Pharma Doc Pipeline 配置概览")
        print("=" * 50)
        print(f"  PDF 解析: {self.parser.backend}")
        print(f"  LLM 后端: {self.llm.backend} ({'本地' if self.llm.is_local else 'API'})")
        print(f"  Embedding: {self.embedding.backend} ({self.embedding.local_model})")
        print(f"  切分深度: {self.chunking.max_depth} 层")
        print(f"  HyDE: {'启用' if self.chunking.enable_hyde else '禁用'}")
        print("=" * 50)


settings = PipelineSettings()
