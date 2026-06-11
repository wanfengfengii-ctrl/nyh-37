"""
图表生成模块：异文分布统计图、抄本差异热力图
"""
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import seaborn as sns
from typing import Optional
import tkinter as tk

plt.rcParams['font.sans-serif'] = ['Songti SC', 'SimHei', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False


def create_volume_diff_chart(volume_stats: pd.DataFrame, book_name: str) -> Figure:
    """
    创建各卷异文数量分布统计图（柱状图）
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    if volume_stats.empty:
        ax.text(0.5, 0.5, '暂无数据', ha='center', va='center', fontsize=16, transform=ax.transAxes)
        fig.suptitle(f'{book_name} - 各卷异文数量统计', fontsize=14, fontweight='bold')
        return fig

    vols = [f'第{v}卷' for v in volume_stats['卷次']]
    x = np.arange(len(vols))
    width = 0.35

    bars1 = ax.bar(x - width / 2, volume_stats['总段落数'], width,
                   label='总段落数', color='#4A90D9', edgecolor='white')
    bars2 = ax.bar(x + width / 2, volume_stats['异文段落数'], width,
                   label='异文段落数', color='#E74C3C', edgecolor='white')

    for bar in bars1:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., height,
                f'{int(height)}', ha='center', va='bottom', fontsize=9)
    for bar in bars2:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width() / 2., height,
                f'{int(height)}', ha='center', va='bottom', fontsize=9)

    ax.set_xlabel('卷次', fontsize=12)
    ax.set_ylabel('段落数', fontsize=12)
    ax.set_title(f'{book_name} - 各卷异文数量分布', fontsize=13, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(vols, rotation=45, ha='right')
    ax.legend(loc='upper right')
    ax.grid(axis='y', alpha=0.3, linestyle='--')
    sns.despine(ax=ax, offset=10, trim=True)

    fig.tight_layout()
    return fig


def create_collation_mark_chart(mark_stats: pd.DataFrame, book_name: str, top_n: int = 10) -> Figure:
    """
    创建高频校勘类型统计图（水平条形图）
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    if mark_stats.empty:
        ax.text(0.5, 0.5, '暂无校勘标记数据', ha='center', va='center', fontsize=16, transform=ax.transAxes)
        fig.suptitle(f'{book_name} - 高频校勘类型统计', fontsize=14, fontweight='bold')
        return fig

    data = mark_stats.head(top_n).iloc[::-1]
    colors = sns.color_palette('YlOrRd_r', n_colors=len(data))
    bars = ax.barh(range(len(data)), data['频次'], color=colors, edgecolor='white')

    ax.set_yticks(range(len(data)))
    ax.set_yticklabels(data['校勘类型'], fontsize=10)
    ax.set_xlabel('出现频次', fontsize=12)
    ax.set_title(f'{book_name} - 高频校勘类型 (Top {top_n})', fontsize=13, fontweight='bold')

    for i, (bar, val) in enumerate(zip(bars, data['频次'])):
        ax.text(bar.get_width() + 0.3, i, f'{int(val)}',
                ha='left', va='center', fontsize=10, fontweight='bold')

    ax.grid(axis='x', alpha=0.3, linestyle='--')
    sns.despine(ax=ax, offset=10, trim=True)

    fig.tight_layout()
    return fig


def create_copy_diff_heatmap(analyzer, book_name: str) -> Figure:
    """
    创建抄本差异热力图（抄本两两之间的异文段落数）
    """
    fig, ax = plt.subplots(figsize=(8, 6))

    copy_batches = analyzer.copy_batches
    n = len(copy_batches)

    if n < 2:
        ax.text(0.5, 0.5, '抄本数量不足2个，无法生成热力图\n（至少需要2个抄本进行比较）',
                ha='center', va='center', fontsize=14, transform=ax.transAxes, wrap=True)
        fig.suptitle(f'{book_name} - 抄本差异热力图', fontsize=14, fontweight='bold')
        return fig

    matrix = analyzer.build_diff_matrix()
    data = np.zeros((n, n), dtype=int)
    for i in range(n):
        for j in range(n):
            if i == j:
                data[i, j] = 0
            else:
                data[i, j] = matrix.get((copy_batches[i], copy_batches[j]), 0)

    df_heatmap = pd.DataFrame(data, index=copy_batches, columns=copy_batches)

    max_val = data.max() if data.max() > 0 else 1
    cmap = sns.color_palette("YlOrRd", as_cmap=True)
    sns.heatmap(df_heatmap, annot=True, fmt='d', cmap=cmap,
                ax=ax, cbar_kws={'label': '异文段落数'},
                linewidths=0.5, linecolor='white',
                vmin=0, vmax=max_val)

    ax.set_title(f'{book_name} - 抄本差异热力图\n(两两之间异文段落总数)',
                 fontsize=13, fontweight='bold', pad=20)
    ax.set_xlabel('抄本批次', fontsize=11)
    ax.set_ylabel('抄本批次', fontsize=11)

    for t in ax.texts:
        t.set_fontsize(10)
        if int(t.get_text()) > max_val * 0.6:
            t.set_color('white')

    fig.tight_layout()
    return fig


def create_volume_copy_heatmap(volume_copy_df: pd.DataFrame, book_name: str) -> Figure:
    """
    创建卷次-抄本异文热力图
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    if volume_copy_df.empty:
        ax.text(0.5, 0.5, '暂无数据', ha='center', va='center', fontsize=16, transform=ax.transAxes)
        fig.suptitle(f'{book_name} - 卷次×抄本异文热力图', fontsize=14, fontweight='bold')
        return fig

    plot_data = volume_copy_df.set_index('卷次')
    max_val = plot_data.max().max()
    if max_val == 0:
        max_val = 1

    cmap = sns.color_palette("Blues", as_cmap=True)
    sns.heatmap(plot_data, annot=True, fmt='d', cmap=cmap,
                ax=ax, cbar_kws={'label': '累计异文段落数'},
                linewidths=0.5, linecolor='white',
                vmin=0, vmax=max_val)

    ax.set_title(f'{book_name} - 卷次×抄本异文累计热力图',
                 fontsize=13, fontweight='bold', pad=20)
    ax.set_xlabel('抄本批次', fontsize=11)
    ax.set_ylabel('卷次', fontsize=11)

    for t in ax.texts:
        try:
            val = int(t.get_text())
            t.set_fontsize(9)
            if val > max_val * 0.6:
                t.set_color('white')
        except:
            pass

    fig.tight_layout()
    return fig


def embed_figure_in_tk(figure: Figure, parent: tk.Widget) -> FigureCanvasTkAgg:
    """
    将matplotlib图表嵌入到Tkinter容器中
    """
    canvas = FigureCanvasTkAgg(figure, master=parent)
    canvas.draw()
    canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
    return canvas
