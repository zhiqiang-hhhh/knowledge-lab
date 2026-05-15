import os
import pandas as pd
import matplotlib.pyplot as plt
from math import ceil

"""
使用用户提供的两组新数据（128 维、268 维），替换旧数据并重新画图。
数据列：
- Dim, Rows, Method, Config, efS, Train(s), Add(s), Build(s), Search(ms), R@100, mbs_on_disk, Compress
"""

# ===============================
# 1. 数据准备（来自用户提供的数据）
# ===============================
data_rows = [
    # 128 维，Rows = 10k
    [128, 10000, "HNSW-Flat", "M=32", 64, 0.00, 0.24, 0.24, 0.01, 0.786, 7.5, 0.7],
    [128, 10000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.00, 1.78, 1.78, 0.06, 0.783, 3.8, 1.3],
    [128, 10000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.00, 2.52, 2.52, 0.07, 0.702, 3.2, 1.5],
    # [128, 10000, "HNSW-PQ",   "M=32,PQ(m=64,nbits=8,tr=1.00)", 64, 6.61, 0.57, 7.18, 0.02, 0.728, 3.3, 1.5],
    # 128 维，Rows = 50k
    [128, 50000, "HNSW-Flat", "M=32", 64, 0.00, 7.65, 7.65, 0.02, 0.502, 37.4, 0.7],
    [128, 50000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.01, 86.37, 86.38, 0.08, 0.503, 19.1, 1.3],
    [128, 50000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.01, 77.11, 77.12, 0.11, 0.457, 16.0, 1.5],
    # [128, 50000, "HNSW-PQ",   "M=32,PQ(m=64,nbits=8,tr=1.00)", 64, 31.44, 20.82, 52.26, 0.02, 0.487, 16.2, 1.5],
    # 128 维，Rows = 100k
    [128, 100000, "HNSW-Flat", "M=32", 64, 0.00, 21.71, 21.71, 0.03, 0.387, 74.8, 0.7],
    [128, 100000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.01, 226.64, 226.66, 0.08, 0.376, 38.2, 1.3],
    [128, 100000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.01, 207.03, 207.04, 0.11, 0.351, 32.1, 1.5],
    # [128, 100000, "HNSW-PQ",   "M=32,PQ(m=64,nbits=8,tr=1.00)", 64, 39.99, 61.25, 101.23, 0.03, 0.363, 32.2, 1.5],

    # 268 维，Rows = 10k
    [268, 10000, "HNSW-Flat", "M=32", 64, 0.00, 0.70, 0.70, 0.02, 0.689, 12.4, 0.8],
    [268, 10000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.00, 7.91, 7.91, 0.12, 0.684, 5.0, 1.9],
    [268, 10000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.00, 10.76, 10.76, 0.15, 0.625, 3.8, 2.6],
    # [268, 10000, "HNSW-PQ",   "M=32,PQ(m=128,nbits=8,tr=1.00)", 64, 12.85, 2.72, 15.56, 0.03, 0.643, 4.1, 2.4],
    # 268 维，Rows = 50k
    [268, 50000, "HNSW-Flat", "M=32", 64, 0.00, 17.33, 17.33, 0.04, 0.330, 61.8, 0.8],
    [268, 50000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.01, 217.44, 217.45, 0.16, 0.336, 25.2, 1.9],
    [268, 50000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.01, 204.41, 204.42, 0.20, 0.313, 19.1, 2.6],
    # [268, 50000, "HNSW-PQ",   "M=32,PQ(m=128,nbits=8,tr=1.00)", 64, 62.83, 88.18, 151.01, 0.05, 0.324, 19.3, 2.5],
    # 268 维，Rows = 100k
    [268, 100000, "HNSW-Flat", "M=32", 64, 0.00, 42.72, 42.72, 0.06, 0.215, 123.6, 0.8],
    [268, 100000, "HNSW-SQ8",  "M=32,QT_8bit", 64, 0.03, 501.92, 501.94, 0.16, 0.225, 50.4, 1.9],
    [268, 100000, "HNSW-SQ4",  "M=32,QT_4bit", 64, 0.03, 490.05, 490.08, 0.21, 0.203, 38.2, 2.6],
    # [268, 100000, "HNSW-PQ",   "M=32,PQ(m=128,nbits=8,tr=1.00)", 64, 82.64, 217.02, 299.66, 0.05, 0.229, 38.4, 2.5],
]

columns = [
    "Dim", "Rows", "Method", "Config", "efS",
    "Train(s)", "Add(s)", "Build(s)",
    "Search(ms)", "R@100", "mbs_on_disk", "Compress",
]

df = pd.DataFrame(data_rows, columns=columns)

# ===============================
# 2. 保存 CSV 文件
# ===============================
out_dir = os.path.dirname(__file__)
csv_path = os.path.join(out_dir, "hnsw_results.csv")
df.to_csv(csv_path, index=False)
print(f"CSV 已生成: {csv_path}")

############################################################
# 3 & 4. 分组柱状图绘制函数（更适合小数据量，可读性更好）
############################################################

def plot_grouped_bars(
    data: pd.DataFrame,
    x_col: str,
    y_col: str,
    group_col: str,
    title: str,
    ylabel: str,
    out_png: str,
    value_fmt: str = "{:.2f}",
    palette=None,
    legend_loc: str = "upper left",
    legend_anchor=None,
    legend_ncol: int | None = None,
    legend_inside: bool = True,
):
    """绘制分组柱状图并在柱顶添加数值标签。

    Parameters
    ----------
    data : DataFrame
        输入数据。
    x_col : str
        X 轴分类列（例如 Rows）。
    y_col : str
        数值列。
    group_col : str
        分组列（例如 Method）。
    title : str
        图标题。
    ylabel : str
        Y 轴标签。
    out_png : str
        输出图片文件名。
    value_fmt : str
        数值标签格式。
    palette : list[str] | None
        自定义颜色列表。
    """

    # 基础数据准备
    categories = sorted(data[x_col].unique())
    groups = list(data[group_col].unique())
    n_cat = len(categories)
    n_grp = len(groups)

    # 动态图宽：每个类别 0.7 英寸 + 边距
    fig_width = max(6, min(18, 0.7 * n_cat * n_grp + 2.5))
    fig, ax = plt.subplots(figsize=(fig_width, 5.2), dpi=140)

    # 调色板
    if palette is None:
        base_colors = plt.get_cmap("tab10").colors
        if n_grp <= len(base_colors):
            colors = base_colors[:n_grp]
        else:
            # 重复使用，保证有颜色
            times = ceil(n_grp / len(base_colors))
            colors = (base_colors * times)[:n_grp]
    else:
        colors = palette

    total_group_width = 0.82  # 每个类别内部总宽度
    bar_width = total_group_width / n_grp

    x_index = range(n_cat)

    for gi, g in enumerate(groups):
        subset = data[data[group_col] == g]
        # 按类别顺序对齐
        y_vals = [subset[subset[x_col] == c][y_col].values[0] for c in categories]
        # 计算每个分组的偏移
        offsets = [x + (gi - n_grp / 2) * bar_width + bar_width / 2 for x in x_index]
        bars = ax.bar(offsets, y_vals, width=bar_width * 0.92, color=colors[gi], label=g, edgecolor="#333", linewidth=0.5)
        # 添加数值标签
        for b, v in zip(bars, y_vals):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                value_fmt.format(v),
                ha="center",
                va="bottom",
                fontsize=9,
                rotation=0,
                color="#222",
            )

    ax.set_xticks(list(x_index))
    ax.set_xticklabels([str(c) for c in categories], fontsize=10)
    ax.set_xlabel(x_col, fontsize=11)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=13, pad=10, weight="semibold")

    # 辅助网格仅 y 轴
    ax.yaxis.grid(True, linestyle="--", linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)

    # 去掉顶部和右边框
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)

    # 图例放上方横排
    # 图例位置控制：默认放在图内左上角；可配置
    if legend_inside:
        ax.legend(
            loc=legend_loc,
            frameon=True,
            fontsize=9,
            fancybox=True,
            framealpha=0.85,
            borderpad=0.4,
            labelspacing=0.4,
        )
    else:
        ax.legend(
            loc=legend_loc,
            bbox_to_anchor=legend_anchor if legend_anchor else (0.5, 1.08),
            ncol=legend_ncol if legend_ncol else min(4, n_grp),
            frameon=False,
            fontsize=10,
        )

    plt.tight_layout()
    plt.savefig(out_png)
    print(f"图片已生成(柱状图): {out_png}")
    plt.close(fig)

# ===============================
# 4. 分维度绘图
# ===============================
dims = sorted(df["Dim"].unique())
for dim in dims:
    sub = df[df["Dim"] == dim].copy()
    suffix = f"_dim{dim}"

    # Build Time 分组柱状图（使用 Build(s)）
    plot_grouped_bars(
        sub,
        x_col="Rows",
        y_col="Build(s)",
        group_col="Method",
        title=f"Build Time vs Rows (Dim={dim})",
        ylabel="Build Time (s)",
        out_png=os.path.join(out_dir, f"build_time_vs_rows{suffix}.png"),
        value_fmt="{:.2f}",
        legend_loc="upper left",
        legend_inside=True,
    )

    # Index Size on Disk 分组柱状图
    plot_grouped_bars(
        sub,
        x_col="Rows",
        y_col="mbs_on_disk",
        group_col="Method",
        title=f"Memory Usage vs Rows (Dim={dim})",
        ylabel="Memory Usage (MB)",
        out_png=os.path.join(out_dir, f"memory_usage_vs_rows{suffix}.png"),
        value_fmt="{:.1f}",
        legend_loc="upper left",
        legend_inside=True,
    )

    # Recall@100 分组柱状图
    plot_grouped_bars(
        sub,
        x_col="Rows",
        y_col="R@100",
        group_col="Method",
        title=f"Recall@100 vs Rows (Dim={dim})",
        ylabel="Recall@100",
        out_png=os.path.join(out_dir, f"recall_vs_rows{suffix}.png"),
        value_fmt="{:.3f}",
        legend_loc="upper left",
        legend_inside=True,
    )

    # Search(ms) 分组柱状图
    plot_grouped_bars(
        sub,
        x_col="Rows",
        y_col="Search(ms)",
        group_col="Method",
        title=f"Search Time vs Rows (Dim={dim})",
        ylabel="Search Time (ms)",
        out_png=os.path.join(out_dir, f"search_time_vs_rows{suffix}.png"),
        value_fmt="{:.2f}",
        legend_loc="upper left",
        legend_inside=True,
    )

print("全部柱状图绘制完成（按维度输出）。")

############################################################
# 5. 维度对比：并排子图（优雅地同时展示 Dim 变化）
############################################################

from matplotlib.patches import Patch

# METHOD_ORDER = ["HNSW-Flat", "HNSW-SQ8", "HNSW-SQ4", "HNSW-PQ"]
METHOD_ORDER = ["HNSW-Flat", "HNSW-SQ8", "HNSW-SQ4"]
BASE_COLORS = list(plt.get_cmap("tab10").colors)
COLOR_MAP = {m: BASE_COLORS[i % len(BASE_COLORS)] for i, m in enumerate(METHOD_ORDER)}


def draw_grouped_bars_on_ax(ax, data: pd.DataFrame, x_col: str, y_col: str, methods: list[str], value_fmt: str):
    """在给定 ax 上绘制分组柱状图，按固定方法顺序与一致配色。"""
    categories = sorted(data[x_col].unique())
    n_cat = len(categories)
    n_grp = len(methods)
    total_group_width = 0.82
    bar_width = total_group_width / max(1, n_grp)
    x_index = list(range(n_cat))

    for gi, method in enumerate(methods):
        subset = data[data["Method"] == method]
        if subset.empty:
            continue
        y_vals = []
        for c in categories:
            vals = subset[subset[x_col] == c][y_col].values
            y_vals.append(vals[0] if len(vals) else 0.0)

        offsets = [x + (gi - n_grp / 2) * bar_width + bar_width / 2 for x in x_index]
        bars = ax.bar(
            offsets,
            y_vals,
            width=bar_width * 0.92,
            color=COLOR_MAP.get(method, BASE_COLORS[gi % len(BASE_COLORS)]),
            edgecolor="#333",
            linewidth=0.5,
            label=method,
        )
        for b, v in zip(bars, y_vals):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height(),
                value_fmt.format(v),
                ha="center",
                va="bottom",
                fontsize=9,
                color="#222",
            )

    ax.set_xticks(list(range(n_cat)))
    ax.set_xticklabels([str(c) for c in categories], fontsize=10)
    ax.yaxis.grid(True, linestyle="--", linewidth=0.6, alpha=0.5)
    ax.set_axisbelow(True)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)


def plot_dim_side_by_side(
    df: pd.DataFrame,
    dims_to_show: list[int],
    x_col: str,
    y_col: str,
    ylabel: str,
    title_prefix: str,
    out_png: str,
    value_fmt: str,
):
    fig, axes = plt.subplots(1, len(dims_to_show), figsize=(11, 4.6), dpi=140, sharey=True)
    if len(dims_to_show) == 1:
        axes = [axes]

    for ax, d in zip(axes, dims_to_show):
        sub = df[df["Dim"] == d]
        draw_grouped_bars_on_ax(ax, sub, x_col=x_col, y_col=y_col, methods=METHOD_ORDER, value_fmt=value_fmt)
        ax.set_xlabel(x_col, fontsize=11)
        ax.set_title(f"Dim={d}", fontsize=12, pad=8)
        ax.set_ylabel(ylabel, fontsize=11)

    legend_handles = [Patch(facecolor=COLOR_MAP[m], edgecolor="#333", label=m) for m in METHOD_ORDER]
    fig.legend(
        handles=legend_handles,
        loc="upper center",
        ncol=min(4, len(METHOD_ORDER)),
        frameon=False,
        fontsize=10,
        bbox_to_anchor=(0.5, 1.05),
    )
    fig.suptitle(f"{title_prefix}", fontsize=13, y=1.08)
    fig.tight_layout()
    plt.savefig(out_png, bbox_inches="tight")
    print(f"图片已生成(维度对比): {out_png}")
    plt.close(fig)


# 生成三类并排维度对比图
plot_dim_side_by_side(
    df,
    dims_to_show=dims,
    x_col="Rows",
    y_col="Build(s)",
    ylabel="Build Time (s)",
    title_prefix="Build Time vs Rows (Dim Comparison)",
    out_png=os.path.join(out_dir, "build_time_vs_rows_dims_compare.png"),
    value_fmt="{:.2f}",
)

plot_dim_side_by_side(
    df,
    dims_to_show=dims,
    x_col="Rows",
    y_col="mbs_on_disk",
    ylabel="Memory Usage (MB)",
    title_prefix="Memory Usage vs Rows (Dim Comparison)",
    out_png=os.path.join(out_dir, "memory_usage_vs_rows_dims_compare.png"),
    value_fmt="{:.1f}",
)

plot_dim_side_by_side(
    df,
    dims_to_show=dims,
    x_col="Rows",
    y_col="R@100",
    ylabel="Recall@100",
    title_prefix="Recall@100 vs Rows (Dim Comparison)",
    out_png=os.path.join(out_dir, "recall_vs_rows_dims_compare.png"),
    value_fmt="{:.3f}",
)

plot_dim_side_by_side(
    df,
    dims_to_show=dims,
    x_col="Rows",
    y_col="Search(ms)",
    ylabel="Search Time (ms)",
    title_prefix="Search Time vs Rows (Dim Comparison)",
    out_png=os.path.join(out_dir, "search_time_vs_rows_dims_compare.png"),
    value_fmt="{:.2f}",
)
