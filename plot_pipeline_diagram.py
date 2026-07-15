"""
PharmGraphRAG Pipeline Architecture Diagram
Corrected layout: S1 (top) → S2 + S3 (parallel) → Agentic Execution
Run: python plot_pipeline_diagram.py
Output: charts/fig8_pipeline_diagram.png
"""

import os
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from matplotlib import rcParams

rcParams['font.family'] = ['Arial', 'DejaVu Sans', 'sans-serif']

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), 'charts')
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── Color palette (matching the PPT image style) ─────────────────────────────
C_BOX_FILL    = '#dbeafe'   # light blue fill
C_BOX_EDGE    = '#93c5fd'   # blue border
C_S2_FILL     = '#bfdbfe'   # slightly deeper blue for S2 (emphasis)
C_TITLE       = '#1e3a5f'   # dark navy
C_ICON        = '#3b82f6'   # medium blue for icons
C_BULLET      = '#374151'   # dark gray text
C_ARROW       = '#6b7280'   # gray arrows
C_AGENTIC_BG  = '#f0f9ff'   # very light blue for bottom bar
C_AGENTIC_EDG = '#7dd3fc'   # border for bottom bar
C_WHITE       = '#ffffff'

fig, ax = plt.subplots(figsize=(13, 9.5))
ax.set_xlim(0, 13)
ax.set_ylim(0, 9.5)
ax.axis('off')
fig.patch.set_facecolor(C_WHITE)


# ════════════════════════════════════════════════════════
#  Helper functions
# ════════════════════════════════════════════════════════

def rounded_box(ax, x, y, w, h, fill, edge, lw=1.8, radius=0.25):
    box = FancyBboxPatch(
        (x, y), w, h,
        boxstyle=f"round,pad={radius}",
        facecolor=fill, edgecolor=edge, linewidth=lw,
        zorder=3,
    )
    ax.add_patch(box)

def arrow(ax, x1, y1, x2, y2, color=C_ARROW):
    ax.annotate(
        '', xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(
            arrowstyle='-|>',
            color=color,
            lw=2.0,
            mutation_scale=18,
        ),
        zorder=4,
    )

def draw_network_icon(ax, cx, cy, r=0.18, lw=1.6):
    """Bottom-up: layered stack / semantic network"""
    nodes = [(-0.45, 0.35), (0, 0.45), (0.45, 0.35),
             (-0.25, 0.0),  (0.25, 0.0),
             (0, -0.38)]
    edges = [(0,1),(1,2),(0,3),(1,3),(1,4),(2,4),(3,5),(4,5)]
    for x0,y0 in nodes:
        ax.add_patch(plt.Circle((cx+x0, cy+y0), r, color=C_ICON, zorder=5))
    for i,j in edges:
        x0,y0 = nodes[i]; x1,y1 = nodes[j]
        ax.plot([cx+x0, cx+x1], [cy+y0, cy+y1],
                color=C_ICON, lw=lw, zorder=4, alpha=0.7)

def draw_topdown_icon(ax, cx, cy, r=0.18):
    """Top-down: hierarchy / person with graph"""
    # Person head
    ax.add_patch(plt.Circle((cx, cy+0.38), r*1.15, color=C_ICON, zorder=5))
    # Body
    body = FancyBboxPatch((cx-0.22, cy-0.1), 0.44, 0.40,
        boxstyle="round,pad=0.04", facecolor=C_ICON, zorder=5)
    ax.add_patch(body)
    # KG lines below person
    for dx in [-0.35, 0, 0.35]:
        ax.add_patch(plt.Circle((cx+dx, cy-0.45), r*0.8, color=C_ICON, zorder=5, alpha=0.75))
    ax.plot([cx, cx-0.35], [cy-0.1, cy-0.35], color=C_ICON, lw=1.6, zorder=4, alpha=0.7)
    ax.plot([cx, cx],      [cy-0.1, cy-0.35], color=C_ICON, lw=1.6, zorder=4, alpha=0.7)
    ax.plot([cx, cx+0.35], [cy-0.1, cy-0.35], color=C_ICON, lw=1.6, zorder=4, alpha=0.7)

def draw_tree_icon(ax, cx, cy, r=0.17):
    """Graph walk: tree / graph traversal"""
    # Root
    ax.add_patch(plt.Circle((cx, cy+0.35), r*1.2, color=C_ICON, zorder=5))
    # Level 2
    for dx in [-0.38, 0.38]:
        ax.add_patch(plt.Circle((cx+dx, cy-0.05), r, color=C_ICON, zorder=5))
        ax.plot([cx, cx+dx], [cy+0.17, cy+0.05],
                color=C_ICON, lw=1.6, zorder=4, alpha=0.8)
    # Level 3
    for dx in [-0.62, -0.18, 0.18, 0.62]:
        ax.add_patch(plt.Circle((cx+dx, cy-0.45), r*0.85,
                                color=C_ICON, alpha=0.75, zorder=5))
    ax.plot([cx-0.38, cx-0.62], [cy-0.17, cy-0.35], color=C_ICON, lw=1.4, zorder=4, alpha=0.7)
    ax.plot([cx-0.38, cx-0.18], [cy-0.17, cy-0.35], color=C_ICON, lw=1.4, zorder=4, alpha=0.7)
    ax.plot([cx+0.38, cx+0.18], [cy-0.17, cy-0.35], color=C_ICON, lw=1.4, zorder=4, alpha=0.7)
    ax.plot([cx+0.38, cx+0.62], [cy-0.17, cy-0.35], color=C_ICON, lw=1.4, zorder=4, alpha=0.7)


# ════════════════════════════════════════════════════════
#  Title
# ════════════════════════════════════════════════════════
ax.text(6.5, 9.1,
        'Core Algorithm Engine: PharmGraphRAG Pipeline',
        ha='center', va='center',
        fontsize=17, fontweight='bold', color=C_TITLE, zorder=6)


# ════════════════════════════════════════════════════════
#  S1 Box — top center, full-ish width
# ════════════════════════════════════════════════════════
S1_X, S1_Y, S1_W, S1_H = 3.3, 5.8, 6.4, 2.8
rounded_box(ax, S1_X, S1_Y, S1_W, S1_H, C_BOX_FILL, C_BOX_EDGE)

# S1 text
ax.text(S1_X+0.35, S1_Y+S1_H-0.42, 'S1:', fontsize=12, fontweight='bold',
        color=C_TITLE, va='top', zorder=6)
ax.text(S1_X+0.35, S1_Y+S1_H-0.82, 'Bottom-Up Semantic Retrieval',
        fontsize=13.5, fontweight='bold', color=C_TITLE, va='top', zorder=6)

# S1 icon (right side of box)
draw_network_icon(ax, S1_X + S1_W - 1.1, S1_Y + S1_H/2 - 0.1)

# S1 bullets
bullets_s1 = [
    'Always-on hybrid recall (FAISS + entity + text)',
    'Foundational semantic accuracy layer',
    'Vector similarity search + HyDE expansion',
    'Sibling chunk auto-expansion',
]
for j, b in enumerate(bullets_s1):
    ax.text(S1_X+0.5, S1_Y+1.65-j*0.42, f'\u2022 {b}',
            fontsize=9.5, color=C_BULLET, va='top', zorder=6)


# ════════════════════════════════════════════════════════
#  Fan-out arrow: S1 → S2 and S1 → S3
# ════════════════════════════════════════════════════════
# Vertical stem down from S1 center
stem_x = 6.5
stem_y_top = S1_Y         # bottom of S1
stem_y_mid = 5.1          # branch point
ax.plot([stem_x, stem_x], [stem_y_top, stem_y_mid],
        color=C_ARROW, lw=2.2, zorder=4)

# Horizontal branch line
branch_y = stem_y_mid
S2_CX = 2.8   # center x of S2 box
S3_CX = 10.2  # center x of S3 box

ax.plot([S2_CX, S3_CX], [branch_y, branch_y],
        color=C_ARROW, lw=2.2, zorder=4)

# Arrow tips pointing into S2 and S3
S2_TOP_Y = 4.7
S3_TOP_Y = 4.7
arrow(ax, S2_CX, branch_y, S2_CX, S2_TOP_Y + 0.02)
arrow(ax, S3_CX, branch_y, S3_CX, S3_TOP_Y + 0.02)


# ════════════════════════════════════════════════════════
#  S2 Box — bottom left
# ════════════════════════════════════════════════════════
S2_X, S2_Y, S2_W, S2_H = 0.4, 1.8, 4.8, 2.9
rounded_box(ax, S2_X, S2_Y, S2_W, S2_H, C_S2_FILL, C_BOX_EDGE, lw=2.2)

ax.text(S2_X+0.35, S2_Y+S2_H-0.42, 'S2:', fontsize=12, fontweight='bold',
        color=C_TITLE, va='top', zorder=6)
ax.text(S2_X+0.35, S2_Y+S2_H-0.82, 'Top-Down Structural',
        fontsize=13, fontweight='bold', color=C_TITLE, va='top', zorder=6)
ax.text(S2_X+0.35, S2_Y+S2_H-1.18, 'Navigation',
        fontsize=13, fontweight='bold', color=C_TITLE, va='top', zorder=6)

draw_topdown_icon(ax, S2_X + S2_W - 1.0, S2_Y + S2_H/2 - 0.1)

bullets_s2 = [
    'Dynamic strategy routing',
    'Intelligent router mechanism',
    'Graph topology exploration',
    'Chapter-level document reading',
]
for j, b in enumerate(bullets_s2):
    ax.text(S2_X+0.45, S2_Y+1.55-j*0.38, f'\u2022 {b}',
            fontsize=9.2, color=C_BULLET, va='top', zorder=6)


# ════════════════════════════════════════════════════════
#  S3 Box — bottom right
# ════════════════════════════════════════════════════════
S3_X, S3_Y, S3_W, S3_H = 7.8, 1.8, 4.8, 2.9
rounded_box(ax, S3_X, S3_Y, S3_W, S3_H, C_BOX_FILL, C_BOX_EDGE)

ax.text(S3_X+0.35, S3_Y+S3_H-0.42, 'S3:', fontsize=12, fontweight='bold',
        color=C_TITLE, va='top', zorder=6)
ax.text(S3_X+0.35, S3_Y+S3_H-0.82, 'LLM-Guided',
        fontsize=13, fontweight='bold', color=C_TITLE, va='top', zorder=6)
ax.text(S3_X+0.35, S3_Y+S3_H-1.18, 'Graph Walk',
        fontsize=13, fontweight='bold', color=C_TITLE, va='top', zorder=6)

draw_tree_icon(ax, S3_X + S3_W - 1.0, S3_Y + S3_H/2 - 0.05)

bullets_s3 = [
    'Conditionally triggered',
    '(high-risk intent detected)',
    'Context-sensitive path selection',
    'Replaces traditional MCTS',
]
for j, b in enumerate(bullets_s3):
    style = 'italic' if '(' in b else 'normal'
    ax.text(S3_X+0.45, S3_Y+1.55-j*0.38, f'\u2022 {b}' if '(' not in b else f'  {b}',
            fontsize=9.2, color=C_BULLET, va='top', zorder=6, style=style)


# ════════════════════════════════════════════════════════
#  Merge arrows: S2 + S3 → Agentic Execution
# ════════════════════════════════════════════════════════
AGENTIC_TOP = 1.5
S2_CX_BOT = S2_X + S2_W / 2
S3_CX_BOT = S3_X + S3_W / 2
MERGE_Y = 1.62

ax.plot([S2_CX_BOT, S2_CX_BOT], [S2_Y, MERGE_Y], color=C_ARROW, lw=2.2, zorder=4)
ax.plot([S3_CX_BOT, S3_CX_BOT], [S3_Y, MERGE_Y], color=C_ARROW, lw=2.2, zorder=4)
ax.plot([S2_CX_BOT, S3_CX_BOT], [MERGE_Y, MERGE_Y], color=C_ARROW, lw=2.2, zorder=4)
arrow(ax, 6.5, MERGE_Y, 6.5, AGENTIC_TOP + 0.02)


# ════════════════════════════════════════════════════════
#  Agentic Execution bar — bottom
# ════════════════════════════════════════════════════════
AG_X, AG_Y, AG_W, AG_H = 0.4, 0.22, 12.2, 1.28
rounded_box(ax, AG_X, AG_Y, AG_W, AG_H, C_AGENTIC_BG, C_AGENTIC_EDG, lw=2.0)

ax.text(AG_X+0.35, AG_Y+AG_H-0.25, 'Agentic Execution',
        fontsize=13.5, fontweight='bold', color=C_TITLE, va='top', zorder=6)
ax.text(AG_X+0.35, AG_Y+0.28,
        'Manufacturer, Regulator, Distributor agents query RAG interface'
        '  \u2192  Unscripted GMP-compliant decisions',
        fontsize=10, color=C_BULLET, va='bottom', zorder=6)


# ════════════════════════════════════════════════════════
#  "Always-on" / "Parallel" labels on branches
# ════════════════════════════════════════════════════════
ax.text(stem_x + 0.1, (stem_y_top + stem_y_mid) / 2,
        'always\nexecuted', fontsize=7.5, color='#6b7280',
        style='italic', va='center', zorder=6)

ax.text((S2_CX + stem_x) / 2 + 0.1, branch_y + 0.12,
        'parallel', fontsize=7.5, color='#6b7280',
        style='italic', ha='center', zorder=6)
ax.text((S3_CX + stem_x) / 2 - 0.1, branch_y + 0.12,
        'parallel', fontsize=7.5, color='#6b7280',
        style='italic', ha='center', zorder=6)

ax.text(S3_X + 0.42, S3_Y + S3_H - 1.55,
        '(conditional)', fontsize=8, color='#9ca3af',
        style='italic', zorder=6)


plt.subplots_adjust(left=0, right=1, top=1, bottom=0)

out = os.path.join(OUTPUT_DIR, 'fig8_pipeline_diagram.png')
plt.savefig(out, dpi=200, bbox_inches='tight',
            facecolor=C_WHITE, edgecolor='none')
plt.close()
print(f'[OK] Saved: {out}')
