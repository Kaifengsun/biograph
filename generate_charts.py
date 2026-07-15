"""
PharmGraphRAG 实验结果图表生成脚本
运行: python generate_charts.py
输出: charts/ 目录下的PNG文件，直接插入PPT使用
"""

import os
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib import rcParams

# ── 字体与样式 ──────────────────────────────────────────────────────────────
rcParams['font.family'] = ['DejaVu Sans', 'Arial', 'sans-serif']
rcParams['axes.spines.top'] = False
rcParams['axes.spines.right'] = False
rcParams['figure.dpi'] = 150
rcParams['savefig.dpi'] = 200
rcParams['savefig.bbox'] = 'tight'

# 配色方案
C_HIST    = '#94a3b8'   # 灰蓝（历史数据）
C_SIM     = '#3b82f6'   # 蓝（仿真）
C_SUCCESS = '#22c55e'   # 绿
C_DANGER  = '#ef4444'   # 红
C_WARN    = '#f59e0b'   # 黄
C_NEUTRAL = '#64748b'   # 中性灰

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'charts')
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ════════════════════════════════════════════════════════════════
# 图1：SST 重现率对比（PharmGraphRAG vs Pure LLM）
# ════════════════════════════════════════════════════════════════
def chart_sst_reproduction():
    fig, ax = plt.subplots(figsize=(7, 3.2))

    methods = ['PharmGraphRAG\n(Ours)', 'Pure LLM\nBaseline']
    values  = [33, 0]
    colors  = [C_SUCCESS, C_DANGER]

    bars = ax.barh(methods, values, color=colors, height=0.45, zorder=3)

    for bar, val in zip(bars, values):
        if val > 0:
            ax.text(val + 0.8, bar.get_y() + bar.get_height() / 2,
                    f'{val}%', va='center', fontsize=13, fontweight='bold',
                    color=C_SUCCESS)
        else:
            ax.text(val + 0.8, bar.get_y() + bar.get_height() / 2,
                    '0%', va='center', fontsize=13, color=C_DANGER)

    ax.set_xlim(0, 50)
    ax.set_xlabel('SST Reproduction Rate (%)', fontsize=11)
    ax.set_title('SST Sequence Reproduction Rate\n(Sense → Seize → Transform, ±2 week tolerance)',
                 fontsize=12, fontweight='bold', pad=12)
    ax.axvline(x=0, color='#e2e8f0', linewidth=1)
    ax.grid(axis='x', linestyle='--', alpha=0.4, zorder=0)
    ax.set_axisbelow(True)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig1_sst_reproduction.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 图2：PSC 每事件得分（峰值严重程度相关性）
# ════════════════════════════════════════════════════════════════
def chart_psc_per_event():
    fig, ax = plt.subplots(figsize=(7, 3.8))

    events = ['E-01\nHurricane\nMaria (2017)', 'E-02\nValsartan\nNDMA (2018)', 'E-03\nIndia COVID\nRestriction (2020)']
    psc    = [0.834, 0.876, 0.0]
    colors = [C_SUCCESS, C_SUCCESS, C_DANGER]

    bars = ax.bar(events, psc, color=colors, width=0.45, zorder=3)

    for bar, val in zip(bars, psc):
        ax.text(bar.get_x() + bar.get_width() / 2, val + 0.02,
                f'{val:.3f}', ha='center', fontsize=12, fontweight='bold')

    ax.set_ylim(0, 1.1)
    ax.set_ylabel('Pearson Correlation (PSC)', fontsize=11)
    ax.set_title('Peak Severity Correlation (PSC) per Event\n(Simulated vs Historical weekly shortage severity)',
                 fontsize=12, fontweight='bold', pad=12)
    ax.axhline(y=0.8, color=C_SUCCESS, linestyle='--', alpha=0.5, linewidth=1, label='Good threshold (0.80)')
    ax.grid(axis='y', linestyle='--', alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    ax.legend(fontsize=9)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig2_psc_per_event.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 图3：E-01 短缺严重程度轨迹（历史 vs 仿真）
# ════════════════════════════════════════════════════════════════
def chart_severity_e01():
    historical = [
        0.0, 0.15, 0.28, 0.38, 0.42, 0.42, 0.41, 0.40,
        0.40, 0.39, 0.38, 0.38, 0.37, 0.36, 0.35, 0.34,
        0.33, 0.32, 0.31, 0.30, 0.29, 0.28, 0.27, 0.26,
        0.24, 0.22, 0.20, 0.18, 0.16, 0.14, 0.12, 0.10,
        0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02,
        0.01, 0.01, 0.00, 0.00,
    ]
    simulated_raw = [
        0.0, 0.0, 0.0, 0.172, 0.561, 0.534, 0.506, 0.478,
        0.36, 0.36, 0.355, 0.327, 0.3, 0.272, 0.244, 0.216,
        0.194, 0.171, 0.148, 0.125, 0.103, 0.08, 0.057,
        0.035, 0.012, 0.029, 0.006, 0.0, 0.0,
    ]
    simulated = simulated_raw + [0.0] * (44 - len(simulated_raw))

    weeks = list(range(1, 45))
    fig, ax = plt.subplots(figsize=(8, 4))

    ax.fill_between(weeks, historical, alpha=0.15, color=C_HIST)
    ax.plot(weeks, historical, color=C_HIST, linewidth=2, label='Historical (FDA Database)', marker='o', markersize=2)
    ax.plot(weeks, simulated,  color=C_SIM,  linewidth=2, label='PharmGraphRAG Simulation', marker='s', markersize=2)

    # SST 阶段标注
    for week, label, color in [(1, 'Sense', C_NEUTRAL), (3, 'Seize', C_WARN), (8, 'Transform', C_SUCCESS)]:
        ax.axvline(x=week, linestyle=':', color=color, alpha=0.7, linewidth=1.5)
        ax.text(week + 0.3, 0.56, label, fontsize=8, color=color, rotation=90, va='top')

    ax.set_xlim(1, 44)
    ax.set_ylim(-0.02, 0.65)
    ax.set_xlabel('Simulation Week', fontsize=11)
    ax.set_ylabel('Shortage Severity\n(Fraction of Unmet Demand)', fontsize=11)
    ax.set_title('E-01 · Hurricane Maria IV Saline Shortage (2017–2018)\nPSC = 0.834  |  SST Reproduced  |  SDE = 22 weeks',
                 fontsize=11, fontweight='bold', pad=10)
    ax.legend(fontsize=10, loc='upper right')
    ax.grid(linestyle='--', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig3_severity_e01.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 图4：E-02 短缺严重程度轨迹（历史 vs 仿真）
# ════════════════════════════════════════════════════════════════
def chart_severity_e02():
    historical = [
        0.0, 0.10, 0.20, 0.32, 0.35, 0.35, 0.34, 0.33,
        0.32, 0.31, 0.30, 0.29, 0.28, 0.27, 0.26, 0.25,
        0.24, 0.23, 0.22, 0.21, 0.20, 0.18, 0.16, 0.14,
        0.12, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03,
        0.02, 0.01, 0.01, 0.00,
    ]
    simulated_raw = [
        0.0, 0.0, 0.12, 0.695, 0.656, 0.618, 0.579, 0.54,
        0.501, 0.463, 0.424, 0.385, 0.307, 0.268, 0.229, 0.19,
        0.157, 0.123, 0.089, 0.055, 0.022, 0.028, 0.0, 0.0, 0.0,
    ]
    simulated = simulated_raw + [0.0] * (36 - len(simulated_raw))

    weeks = list(range(1, 37))
    fig, ax = plt.subplots(figsize=(8, 4))

    ax.fill_between(weeks, historical, alpha=0.15, color=C_HIST)
    ax.plot(weeks, historical, color=C_HIST, linewidth=2, label='Historical (EMA/FDA)', marker='o', markersize=2)
    ax.plot(weeks, simulated,  color=C_SIM,  linewidth=2, label='PharmGraphRAG Simulation', marker='s', markersize=2)

    for week, label, color in [(1, 'Sense', C_NEUTRAL), (4, 'Seize', C_WARN), (12, 'Transform', C_SUCCESS)]:
        ax.axvline(x=week, linestyle=':', color=color, alpha=0.7, linewidth=1.5)
        ax.text(week + 0.3, 0.72, label, fontsize=8, color=color, rotation=90, va='top')

    ax.set_xlim(1, 36)
    ax.set_ylim(-0.02, 0.82)
    ax.set_xlabel('Simulation Week', fontsize=11)
    ax.set_ylabel('Shortage Severity\n(Fraction of Unmet Demand)', fontsize=11)
    ax.set_title('E-02 · Valsartan NDMA Contamination Recall (2018–2019)\nPSC = 0.876  |  Partial SST  |  SDE = 16 weeks',
                 fontsize=11, fontweight='bold', pad=10)
    ax.legend(fontsize=10, loc='upper right')
    ax.grid(linestyle='--', alpha=0.3)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig4_severity_e02.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 图5：知识图谱节点类型构成（甜甜圈图）
# ════════════════════════════════════════════════════════════════
def chart_kg_composition():
    labels = ['Drug', 'Manufacturer', 'API / Compound', 'Regulation', 'ShortageEvent', 'Country']
    sizes  = [2847, 1432, 1198, 1124, 512, 367]
    colors = ['#3b82f6', '#8b5cf6', '#06b6d4', '#f59e0b', '#ef4444', '#22c55e']

    fig, ax = plt.subplots(figsize=(7, 5))
    wedges, texts, autotexts = ax.pie(
        sizes,
        labels=None,
        colors=colors,
        autopct='%1.1f%%',
        pctdistance=0.78,
        startangle=140,
        wedgeprops=dict(width=0.55, edgecolor='white', linewidth=2),
    )
    for at in autotexts:
        at.set_fontsize(9)
        at.set_color('white')
        at.set_fontweight('bold')

    legend_labels = [f'{l}  ({s:,})' for l, s in zip(labels, sizes)]
    ax.legend(wedges, legend_labels, loc='lower center', bbox_to_anchor=(0.5, -0.18),
              ncol=2, fontsize=9, frameon=False)

    ax.text(0, 0, '7,480\nnodes', ha='center', va='center', fontsize=12,
            fontweight='bold', color='#1e293b')
    ax.set_title('Knowledge Graph Node Composition\n(Heterogeneous Pharmaceutical KG)',
                 fontsize=12, fontweight='bold', pad=12)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig5_kg_composition.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 图6：GraphRAG 三阶段流水线统计（水平条形图）
# ════════════════════════════════════════════════════════════════
def chart_pipeline_stats():
    stages = ['Stage 3\nLLM Graph Walk', 'Stage 2\nKG Structure Traversal', 'Stage 1\nSemantic Retrieval']
    values = [10, 160, 25]
    units  = ['Risk Paths', 'KG Relations', 'Text Chunks']
    colors = [C_SUCCESS, C_WARN, C_SIM]

    fig, ax = plt.subplots(figsize=(7, 3.5))
    bars = ax.barh(stages, values, color=colors, height=0.4, zorder=3)

    for bar, val, unit in zip(bars, values, units):
        ax.text(val + 1.5, bar.get_y() + bar.get_height() / 2,
                f'{val}  {unit}', va='center', fontsize=11, fontweight='bold')

    ax.set_xlim(0, 220)
    ax.set_xlabel('Count', fontsize=11)
    ax.set_title('GraphRAG Three-Stage Retrieval Pipeline\n(Per query statistics — representative example)',
                 fontsize=12, fontweight='bold', pad=12)
    ax.grid(axis='x', linestyle='--', alpha=0.4, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis='y', labelsize=10)

    plt.tight_layout()
    path = os.path.join(OUTPUT_DIR, 'fig6_pipeline_stats.png')
    plt.savefig(path)
    plt.close()
    print(f'[OK] {path}')


# ════════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════════
if __name__ == '__main__':
    print('Generating PharmGraphRAG experiment charts...\n')
    chart_sst_reproduction()
    chart_psc_per_event()
    chart_severity_e01()
    chart_severity_e02()
    chart_kg_composition()
    chart_pipeline_stats()
    print(f'\nDone! All charts saved to: {OUTPUT_DIR}')
    print('Files:')
    for f in sorted(os.listdir(OUTPUT_DIR)):
        if f.endswith('.png'):
            size = os.path.getsize(os.path.join(OUTPUT_DIR, f))
            print(f'  {f}  ({size // 1024} KB)')
