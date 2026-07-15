"""
项目配置文件
定义数据源 URL、输出路径、图谱 Schema 等常量
"""

import os

# ============================================================
#  网络设置（禁用代理，解决连接问题）
# ============================================================
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    if var in os.environ:
        del os.environ[var]

# ============================================================
#  路径配置
# ============================================================
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
DATA_DIR = os.path.join(BASE_DIR, "data")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# ============================================================
#  FDA API 配置
# ============================================================
FDA_DRUG_LABEL_API = "https://api.fda.gov/drug/label.json"
FDA_DRUG_NDC_API = "https://api.fda.gov/drug/ndc.json"
FDA_DRUG_EVENT_API = "https://api.fda.gov/drug/event.json"
FDA_DRUG_ENFORCEMENT_API = "https://api.fda.gov/drug/enforcement.json"

# API 请求配置
FDA_API_LIMIT = 100          # 每次请求的最大记录数
FDA_REQUEST_DELAY = 0.5      # 请求间隔（秒）
FDA_MAX_RETRIES = 3          # 最大重试次数
FDA_TIMEOUT = 30             # 请求超时（秒）

# ============================================================
#  图谱 Schema 定义
# ============================================================

# 节点类型
NODE_LABELS = {
    "Drug":            "药品",
    "API":             "活性药物成分",
    "Manufacturer":    "制造商",
    "Country":         "国家/地区",
    "TherapeuticArea": "治疗领域",
    "ShortageEvent":   "短缺事件",
    "Regulation":      "监管法规",
    "RecallEvent":     "召回事件",
    "Target":          "药物靶点",
    "Indication":      "适应症",
}

# 关系类型
EDGE_TYPES = {
    "CONTAINS_API":     "包含成分",
    "SUPPLIED_BY":      "供应方",
    "INTERACTS_WITH":   "药物相互作用",
    "LOCATED_IN":       "位于",
    "BELONGS_TO_AREA":  "属于治疗领域",
    "HAD_SHORTAGE":     "曾发生短缺",
    "REGULATED_BY":     "受监管于",
    "SUBSTITUTE_OF":    "可替代",
    "MANUFACTURED_BY":  "生产商",
    "WAS_RECALLED":     "被召回",
    "ACTS_ON":          "作用于靶点",
    "TREATS":           "治疗适应症",
}

# ============================================================
#  DrugBank 配置（可选增强数据源）
# ============================================================
DRUGBANK_XML_PATH = os.path.join(DATA_DIR, "drugbank_full_database.xml")

# ============================================================
#  输出文件名
# ============================================================
NODES_CSV = os.path.join(OUTPUT_DIR, "pharma_kg_nodes.csv")
EDGES_CSV = os.path.join(OUTPUT_DIR, "pharma_kg_edges.csv")
KG_STATS_FILE = os.path.join(OUTPUT_DIR, "kg_statistics.json")
