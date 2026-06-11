"""
主GUI界面模块：古籍抄本异文对照与分段校勘台
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import os

from data_validator import validate_csv, ValidationError
from collation_analyzer import CollationAnalyzer
from chart_generator import (
    create_volume_diff_chart,
    create_collation_mark_chart,
    create_copy_diff_heatmap,
    create_volume_copy_heatmap,
    embed_figure_in_tk
)


class AncientTextCollationApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("古籍抄本异文对照与分段校勘台")
        self.root.geometry("1400x900")
        self.root.minsize(1200, 800)

        self.analyzer: CollationAnalyzer = None
        self.validation_errors: list[ValidationError] = []
        self.current_file: str = ''
        self._chart_canvases = {}

        self._setup_style()
        self._build_ui()
        self._refresh_all()

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass
        style.configure('Title.TLabel', font=('SimHei', 18, 'bold'), padding=10)
        style.configure('Subtitle.TLabel', font=('SimHei', 12, 'bold'), padding=5)
        style.configure('Status.TLabel', font=('SimHei', 10), padding=5)
        style.configure('Treeview', font=('SimHei', 10), rowheight=28)
        style.configure('Treeview.Heading', font=('SimHei', 11, 'bold'))
        style.configure('Action.TButton', font=('SimHei', 11, 'bold'), padding=8)

    def _build_ui(self):
        top_frame = ttk.Frame(self.root, padding=10)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        title = ttk.Label(top_frame, text="古籍抄本异文对照与分段校勘台", style='Title.TLabel')
        title.pack(side=tk.LEFT)

        btn_frame = ttk.Frame(top_frame)
        btn_frame.pack(side=tk.RIGHT)

        self.btn_import = ttk.Button(btn_frame, text="📂 导入CSV", command=self._on_import, style='Action.TButton')
        self.btn_import.pack(side=tk.LEFT, padx=5)

        self.btn_refresh = ttk.Button(btn_frame, text="🔄 重新计算", command=self._refresh_all, style='Action.TButton')
        self.btn_refresh.pack(side=tk.LEFT, padx=5)

        self.btn_export = ttk.Button(btn_frame, text="💾 导出结果", command=self._on_export, style='Action.TButton')
        self.btn_export.pack(side=tk.LEFT, padx=5)

        status_frame = ttk.Frame(self.root, padding=(10, 0, 10, 5))
        status_frame.pack(side=tk.TOP, fill=tk.X)

        self.lbl_status = ttk.Label(status_frame, text="请导入CSV数据文件开始分析", style='Status.TLabel')
        self.lbl_status.pack(side=tk.LEFT)

        self.lbl_counts = ttk.Label(status_frame, text="", style='Status.TLabel')
        self.lbl_counts.pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self._build_comparison_tab()
        self._build_stats_tab()
        self._build_heatmap_tab()
        self._build_data_tab()
        self._build_errors_tab()

    def _build_comparison_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📋 分卷分段对照表")

        filter_frame = ttk.Frame(frame, padding=8)
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="卷次筛选:").pack(side=tk.LEFT, padx=2)
        self.cmb_volume = ttk.Combobox(filter_frame, width=12, state='readonly')
        self.cmb_volume.pack(side=tk.LEFT, padx=5)
        self.cmb_volume.bind('<<ComboboxSelected>>', lambda e: self._apply_comparison_filter())

        ttk.Label(filter_frame, text="段落范围:").pack(side=tk.LEFT, padx=(15, 2))
        self.entry_para_start = ttk.Entry(filter_frame, width=8)
        self.entry_para_start.pack(side=tk.LEFT, padx=2)
        ttk.Label(filter_frame, text="-").pack(side=tk.LEFT)
        self.entry_para_end = ttk.Entry(filter_frame, width=8)
        self.entry_para_end.pack(side=tk.LEFT, padx=2)

        self.chk_only_diff = ttk.Checkbutton(filter_frame, text="仅显示有异文的段落", command=self._apply_comparison_filter)
        self.chk_only_diff.pack(side=tk.LEFT, padx=20)

        ttk.Button(filter_frame, text="筛选", command=self._apply_comparison_filter).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="重置", command=self._reset_comparison_filter).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_comparison = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_comparison.yview)
        xscroll.config(command=self.tree_comparison.xview)

        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_comparison.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        missing_frame = ttk.LabelFrame(frame, text="缺段区间标注", padding=8)
        missing_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)
        self.txt_missing = scrolledtext.ScrolledText(missing_frame, height=5, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_missing.pack(fill=tk.X)
        self.txt_missing.config(state=tk.DISABLED)

    def _build_stats_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📊 异文分布统计")

        top_split = ttk.Frame(frame)
        top_split.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        left_frame = ttk.LabelFrame(top_split, text="各卷异文数量统计图", padding=8)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas_diff_chart = ttk.Frame(left_frame)
        self.canvas_diff_chart.pack(fill=tk.BOTH, expand=True)

        right_frame = ttk.LabelFrame(top_split, text="高频校勘类型统计图", padding=8)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas_mark_chart = ttk.Frame(right_frame)
        self.canvas_mark_chart.pack(fill=tk.BOTH, expand=True)

        bottom_frame = ttk.LabelFrame(frame, text="各卷异文与缺段统计表", padding=8)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=8, pady=8)

        yscroll = ttk.Scrollbar(bottom_frame, orient=tk.VERTICAL)
        self.tree_volume_stats = ttk.Treeview(bottom_frame, yscrollcommand=yscroll.set)
        yscroll.config(command=self.tree_volume_stats.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_volume_stats.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _build_heatmap_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔥 抄本差异热力图")

        top_frame = ttk.LabelFrame(frame, text="抄本两两差异热力图", padding=8)
        top_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas_heatmap1 = ttk.Frame(top_frame)
        self.canvas_heatmap1.pack(fill=tk.BOTH, expand=True)

        bottom_frame = ttk.LabelFrame(frame, text="卷次×抄本异文累计热力图", padding=8)
        bottom_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=8, pady=8)
        self.canvas_heatmap2 = ttk.Frame(bottom_frame)
        self.canvas_heatmap2.pack(fill=tk.BOTH, expand=True)

    def _build_data_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="✏️ 原始数据编辑")

        btn_frame = ttk.Frame(frame, padding=8)
        btn_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(btn_frame, text="选中行后双击单元格可编辑：").pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除选中行", command=self._delete_selected_row).pack(side=tk.LEFT, padx=10)
        ttk.Label(btn_frame, text="（修改后需点击上方【重新计算】按钮刷新异文统计）",
                  foreground='#888').pack(side=tk.LEFT, padx=10)

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_raw_data = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_raw_data.yview)
        xscroll.config(command=self.tree_raw_data.xview)

        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_raw_data.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_raw_data.bind('<Double-1>', self._on_cell_double_click)

    def _build_errors_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="⚠️ 导入错误记录")

        info_frame = ttk.Frame(frame, padding=10)
        info_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(info_frame, text="以下行在导入时验证失败，未参与分析（包含详细原因）：",
                  style='Subtitle.TLabel', foreground='#D35400').pack(side=tk.LEFT)

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_errors = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_errors.yview)
        xscroll.config(command=self.tree_errors.xview)

        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_errors.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        columns = ('row', 'reason', '书名', '抄本批次', '卷次', '段落编号', '原文内容', '校勘标记')
        self.tree_errors['columns'] = columns
        for col in columns:
            width_map = {'row': 80, 'reason': 350, '书名': 120, '抄本批次': 120,
                         '卷次': 80, '段落编号': 90, '原文内容': 250, '校勘标记': 150}
            anchor = tk.CENTER if col in ('row', '卷次', '段落编号') else tk.W
            self.tree_errors.heading(col, text=col)
            self.tree_errors.column(col, width=width_map.get(col, 150), anchor=anchor, stretch=True)
        self.tree_errors['show'] = 'headings'

    # ---------- 事件处理 ----------

    def _on_import(self):
        file_path = filedialog.askopenfilename(
            title="选择古籍抄本CSV数据文件",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        if not file_path:
            return

        try:
            df, errors, book_name = validate_csv(file_path)
        except Exception as e:
            messagebox.showerror("导入失败", f"文件导入错误：\n{str(e)}")
            return

        self.validation_errors = errors
        self.current_file = file_path
        self.analyzer = CollationAnalyzer(df, book_name)

        total_rows = len(df) + len(errors)
        msg = f"成功导入: {book_name} | 文件: {os.path.basename(file_path)} | 有效: {len(df)}行 / 共{total_rows}行"
        if errors:
            msg += f" | ⚠️ {len(errors)}行验证失败"
        self.lbl_status.config(text=msg)

        self._refresh_all()

        if errors:
            self.notebook.select(4)

    def _on_export(self):
        if not self.analyzer:
            messagebox.showinfo("提示", "请先导入数据")
            return
        out_dir = filedialog.askdirectory(title="选择导出目录")
        if not out_dir:
            return
        try:
            book = self.analyzer.book_name
            self.analyzer.build_comparison_table().to_csv(
                os.path.join(out_dir, f'{book}_分卷分段对照表.csv'), index=False, encoding='utf-8-sig')
            self.analyzer.get_volume_stats().to_csv(
                os.path.join(out_dir, f'{book}_各卷异文统计.csv'), index=False, encoding='utf-8-sig')
            self.analyzer.get_collation_mark_stats().to_csv(
                os.path.join(out_dir, f'{book}_高频校勘类型.csv'), index=False, encoding='utf-8-sig')
            vol_copy = self.analyzer.get_copy_volume_diff_count()
            if not vol_copy.empty:
                vol_copy.to_csv(os.path.join(out_dir, f'{book}_卷次抄本异文热力数据.csv'),
                                index=False, encoding='utf-8-sig')
            if not self.analyzer.df.empty:
                self.analyzer.df.to_csv(os.path.join(out_dir, f'{book}_有效数据.csv'),
                                        index=False, encoding='utf-8-sig')
            messagebox.showinfo("导出完成", f"所有结果已导出到：\n{out_dir}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _on_cell_double_click(self, event):
        if not self.analyzer:
            return
        region = self.tree_raw_data.identify_region(event.x, event.y)
        if region != 'cell':
            return
        item = self.tree_raw_data.selection()
        if not item:
            return
        row_id = self.tree_raw_data.identify_row(event.y)
        col_id = self.tree_raw_data.identify_column(event.x)
        col_idx = int(col_id.replace('#', '')) - 1
        cols = self.tree_raw_data['columns']
        if col_idx < 0 or col_idx >= len(cols):
            return
        col_name = cols[col_idx]

        x, y, w, h = self.tree_raw_data.bbox(row_id, col_id)
        old_value = self.tree_raw_data.set(row_id, col_name)

        entry = ttk.Entry(self.tree_raw_data)
        entry.insert(0, str(old_value))
        entry.select_range(0, tk.END)
        entry.focus()
        entry.place(x=x, y=y, width=w, height=h)

        def save_edit(e=None):
            new_val = entry.get().strip()
            entry.destroy()
            data_idx = int(self.tree_raw_data.item(row_id, 'tags')[0])
            if self.analyzer.update_record(data_idx, col_name, new_val):
                self.tree_raw_data.set(row_id, col_name, self.analyzer.df.iloc[data_idx][col_name])
                self.lbl_status.config(text=f"已修改行{data_idx + 2}的【{col_name}】，请点击【重新计算】刷新统计")

        entry.bind('<Return>', save_edit)
        entry.bind('<FocusOut>', save_edit)
        entry.bind('<Escape>', lambda e: entry.destroy())

    def _delete_selected_row(self):
        if not self.analyzer:
            return
        items = self.tree_raw_data.selection()
        if not items:
            messagebox.showinfo("提示", "请先选择要删除的行")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(items)} 条记录吗？\n删除后请点击【重新计算】刷新统计。"):
            return
        indices = sorted([int(self.tree_raw_data.item(i, 'tags')[0]) for i in items], reverse=True)
        for idx in indices:
            self.analyzer.delete_record(idx)
        self.lbl_status.config(text="已删除记录，请点击【重新计算】刷新统计")
        self._load_raw_data_tree()

    # ---------- 刷新与渲染 ----------

    def _refresh_all(self):
        self._refresh_volume_filter()
        self._load_comparison_tree()
        self._load_missing_info()
        self._load_stats_charts()
        self._load_heatmaps()
        self._load_raw_data_tree()
        self._load_errors_tree()
        self._update_counts_label()

    def _update_counts_label(self):
        if not self.analyzer:
            self.lbl_counts.config(text="")
            return
        a = self.analyzer
        table = a.build_comparison_table()
        diff_count = len(table[table['异文'] == '有']) if not table.empty else 0
        missing_dict = a.get_missing_paragraphs()
        missing_count = sum(sum(e - s + 1 for s, e in ranges) for ranges in missing_dict.values())
        self.lbl_counts.config(
            text=f"抄本:{len(a.copy_batches)}个 | 卷次:{len(a.volumes)}卷 | "
                 f"有效记录:{len(a.df)}条 | 有异文段落:{diff_count}处 | 缺段总数:{missing_count}个"
        )

    def _refresh_volume_filter(self):
        vols = ['全部'] + [f'第{v}卷' for v in (self.analyzer.volumes if self.analyzer else [])]
        self.cmb_volume['values'] = vols
        self.cmb_volume.current(0)

    def _reset_comparison_filter(self):
        self.cmb_volume.current(0)
        self.entry_para_start.delete(0, tk.END)
        self.entry_para_end.delete(0, tk.END)
        self.chk_only_diff.state(['!selected'])
        self._load_comparison_tree()

    def _apply_comparison_filter(self):
        self._load_comparison_tree()

    def _populate_tree(self, tree, dataframe, text_tags_by_col=None):
        tree.delete(*tree.get_children())
        if dataframe is None or dataframe.empty:
            tree['columns'] = ('info',)
            tree.heading('info', text='暂无数据')
            tree.column('info', width=800, anchor=tk.CENTER)
            tree['show'] = 'headings'
            return

        cols = list(dataframe.columns)
        tree['columns'] = cols
        for col in cols:
            anchor = tk.CENTER if str(col) in ('卷次', '段落编号', '总段落数', '异文段落数',
                                               '异文率(%)', '缺段总数', '频次') else tk.W
            txt = str(col)
            tree.heading(col, text=txt)
            width = 200
            if txt in ('卷次', '段落编号', '异文'):
                width = 80
            elif txt == '状态':
                width = 90
            elif '内容' in txt:
                width = 320
            elif '校勘' in txt or '缺段' in txt:
                width = 200
            tree.column(col, width=width, anchor=anchor, stretch=True)
        tree['show'] = 'headings'

        tags_func = text_tags_by_col or (lambda idx, row: ())
        for idx, row in dataframe.iterrows():
            values = []
            for col in cols:
                v = row[col]
                if pd.isna(v):
                    values.append('')
                else:
                    values.append(str(v))
            tags = tags_func(idx, row)
            tree.insert('', tk.END, values=values, tags=tags)

    def _load_comparison_tree(self):
        if not self.analyzer:
            self._populate_tree(self.tree_comparison, None)
            return

        table = self.analyzer.build_comparison_table().copy()
        if table.empty:
            self._populate_tree(self.tree_comparison, None)
            return

        vol_sel = self.cmb_volume.get()
        if vol_sel and vol_sel != '全部':
            v = int(vol_sel.replace('第', '').replace('卷', ''))
            table = table[table['卷次'] == v]

        try:
            p_start = int(self.entry_para_start.get().strip())
            table = table[table['段落编号'] >= p_start]
        except (ValueError, tk.TclError):
            pass
        try:
            p_end = int(self.entry_para_end.get().strip())
            table = table[table['段落编号'] <= p_end]
        except (ValueError, tk.TclError):
            pass

        only_diff = 'selected' in self.chk_only_diff.state()
        if only_diff:
            table = table[table['异文'] == '有']

        def tag_row(idx, row):
            tags = ()
            if row.get('异文') == '有':
                tags = ('diff',) + tags
            if row.get('状态') == '有缺段':
                tags = ('missing',) + tags
            return tags

        self._populate_tree(self.tree_comparison, table.reset_index(drop=True), tag_row)

        self.tree_comparison.tag_configure('diff', background='#FFF5E1')
        self.tree_comparison.tag_configure('missing', background='#FDEDEC')

        for col in self.tree_comparison['columns']:
            if '内容' in col or '校勘' in col:
                self.tree_comparison.column(col, width=320)

    def _load_missing_info(self):
        self.txt_missing.config(state=tk.NORMAL)
        self.txt_missing.delete('1.0', tk.END)

        if not self.analyzer:
            self.txt_missing.config(state=tk.DISABLED)
            return

        missing = self.analyzer.get_missing_paragraphs()
        if not missing:
            self.txt_missing.insert(tk.END, "✅ 所有抄本各卷的段落编号均完整，无缺段。")
        else:
            lines = ["以下抄本在对应卷次中存在缺失段落区间：\n"]
            by_copy = {}
            for (copy_b, vol), ranges in missing.items():
                by_copy.setdefault(copy_b, []).append((vol, ranges))
            for copy_b, vol_list in sorted(by_copy.items()):
                lines.append(f"\n【{copy_b}】:")
                for vol, ranges in sorted(vol_list):
                    range_strs = [f"{s}-{e}" if s != e else str(s) for s, e in ranges]
                    total = sum(e - s + 1 for s, e in ranges)
                    lines.append(f"    第{vol}卷 → 缺失段落: {', '.join(range_strs)} (共{total}段)")
            self.txt_missing.insert(tk.END, '\n'.join(lines))

        self.txt_missing.config(state=tk.DISABLED)

    def _clear_chart_canvas(self, canvas_frame):
        for w in canvas_frame.winfo_children():
            w.destroy()

    def _load_stats_charts(self):
        self._clear_chart_canvas(self.canvas_diff_chart)
        self._clear_chart_canvas(self.canvas_mark_chart)

        if not self.analyzer:
            self._populate_tree(self.tree_volume_stats, None)
            return

        vol_stats = self.analyzer.get_volume_stats()
        mark_stats = self.analyzer.get_collation_mark_stats()

        fig1 = create_volume_diff_chart(vol_stats, self.analyzer.book_name)
        embed_figure_in_tk(fig1, self.canvas_diff_chart)

        fig2 = create_collation_mark_chart(mark_stats, self.analyzer.book_name)
        embed_figure_in_tk(fig2, self.canvas_mark_chart)

        self._populate_tree(self.tree_volume_stats, vol_stats)

    def _load_heatmaps(self):
        self._clear_chart_canvas(self.canvas_heatmap1)
        self._clear_chart_canvas(self.canvas_heatmap2)

        if not self.analyzer:
            return

        fig1 = create_copy_diff_heatmap(self.analyzer, self.analyzer.book_name)
        embed_figure_in_tk(fig1, self.canvas_heatmap1)

        vol_copy_df = self.analyzer.get_copy_volume_diff_count()
        fig2 = create_volume_copy_heatmap(vol_copy_df, self.analyzer.book_name)
        embed_figure_in_tk(fig2, self.canvas_heatmap2)

    def _load_raw_data_tree(self):
        if not self.analyzer or self.analyzer.df.empty:
            self._populate_tree(self.tree_raw_data, None)
            return

        df = self.analyzer.df.copy()
        for col in ['卷次', '段落编号']:
            df[col] = df[col].astype(int)

        def tag_func(idx, row):
            return (str(idx),)

        self._populate_tree(self.tree_raw_data, df, tag_func)

    def _load_errors_tree(self):
        self.tree_errors.delete(*self.tree_errors.get_children())
        if not self.validation_errors:
            self.tree_errors.insert('', tk.END, values=('-', '暂无导入错误，所有数据行均通过验证 ✅',
                                                          '', '', '', '', '', ''))
            return

        for err in self.validation_errors:
            d = err.data or {}
            self.tree_errors.insert('', tk.END, values=(
                f'行{err.row_index}',
                err.reason,
                d.get('书名', ''),
                d.get('抄本批次', ''),
                d.get('卷次', ''),
                d.get('段落编号', ''),
                str(d.get('原文内容', ''))[:60],
                d.get('校勘标记', '')
            ))


def main():
    root = tk.Tk()
    app = AncientTextCollationApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()
