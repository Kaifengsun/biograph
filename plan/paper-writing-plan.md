---
goal: 生物医药供应链GraphRAG论文完整写作计划（ESWA投稿）
version: 1.0
date_created: 2026-04-12
last_updated: 2026-04-12
owner: 孙凯枫 / Supervisor: Nektarios Oraiopoulos
status: 'In progress'
tags: [paper-writing, GraphRAG, pharmaceutical-supply-chain, dynamic-capabilities, ESWA]
---

# Introduction

![Status: In progress](https://img.shields.io/badge/status-In%20progress-yellow)

本计划覆盖从论文框架设计到最终投稿的完整写作流程。论文题目为《Beyond Time Series: Enhancing Dynamic Capabilities for Pharmaceutical Supply Chain Risk Management via GraphRAG and Agentic Simulation》（暂定），目标期刊为 **Expert Systems with Applications (ESWA)**，备选 Knowledge-Based Systems (KBS)。

**论文核心贡献（三条）：**
1. 异构医药知识图谱构建（结构化FDA/ChEMBL/RxNorm + 非结构化ICH/EMA监管文档）
2. 3-Stage GraphRAG（LLM替代MCTS做图游走，实现深层合规风险穿透）
3. LLM-Agent动态仿真层（级联风险推演 + 历史断供回测，验证Dynamic Capabilities三要素）

**理论框架：** Dynamic Capabilities (Sense–Seize–Transform, Teece 1997/2007)

---

## 1. Requirements & Constraints

- **REQ-001**: 论文全文英文写作，目标8,000–12,000 words（不含参考文献）
- **REQ-002**: 严格遵循 `.kiro/steering/academic-writing-guide.md` 中的ESWA写作规范
- **REQ-003**: 引用文献全部来自 Zotero「医药供应链知识图谱」集合（含补充子集合）及「化工知识图谱」中的RAG基础方法论文
- **REQ-004**: 所有实验数据已完成（GraphRAG消融实验 + Agent历史回测），写作时实验结果可直接填入
- **REQ-005**: 实验数据暂未完全整理时使用 `[PLACEHOLDER: XX.X%]` 格式占位
- **REQ-006**: 参考文献格式为 Elsevier Author-Year (Harvard style)，如 (Teece et al., 1997)
- **CON-001**: 不使用AI写作痕迹词汇（"delve into", "leverage", "it is worth noting"等，详见writing guide）
- **CON-002**: 每段4–8句，有明确主题句，数字结果必须量化（不写"significantly improves"）
- **CON-003**: 图表编号连续，图captions在图下，表captions在表上
- **GUD-001**: 写作顺序：Related Work → Methodology → Experiments → Introduction → Conclusion → Abstract（最后写）
- **GUD-002**: 使用 Sonnet 模型完成初稿，最终润色阶段切换至 Opus 模型
- **PAT-001**: 每章节完成后立即检查是否有 [PLACEHOLDER] 未填，实验数据到位后优先替换

---

## 2. Implementation Steps

### Phase 1: 论文框架设计与章节大纲

- GOAL-001: 在正式写作前，确定论文的完整章节结构、每章节的核心论点和关键图表规划

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-001 | 确定论文最终英文标题（含副标题），需体现GraphRAG + Agent + Dynamic Capabilities三个关键词 | ✅ | 2026-04-12 |
| TASK-002 | 设计完整的章节结构（6–7节），确定每节的核心论点和字数分配 | | |
| TASK-003 | 规划所有图表：框架图（Figure 1）、KG Schema图（Figure 2）、实验结果表（Table 1–4）、Agent仿真流程图 | | |
| TASK-004 | 确定Related Work的4个子主题和每个子主题的引用文献列表 | | |
| TASK-005 | 确定3条贡献的精确表述（含量化指标），写入Introduction贡献列表 | | |

---

### Phase 2: Related Work 写作

- GOAL-002: 完成约1,200字的Related Work，覆盖4个研究脉络，每节末尾明确指出与本文的差异

**建议章节结构：**
- 2.1 Supply Chain Risk Management and Pharmaceutical Vulnerabilities（供应链风险管理与医药领域特殊性）
- 2.2 Knowledge Graphs and GraphRAG for Domain-Specific Retrieval（知识图谱与GraphRAG方法演进）
- 2.3 LLM-Based Agent Simulation in Supply Chain Contexts（LLM智能体仿真）
- 2.4 Dynamic Capabilities Theory and AI-Augmented Decision Making（动态能力理论与AI结合）

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-006 | 写作 2.1：药品短缺背景、医药SC特殊性（路径依赖/GMP认证周期），引用Tucker & Daskin 2022, Cornelissen 2026, Aspinall 2026等 | ✅ | 2026-04-12 |
| TASK-007 | 写作 2.2：RAG演进（Lewis 2020 → HyDE → GraphRAG Edge 2024 → LightRAG → 本文），对比本文3-Stage架构的差异 | ✅ | 2026-04-12 |
| TASK-008 | 写作 2.3：ABM供应链仿真（传统ABM局限）→ LLM Agent仿真（Park 2023 Generative Agents, Proselkov 2023 ABM ripple effect），指出本文用GraphRAG驱动Agent的创新 | ✅ | 2026-04-12 |
| TASK-009 | 写作 2.4：Teece 1997/2007 Dynamic Capabilities理论 → 近年AI+DC结合研究（Quayson 2023, Kurrahman 2025）→ 指出缺乏计算机制验证的空白 | ✅ | 2026-04-12 |
| TASK-010 | 检查每节末尾是否有明确的gap sentence，整节引用数是否达到25–30篇 | ✅ | 2026-04-12 |

---

### Phase 3: Methodology 写作

- GOAL-003: 完成约2,500字的方法论章节，包含框架图、KG Schema、3-Stage GraphRAG详述、Agent仿真架构

**建议章节结构：**
- 4.1 Overall Framework（框架概述 + Figure 1）
- 4.2 Heterogeneous Pharmaceutical Knowledge Graph Construction（异构KG构建）
- 4.3 Three-Stage GraphRAG for Risk Signal Extraction（3阶段GraphRAG详述）
  - 4.3.1 Bottom-Up Semantic Retrieval
  - 4.3.2 Top-Down Structure Exploration
  - 4.3.3 Graph Walk with LLM-Guided Traversal（LLM替代MCTS的核心创新）
- 4.4 LLM-Agent Simulation for Cascade Risk Prediction（Agent仿真层）
  - 4.4.1 Agent Role Design（药厂/监管机构/分销商Agent定义）
  - 4.4.2 Simulation Protocol（沙盘运行机制）

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-011 | 写作 4.1：整体框架描述，引用Figure 1（需提前准备框架图），说明三大模块的串联关系 | ✅ | 2026-04-12 |
| TASK-012 | 写作 4.2：KG构建——数据来源（FDA/ChEMBL/RxNorm/ICH/EMA），实体类型（Drug/API/Manufacturer/Regulator），关系类型，Neo4j Schema，节点/边统计（7,480+节点） | ✅ | 2026-04-12 |
| TASK-013 | 写作 4.3.1–4.3.2：Bottom-Up（向量检索+HyDE+Sibling Expansion）和Top-Down（目录导航+批量读取）两个策略 | ✅ | 2026-04-12 |
| TASK-014 | 写作 4.3.3：**Graph Walk核心创新**——LLM替代MCTS做图游走，详述决策机制、剪枝策略、与化工论文的区别（医药图谱的异构性、监管文档的特殊处理） | ✅ | 2026-04-12 |
| TASK-015 | 写作 4.4：Agent仿真层——角色设计（赋予各Agent不同权限和信息视野）、仿真协议（历史断供场景冷启动）、GraphRAG接口调用机制 | ✅ | 2026-04-12 |
| TASK-016 | 检查所有公式是否编号，所有图表是否有引用，LLM替代MCTS的技术细节是否足够清晰可复现 | ✅ | 2026-04-12 |

---

### Phase 4: Experiments 写作

- GOAL-004: 完成约2,200字的实验章节，包含两个实验：GraphRAG消融实验 + Agent历史回测

**建议章节结构：**
- 5.1 Experimental Setup（数据集、baseline方法、评估指标）
- 5.2 Experiment 1: Ablation Study on 3-Stage GraphRAG（消融实验）
- 5.3 Experiment 2: Historical Replication via Agent Simulation（历史回测）
- 5.4 Discussion（为什么work？失败案例？计算开销？）

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-017 | 写作 5.1：数据集描述（FDA Shortage Database + ICH/EMA文档统计）、baseline方法（Naive RAG/GraphRAG Edge/LightRAG等6个基线）、评估指标定义（Recall@K/Precision/MRR/短缺预测准确率） | ✅ | 2026-04-12 |
| TASK-018 | 写作 5.2：消融实验——逐阶段去除（无Graph Walk/无Top-Down/无HyDE），对比3-Stage完整方法，表格展示（Table 2），统计显著性检验（p<0.01） | ✅ | 2026-04-12 |
| TASK-019 | 写作 5.3：历史回测——选取FDA历史上1–2个真实断供案例，冷启动Agent仿真，对比"模拟短缺深度"与"历史实际短缺持续期"，ANOVA方差分析 | ✅ | 2026-04-12 |
| TASK-020 | 写作 5.4：Discussion——解释为什么3-Stage优于baseline、Agent仿真的局限性（LLM决策的随机性、时滞建模的简化）、计算开销分析 | ✅ | 2026-04-12 |
| TASK-021 | 替换所有 [PLACEHOLDER] 为实验真实数据，确认Table和Figure编号连续 | | |

---

### Phase 5: Introduction 写作

- GOAL-005: 完成约1,000字的Introduction，4–5段结构，贡献列表精确量化

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-022 | 写作 Paragraph 1：医药供应链断供的现实背景（引用具体数据，如FDA短缺数据库的统计），突出路径依赖和模糊性问题 | ✅ | 2026-04-12 |
| TASK-023 | 写作 Paragraph 2：现有方法的三类局限——(1)时序模型无法处理无历史数据的模糊事件 (2)静态KG缺乏非结构化文档穿透 (3)传统ABM依赖人工设定转移概率 | ✅ | 2026-04-12 |
| TASK-024 | 写作 Paragraph 3：提出本文框架（命名+缩写），简要描述三个组件如何对应解决三类局限 | ✅ | 2026-04-12 |
| TASK-025 | 写作 Paragraph 4：贡献列表（3–4条，每条含量化指标，格式参见writing guide） | ✅ | 2026-04-12 |
| TASK-026 | 写作 Paragraph 5：论文组织说明（固定句式："The remainder of this paper is organized as follows..."） | ✅ | 2026-04-12 |

---

### Phase 6: Conclusion + Abstract 写作

- GOAL-006: 完成Conclusion（400字）和Abstract（200字），Abstract最后写，需包含定量结果

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-027 | 写作 Conclusion Paragraph 1：总结问题+方法+关键量化结果（复用Abstract中最重要的数字） | ✅ | 2026-04-12 |
| TASK-028 | 写作 Conclusion Paragraph 2：局限性（2–3条，直接陈述，不使用"may"等不确定表述） | ✅ | 2026-04-12 |
| TASK-029 | 写作 Conclusion Paragraph 3：未来工作（2–3条，与局限性直接对应） | ✅ | 2026-04-12 |
| TASK-030 | 最后写Abstract：严格按照5句弧（背景→差距→方案→量化结果→意义），150–250字，必须包含具体数字 | ✅ | 2026-04-12 |

---

### Phase 7: 润色与提交准备（切换Opus模型）

- GOAL-007: 完成全文润色、引用核查、格式整理，生成提交版本

| Task | Description | Completed | Date |
|------|-------------|-----------|------|
| TASK-031 | 运行 `/stop-slop` skill：逐段扫描去除AI写作痕迹词汇 | | |
| TASK-032 | 运行 `/ml-paper-writing` skill：按ESWA标准检查论文质量（贡献清晰度、实验充分性、related work覆盖度） | | |
| TASK-033 | 运行 `/citation-management` skill：核查所有引用的准确性，生成完整BibTeX文件 | | |
| TASK-034 | 检查全文[PLACEHOLDER]是否全部替换；图表编号是否连续；所有缩写是否在首次出现时定义 | | |
| TASK-035 | 字数统计：确认正文8,000–12,000 words；关键词5–6个；摘要150–250 words | | |
| TASK-036 | 格式转换：Markdown → Word（中文版给老师审阅）；Markdown → LaTeX（英文版投稿） | | |
| TASK-037 | 最终提交前检查清单：参考文献格式（Elsevier Harvard）、图片分辨率（≥300dpi）、Cover Letter撰写 | | |

---

## 3. Alternatives

- **ALT-001**: 先写Introduction再写Related Work——不推荐，Related Work需要先确定引用范围才能写出精确的贡献点
- **ALT-002**: 投KBS作为首选而非ESWA——KBS更偏知识图谱，但本文的Agent仿真和Dynamic Capabilities理论贡献在ESWA受众更广；若ESWA一轮拒稿再转KBS
- **ALT-003**: 同时写中英文版本——不推荐，中文版作为给导师审阅的参考，等英文初稿定稿后用pandoc转换即可

---

## 4. Dependencies

- **DEP-001**: Lewis et al. (2020) RAG原论文——仍缺失，需在TASK-007前补充到Zotero（Google Scholar搜 `Lewis 2020 Retrieval-Augmented Generation NeurIPS`）
- **DEP-002**: 论文框架图（Figure 1）——需要在TASK-011前准备好，建议用draw.io绘制
- **DEP-003**: 实验数据——GraphRAG消融实验结果和Agent历史回测数值，TASK-018/TASK-019依赖此数据；未完成时用[PLACEHOLDER]
- **DEP-004**: Teece et al. (1997) Zotero条目元数据不完整（年份/期刊缺失）——补全前引用可能出错，需手动填入：Strategic Management Journal, 18(7), 509–533

---

## 5. Files

- **FILE-001**: `D:/Projects/financial knowledge graph/plan/paper-writing-plan.md` — 本实施计划文件
- **FILE-002**: `D:/Projects/financial knowledge graph/.kiro/steering/academic-writing-guide.md` — 写作规范指南（Kiro自动加载）
- **FILE-003**: `D:/Projects/financial knowledge graph/sections/01_abstract.md` — 摘要章节（待创建）
- **FILE-004**: `D:/Projects/financial knowledge graph/sections/02_introduction.md` — 引言章节（待创建）
- **FILE-005**: `D:/Projects/financial knowledge graph/sections/03_related_work.md` — 相关工作章节（待创建）
- **FILE-006**: `D:/Projects/financial knowledge graph/sections/04_methodology.md` — 方法章节（待创建）
- **FILE-007**: `D:/Projects/financial knowledge graph/sections/05_experiments.md` — 实验章节（待创建）
- **FILE-008**: `D:/Projects/financial knowledge graph/sections/06_conclusion.md` — 结论章节（待创建）
- **FILE-009**: `D:/Projects/financial knowledge graph/docs/literature-review-summary.md` — 文献综述摘要（供写作参考，待生成）
- **FILE-010**: `D:/Projects/financial knowledge graph/references/references.bib` — BibTeX参考文献文件（Phase 7生成）

---

## 6. Testing

- **TEST-001**: Related Work完成后——检查引用总数是否在25–30篇范围内，每小节是否有明确的gap sentence
- **TEST-002**: Methodology完成后——检查LLM替代MCTS的机制描述是否足够清晰（能让同行复现）；图谱Schema是否完整
- **TEST-003**: Experiments完成后——检查Table 1（主实验对比）中是否标注统计显著性（*p<0.01）；消融实验变量是否互相独立
- **TEST-004**: 全文完成后——运行stop-slop检查；用ml-paper-writing评估论文质量
- **TEST-005**: 投稿前——验证所有[PLACEHOLDER]已替换；字数符合要求；Cover Letter已准备

---

## 7. Risks & Assumptions

- **RISK-001**: 实验数据尚未完全整理——GraphRAG消融实验和Agent回测的量化指标若未最终确定，Experiments章节和Abstract将无法完成；缓解措施：用[PLACEHOLDER]先行写作，数据到位后优先替换
- **RISK-002**: Lewis et al. (2020) RAG原论文仍缺失——若Related Work写作时仍未补充，暂时略去该引用，用RAG Survey (Kamalipour et al., 2026)替代；但投稿前必须补充
- **RISK-003**: Teece 1997元数据不完整——引用时手动核对，期刊：Strategic Management Journal, 18(7), 509–533, 1997
- **RISK-004**: Agent仿真的可复现性——LLM决策存在随机性，历史回测结果可能因模型版本不同而有差异；需在Section 5.1中明确声明随机种子和模型版本（如Qwen3-72B）
- **ASSUMPTION-001**: 实验已全部完成，论文写作阶段不再进行新实验，仅整理和呈现已有结果
- **ASSUMPTION-002**: 目标期刊ESWA，审稿周期约3–6个月，写作完成后直接通过Elsevier投稿系统提交
- **ASSUMPTION-003**: 导师Nektarios Oraiopoulos会在投稿前审阅论文，需为导师审阅预留2–3周时间

---

## 8. Related Specifications / Further Reading

- [写作规范指南](D:/Projects/financial knowledge graph/.kiro/steering/academic-writing-guide.md)
- [研究计划 (Research Proposal)](D:/Projects/financial knowledge graph/研究计划.md)
- [论文写作工作流总结](D:/Projects/知识图谱论文/docs/paper-writing-workflow.md)
- [上篇化工论文初稿（写作范式参考）](D:/Projects/知识图谱论文/draft_chinese.md)
- [ESWA投稿指南](https://www.elsevier.com/journals/expert-systems-with-applications/0957-4174/guide-for-authors)
