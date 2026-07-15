# PharmGraphRAG 项目文档

> 版本：2025-07 | 维护人：孙凯枫

---

## 1. 项目概述

**PharmGraphRAG** 是一个面向制药供应链断供风险管控的知识图谱增强检索与多智能体仿真框架。核心主张：将分散的监管合规文本（ICH、EMA、FDA GMP指南）与结构化供应网络数据（FDA短缺记录、ChEMBL药物数据库、RxNorm药品标准）整合为统一异构知识图谱，通过三阶段GraphRAG流水线支持多跳合规风险推理，再由LLM智能体仿真层验证风险预测的历史真实性。

**研究问题**：知识图谱辅助的LLM智能体能否比纯参数化LLM更准确地复现历史断供事件的感知—捕获—转化应对过程？

**核心评估结果**：
- GraphRAG消融（n=23查询）：所有A/B/C/D变体在全局集上 R@5=9.4%、MRR=0.117；ICH子集（n=6）R@5=31.9%、MRR=0.517
- 5个历史事件仿真：PharmGraphRAG PSC均值=0.777，纯LLM PSC均值=0.570；E-03/04/05纯LLM崩溃（PSC=0），PharmGraphRAG保持0.648–0.801

---

## 2. 目录结构详解

### 2.1 核心模块目录

#### `pharma_doc_pipeline/` — 文档处理流水线
将原始PDF监管文档转化为知识图谱节点的完整流水线。

| 文件 | 功能 |
|------|------|
| `config.py` | 全局配置（数据路径、模型名称、分块参数等） |
| `main.py` | 流水线入口，按步骤顺序执行 step_00→step_04 |
| `step_00_download.py` | 从FDA/ICH/EMA官网下载PDF文档 |
| `step_01_convert.py` | 调用MinerU将PDF转换为结构化Markdown，保留章节层级和表格 |
| `step_02_chunk.py` | 将Markdown按章节边界切分为约512词元的分块，保留父级标题上下文 |
| `step_03_enrich.py` | 通过ChEMBL API和RxNorm API为分块中提及的药物名称添加标准化实体信息 |
| `step_04_vectorize.py` | 使用tencent/Youtu-Embedding（2048维）对分块向量化，存入FAISS索引 |

**运行方式**：
```bash
python pharma_doc_pipeline/main.py
# 或单步执行：
python pharma_doc_pipeline/step_02_chunk.py
```

---

#### `pharma_supply_chain/` — 知识图谱构建模块
从结构化数据源构建KG节点和边。

| 文件 | 功能 |
|------|------|
| `config.py` | Neo4j连接配置（bolt://localhost:7687，auth: neo4j/Nb87891882） |
| `core_data.py` | 手工维护的核心供应链关系数据（药品→制造商、API→制造商） |
| `chembl_fetcher.py` | 单次查询ChEMBL API获取药物-靶点数据 |
| `bulk_chembl_fetcher.py` | 批量获取ChEMBL数据，支持断点续传 |
| `fda_fetcher.py` | 获取FDA药品短缺数据库记录，含原因类别和历史时间线 |
| `rxnorm_fetcher.py` | 调用RxNorm API标准化药品名称（通用名/商品名/CUI映射） |
| `kg_builder.py` | 将获取的结构化数据构建为Neo4j图节点和边 |
| `bulk_kg_builder.py` | 批量构建，适用于大规模导入 |
| `neo4j_import.py` | 生成并执行Cypher导入脚本 |
| `main.py` | 模块入口，协调各数据源的获取和图构建 |

---

#### `pharma_graphrag/` — GraphRAG检索模块
实现三阶段GraphRAG检索流水线，是智能体仿真的知识后端。

| 文件 | 功能 |
|------|------|
| `config.py` | 检索参数（top-k、相似度阈值、图游走深度限制） |
| `llm_client.py` | DeepSeek-Chat API调用封装（支持流式和非流式，含重试逻辑） |
| `retriever.py` | **核心文件**：三阶段检索实现 |
| `main.py` | 检索模块入口，可单独调用进行交互式查询测试 |

**三阶段检索逻辑**（`retriever.py`）：
1. **第一阶段**（HyDE增强密集向量检索）：用LLM生成假设答案，对假设答案向量化后检索FAISS，返回top-k分块及其相邻分块
2. **第二阶段**（自顶向下文档导航）：识别第一阶段结果中的实体，通过Neo4j `MENTIONS` 反向查找关联文档节点，并向下展开子节点
3. **第三阶段**（LLM引导图游走）：以识别出的KG实体为起点，每步让LLM根据查询和邻居节点描述决定下一步游走方向，积累相关节点上下文

---

#### `agent_sim/` — 多智能体仿真模块
在知识图谱上运行LLM驱动的多智能体供应链断供仿真。

| 文件 | 功能 |
|------|------|
| `base_agent.py` | 智能体基类，定义 `perceive()`、`decide()`、`act()` 接口和知识图谱查询辅助方法 |
| `manufacturer_agent.py` | **ManufacturerAgent**：制造商智能体，负责生产调度、供应商认证申请、库存管理 |
| `regulator_agent.py` | **RegulatorAgent**：监管机构智能体，负责GMP检查结论发布、短缺豁免审批 |
| `distributor_agent.py` | **DistributorAgent**：分销商智能体，负责库存分配和需求响应 |
| `events.py` | 5个历史事件的事件定义（E-01~E-05），含初始化参数和历史时间线标注 |
| `simulator.py` | **仿真主循环**：初始化智能体状态，按周迭代执行感知→决策→行动→状态更新，记录每周PSC数据 |

**仿真配置**：
- 最大仿真周数：52周
- 随机种子：42
- LLM温度：智能体审议=0.7，检索决策=0.1
- GraphRAG条件：是/否（通过参数切换）

---

### 2.2 数据目录

#### `data/` — 所有数据文件
```
data/
├── pdfs/                   原始PDF监管文档（ICH Q1-Q14、EMA GMP、FDA指导等）
├── markdown/               MinerU转换后的结构化Markdown文件
├── chunks/                 分块后的JSON文件（每块含文本、父标题、源文档、位置信息）
├── vectors/
│   ├── pharma_docs.faiss   文档分块的FAISS向量索引（3,500向量，2048维）
│   ├── pharma_docs_meta.pkl 分块元数据（与FAISS索引对应）
│   ├── pharma_entities.faiss 实体向量索引（7,480实体，2048维）
│   └── pharma_entities_meta.pkl 实体元数据
├── pipeline_cache/         各步骤的中间缓存（避免重复API调用）
├── eval_queries.json       检索评估集（50个查询，含23个有可验证ground truth的子集）
├── ablation_results_full.json  消融实验完整结果（A/B/C/D四变体，n=23）
├── ablation_results_abc.json   早期A/B/C三变体结果
├── chembl_bulk_data.json   批量获取的ChEMBL药物数据
├── chembl_data.json        ChEMBL基础数据
├── fda_enrichment_data.json FDA丰富化数据
├── fda_shortage_additional.json 额外获取的FDA短缺记录
└── rxnorm_data.json        RxNorm标准化数据
```

#### `simulation_results/` — 仿真结果
```
simulation_results/
├── all_graphrag.json       PharmGraphRAG条件下5个事件的完整仿真结果（events为列表）
├── all_results_no_graphrag_no_graphrag.json  纯LLM基线5个事件结果（E-04/05 PSC=0）
├── all_no_graphrag_baseline_no_graphrag.json 另一版本基线结果
├── all_results.json        早期混合结果（已弃用）
├── E01_results.json        E-01单事件早期测试结果
├── E01_no_graphrag_test_no_graphrag.json E-01基线单独测试
└── graphrag_run.log        GraphRAG仿真运行日志
```

#### `output/` — 知识图谱导出
```
output/
├── import_neo4j.cypher     完整的Neo4j导入Cypher脚本
├── pharma_kg_nodes.csv     所有节点（含类型、属性）的CSV导出
├── pharma_kg_edges.csv     所有边（含类型、起终点）的CSV导出
└── kg_statistics.json      图统计信息（节点/边计数，分类型汇总）
```

#### `neo4j_docker_data/` — Neo4j数据卷
Neo4j Docker容器的持久化数据目录，挂载为容器内的 `/data`。

---

### 2.3 论文写作目录

#### `sections/` — 论文章节草稿
```
sections/
├── draft_chinese.md        **主工作文件**：中文论文完整草稿（含所有实验数据）
├── 孙凯枫论文初稿.md       原始初稿（参考用，不修改）
├── 01_abstract.md          摘要英文草稿
├── 02_introduction.md      引言英文草稿
├── 03_related_work.md      相关工作英文草稿
├── 03b_problem_definition.md 问题定义章节
├── 04_methodology.md       方法论英文草稿
├── 05_experiments.md       实验英文草稿
├── 06_conclusion.md        结论英文草稿
└── image/                  论文图表存放目录
```

#### `plan/` — 写作计划
```
plan/
└── paper-writing-plan.md   论文写作时间线和章节任务分配
```

#### `references/` — 参考文献管理
存放BibTeX或Markdown格式的参考文献文件。

#### `文献/` — 文献资源（中文）
```
文献/
├── 国内参考文献引用映射表.md  中文参考文献到论文引用位置的映射
├── 国外参考文献引用映射表.md  英文参考文献映射
├── 英文参考文献/Literature_Notes.md  英文文献阅读笔记
└── 中文参考文献/             中文文献PDF（.caj格式）
```

---

### 2.4 根目录脚本（功能分类）

#### 仿真与评估脚本（主要使用）

| 文件 | 功能 | 主要参数 |
|------|------|---------|
| `run_simulation.py` | **主仿真脚本**，运行GraphRAG vs 纯LLM对比 | `--event E01~E05`，`--no-graphrag`，`--seed` |
| `retrieval_ablation.py` | A/B/C/D消融实验，批量评估所有变体 | `--variant A/B/C/D`，`--output` |
| `eval_retrieval.py` | 在评估集上运行检索并计算R@K/MRR | `--queries eval_queries.json` |
| `analyze_ablation.py` | 分析消融结果，计算统计显著性 | 读取 `ablation_results_full.json` |
| `compare_results.py` | 对比GraphRAG vs 基线的仿真结果 | 读取 `simulation_results/*.json` |
| `dump_results.py` | 将仿真JSON结果格式化输出为人类可读表格 | — |

#### Neo4j图数据库脚本

| 文件 | 功能 |
|------|------|
| `import_neo4j_data.py` | 从CSV/Cypher导入数据到Neo4j，含实体消歧逻辑 |
| `verify_neo4j.py` | 验证Neo4j连接和基本图统计（节点/边计数） |
| `diagnose_graph.py` | 深度诊断图结构，检查孤立节点、断链等问题 |

**Neo4j连接信息**：
- 容器名：`pharma-neo4j`（Docker）
- 地址：`bolt://localhost:7687`
- 认证：`neo4j` / `Nb87891882`
- 启动命令：`docker start pharma-neo4j`

#### 文献处理脚本

| 文件 | 功能 |
|------|------|
| `process_literature.py` | 处理文献PDF，提取摘要和关键信息 |
| `summarize_literature.py` | 用LLM生成文献摘要，写入Markdown |

#### 图表与可视化脚本

| 文件 | 功能 |
|------|------|
| `generate_charts.py` | 生成仿真结果可视化图（PSC时间线、SDE分布等） |
| `plot_pipeline_diagram.py` | 绘制流水线架构图 |
| `plot_unstructured_funnel.py` | 绘制文档处理漏斗图（PDF→Chunk→Vector） |
| `export_pipeline_pptx.py` | 将流水线图导出为PowerPoint格式 |

#### 以下划线开头的工具/调试脚本（一次性或辅助用途）

| 文件 | 功能 |
|------|------|
| `_check_gemini.py` | 测试Gemini API连接（已弃用） |
| `_download_remaining.py` | 下载遗漏的PDF文档 |
| `_gemini_verify.py` | Gemini验证工具（已弃用） |
| `_level_stats.py` | 查看分块层级统计 |
| `_run_full_chunk.py` | 触发完整重新分块 |
| `_test_chunk_5docs.py` | 测试5个文档的分块效果 |
| `_test_chunk_v2.py` | v2分块算法测试 |
| `_test_mineru.py` | 测试MinerU PDF转换 |
| `_verify_quality.py` | 验证分块质量（长度分布、截断率） |
| `_eval_stats.py` | 评估集统计 |
| `_inspect_chunk.py` | 检查单个分块内容 |
| `_list_all_chunks.py` | 列出所有分块的简要信息 |
| `_neo4j_stats.py` | 快速输出Neo4j统计信息 |
| `_show_chunks.py` | 格式化展示分块内容 |
| `_show_sim_results.py` | 格式化展示仿真结果 |

#### PowerShell/批处理脚本

| 文件 | 功能 |
|------|------|
| `run_full_pipeline.ps1` | 端到端运行完整流水线（step_00~step_04） |
| `bg_launch.ps1` | 后台启动仿真任务 |
| `postprocess.ps1` | 仿真后处理（结果汇总） |
| `.pipeline_run.ps1` / `.pipeline_run.cmd` | 流水线运行配置脚本 |

---

### 2.5 其他文件

| 文件 | 功能 |
|------|------|
| `requirements.txt` | Python依赖（torch、faiss-cpu、neo4j、openai等） |
| `HANDOFF.md` | 上下文切换备忘录（任务状态、待完成项） |
| `HANDOFF_TO_VSCODE.md` | VS Code会话切换备忘录 |
| `research_proposal_EN.md` / `.docx` | 英文研究计划书 |
| `研究计划.md` / `研究计划书.md` | 中文研究计划书 |
| `实验方案单独补充说明.md` | 实验设计补充说明 |
| `TA_Tutorial_Notes.md` | 助教/导师指导笔记 |
| `agent_sim_results.json` | 早期智能体仿真汇总结果 |
| `run_full.log` / `run_test.log` | 运行日志 |
| `切分错误.txt` | 分块错误案例记录 |
| `检索方法2.txt` | 检索方法备选方案笔记 |

---

## 3. 完整数据流程

```
原始数据源
    │
    ├─ 结构化：FDA短缺数据库、ChEMBL v34、RxNorm
    │   └─ pharma_supply_chain/ → data/chembl_*.json, fda_*.json, rxnorm_*.json
    │
    └─ 非结构化：ICH Q1-Q14、EMA GMP、FDA指导PDF
        └─ pharma_doc_pipeline/step_00_download.py → data/pdfs/
                    │
                    ▼
         step_01_convert.py (MinerU)
                    │
                    ▼
            data/markdown/        ← 结构化Markdown（含章节标题、表格）
                    │
                    ▼
         step_02_chunk.py
                    │
                    ▼
            data/chunks/          ← JSON分块（每块约512词元）
                    │
         step_03_enrich.py        ← 注入ChEMBL/RxNorm实体信息
                    │
                    ▼
         step_04_vectorize.py
                    │
                    ▼
    data/vectors/pharma_docs.faiss ← FAISS索引（3,500向量）

结构化数据 ──────────────────────────────────────────────┐
                                                          │
                                                          ▼
                                         import_neo4j_data.py
                                                          │
                                                          ▼
                                    Neo4j图数据库 (Docker)
                                    ├─ 20,294 节点
                                    └─ 55,797 条边
                                    (Drug/DocChunk/Manufacturer/
                                     RecallEvent/ShortageEvent 等)

                    ┌──────────────────────────────────────┐
                    │        pharma_graphrag/               │
                    │  ┌─────────────────────────────────┐ │
查询 ──────────────▶│  │ 第一阶段：HyDE + FAISS           │ │
                    │  │ 第二阶段：Neo4j实体导航          │ │
                    │  │ 第三阶段：LLM引导图游走          │ │
                    │  └─────────────────────────────────┘ │
                    └──────────────────┬───────────────────┘
                                       │ 检索上下文
                                       ▼
                    ┌──────────────────────────────────────┐
                    │        agent_sim/                     │
                    │  ManufacturerAgent                    │
                    │  RegulatorAgent        ×52周          │
                    │  DistributorAgent                     │
                    └──────────────────┬───────────────────┘
                                       │
                                       ▼
                    simulation_results/all_graphrag.json
                    (PSC、SDE、SST 每事件指标)
```

---

## 4. 知识图谱统计（当前状态）

| 实体类型 | 数量 | 关系类型 | 数量 |
|---------|------|---------|------|
| Drug | 4,028 | TREATS | 33,780 |
| Entity（通用实体） | 7,480 | NEXT_CHUNK | 5,894 |
| DocChunk | 5,299 | SUPPLIED_BY | 329 |
| RecallEvent | 244 | MENTIONS | 542 |
| ShortageEvent | 45 | WAS_RECALLED | 248 |
| Manufacturer | 69 | HAS_SHORTAGE | 45 |
| RegulatoryDoc | 35 | REFERENCES | ~800 |
| **总计** | **20,294** | **总计** | **55,797** |

---

## 5. 5个历史仿真事件

| ID | 药品 | 历史期间 | 历史持续 | 类型 | 用途 |
|----|------|---------|---------|------|------|
| E-01 | Sodium Chloride 0.9%（生理盐水） | 2014-09 | 44周 | 生产/质量 | 通用溶媒 |
| E-02 | Valsartan（缬沙坦） | 2018-07 | 36周 | 污染（NDMA） | 高血压 |
| E-03 | Doxorubicin（阿霉素） | 2012-07 | 52周 | 生产/质量 | 肿瘤化疗 |
| E-04 | Lidocaine（利多卡因） | 2019-04 | 24周 | 生产/质量 | 麻醉 |
| E-05 | Methotrexate（甲氨蝶呤） | 2022-01 | 26周 | 生产/质量+需求激增 | 肿瘤/免疫 |

### 仿真结果汇总

| 事件 | PharmGraphRAG PSC | 纯LLM PSC | PharmGraphRAG SST | SDE（GraphRAG） |
|------|-------------------|----------|-------------------|----------------|
| E-01 | 0.834 | 0.834 | ✓ 复现 | 22周 |
| E-02 | 0.876 | 0.876 | ✗ 未复现 | 16周 |
| E-03 | 0.726 | 0.0（崩溃） | ✗ 未复现 | 23周 |
| E-04 | 0.648 | 0.0（崩溃） | ✗ 未复现 | 14周 |
| E-05 | 0.801 | 0.0（崩溃） | ✓ 复现 | 15周 |
| **均值** | **0.777** | **0.570** | **40%（2/5）** | **18.0周** |

---

## 6. 技术配置

### Python环境
```
解释器：D:\Anaconda3\python.exe
关键依赖：
  - torch（GPU：RTX 5060 Laptop）
  - faiss-cpu
  - neo4j（Python驱动）
  - openai（兼容DeepSeek API）
  - sentence-transformers
  - mineru（PDF转换）
```

### LLM配置
```
提供商：DeepSeek
模型：deepseek-chat
API端点：https://api.deepseek.com/v1
API密钥：通过环境变量 OPENAI_API_KEY 提供，不写入仓库
检索温度：0.1
智能体温度：0.7
```

### 向量化配置
```
模型：tencent/Youtu-Embedding
维度：2048
精度：FP16
设备：RTX 5060 Laptop GPU
```

### Neo4j配置
```
连接：bolt://localhost:7687
用户名：neo4j
密码：Nb87891882
容器：pharma-neo4j（Docker）
数据卷：neo4j_docker_data/
```

---

## 7. 常用命令

### 启动Neo4j
```bash
docker start pharma-neo4j
python verify_neo4j.py   # 验证连接
```

### 运行仿真（GraphRAG）
```bash
python run_simulation.py --event E01
python run_simulation.py  # 所有5个事件
```

### 运行仿真（纯LLM基线）
```bash
python run_simulation.py --no-graphrag
```

### 运行消融实验
```bash
python retrieval_ablation.py
# 结果写入 data/ablation_results_full.json
```

### 查看仿真结果
```bash
python dump_results.py
python _show_sim_results.py
```

### 重建知识图谱（完整流程）
```bash
# 1. 下载文档
python pharma_doc_pipeline/step_00_download.py
# 2. 转换PDF
python pharma_doc_pipeline/step_01_convert.py
# 3. 分块
python pharma_doc_pipeline/step_02_chunk.py
# 4. 丰富化
python pharma_doc_pipeline/step_03_enrich.py
# 5. 向量化
python pharma_doc_pipeline/step_04_vectorize.py
# 6. 导入Neo4j
python import_neo4j_data.py
```

---

## 8. 已知问题与局限

### 实验层面
1. **消融A=B=C=D**：当前23个评估查询87%为纯文本GMP合规查询，无知识图谱实体锚点，导致第二/三阶段无法产生增量贡献。需扩充包含供应商/短缺事件实体的多跳查询（已计划为future work）。

2. **仿真初始化偏差**：智能体初始状态依赖公开FDA短缺记录，制造商级生产数据不可得时从聚合代理推算，引入SDE膨胀误差（E-03 SDE=23周 vs 历史52周）。

3. **E-03感知时间差**：仿真Sense=第1周，历史Sense=第2周。原因：仿真初始化时直接在提示中包含GMP检查发现；历史上存在约1周监管发布滞后。

4. **Table 6外部基线缺失**：NaiveRAG/GraphRAG-Global/HippoRAG等外部系统尚未独立部署对比，延迟数字无法填写，留待future work。

### 系统层面
5. **实体消歧精度**：FDA记录中制造商名称与ChEMBL/ICH文档不一致，基于编辑距离（阈值0.85）的模糊匹配有漏网情况，影响图游走覆盖率。

6. **Docker依赖**：Neo4j需要Docker运行，本地部署时需先 `docker start pharma-neo4j`。

7. **MinerU版本**：PDF转换效果依赖MinerU版本，部分扫描版PDF（非原生PDF）转换质量差，已在 `切分错误.txt` 中记录。

---

## 9. 下一步实验建议

1. **扩充评估集**：增加20+个含知识图谱实体锚点的多跳供应链查询，以量化第二/三阶段的增量贡献。

2. **外部基线部署**：独立部署NaiveRAG（作为消融基准）和GraphRAG-Global（微软开源实现），在同一查询集上对比延迟和R@K。

3. **更多仿真事件**：扩展至10+个历史事件，增加统计显著性分析（当前5事件样本量较小）。

4. **实体链接改进**：训练或微调制药领域实体链接模型（基于FDA FEI和ChEMBL交叉引用），改善跨来源制造商名称统一。

5. **动态KG更新**：将FDA Drug Shortages RSS作为实时数据源接入，实现增量图更新，测试在真实监控场景下的感知速度。
