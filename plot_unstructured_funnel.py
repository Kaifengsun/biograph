"""
Unstructured Data Processing Pipeline — Funnel Chart
Run: python plot_unstructured_funnel.py
Output: charts/fig7_unstructured_pipeline.png
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as FancyArrowPatch
import numpy as np
from matplotlib import rcParams

rcParams['font.family'] = ['Arial', 'DejaVu Sans', 'sans-serif']
rcParams['axes.spines.top']   = False
rcParams['axes.spines.right'] = False
rcParams['axes.spines.left']  = False
rcParams['figure.dpi'] = 150

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'charts')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Real data from workspace scan ──────────────────────────────────────────
STAGES = [
    {
        'label':    'Raw Regulatory\nDocuments',
        'sublabel': 'ICH Q-series · FDA CGMP · EMA · WHO',
        'value':    34,
        'unit':     'PDF Files',
        'color':    '#3b82f6',   # blue
        'width':    1.00,
    },
    {
        'label':    'Parsed Text\n(MinerU OCR)',
        'sublabel': 'Markdown extraction · Layout preservation',
        'value':    412_000,
        'unit':     'Tokens',
        'color':    '#8b5cf6',   # purple
        'width':    0.80,
    },
    {
        'label':    'Hierarchical\nSemantic Chunks',
        'sublabel': 'Multi-level: Section → Paragraph → Clause',
        'value':    2_741,
        'unit':     'Chunks',
        'color':    '#f59e0b',   # amber
        'width':    0.60,
    },
    {
        'label':    'Vectorized\nEmbeddings (FAISS)',
        'sublabel': 'tencent/Youtu-Embedding · 2048-dim · cosine',
        'value':    7_835,
        'unit':     'Vectors',
        'color':    '#10b981',   # green
        'width':    0.42,
    },
]

# Labels shown beside each inter-stage arrow (3 transitions for 4 stages)
ARROW_LABELS = [
    'PDF Parsing & OCR\n(MinerU)',
    'Hierarchical Chunking\n(Custom Code)',
    'HyDE + Entity\nExpansion',
]

BAR_HEIGHT = 0.52
GAP        = 0.28
N          = len(STAGES)
fig_h      = N * (BAR_HEIGHT + GAP) + 1.4

fig, ax = plt.subplots(figsize=(10, fig_h))

# y positions (top → bottom)
ys = [N - i - 1 for i in range(N)]
max_bar_w = 8.5   # data-units wide at scale 1.0

for i, (stage, y) in enumerate(zip(STAGES, ys)):
    bar_w = max_bar_w * stage['width']
    left  = (max_bar_w - bar_w) / 2      # center each bar

    # Bar
    rect = plt.Rectangle(
        (left, y - BAR_HEIGHT / 2),
        bar_w, BAR_HEIGHT,
        facecolor=stage['color'],
        alpha=0.88,
        zorder=3,
    )
    ax.add_patch(rect)

    # Value label — inside bar, left-aligned
    ax.text(
        left + 0.22,
        y + 0.07,
        f"{stage['value']:,}",
        va='center', ha='left',
        fontsize=20, fontweight='bold',
        color='white', zorder=4,
    )
    ax.text(
        left + 0.22,
        y - 0.13,
        stage['unit'],
        va='top', ha='left',
        fontsize=10,
        color='white', alpha=0.85, zorder=4,
    )

    # Stage label — right of bar
    ax.text(
        left + bar_w + 0.2,
        y + 0.06,
        stage['label'],
        va='center', ha='left',
        fontsize=11, fontweight='bold',
        color='#1e293b', zorder=4,
    )
    ax.text(
        left + bar_w + 0.2,
        y - 0.18,
        stage['sublabel'],
        va='top', ha='left',
        fontsize=8.5,
        color='#64748b', zorder=4,
    )

    # Connecting arrow to next bar (skip last)
    if i < N - 1:
        arrow_x = max_bar_w / 2  # center x
        y_top   = y - BAR_HEIGHT / 2 - 0.02
        y_bot   = ys[i + 1] + BAR_HEIGHT / 2 + 0.02
        y_mid   = (y_top + y_bot) / 2

        ax.annotate(
            '',
            xy=(arrow_x, y_bot),
            xytext=(arrow_x, y_top),
            arrowprops=dict(
                arrowstyle='-|>',
                color='#cbd5e1',
                lw=1.6,
                mutation_scale=14,
            ),
            zorder=2,
        )

        # Arrow label — left of arrow, italic grey
        ax.text(
            arrow_x - 0.3,
            y_mid,
            ARROW_LABELS[i],
            va='center', ha='right',
            fontsize=8.5,
            color='#94a3b8',
            style='italic',
            zorder=5,
        )

    # Step badge
    ax.text(
        left - 0.1,
        y,
        f'Step {i + 1}',
        va='center', ha='right',
        fontsize=9, fontweight='bold',
        color=stage['color'],
    )

# Grid
ax.set_xlim(-1.0, max_bar_w + 4.5)
ax.set_ylim(-BAR_HEIGHT, N - 1 + BAR_HEIGHT + 0.2)
ax.set_xticks([])
ax.set_yticks([])
ax.spines['bottom'].set_visible(False)

# Title
fig.text(
    0.50, 0.97,
    'Unstructured Data Processing Pipeline',
    ha='center', va='top',
    fontsize=15, fontweight='bold',
    color='#0f172a',
)
fig.text(
    0.50, 0.935,
    'Regulatory Text to RAG Chunks  ·  PharmGraphRAG',
    ha='center', va='top',
    fontsize=10,
    color='#64748b',
)

plt.subplots_adjust(left=0.04, right=0.98, top=0.89, bottom=0.04)

out = os.path.join(OUTPUT_DIR, 'fig7_unstructured_pipeline_final.png')
plt.savefig(out, dpi=300, bbox_inches='tight')
plt.close()
print(f'[OK] Saved: {out}')
