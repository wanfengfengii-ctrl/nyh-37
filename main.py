"""
主GUI界面模块：古籍抄本异文对照与分段校勘台
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import pandas as pd
import os
from datetime import datetime

from data_validator import validate_csv, ValidationError
from collation_analyzer import CollationAnalyzer
from chart_generator import (
    create_volume_diff_chart,
    create_collation_mark_chart,
    create_copy_diff_heatmap,
    create_volume_copy_heatmap,
    embed_figure_in_tk
)
from collation_project import ProjectManager, CollationProject, ProjectStatus
from workflow_engine import Role, DoubtStatus, ReviewAction
from collation_rules import CollationType
from doubt_detector import DoubtDetector
from collation_exporter import CollationExporter
from citation_analyzer import (
    CitationType as CitationTypeEnum,
    CitationStatus as CitationStatusEnum,
    CitationSource,
    CitationAnalyzer
)
from case_library import (
    CaseSourceType,
    CaseStatus,
    CaseCategory,
    RecommendationStatus,
    CaseFilter,
    RecommendationFilter,
    CaseResolution
)


class AncientTextCollationApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("古籍抄本异文对照与校勘工作台")
        self.root.geometry("1500x950")
        self.root.minsize(1300, 850)

        self.analyzer: CollationAnalyzer = None
        self.validation_errors: list[ValidationError] = []
        self.current_file: str = ''
        self._chart_canvases = {}

        self.project_manager: ProjectManager = ProjectManager()
        self.current_project: CollationProject = None
        self.current_user: str = 'admin'
        self.current_role: Role = Role.ADMIN
        self.doubt_detector: DoubtDetector = DoubtDetector()
        self.doubt_filter_status: str = '全部'
        self.doubt_filter_type: str = '全部'
        self._current_selected_doubt_id: str = ''
        self._current_selected_citation_id: str = ''

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

        user_frame = ttk.Frame(top_frame)
        user_frame.pack(side=tk.LEFT, padx=30)

        ttk.Label(user_frame, text="当前用户:", style='Status.TLabel').pack(side=tk.LEFT, padx=2)
        self.entry_user = ttk.Entry(user_frame, width=12)
        self.entry_user.insert(0, self.current_user)
        self.entry_user.pack(side=tk.LEFT, padx=2)

        ttk.Label(user_frame, text="角色:", style='Status.TLabel').pack(side=tk.LEFT, padx=2)
        self.cmb_role = ttk.Combobox(user_frame, values=[r.value for r in Role], width=10, state='readonly')
        self.cmb_role.current(0)
        self.cmb_role.pack(side=tk.LEFT, padx=2)
        self.cmb_role.bind('<<ComboboxSelected>>', self._on_role_change)

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

        self.lbl_project_info = ttk.Label(status_frame, text="【未选择项目】", style='Status.TLabel', foreground='#2980B9')
        self.lbl_project_info.pack(side=tk.LEFT)

        self.lbl_status = ttk.Label(status_frame, text="请导入CSV数据或创建校勘项目", style='Status.TLabel')
        self.lbl_status.pack(side=tk.LEFT, padx=30)

        self.lbl_counts = ttk.Label(status_frame, text="", style='Status.TLabel')
        self.lbl_counts.pack(side=tk.RIGHT)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self._build_project_tab()
        self._build_comparison_tab()
        self._build_doubt_detection_tab()
        self._build_review_tab()
        self._build_citation_tab()
        self._build_case_library_tab()
        self._build_export_tab()
        self._build_audit_tab()
        self._build_stats_tab()
        self._build_heatmap_tab()
        self._build_data_tab()
        self._build_errors_tab()

    def _build_project_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📁 校勘项目管理")

        left_frame = ttk.LabelFrame(frame, text="项目列表", padding=8)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="➕ 新建项目", command=self._on_create_project, style='Action.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📂 导入CSV到项目", command=self._on_import_to_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="👥 分配用户", command=self._on_assign_user).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="▶️ 启动项目", command=self._on_start_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="⏸️ 暂停项目", command=self._on_pause_project).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📊 项目统计", command=self._on_project_stats).pack(side=tk.LEFT, padx=5)

        yscroll = ttk.Scrollbar(left_frame, orient=tk.VERTICAL)
        self.tree_projects = ttk.Treeview(left_frame, yscrollcommand=yscroll.set)
        yscroll.config(command=self.tree_projects.yview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_projects.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_projects.bind('<<TreeviewSelect>>', self._on_project_select)

        cols = ('project_id', 'project_name', 'book_name', 'status', 'total_doubts', 'pending_doubts', 'created_at', 'created_by')
        self.tree_projects['columns'] = cols
        for col in cols:
            width_map = {'project_id': 180, 'project_name': 200, 'book_name': 150, 'status': 100,
                        'total_doubts': 90, 'pending_doubts': 100, 'created_at': 150, 'created_by': 100}
            anchor = tk.CENTER if col in ('status', 'total_doubts', 'pending_doubts', 'created_at') else tk.W
            self.tree_projects.heading(col, text={'project_id': '项目ID', 'project_name': '项目名称', 'book_name': '书名',
                                                  'status': '状态', 'total_doubts': '总疑点', 'pending_doubts': '待复核',
                                                  'created_at': '创建时间', 'created_by': '创建人'}[col])
            self.tree_projects.column(col, width=width_map.get(col, 150), anchor=anchor, stretch=True)
        self.tree_projects['show'] = 'headings'

        right_frame = ttk.LabelFrame(frame, text="项目详情", padding=8)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        info_frame = ttk.Frame(right_frame)
        info_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.lbl_project_detail = ttk.Label(info_frame, text="请选择一个项目查看详情", style='Subtitle.TLabel')
        self.lbl_project_detail.pack(side=tk.LEFT)

        members_frame = ttk.LabelFrame(right_frame, text="项目成员", padding=5)
        members_frame.pack(side=tk.TOP, fill=tk.X, pady=5)
        self.tree_members = ttk.Treeview(members_frame, columns=('user', 'role'), show='headings', height=6)
        self.tree_members.heading('user', text='用户名')
        self.tree_members.heading('role', text='角色')
        self.tree_members.column('user', width=150)
        self.tree_members.column('role', width=150)
        self.tree_members.pack(side=tk.LEFT, fill=tk.X, expand=True)

        timeline_frame = ttk.LabelFrame(right_frame, text="项目时间线", padding=5)
        timeline_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)
        self.txt_project_timeline = scrolledtext.ScrolledText(timeline_frame, height=15, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_project_timeline.pack(fill=tk.BOTH, expand=True)
        self.txt_project_timeline.config(state=tk.DISABLED)

    def _build_doubt_detection_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="🔍 自动疑点识别")

        btn_frame = ttk.Frame(frame, padding=8)
        btn_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(btn_frame, text="检测类型:").pack(side=tk.LEFT, padx=2)
        self.chk_detect_wrong = ttk.Checkbutton(btn_frame, text="错字")
        self.chk_detect_wrong.state(['selected'])
        self.chk_detect_wrong.pack(side=tk.LEFT, padx=5)
        self.chk_detect_missing = ttk.Checkbutton(btn_frame, text="脱文")
        self.chk_detect_missing.state(['selected'])
        self.chk_detect_missing.pack(side=tk.LEFT, padx=5)
        self.chk_detect_extra = ttk.Checkbutton(btn_frame, text="衍文")
        self.chk_detect_extra.state(['selected'])
        self.chk_detect_extra.pack(side=tk.LEFT, padx=5)
        self.chk_detect_reversed = ttk.Checkbutton(btn_frame, text="倒文")
        self.chk_detect_reversed.state(['selected'])
        self.chk_detect_reversed.pack(side=tk.LEFT, padx=5)
        self.chk_detect_number = ttk.Checkbutton(btn_frame, text="编号断裂")
        self.chk_detect_number.state(['selected'])
        self.chk_detect_number.pack(side=tk.LEFT, padx=5)

        ttk.Button(btn_frame, text="▶️ 全量检测", command=self._on_detect_all, style='Action.TButton').pack(side=tk.LEFT, padx=15)
        ttk.Button(btn_frame, text="📖 按卷检测", command=self._on_detect_volume).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="📊 检测统计", command=self._on_detection_stats).pack(side=tk.LEFT, padx=5)

        filter_frame = ttk.Frame(frame, padding=8)
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="状态筛选:").pack(side=tk.LEFT, padx=2)
        self.cmb_doubt_status = ttk.Combobox(filter_frame, values=['全部', '待复核', '处理中', '已复核', '已驳回', '已解决', '已失效'],
                                              width=10, state='readonly')
        self.cmb_doubt_status.current(0)
        self.cmb_doubt_status.pack(side=tk.LEFT, padx=5)
        self.cmb_doubt_status.bind('<<ComboboxSelected>>', lambda e: self._load_doubts_tree())

        ttk.Label(filter_frame, text="类型筛选:").pack(side=tk.LEFT, padx=10)
        self.cmb_doubt_type = ttk.Combobox(filter_frame, values=['全部', '错字', '脱文', '衍文', '倒文', '编号断裂'],
                                            width=10, state='readonly')
        self.cmb_doubt_type.current(0)
        self.cmb_doubt_type.pack(side=tk.LEFT, padx=5)
        self.cmb_doubt_type.bind('<<ComboboxSelected>>', lambda e: self._load_doubts_tree())

        ttk.Label(filter_frame, text="卷次:").pack(side=tk.LEFT, padx=10)
        self.cmb_doubt_volume = ttk.Combobox(filter_frame, width=10, state='readonly')
        self.cmb_doubt_volume.pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="筛选", command=self._load_doubts_tree).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="重置", command=self._reset_doubt_filter).pack(side=tk.LEFT, padx=2)

        tree_frame = ttk.Frame(frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_doubts = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_doubts.yview)
        xscroll.config(command=self.tree_doubts.xview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_doubts.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_doubts.bind('<<TreeviewSelect>>', self._on_doubt_select)

        cols = ('doubt_id', 'collation_type', 'volume', 'paragraph', 'copy_batch',
                'original_text', 'suggested_text', 'confidence', 'status', 'created_at', 'assignee')
        self.tree_doubts['columns'] = cols
        for col in cols:
            width_map = {'doubt_id': 180, 'collation_type': 90, 'volume': 60, 'paragraph': 80,
                        'copy_batch': 100, 'original_text': 200, 'suggested_text': 200,
                        'confidence': 80, 'status': 80, 'created_at': 150, 'assignee': 100}
            anchor = tk.CENTER if col in ('volume', 'paragraph', 'confidence', 'status', 'created_at') else tk.W
            self.tree_doubts.heading(col, text={'doubt_id': '疑点ID', 'collation_type': '类型', 'volume': '卷次',
                                                 'paragraph': '段落', 'copy_batch': '抄本', 'original_text': '原文',
                                                 'suggested_text': '建议', 'confidence': '置信度', 'status': '状态',
                                                 'created_at': '创建时间', 'assignee': '指派人'}[col])
            self.tree_doubts.column(col, width=width_map.get(col, 150), anchor=anchor, stretch=True)
        self.tree_doubts['show'] = 'headings'

        detail_frame = ttk.LabelFrame(frame, text="疑点详情", padding=8)
        detail_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)

        self.txt_doubt_detail = scrolledtext.ScrolledText(detail_frame, height=6, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_doubt_detail.pack(fill=tk.X)
        self.txt_doubt_detail.config(state=tk.DISABLED)

    def _build_review_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="✅ 人工复核工作流")

        left_frame = ttk.Frame(frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        filter_frame = ttk.Frame(left_frame, padding=5)
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="状态:").pack(side=tk.LEFT, padx=2)
        self.cmb_review_status = ttk.Combobox(filter_frame, values=['全部', '待复核', '处理中', '已复核', '已驳回', '已解决', '已失效'],
                                              width=10, state='readonly')
        self.cmb_review_status.current(1)
        self.cmb_review_status.pack(side=tk.LEFT, padx=5)
        self.cmb_review_status.bind('<<ComboboxSelected>>', lambda e: self._load_review_tree())

        ttk.Label(filter_frame, text="指派给我:").pack(side=tk.LEFT, padx=10)
        self.chk_only_mine = ttk.Checkbutton(filter_frame, command=self._load_review_tree)
        self.chk_only_mine.pack(side=tk.LEFT, padx=2)

        ttk.Button(filter_frame, text="刷新", command=self._load_review_tree).pack(side=tk.LEFT, padx=10)

        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_review = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_review.yview)
        xscroll.config(command=self.tree_review.xview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_review.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_review.bind('<<TreeviewSelect>>', self._on_review_select)

        cols = ('doubt_id', 'collation_type', 'volume', 'paragraph', 'copy_batch',
                'original_text', 'suggested_text', 'status', 'assignee')
        self.tree_review['columns'] = cols
        for col in cols:
            width_map = {'doubt_id': 160, 'collation_type': 80, 'volume': 50, 'paragraph': 70,
                        'copy_batch': 90, 'original_text': 180, 'suggested_text': 180,
                        'status': 80, 'assignee': 90}
            anchor = tk.CENTER if col in ('volume', 'paragraph', 'status') else tk.W
            self.tree_review.heading(col, text={'doubt_id': '疑点ID', 'collation_type': '类型', 'volume': '卷',
                                                 'paragraph': '段', 'copy_batch': '抄本', 'original_text': '原文',
                                                 'suggested_text': '建议', 'status': '状态', 'assignee': '指派人'}[col])
            self.tree_review.column(col, width=width_map.get(col, 150), anchor=anchor, stretch=True)
        self.tree_review['show'] = 'headings'

        right_frame = ttk.Frame(frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        detail_frame = ttk.LabelFrame(right_frame, text="疑点信息", padding=8)
        detail_frame.pack(side=tk.TOP, fill=tk.X)

        self.lbl_review_detail = ttk.Label(detail_frame, text="请选择一个疑点进行复核", style='Subtitle.TLabel')
        self.lbl_review_detail.pack(side=tk.TOP, anchor=tk.W)

        self.txt_review_detail = scrolledtext.ScrolledText(detail_frame, height=8, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_review_detail.pack(fill=tk.X, pady=5)
        self.txt_review_detail.config(state=tk.DISABLED)

        action_frame = ttk.LabelFrame(right_frame, text="复核操作", padding=8)
        action_frame.pack(side=tk.TOP, fill=tk.X, pady=8)

        ttk.Label(action_frame, text="操作:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=5)
        self.cmb_review_action = ttk.Combobox(action_frame, values=[a.value for a in ReviewAction],
                                               width=10, state='readonly')
        self.cmb_review_action.current(0)
        self.cmb_review_action.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(action_frame, text="转交用户:").grid(row=0, column=2, sticky=tk.W, padx=2, pady=5)
        self.entry_reassign = ttk.Entry(action_frame, width=12)
        self.entry_reassign.grid(row=0, column=3, padx=5, pady=5)

        ttk.Label(action_frame, text="复核意见:").grid(row=1, column=0, sticky=tk.NW, padx=2, pady=5)
        self.txt_review_comment = scrolledtext.ScrolledText(action_frame, height=4, width=60, font=('SimHei', 10))
        self.txt_review_comment.grid(row=1, column=1, columnspan=3, padx=5, pady=5, sticky=tk.EW)

        btn_row = ttk.Frame(action_frame)
        btn_row.grid(row=2, column=0, columnspan=4, pady=5)
        ttk.Button(btn_row, text="📝 提交复核", command=self._on_submit_review, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_row, text="🔄 重新激活", command=self._on_reactivate_doubt).pack(side=tk.LEFT, padx=10)

        history_frame = ttk.LabelFrame(right_frame, text="复核历史", padding=8)
        history_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=5)

        self.txt_review_history = scrolledtext.ScrolledText(history_frame, height=10, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_review_history.pack(fill=tk.BOTH, expand=True)
        self.txt_review_history.config(state=tk.DISABLED)

    def _build_citation_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📚 引文溯源与互证分析")

        top_frame = ttk.Frame(frame, padding=8)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(top_frame, text="检测类型:").pack(side=tk.LEFT, padx=2)
        self.chk_cite_quotation = ttk.Checkbutton(top_frame, text="引文")
        self.chk_cite_quotation.state(['selected'])
        self.chk_cite_quotation.pack(side=tk.LEFT, padx=5)
        self.chk_cite_allusion = ttk.Checkbutton(top_frame, text="典故")
        self.chk_cite_allusion.pack(side=tk.LEFT, padx=5)
        self.chk_cite_repetition = ttk.Checkbutton(top_frame, text="重复语段")
        self.chk_cite_repetition.state(['selected'])
        self.chk_cite_repetition.pack(side=tk.LEFT, padx=5)
        self.chk_cite_misquote = ttk.Checkbutton(top_frame, text="疑似误引")
        self.chk_cite_misquote.state(['selected'])
        self.chk_cite_misquote.pack(side=tk.LEFT, padx=5)

        ttk.Button(top_frame, text="▶️ 全量检测", command=self._on_citation_detect_all, style='Action.TButton').pack(side=tk.LEFT, padx=15)
        ttk.Button(top_frame, text="🎯 范围检测", command=self._on_citation_detect_volume).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="📊 检测统计", command=self._on_citation_stats).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="🕸️ 互证图谱", command=self._on_show_citation_graph).pack(side=tk.LEFT, padx=5)

        filter_frame = ttk.Frame(frame, padding=8)
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="状态筛选:").pack(side=tk.LEFT, padx=2)
        self.cmb_citation_status = ttk.Combobox(filter_frame,
            values=['全部'] + [s.value for s in CitationStatusEnum],
            width=10, state='readonly')
        self.cmb_citation_status.current(0)
        self.cmb_citation_status.pack(side=tk.LEFT, padx=5)
        self.cmb_citation_status.bind('<<ComboboxSelected>>', lambda e: self._load_citations_tree())

        ttk.Label(filter_frame, text="类型筛选:").pack(side=tk.LEFT, padx=10)
        self.cmb_citation_type = ttk.Combobox(filter_frame,
            values=['全部'] + [t.value for t in CitationTypeEnum],
            width=10, state='readonly')
        self.cmb_citation_type.current(0)
        self.cmb_citation_type.pack(side=tk.LEFT, padx=5)
        self.cmb_citation_type.bind('<<ComboboxSelected>>', lambda e: self._load_citations_tree())

        ttk.Label(filter_frame, text="书名:").pack(side=tk.LEFT, padx=10)
        self.cmb_citation_book = ttk.Combobox(filter_frame, width=12, state='readonly')
        self.cmb_citation_book.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="卷次:").pack(side=tk.LEFT, padx=10)
        self.cmb_citation_volume = ttk.Combobox(filter_frame, width=10, state='readonly')
        self.cmb_citation_volume.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="抄本:").pack(side=tk.LEFT, padx=10)
        self.cmb_citation_copy = ttk.Combobox(filter_frame, width=10, state='readonly')
        self.cmb_citation_copy.pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="筛选", command=self._load_citations_tree).pack(side=tk.LEFT, padx=5)
        ttk.Button(filter_frame, text="重置", command=self._reset_citation_filter).pack(side=tk.LEFT, padx=2)

        content_pane = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        content_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        left_frame = ttk.Frame(content_pane)
        content_pane.add(left_frame, weight=3)

        tree_frame = ttk.Frame(left_frame)
        tree_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        yscroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)
        xscroll = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL)
        self.tree_citations = ttk.Treeview(tree_frame, yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.config(command=self.tree_citations.yview)
        xscroll.config(command=self.tree_citations.xview)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_citations.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_citations.bind('<<TreeviewSelect>>', self._on_citation_select)

        cols = ('citation_id', 'citation_type', 'volume', 'paragraph', 'copy_batch',
                'quoted_text', 'confidence', 'match_basis', 'status', 'created_at', 'confirmed_by')
        self.tree_citations['columns'] = cols
        for col in cols:
            width_map = {'citation_id': 180, 'citation_type': 90, 'volume': 60, 'paragraph': 80,
                        'copy_batch': 100, 'quoted_text': 250, 'confidence': 80,
                        'match_basis': 200, 'status': 80, 'created_at': 150, 'confirmed_by': 100}
            anchor = tk.CENTER if col in ('volume', 'paragraph', 'confidence', 'status', 'created_at') else tk.W
            self.tree_citations.heading(col, text={
                'citation_id': '引文ID', 'citation_type': '类型', 'volume': '卷次',
                'paragraph': '段落', 'copy_batch': '抄本', 'quoted_text': '引文字段',
                'confidence': '置信度', 'match_basis': '匹配依据', 'status': '状态',
                'created_at': '创建时间', 'confirmed_by': '确认人'
            }[col])
            self.tree_citations.column(col, width=width_map.get(col, 150), anchor=anchor, stretch=True)
        self.tree_citations['show'] = 'headings'

        right_frame = ttk.Frame(content_pane)
        content_pane.add(right_frame, weight=2)

        detail_frame = ttk.LabelFrame(right_frame, text="引文详情", padding=8)
        detail_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        self.txt_citation_detail = scrolledtext.ScrolledText(detail_frame, height=10, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_citation_detail.pack(fill=tk.BOTH, expand=True)
        self.txt_citation_detail.config(state=tk.DISABLED)

        match_frame = ttk.LabelFrame(right_frame, text="匹配出处", padding=8)
        match_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        self.tree_citation_matches = ttk.Treeview(match_frame, height=8)
        cols_match = ('book', 'volume', 'paragraph', 'copy', 'similarity', 'basis', 'is_misquote')
        self.tree_citation_matches['columns'] = cols_match
        for col in cols_match:
            width_map2 = {'book': 150, 'volume': 60, 'paragraph': 70, 'copy': 100,
                         'similarity': 80, 'basis': 200, 'is_misquote': 80}
            anchor2 = tk.CENTER if col in ('volume', 'paragraph', 'similarity', 'is_misquote') else tk.W
            self.tree_citation_matches.heading(col, text={
                'book': '书名', 'volume': '卷', 'paragraph': '段',
                'copy': '抄本', 'similarity': '相似度', 'basis': '匹配依据', 'is_misquote': '疑似误引'
            }[col])
            self.tree_citation_matches.column(col, width=width_map2.get(col, 120), anchor=anchor2, stretch=True)
        self.tree_citation_matches['show'] = 'headings'
        self.tree_citation_matches.pack(fill=tk.BOTH, expand=True)

        action_frame = ttk.LabelFrame(right_frame, text="复核操作", padding=8)
        action_frame.pack(side=tk.TOP, fill=tk.X, pady=2)

        ttk.Label(action_frame, text="操作:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=5)
        self.cmb_citation_action = ttk.Combobox(action_frame,
            values=['确认', '驳回', '补充出处'], width=10, state='readonly')
        self.cmb_citation_action.current(0)
        self.cmb_citation_action.grid(row=0, column=1, padx=5, pady=5)

        ttk.Label(action_frame, text="意见/说明:").grid(row=0, column=2, sticky=tk.W, padx=2, pady=5)
        self.txt_citation_comment = scrolledtext.ScrolledText(action_frame, height=3, width=40, font=('SimHei', 10))
        self.txt_citation_comment.grid(row=0, column=3, padx=5, pady=5, sticky=tk.EW)

        btn_row = ttk.Frame(action_frame)
        btn_row.grid(row=1, column=0, columnspan=4, pady=5)
        ttk.Button(btn_row, text="📝 提交复核", command=self._on_submit_citation_review, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_row, text="🔄 重新激活", command=self._on_reactivate_citation).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_row, text="➕ 补充出处", command=self._on_supplement_source).pack(side=tk.LEFT, padx=10)

        history_frame = ttk.LabelFrame(right_frame, text="处理历史", padding=8)
        history_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        self.txt_citation_history = scrolledtext.ScrolledText(history_frame, height=6, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_citation_history.pack(fill=tk.BOTH, expand=True)
        self.txt_citation_history.config(state=tk.DISABLED)

    def _on_citation_detect_all(self):
        if not self.current_project or not self.current_project.analyzer:
            messagebox.showinfo("提示", "请先选择项目并导入数据")
            return
        try:
            detect_types = []
            if 'selected' in self.chk_cite_quotation.state():
                detect_types.append(CitationTypeEnum.QUOTATION)
            if 'selected' in self.chk_cite_allusion.state():
                detect_types.append(CitationTypeEnum.ALLUSION)
            if 'selected' in self.chk_cite_repetition.state():
                detect_types.append(CitationTypeEnum.REPETITION)
            if 'selected' in self.chk_cite_misquote.state():
                detect_types.append(CitationTypeEnum.MISQUOTE)

            if not detect_types:
                messagebox.showinfo("提示", "请至少选择一种检测类型")
                return

            summary = self.current_project.run_citation_detection(
                operator=self.current_user,
                detect_types=detect_types
            )
            msg = f"引文溯源检测完成！\n\n"
            msg += f"检测到: {summary.total_detected} 条\n"
            msg += f"新增: {summary.new_created} 条\n"
            msg += f"跳过重复: {summary.duplicates_skipped} 条\n"
            msg += f"疑似误引: {summary.misquote_count} 条\n\n"
            msg += "按类型统计:\n"
            for type_name, count in summary.by_type.items():
                msg += f"  {type_name}: {count}条\n"
            self.lbl_status.config(text=f"引文检测完成: 新增{summary.new_created}条")
            messagebox.showinfo("检测完成", msg)
            self._load_citations_tree()
            self._load_projects_tree()
        except Exception as e:
            messagebox.showerror("检测失败", str(e))

    def _on_citation_detect_volume(self):
        if not self.current_project or not self.current_project.analyzer:
            messagebox.showinfo("提示", "请先选择项目并导入数据")
            return
        vols = self.current_project.analyzer.volumes
        copies = self.current_project.analyzer.copy_batches
        if not vols:
            messagebox.showinfo("提示", "无可检测的卷次")
            return
        win = tk.Toplevel(self.root)
        win.title("范围检测引文")
        win.geometry("340x230")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="选择卷次:").pack(pady=(15, 5), anchor=tk.W, padx=30)
        cmb_vol = ttk.Combobox(win, values=['全部'] + [f'第{v}卷' for v in vols], state='readonly', width=20)
        cmb_vol.current(0)
        cmb_vol.pack(pady=2)

        ttk.Label(win, text="选择抄本:").pack(pady=(10, 5), anchor=tk.W, padx=30)
        cmb_copy = ttk.Combobox(win, values=['全部'] + list(copies), state='readonly', width=20)
        cmb_copy.current(0)
        cmb_copy.pack(pady=2)

        def do_detect():
            vol_str = cmb_vol.get()
            copy_str = cmb_copy.get()
            v = None
            if vol_str and vol_str != '全部':
                v = int(vol_str.replace('第', '').replace('卷', ''))
            c = None
            if copy_str and copy_str != '全部':
                c = copy_str

            detect_types = []
            if 'selected' in self.chk_cite_quotation.state():
                detect_types.append(CitationTypeEnum.QUOTATION)
            if 'selected' in self.chk_cite_allusion.state():
                detect_types.append(CitationTypeEnum.ALLUSION)
            if 'selected' in self.chk_cite_repetition.state():
                detect_types.append(CitationTypeEnum.REPETITION)
            if 'selected' in self.chk_cite_misquote.state():
                detect_types.append(CitationTypeEnum.MISQUOTE)

            if not detect_types:
                messagebox.showinfo("提示", "请至少选择一种检测类型")
                return

            scope_desc = []
            if v:
                scope_desc.append(f'第{v}卷')
            else:
                scope_desc.append('全卷')
            if c:
                scope_desc.append(c)
            else:
                scope_desc.append('全部抄本')
            scope = ' '.join(scope_desc)

            try:
                summary = self.current_project.run_citation_detection(
                    operator=self.current_user,
                    volume=v,
                    copy_batch=c,
                    detect_types=detect_types
                )
                self.lbl_status.config(text=f"{scope}引文检测完成: 新增{summary.new_created}条")
                messagebox.showinfo("完成", f"{scope}检测完成\n新增: {summary.new_created}条\n总检测: {summary.total_detected}条\n跳过重复: {summary.duplicates_skipped}条")
                win.destroy()
                self._load_citations_tree()
                self._load_projects_tree()
            except Exception as e:
                messagebox.showerror("检测失败", str(e))

        ttk.Button(win, text="开始检测", command=do_detect, style='Action.TButton').pack(pady=15)

    def _on_citation_stats(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        stats = self.current_project.get_citation_statistics()
        msg = "引文溯源统计\n\n"
        msg += f"总数: {stats.get('total', 0)}\n"
        msg += f"待确认: {stats.get('pending', 0)}\n"
        msg += f"已确认: {stats.get('confirmed', 0)}\n"
        msg += f"已驳回: {stats.get('rejected', 0)}\n"
        msg += f"已失效: {stats.get('invalidated', 0)}\n"
        msg += f"疑似误引: {stats.get('misquote_count', 0)}\n\n"
        msg += "按类型统计:\n"
        for k, v in stats.get('by_type', {}).items():
            msg += f"  {k}: {v}\n"
        messagebox.showinfo("引文统计", msg)

    def _on_show_citation_graph(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        try:
            citations = self.current_project.get_all_citations()
            if not citations:
                messagebox.showinfo("提示", "暂无引文数据，请先运行检测")
                return
            graph = self.current_project.citation_analyzer.build_citation_graph(citations)
            self._show_citation_graph_window(graph)
        except Exception as e:
            messagebox.showerror("错误", str(e))

    def _show_citation_graph_window(self, graph):
        win = tk.Toplevel(self.root)
        win.title("互证关系图谱")
        win.geometry("900x700")
        win.transient(self.root)

        info_frame = ttk.LabelFrame(win, text="图谱信息", padding=8)
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=5)
        ttk.Label(info_frame, text=f"节点数: {len(graph.nodes)}    关系数: {len(graph.edges)}").pack(side=tk.LEFT)

        text_frame = ttk.LabelFrame(win, text="图谱数据（节点与关系列表）", padding=8)
        text_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        notebook = ttk.Notebook(text_frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        nodes_frame = ttk.Frame(notebook)
        notebook.add(nodes_frame, text="节点列表")
        tree_nodes = ttk.Treeview(nodes_frame)
        tree_nodes['columns'] = ('node_id', 'label', 'node_type', 'book', 'volume', 'paragraph')
        for col in tree_nodes['columns']:
            tree_nodes.heading(col, text={
                'node_id': '节点ID', 'label': '标签', 'node_type': '类型',
                'book': '书名', 'volume': '卷', 'paragraph': '段'
            }[col])
            tree_nodes.column(col, width=140 if col in ('node_id', 'label') else 90, anchor=tk.W)
        tree_nodes['show'] = 'headings'
        tree_nodes.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for n in graph.nodes:
            tree_nodes.insert('', tk.END, values=(
                n.node_id, n.label, n.node_type, n.book,
                n.volume or '', n.paragraph or ''
            ))

        edges_frame = ttk.Frame(notebook)
        notebook.add(edges_frame, text="关系列表")
        tree_edges = ttk.Treeview(edges_frame)
        tree_edges['columns'] = ('source', 'target', 'relation', 'similarity')
        for col in tree_edges['columns']:
            tree_edges.heading(col, text={
                'source': '源节点', 'target': '目标节点',
                'relation': '关系', 'similarity': '相似度'
            }[col])
            tree_edges.column(col, width=220 if col in ('source', 'target') else 120, anchor=tk.W)
        tree_edges['show'] = 'headings'
        tree_edges.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        for e in graph.edges:
            tree_edges.insert('', tk.END, values=(
                e.source_id, e.target_id, e.relation,
                f"{e.similarity:.2%}" if e.similarity > 0 else ''
            ))

        btn_frame = ttk.Frame(win)
        btn_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=8)
        ttk.Button(btn_frame, text="关闭", command=win.destroy).pack(side=tk.RIGHT)

    def _on_citation_select(self, event=None):
        selection = self.tree_citations.selection()
        if not selection:
            return
        citation_id = self.tree_citations.item(selection[0], 'values')[0]
        self._current_selected_citation_id = citation_id
        self._current_selected_doubt_id = ''
        if hasattr(self, '_load_recommendations_tree'):
            self._load_recommendations_tree()
        if not self.current_project:
            return
        citation = self.current_project.workflow_engine.get_citation(citation_id)
        if not citation:
            return

        self.txt_citation_detail.config(state=tk.NORMAL)
        self.txt_citation_detail.delete('1.0', tk.END)
        content = (f"引文ID: {citation.citation_id}\n"
                   f"类型: {citation.citation_type.value}\n"
                   f"位置: 第{citation.volume}卷 第{citation.paragraph}段 ({citation.copy_batch})\n"
                   f"原文段落: {citation.original_text}\n"
                   f"疑似引文字段: {citation.quoted_text}\n"
                   f"位置范围: [{citation.start_pos}, {citation.end_pos}]\n"
                   f"置信度: {citation.confidence:.2%}\n"
                   f"匹配依据: {citation.match_basis}\n"
                   f"状态: {citation.status.value}\n"
                   f"创建人: {citation.created_by}  {citation.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"确认人: {citation.confirmed_by or '未确认'}  "
                   f"{citation.confirmed_at.strftime('%Y-%m-%d %H:%M:%S') if citation.confirmed_at else ''}\n"
                   f"失效原因: {citation.invalidated_reason or '无'}\n"
                   f"数据指纹: {citation.data_hash}")
        if citation.confirmed_source:
            src = citation.confirmed_source
            content += f"\n\n已确认出处:\n  书名: {src.source_book}"
            if src.source_volume:
                content += f"\n  卷次: 第{src.source_volume}卷"
            if src.source_paragraph:
                content += f"\n  段落: 第{src.source_paragraph}段"
            if src.source_chapter:
                content += f"\n  章节: {src.source_chapter}"
            if src.source_page:
                content += f"\n  页码: {src.source_page}"
            if src.source_text:
                content += f"\n  原文: {src.source_text}"
            if src.note:
                content += f"\n  备注: {src.note}"
        self.txt_citation_detail.insert('1.0', content)
        self.txt_citation_detail.config(state=tk.DISABLED)

        self.tree_citation_matches.delete(*self.tree_citation_matches.get_children())
        for m in citation.matches:
            self.tree_citation_matches.insert('', tk.END, values=(
                m.match_book,
                m.match_volume or '',
                m.match_paragraph or '',
                m.match_copy_batch or '',
                f"{m.match_similarity:.2%}",
                m.match_basis,
                '是' if m.is_suspected_misquote else '否'
            ))

        self.txt_citation_history.config(state=tk.NORMAL)
        self.txt_citation_history.delete('1.0', tk.END)
        for h in citation.processing_history:
            time_str = h['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            self.txt_citation_history.insert(tk.END,
                f"{time_str} {h['operator']}[{h.get('operator_role', '')}] {h['action']}: {h['content']}\n")
        self.txt_citation_history.config(state=tk.DISABLED)

    def _on_submit_citation_review(self):
        selection = self.tree_citations.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择要复核的引文")
            return
        citation_id = self.tree_citations.item(selection[0], 'values')[0]
        action_str = self.cmb_citation_action.get()
        content = self.txt_citation_comment.get('1.0', tk.END).strip()

        if not content:
            messagebox.showinfo("提示", "请填写复核意见")
            return

        try:
            if action_str == '确认':
                citation = self.current_project.confirm_citation(self.current_user, citation_id, note=content)
            elif action_str == '驳回':
                citation = self.current_project.reject_citation(self.current_user, citation_id, reason=content)
            else:
                messagebox.showinfo("提示", "请使用【补充出处】按钮添加出处信息")
                return
            self.lbl_status.config(text=f"引文复核成功: {citation_id} -> {citation.status.value}")
            self.txt_citation_comment.delete('1.0', tk.END)
            self._load_citations_tree()
            self._load_projects_tree()
            self._on_citation_select()
        except Exception as e:
            messagebox.showerror("复核失败", str(e))

    def _on_reactivate_citation(self):
        selection = self.tree_citations.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择要重新激活的引文")
            return
        citation_id = self.tree_citations.item(selection[0], 'values')[0]
        try:
            citation = self.current_project.reactivate_citation(self.current_user, citation_id)
            self.lbl_status.config(text=f"已重新激活引文: {citation_id}")
            self._load_citations_tree()
            self._load_projects_tree()
            self._on_citation_select()
        except Exception as e:
            messagebox.showerror("操作失败", str(e))

    def _on_supplement_source(self):
        selection = self.tree_citations.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条引文")
            return
        citation_id = self.tree_citations.item(selection[0], 'values')[0]

        win = tk.Toplevel(self.root)
        win.title("补充引文出处")
        win.geometry("500x420")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="书名*:", style='Subtitle.TLabel').grid(row=0, column=0, sticky=tk.W, padx=10, pady=8)
        entry_book = ttk.Entry(win, width=40)
        entry_book.grid(row=0, column=1, padx=10, pady=8)
        entry_book.insert(0, self.current_project.book_name if self.current_project else '')

        ttk.Label(win, text="卷次:", style='Subtitle.TLabel').grid(row=1, column=0, sticky=tk.W, padx=10, pady=8)
        entry_vol = ttk.Entry(win, width=40)
        entry_vol.grid(row=1, column=1, padx=10, pady=8)

        ttk.Label(win, text="段落:", style='Subtitle.TLabel').grid(row=2, column=0, sticky=tk.W, padx=10, pady=8)
        entry_para = ttk.Entry(win, width=40)
        entry_para.grid(row=2, column=1, padx=10, pady=8)

        ttk.Label(win, text="抄本批次:", style='Subtitle.TLabel').grid(row=3, column=0, sticky=tk.W, padx=10, pady=8)
        entry_copy = ttk.Entry(win, width=40)
        entry_copy.grid(row=3, column=1, padx=10, pady=8)

        ttk.Label(win, text="章节:", style='Subtitle.TLabel').grid(row=4, column=0, sticky=tk.W, padx=10, pady=8)
        entry_chapter = ttk.Entry(win, width=40)
        entry_chapter.grid(row=4, column=1, padx=10, pady=8)

        ttk.Label(win, text="页码:", style='Subtitle.TLabel').grid(row=5, column=0, sticky=tk.W, padx=10, pady=8)
        entry_page = ttk.Entry(win, width=40)
        entry_page.grid(row=5, column=1, padx=10, pady=8)

        ttk.Label(win, text="出处原文:", style='Subtitle.TLabel').grid(row=6, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_source = scrolledtext.ScrolledText(win, width=40, height=4)
        txt_source.grid(row=6, column=1, padx=10, pady=8)

        ttk.Label(win, text="备注说明:", style='Subtitle.TLabel').grid(row=7, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_note = scrolledtext.ScrolledText(win, width=40, height=3)
        txt_note.grid(row=7, column=1, padx=10, pady=8)

        def do_supplement():
            book = entry_book.get().strip()
            if not book:
                messagebox.showerror("错误", "书名为必填项")
                return
            vol_str = entry_vol.get().strip()
            vol = int(vol_str) if vol_str.isdigit() else None
            para_str = entry_para.get().strip()
            para = int(para_str) if para_str.isdigit() else None
            source = CitationSource(
                source_book=book,
                source_volume=vol,
                source_paragraph=para,
                source_copy_batch=entry_copy.get().strip() or None,
                source_chapter=entry_chapter.get().strip(),
                source_page=entry_page.get().strip(),
                source_text=txt_source.get('1.0', tk.END).strip(),
                note=txt_note.get('1.0', tk.END).strip()
            )
            try:
                self.current_project.supplement_citation_source(
                    self.current_user, citation_id, source,
                    note=txt_note.get('1.0', tk.END).strip()
                )
                messagebox.showinfo("成功", "出处补充成功")
                win.destroy()
                self._load_citations_tree()
                self._on_citation_select()
            except Exception as e:
                messagebox.showerror("失败", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.grid(row=8, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="确认补充", command=do_supplement, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=10)

    def _reset_citation_filter(self):
        self.cmb_citation_status.current(0)
        self.cmb_citation_type.current(0)
        if self.cmb_citation_book['values']:
            self.cmb_citation_book.current(0)
        if self.cmb_citation_volume['values']:
            self.cmb_citation_volume.current(0)
        if self.cmb_citation_copy['values']:
            self.cmb_citation_copy.current(0)
        self._load_citations_tree()

    def _build_case_library_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📚 校勘判例库与智能推荐")

        top_frame = ttk.Frame(frame, padding=8)
        top_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top_frame, text="📊 判例库统计", command=self._on_case_library_stats,
                   style='Action.TButton').pack(side=tk.LEFT, padx=5)
        ttk.Button(top_frame, text="🔄 刷新判例库", command=self._load_cases_tree).pack(side=tk.LEFT, padx=5)

        filter_frame = ttk.LabelFrame(frame, text="筛选条件", padding=8)
        filter_frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=5)

        ttk.Label(filter_frame, text="书名:").grid(row=0, column=0, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_book = ttk.Combobox(filter_frame, width=15, state='readonly')
        self.cmb_case_book.grid(row=0, column=1, padx=5, pady=3)

        ttk.Label(filter_frame, text="卷次:").grid(row=0, column=2, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_volume = ttk.Combobox(filter_frame, width=10, state='readonly')
        self.cmb_case_volume.grid(row=0, column=3, padx=5, pady=3)

        ttk.Label(filter_frame, text="抄本:").grid(row=0, column=4, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_copy = ttk.Combobox(filter_frame, width=10, state='readonly')
        self.cmb_case_copy.grid(row=0, column=5, padx=5, pady=3)

        ttk.Label(filter_frame, text="校勘类型:").grid(row=1, column=0, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_category = ttk.Combobox(filter_frame,
            values=['全部'] + [c.value for c in CaseCategory], width=12, state='readonly')
        self.cmb_case_category.current(0)
        self.cmb_case_category.grid(row=1, column=1, padx=5, pady=3)

        ttk.Label(filter_frame, text="来源类型:").grid(row=1, column=2, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_source = ttk.Combobox(filter_frame,
            values=['全部'] + [s.value for s in CaseSourceType], width=12, state='readonly')
        self.cmb_case_source.current(0)
        self.cmb_case_source.grid(row=1, column=3, padx=5, pady=3)

        ttk.Label(filter_frame, text="处理状态:").grid(row=1, column=4, sticky=tk.W, padx=2, pady=3)
        self.cmb_case_status = ttk.Combobox(filter_frame,
            values=['全部'] + [s.value for s in CaseStatus], width=10, state='readonly')
        self.cmb_case_status.current(0)
        self.cmb_case_status.grid(row=1, column=5, padx=5, pady=3)

        ttk.Label(filter_frame, text="关键词:").grid(row=2, column=0, sticky=tk.W, padx=2, pady=3)
        self.entry_case_keyword = ttk.Entry(filter_frame, width=25)
        self.entry_case_keyword.grid(row=2, column=1, padx=5, pady=3, columnspan=2, sticky=tk.W)

        ttk.Button(filter_frame, text="🔍 筛选", command=self._load_cases_tree).grid(
            row=2, column=3, padx=5, pady=3)
        ttk.Button(filter_frame, text="🔄 重置", command=self._reset_case_filter).grid(
            row=2, column=4, padx=5, pady=3)

        content_pane = ttk.PanedWindow(frame, orient=tk.HORIZONTAL)
        content_pane.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=5)

        left_frame = ttk.Frame(content_pane)
        content_pane.add(left_frame, weight=3)

        left_label = ttk.LabelFrame(left_frame, text="判例列表", padding=5)
        left_label.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        yscroll1 = ttk.Scrollbar(left_label, orient=tk.VERTICAL)
        xscroll1 = ttk.Scrollbar(left_label, orient=tk.HORIZONTAL)
        self.tree_cases = ttk.Treeview(left_label, yscrollcommand=yscroll1.set, xscrollcommand=xscroll1.set)
        yscroll1.config(command=self.tree_cases.yview)
        xscroll1.config(command=self.tree_cases.xview)
        yscroll1.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll1.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree_cases.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.tree_cases.bind('<<TreeviewSelect>>', self._on_case_select)

        cols_case = ('case_id', 'category', 'source_type', 'book_name', 'volume', 'paragraph',
                     'copy_batch', 'original_text', 'variant_text', 'confidence', 'status',
                     'usage_count', 'accept_count', 'created_at')
        self.tree_cases['columns'] = cols_case
        for col in cols_case:
            width_map2 = {
                'case_id': 180, 'category': 80, 'source_type': 100, 'book_name': 120,
                'volume': 50, 'paragraph': 60, 'copy_batch': 90, 'original_text': 180,
                'variant_text': 180, 'confidence': 70, 'status': 70, 'usage_count': 60,
                'accept_count': 60, 'created_at': 140
            }
            anchor2 = tk.CENTER if col in ('volume', 'paragraph', 'confidence', 'status',
                                            'usage_count', 'accept_count', 'created_at') else tk.W
            self.tree_cases.heading(col, text={
                'case_id': '判例ID', 'category': '类型', 'source_type': '来源',
                'book_name': '书名', 'volume': '卷', 'paragraph': '段',
                'copy_batch': '抄本', 'original_text': '原文', 'variant_text': '异文/引文',
                'confidence': '置信度', 'status': '状态', 'usage_count': '使用',
                'accept_count': '采纳', 'created_at': '创建时间'
            }[col])
            self.tree_cases.column(col, width=width_map2.get(col, 120), anchor=anchor2, stretch=True)
        self.tree_cases['show'] = 'headings'

        right_frame = ttk.Frame(content_pane)
        content_pane.add(right_frame, weight=2)

        detail_frame = ttk.LabelFrame(right_frame, text="判例详情", padding=5)
        detail_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        self.txt_case_detail = scrolledtext.ScrolledText(detail_frame, height=12, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_case_detail.pack(fill=tk.BOTH, expand=True)
        self.txt_case_detail.config(state=tk.DISABLED)

        res_frame = ttk.LabelFrame(right_frame, text="处理结论与依据", padding=5)
        res_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=2)

        self.txt_case_resolution = scrolledtext.ScrolledText(res_frame, height=10, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_case_resolution.pack(fill=tk.BOTH, expand=True)
        self.txt_case_resolution.config(state=tk.DISABLED)

        action_frame = ttk.LabelFrame(right_frame, text="操作", padding=5)
        action_frame.pack(side=tk.TOP, fill=tk.X, pady=2)

        ttk.Button(action_frame, text="📝 沉淀当前疑点为判例",
                   command=self._on_precipitate_doubt_case).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(action_frame, text="📚 沉淀当前引文为判例",
                   command=self._on_precipitate_citation_case).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(action_frame, text="🔄 重新激活判例",
                   command=self._on_reactivate_case).pack(side=tk.LEFT, padx=3, pady=2)
        ttk.Button(action_frame, text="❌ 使判例失效",
                   command=self._on_invalidate_case).pack(side=tk.LEFT, padx=3, pady=2)

        rec_frame = ttk.LabelFrame(frame, text="当前记录的智能推荐（选中疑点/引文后显示）", padding=8)
        rec_frame.pack(side=tk.BOTTOM, fill=tk.X, padx=8, pady=5)

        rec_top = ttk.Frame(rec_frame)
        rec_top.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(rec_top, text="推荐状态筛选:").pack(side=tk.LEFT, padx=2)
        self.cmb_rec_status = ttk.Combobox(rec_top,
            values=['全部'] + [s.value for s in RecommendationStatus], width=10, state='readonly')
        self.cmb_rec_status.current(0)
        self.cmb_rec_status.pack(side=tk.LEFT, padx=5)
        self.cmb_rec_status.bind('<<ComboboxSelected>>', lambda e: self._load_recommendations_tree())

        ttk.Button(rec_top, text="🔮 为当前疑点生成推荐",
                   command=self._on_gen_rec_for_doubt).pack(side=tk.LEFT, padx=10)
        ttk.Button(rec_top, text="🔮 为当前引文生成推荐",
                   command=self._on_gen_rec_for_citation).pack(side=tk.LEFT, padx=5)

        yscroll2 = ttk.Scrollbar(rec_frame, orient=tk.VERTICAL)
        self.tree_recommendations = ttk.Treeview(rec_frame, yscrollcommand=yscroll2.set, height=8)
        yscroll2.config(command=self.tree_recommendations.yview)
        yscroll2.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree_recommendations.pack(side=tk.TOP, fill=tk.X, expand=True, pady=5)
        self.tree_recommendations.bind('<<TreeviewSelect>>', self._on_recommendation_select)

        cols_rec = ('rec_id', 'case_id', 'similarity', 'reason', 'status',
                    'created_at', 'decided_by', 'decided_at')
        self.tree_recommendations['columns'] = cols_rec
        for col in cols_rec:
            width_map3 = {
                'rec_id': 180, 'case_id': 180, 'similarity': 80, 'reason': 300,
                'status': 80, 'created_at': 140, 'decided_by': 80, 'decided_at': 140
            }
            anchor3 = tk.CENTER if col in ('similarity', 'status', 'created_at', 'decided_at') else tk.W
            self.tree_recommendations.heading(col, text={
                'rec_id': '推荐ID', 'case_id': '关联判例', 'similarity': '相似度',
                'reason': '推荐理由', 'status': '状态', 'created_at': '生成时间',
                'decided_by': '处理人', 'decided_at': '处理时间'
            }[col])
            self.tree_recommendations.column(col, width=width_map3.get(col, 120), anchor=anchor3, stretch=True)
        self.tree_recommendations['show'] = 'headings'

        rec_action_frame = ttk.Frame(rec_frame)
        rec_action_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(rec_action_frame, text="处理备注:").pack(side=tk.LEFT, padx=2)
        self.entry_rec_note = ttk.Entry(rec_action_frame, width=50)
        self.entry_rec_note.pack(side=tk.LEFT, padx=5)
        ttk.Button(rec_action_frame, text="✅ 采纳", command=self._on_accept_recommendation,
                   style='Action.TButton').pack(side=tk.LEFT, padx=8)
        ttk.Button(rec_action_frame, text="❌ 驳回", command=self._on_reject_recommendation).pack(side=tk.LEFT, padx=5)
        ttk.Button(rec_action_frame, text="✏️ 修订后采纳", command=self._on_modify_recommendation).pack(side=tk.LEFT, padx=5)

        self.txt_rec_detail = scrolledtext.ScrolledText(rec_frame, height=4, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_rec_detail.pack(side=tk.TOP, fill=tk.X, pady=3)
        self.txt_rec_detail.config(state=tk.DISABLED)

        self._current_selected_doubt_id = ''
        self._current_selected_citation_id = ''

    def _refresh_case_filters(self):
        if not hasattr(self, 'cmb_case_book'):
            return
        book_vals = ['全部']
        if self.analyzer:
            book_vals = ['全部', self.analyzer.book_name]
        self.cmb_case_book['values'] = book_vals
        if book_vals:
            self.cmb_case_book.current(0)
        vols = ['全部'] + [f'第{v}卷' for v in (self.analyzer.volumes if self.analyzer else [])]
        self.cmb_case_volume['values'] = vols
        if vols:
            self.cmb_case_volume.current(0)
        copies = ['全部'] + list(self.analyzer.copy_batches if self.analyzer else [])
        self.cmb_case_copy['values'] = copies
        if copies:
            self.cmb_case_copy.current(0)

    def _reset_case_filter(self):
        self._refresh_case_filters()
        self.cmb_case_category.current(0)
        self.cmb_case_source.current(0)
        self.cmb_case_status.current(0)
        self.entry_case_keyword.delete(0, tk.END)
        self._load_cases_tree()

    def _load_cases_tree(self):
        self.tree_cases.delete(*self.tree_cases.get_children())
        if not self.current_project:
            return
        try:
            pm = self.current_project.workflow_engine.permission_manager
            pm.set_user_role(self.current_user, self.current_role)
            pm.check_permission(self.current_user, 'view_cases')
        except Exception:
            return

        f = CaseFilter(project_id=self.current_project.project_id)

        book_filter = self.cmb_case_book.get() if hasattr(self, 'cmb_case_book') else ''
        if book_filter and book_filter != '全部':
            f.book_name = book_filter

        vol_filter = self.cmb_case_volume.get() if hasattr(self, 'cmb_case_volume') else ''
        if vol_filter and vol_filter != '全部':
            try:
                f.volume = int(vol_filter.replace('第', '').replace('卷', ''))
            except Exception:
                pass

        copy_filter = self.cmb_case_copy.get() if hasattr(self, 'cmb_case_copy') else ''
        if copy_filter and copy_filter != '全部':
            f.copy_batch = copy_filter

        cat_filter = self.cmb_case_category.get() if hasattr(self, 'cmb_case_category') else ''
        if cat_filter and cat_filter != '全部':
            for c in CaseCategory:
                if c.value == cat_filter:
                    f.category = c
                    break

        src_filter = self.cmb_case_source.get() if hasattr(self, 'cmb_case_source') else ''
        if src_filter and src_filter != '全部':
            for s in CaseSourceType:
                if s.value == src_filter:
                    f.source_type = s
                    break

        status_filter = self.cmb_case_status.get() if hasattr(self, 'cmb_case_status') else ''
        if status_filter and status_filter != '全部':
            for s in CaseStatus:
                if s.value == status_filter:
                    f.status = s
                    break

        kw = self.entry_case_keyword.get().strip() if hasattr(self, 'entry_case_keyword') else ''
        if kw:
            f.keyword = kw

        cases = self.current_project.filter_cases(f)

        for c in cases:
            display_text = c.quoted_text if (not c.variant_text and c.quoted_text) else c.variant_text
            self.tree_cases.insert('', tk.END, values=(
                c.case_id,
                c.category.value,
                c.source_type.value,
                c.book_name,
                c.volume or '',
                c.paragraph or '',
                c.copy_batch or '',
                c.original_text,
                display_text,
                f"{c.confidence:.1%}",
                c.status.value,
                c.usage_count,
                c.accept_count,
                c.created_at.strftime('%Y-%m-%d %H:%M')
            ))

    def _on_case_select(self, event=None):
        selection = self.tree_cases.selection()
        if not selection:
            return
        case_id = self.tree_cases.item(selection[0], 'values')[0]
        if not self.current_project:
            return
        case = self.current_project.get_case(case_id)
        if not case:
            return

        self.txt_case_detail.config(state=tk.NORMAL)
        self.txt_case_detail.delete('1.0', tk.END)
        content = (f"判例ID: {case.case_id}\n"
                   f"类型: {case.category.value}    来源: {case.source_type.value}\n"
                   f"书名: {case.book_name}\n")
        if case.volume:
            content += f"卷次: 第{case.volume}卷    "
        if case.paragraph:
            content += f"段落: 第{case.paragraph}段    "
        if case.copy_batch:
            content += f"抄本: {case.copy_batch}"
        content += f"\n置信度: {case.confidence:.2%}\n"
        content += f"状态: {case.status.value}"
        if case.invalidated_reason:
            content += f"    失效原因: {case.invalidated_reason}"
        content += f"\n原文: {case.original_text}\n"
        if case.variant_text:
            content += f"异文/建议: {case.variant_text}\n"
        if case.quoted_text:
            content += f"引文字段: {case.quoted_text}\n"
        if case.rule_id:
            content += f"规则ID: {case.rule_id}\n"
        if case.description:
            content += f"描述: {case.description}\n"
        content += f"创建人: {case.created_by}    创建时间: {case.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
        content += f"关联记录: {case.source_record_id or '无'}\n"
        content += f"使用次数: {case.usage_count}    采纳次数: {case.accept_count}"
        if case.tags:
            content += f"\n标签: {', '.join(case.tags)}"
        self.txt_case_detail.insert('1.0', content)
        self.txt_case_detail.config(state=tk.DISABLED)

        self.txt_case_resolution.config(state=tk.NORMAL)
        self.txt_case_resolution.delete('1.0', tk.END)
        if case.resolution:
            res_content = (f"处理结论: {case.resolution.conclusion}\n\n"
                           f"采用依据:\n{case.resolution.basis}\n")
            if case.resolution.final_text:
                res_content += f"\n最终文本: {case.resolution.final_text}\n"
            if case.resolution.notes:
                res_content += f"\n备注: {case.resolution.notes}\n"
            if case.resolution.reference_sources:
                res_content += f"\n参考出处 ({len(case.resolution.reference_sources)}条):\n"
                for i, src in enumerate(case.resolution.reference_sources, 1):
                    src_parts = [f"  {i}. 书名: {src.get('source_book', '')}"]
                    if src.get('source_volume'):
                        src_parts.append(f"卷{src['source_volume']}")
                    if src.get('source_paragraph'):
                        src_parts.append(f"段{src['source_paragraph']}")
                    if src.get('source_chapter'):
                        src_parts.append(f"章节: {src['source_chapter']}")
                    if src.get('source_page'):
                        src_parts.append(f"页码: {src['source_page']}")
                    res_content += '  ' + ' '.join(src_parts) + '\n'
                    if src.get('source_text'):
                        res_content += f"     原文: {src['source_text'][:100]}\n"
            self.txt_case_resolution.insert('1.0', res_content)
        else:
            self.txt_case_resolution.insert('1.0', '此判例暂无处理结论信息')
        self.txt_case_resolution.config(state=tk.DISABLED)

    def _on_case_library_stats(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        stats = self.current_project.get_case_statistics()
        msg = "校勘判例库统计\n\n"
        msg += f"判例总数: {stats.get('total_cases', 0)}\n"
        msg += f"  有效判例: {stats.get('active_cases', 0)}\n"
        msg += f"  已失效: {stats.get('invalidated_cases', 0)}\n"
        msg += f"  已归档: {stats.get('archived_cases', 0)}\n\n"
        msg += f"推荐总数: {stats.get('total_recommendations', 0)}\n"
        msg += f"  待处理: {stats.get('pending_recommendations', 0)}\n"
        msg += f"  已采纳: {stats.get('accepted_recommendations', 0)}\n"
        msg += f"  已驳回: {stats.get('rejected_recommendations', 0)}\n"
        msg += f"  已修订: {stats.get('modified_recommendations', 0)}\n"
        msg += f"  已失效: {stats.get('invalidated_recommendations', 0)}\n"
        ar = stats.get('accept_rate', 0.0)
        msg += f"  采纳率: {ar:.1%}\n\n"
        msg += "按来源统计:\n"
        for k, v in stats.get('by_source_type', {}).items():
            msg += f"  {k}: {v}\n"
        msg += "\n按类型统计:\n"
        for k, v in stats.get('by_category', {}).items():
            msg += f"  {k}: {v}\n"
        messagebox.showinfo("判例库统计", msg)

    def _on_precipitate_doubt_case(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        doubt_id = getattr(self, '_current_selected_doubt_id', '')
        if not doubt_id:
            messagebox.showinfo("提示", "请先在【人工复核工作流】Tab中选中一个疑点")
            return
        try:
            case = self.current_project.create_case_from_doubt(
                self.current_user, doubt_id, extra_notes='人工沉淀'
            )
            self.lbl_status.config(text=f"已沉淀判例: {case.case_id}")
            messagebox.showinfo("成功", f"已成功将疑点沉淀为判例:\n{case.case_id}")
            self._load_cases_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_precipitate_citation_case(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        citation_id = getattr(self, '_current_selected_citation_id', '')
        if not citation_id:
            messagebox.showinfo("提示", "请先在【引文溯源与互证分析】Tab中选中一条引文")
            return
        try:
            case = self.current_project.create_case_from_citation(
                self.current_user, citation_id, extra_notes='人工沉淀'
            )
            self.lbl_status.config(text=f"已沉淀判例: {case.case_id}")
            messagebox.showinfo("成功", f"已成功将引文沉淀为判例:\n{case.case_id}")
            self._load_cases_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_reactivate_case(self):
        selection = self.tree_cases.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个判例")
            return
        case_id = self.tree_cases.item(selection[0], 'values')[0]
        try:
            self.current_project.reactivate_case(self.current_user, case_id)
            self.lbl_status.config(text=f"已重新激活判例: {case_id}")
            self._load_cases_tree()
            self._on_case_select()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_invalidate_case(self):
        selection = self.tree_cases.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一个判例")
            return
        case_id = self.tree_cases.item(selection[0], 'values')[0]
        reason = ''
        win = tk.Toplevel(self.root)
        win.title("失效原因")
        win.geometry("400x180")
        win.transient(self.root)
        win.grab_set()
        ttk.Label(win, text="请输入失效原因:", style='Subtitle.TLabel').pack(pady=10)
        entry_reason = ttk.Entry(win, width=40)
        entry_reason.pack(pady=5)

        def do_invalidate():
            nonlocal reason
            reason = entry_reason.get().strip() or '人工操作失效'
            try:
                self.current_project.invalidate_case(self.current_user, case_id, reason)
                self.lbl_status.config(text=f"已使判例失效: {case_id}")
                win.destroy()
                self._load_cases_tree()
                self._on_case_select()
            except Exception as e:
                messagebox.showerror("失败", str(e))

        ttk.Button(win, text="确认失效", command=do_invalidate, style='Action.TButton').pack(pady=15)

    def _on_gen_rec_for_doubt(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        doubt_id = getattr(self, '_current_selected_doubt_id', '')
        if not doubt_id:
            messagebox.showinfo("提示", "请先在【人工复核工作流】Tab中选中一个疑点")
            return
        try:
            recs = self.current_project.generate_recommendations_for_doubt(
                self.current_user, doubt_id, top_k=5
            )
            self.lbl_status.config(text=f"为疑点{doubt_id}生成了{len(recs)}条推荐")
            messagebox.showinfo("完成", f"已为疑点{doubt_id}生成{len(recs)}条智能推荐")
            self._load_recommendations_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_gen_rec_for_citation(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        citation_id = getattr(self, '_current_selected_citation_id', '')
        if not citation_id:
            messagebox.showinfo("提示", "请先在【引文溯源与互证分析】Tab中选中一条引文")
            return
        try:
            recs = self.current_project.generate_recommendations_for_citation(
                self.current_user, citation_id, top_k=5
            )
            self.lbl_status.config(text=f"为引文{citation_id}生成了{len(recs)}条推荐")
            messagebox.showinfo("完成", f"已为引文{citation_id}生成{len(recs)}条智能推荐")
            self._load_recommendations_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _load_recommendations_tree(self):
        self.tree_recommendations.delete(*self.tree_recommendations.get_children())
        if not self.current_project:
            return
        try:
            pm = self.current_project.workflow_engine.permission_manager
            pm.set_user_role(self.current_user, self.current_role)
            pm.check_permission(self.current_user, 'view_recommendations')
        except Exception:
            return

        target_id = getattr(self, '_current_selected_doubt_id', '') or getattr(self, '_current_selected_citation_id', '')
        if not target_id:
            return

        status_val = None
        status_filter = self.cmb_rec_status.get() if hasattr(self, 'cmb_rec_status') else ''
        if status_filter and status_filter != '全部':
            for s in RecommendationStatus:
                if s.value == status_filter:
                    status_val = s
                    break

        recs = self.current_project.get_recommendations_for_target(target_id, status=status_val)
        for r in recs:
            self.tree_recommendations.insert('', tk.END, values=(
                r.recommendation_id,
                r.case_id,
                f"{r.similarity.overall:.2%}",
                r.reason,
                r.status.value,
                r.created_at.strftime('%Y-%m-%d %H:%M'),
                r.decided_by or '-',
                r.decided_at.strftime('%Y-%m-%d %H:%M') if r.decided_at else '-'
            ))

    def _on_recommendation_select(self, event=None):
        selection = self.tree_recommendations.selection()
        if not selection or not self.current_project:
            return
        rec_id = self.tree_recommendations.item(selection[0], 'values')[0]
        rec = self.current_project.workflow_engine.get_recommendation(rec_id)
        if not rec:
            return
        case = self.current_project.get_case(rec.case_id)

        self.txt_rec_detail.config(state=tk.NORMAL)
        self.txt_rec_detail.delete('1.0', tk.END)
        content = f"推荐ID: {rec.recommendation_id}\n"
        content += f"关联判例: {rec.case_id}\n"
        sim = rec.similarity
        content += (f"相似度分解: 综合{sim.overall:.2%} = 文本{sim.text_similarity:.0%}×40% + "
                   f"类型{sim.category_match:.0%}×20% + 同书{sim.book_match:.0%}×15% + "
                   f"卷次{sim.volume_proximity:.0%}×10% + 来源{sim.source_type_match:.0%}×10% + 规则{sim.rule_match:.0%}×5%\n")
        content += f"推荐理由: {rec.reason}\n"
        if case and case.resolution:
            content += f"\n【判例处理结论】{case.resolution.conclusion}\n"
            content += f"【采用依据】{case.resolution.basis}\n"
            if case.resolution.final_text:
                content += f"【建议最终文本】{case.resolution.final_text}\n"
            if case.resolution.reference_sources:
                content += f"【参考出处】{len(case.resolution.reference_sources)}条\n"
        if rec.operation_history:
            content += "\n操作历史:\n"
            for h in rec.operation_history:
                content += f"  {h.get('timestamp', '')} {h.get('operator', '')}[{h.get('operator_role', '')}] {h.get('action', '')}: {h.get('content', '')}\n"
        if rec.invalidated_reason:
            content += f"\n失效原因: {rec.invalidated_reason}"
        self.txt_rec_detail.insert('1.0', content)
        self.txt_rec_detail.config(state=tk.DISABLED)

    def _on_accept_recommendation(self):
        selection = self.tree_recommendations.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条推荐")
            return
        rec_id = self.tree_recommendations.item(selection[0], 'values')[0]
        note = self.entry_rec_note.get().strip()
        try:
            self.current_project.accept_recommendation(self.current_user, rec_id, note)
            self.lbl_status.config(text=f"已采纳推荐: {rec_id}")
            self.entry_rec_note.delete(0, tk.END)
            self._load_recommendations_tree()
            self._on_recommendation_select()
            self._load_cases_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_reject_recommendation(self):
        selection = self.tree_recommendations.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条推荐")
            return
        rec_id = self.tree_recommendations.item(selection[0], 'values')[0]
        reason = self.entry_rec_note.get().strip()
        try:
            self.current_project.reject_recommendation(self.current_user, rec_id, reason)
            self.lbl_status.config(text=f"已驳回推荐: {rec_id}")
            self.entry_rec_note.delete(0, tk.END)
            self._load_recommendations_tree()
            self._on_recommendation_select()
            self._load_cases_tree()
        except Exception as e:
            messagebox.showerror("失败", str(e))

    def _on_modify_recommendation(self):
        selection = self.tree_recommendations.selection()
        if not selection:
            messagebox.showinfo("提示", "请先选择一条推荐")
            return
        rec_id = self.tree_recommendations.item(selection[0], 'values')[0]
        case_id = self.tree_recommendations.item(selection[0], 'values')[1]
        case = self.current_project.get_case(case_id) if self.current_project else None
        if not case:
            messagebox.showerror("错误", "关联判例不存在")
            return

        win = tk.Toplevel(self.root)
        win.title("修订推荐内容")
        win.geometry("550x450")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="处理结论:", style='Subtitle.TLabel').grid(row=0, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_conclusion = scrolledtext.ScrolledText(win, width=50, height=3)
        txt_conclusion.grid(row=0, column=1, padx=10, pady=8)
        if case.resolution:
            txt_conclusion.insert('1.0', case.resolution.conclusion)

        ttk.Label(win, text="采用依据:", style='Subtitle.TLabel').grid(row=1, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_basis = scrolledtext.ScrolledText(win, width=50, height=4)
        txt_basis.grid(row=1, column=1, padx=10, pady=8)
        if case.resolution:
            txt_basis.insert('1.0', case.resolution.basis)

        ttk.Label(win, text="建议最终文本:", style='Subtitle.TLabel').grid(row=2, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_final = scrolledtext.ScrolledText(win, width=50, height=3)
        txt_final.grid(row=2, column=1, padx=10, pady=8)
        if case.resolution:
            txt_final.insert('1.0', case.resolution.final_text)

        ttk.Label(win, text="备注说明:", style='Subtitle.TLabel').grid(row=3, column=0, sticky=tk.NW, padx=10, pady=8)
        txt_note = scrolledtext.ScrolledText(win, width=50, height=3)
        txt_note.grid(row=3, column=1, padx=10, pady=8)

        def do_modify():
            modified = {
                'conclusion': txt_conclusion.get('1.0', tk.END).strip(),
                'basis': txt_basis.get('1.0', tk.END).strip(),
                'final_text': txt_final.get('1.0', tk.END).strip(),
                'note': txt_note.get('1.0', tk.END).strip()
            }
            try:
                self.current_project.modify_recommendation(
                    self.current_user, rec_id, modified,
                    note=txt_note.get('1.0', tk.END).strip()
                )
                self.lbl_status.config(text=f"已修订并采纳推荐: {rec_id}")
                win.destroy()
                self._load_recommendations_tree()
                self._on_recommendation_select()
                self._load_cases_tree()
            except Exception as e:
                messagebox.showerror("失败", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.grid(row=4, column=0, columnspan=2, pady=15)
        ttk.Button(btn_frame, text="确认修订并采纳", command=do_modify, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=10)

    def _load_citations_tree(self):
        self.tree_citations.delete(*self.tree_citations.get_children())
        if not self.current_project:
            return

        try:
            pm = self.current_project.workflow_engine.permission_manager
            pm.set_user_role(self.current_user, self.current_role)
            pm.check_permission(self.current_user, 'view_citations')
        except Exception:
            return

        status_filter = self.cmb_citation_status.get() if hasattr(self, 'cmb_citation_status') else ''
        type_filter = self.cmb_citation_type.get() if hasattr(self, 'cmb_citation_type') else ''
        book_filter = self.cmb_citation_book.get() if hasattr(self, 'cmb_citation_book') else ''
        vol_filter = self.cmb_citation_volume.get() if hasattr(self, 'cmb_citation_volume') else ''
        copy_filter = self.cmb_citation_copy.get() if hasattr(self, 'cmb_citation_copy') else ''

        status_val = None
        if status_filter and status_filter != '全部':
            for s in CitationStatusEnum:
                if s.value == status_filter:
                    status_val = s
                    break

        type_val = None
        if type_filter and type_filter != '全部':
            for t in CitationTypeEnum:
                if t.value == type_filter:
                    type_val = t
                    break

        vol_val = None
        if vol_filter and vol_filter != '全部':
            try:
                vol_val = int(vol_filter.replace('第', '').replace('卷', ''))
            except Exception:
                pass

        copy_val = None
        if copy_filter and copy_filter != '全部':
            copy_val = copy_filter

        citations = self.current_project.get_citations(status_val, type_val, vol_val, copy_val)

        if book_filter and book_filter != '全部':
            citations = [c for c in citations if self.current_project.book_name == book_filter]

        for c in citations:
            self.tree_citations.insert('', tk.END, values=(
                c.citation_id,
                c.citation_type.value,
                c.volume,
                c.paragraph,
                c.copy_batch,
                c.quoted_text,
                f"{c.confidence:.1%}",
                c.match_basis,
                c.status.value,
                c.created_at.strftime('%Y-%m-%d %H:%M'),
                c.confirmed_by or '-'
            ))

    def _refresh_citation_filters(self):
        if not hasattr(self, 'cmb_citation_volume'):
            return
        book_vals = ['全部']
        if self.analyzer:
            book_vals = ['全部', self.analyzer.book_name]
        self.cmb_citation_book['values'] = book_vals
        if book_vals:
            self.cmb_citation_book.current(0)

        vols = ['全部'] + [f'第{v}卷' for v in (self.analyzer.volumes if self.analyzer else [])]
        self.cmb_citation_volume['values'] = vols
        if vols:
            self.cmb_citation_volume.current(0)

        copies = ['全部'] + list(self.analyzer.copy_batches if self.analyzer else [])
        self.cmb_citation_copy['values'] = copies
        if copies:
            self.cmb_citation_copy.current(0)

    def _build_export_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📤 校勘结果导出")

        left_frame = ttk.LabelFrame(frame, text="导出选项", padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=8, pady=8)

        ttk.Label(left_frame, text="导出范围:", style='Subtitle.TLabel').pack(anchor=tk.W, pady=5)
        self.chk_export_report = ttk.Checkbutton(left_frame, text="校勘报告 (CSV)")
        self.chk_export_report.state(['selected'])
        self.chk_export_report.pack(anchor=tk.W, pady=2)
        self.chk_export_variant = ttk.Checkbutton(left_frame, text="异文清单 (CSV)")
        self.chk_export_variant.state(['selected'])
        self.chk_export_variant.pack(anchor=tk.W, pady=2)
        self.chk_export_review = ttk.Checkbutton(left_frame, text="复核日志 (CSV)")
        self.chk_export_review.state(['selected'])
        self.chk_export_review.pack(anchor=tk.W, pady=2)
        self.chk_export_citation = ttk.Checkbutton(left_frame, text="引文溯源表 (CSV)")
        self.chk_export_citation.state(['!selected'])
        self.chk_export_citation.pack(anchor=tk.W, pady=2)
        self.chk_export_misquote = ttk.Checkbutton(left_frame, text="疑似误引清单 (CSV)")
        self.chk_export_misquote.state(['!selected'])
        self.chk_export_misquote.pack(anchor=tk.W, pady=2)
        self.chk_export_audit = ttk.Checkbutton(left_frame, text="审计日志 (CSV)")
        self.chk_export_audit.state(['!selected'])
        self.chk_export_audit.pack(anchor=tk.W, pady=2)
        self.chk_export_md = ttk.Checkbutton(left_frame, text="校勘报告书 (Markdown)")
        self.chk_export_md.state(['selected'])
        self.chk_export_md.pack(anchor=tk.W, pady=2)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(left_frame, text="卷次筛选:", style='Subtitle.TLabel').pack(anchor=tk.W, pady=5)
        self.cmb_export_volume = ttk.Combobox(left_frame, width=15, state='readonly')
        self.cmb_export_volume.pack(anchor=tk.W, pady=2)

        ttk.Separator(left_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Button(left_frame, text="📁 选择导出目录", command=self._on_select_export_dir).pack(anchor=tk.W, pady=5)
        self.lbl_export_dir = ttk.Label(left_frame, text="未选择目录", foreground='#666')
        self.lbl_export_dir.pack(anchor=tk.W, pady=2)

        ttk.Button(left_frame, text="🚀 开始导出", command=self._on_do_export, style='Action.TButton').pack(anchor=tk.W, pady=15)

        right_frame = ttk.LabelFrame(frame, text="导出预览", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.txt_export_preview = scrolledtext.ScrolledText(right_frame, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_export_preview.pack(fill=tk.BOTH, expand=True)
        self.txt_export_preview.config(state=tk.DISABLED)

    def _build_audit_tab(self):
        frame = ttk.Frame(self.notebook)
        self.notebook.add(frame, text="📜 审计日志")

        filter_frame = ttk.Frame(frame, padding=8)
        filter_frame.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(filter_frame, text="操作人:").pack(side=tk.LEFT, padx=2)
        self.entry_audit_user = ttk.Entry(filter_frame, width=12)
        self.entry_audit_user.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="操作类型:").pack(side=tk.LEFT, padx=10)
        self.cmb_audit_type = ttk.Combobox(filter_frame, width=15, state='readonly')
        self.cmb_audit_type.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="起始时间:").pack(side=tk.LEFT, padx=10)
        self.entry_audit_start = ttk.Entry(filter_frame, width=18)
        self.entry_audit_start.pack(side=tk.LEFT, padx=5)

        ttk.Label(filter_frame, text="结束时间:").pack(side=tk.LEFT, padx=10)
        self.entry_audit_end = ttk.Entry(filter_frame, width=18)
        self.entry_audit_end.pack(side=tk.LEFT, padx=5)

        ttk.Button(filter_frame, text="查询", command=self._on_audit_query).pack(side=tk.LEFT, padx=10)
        ttk.Button(filter_frame, text="重置", command=self._reset_audit_filter).pack(side=tk.LEFT, padx=2)

        timeline_frame = ttk.LabelFrame(frame, text="操作时间线", padding=8)
        timeline_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.txt_audit_timeline = scrolledtext.ScrolledText(timeline_frame, font=('SimHei', 10), wrap=tk.WORD)
        self.txt_audit_timeline.pack(fill=tk.BOTH, expand=True)
        self.txt_audit_timeline.config(state=tk.DISABLED)

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
        ttk.Label(btn_frame, text="（修改后异文统计会自动重新计算）",
                  foreground='#2E8B57').pack(side=tk.LEFT, padx=10)

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

    def _on_role_change(self, event=None):
        role_str = self.cmb_role.get()
        for role in Role:
            if role.value == role_str:
                self.current_role = role
                break
        self.current_user = self.entry_user.get().strip() or 'unknown'
        self.lbl_status.config(text=f"当前用户: {self.current_user} [{self.current_role.value}]")
        self._refresh_all()

    def _on_create_project(self):
        try:
            self.project_manager.check_permission(self.current_user, self.current_role, 'create_project')
        except Exception as e:
            messagebox.showerror("权限不足", str(e))
            return

        win = tk.Toplevel(self.root)
        win.title("新建校勘项目")
        win.geometry("500x400")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="项目名称:", style='Subtitle.TLabel').grid(row=0, column=0, sticky=tk.W, padx=10, pady=10)
        entry_name = ttk.Entry(win, width=40)
        entry_name.grid(row=0, column=1, padx=10, pady=10)
        entry_name.insert(0, "论语集注校勘项目")

        ttk.Label(win, text="书名:", style='Subtitle.TLabel').grid(row=1, column=0, sticky=tk.W, padx=10, pady=10)
        entry_book = ttk.Entry(win, width=40)
        entry_book.grid(row=1, column=1, padx=10, pady=10)
        entry_book.insert(0, "论语集注")

        ttk.Label(win, text="卷次(逗号分隔):", style='Subtitle.TLabel').grid(row=2, column=0, sticky=tk.W, padx=10, pady=10)
        entry_vols = ttk.Entry(win, width=40)
        entry_vols.grid(row=2, column=1, padx=10, pady=10)
        entry_vols.insert(0, "1,2")

        ttk.Label(win, text="抄本批次(逗号分隔):", style='Subtitle.TLabel').grid(row=3, column=0, sticky=tk.W, padx=10, pady=10)
        entry_batches = ttk.Entry(win, width=40)
        entry_batches.grid(row=3, column=1, padx=10, pady=10)
        entry_batches.insert(0, "宋刊本,元抄本,明抄本")

        ttk.Label(win, text="描述:", style='Subtitle.TLabel').grid(row=4, column=0, sticky=tk.NW, padx=10, pady=10)
        txt_desc = scrolledtext.ScrolledText(win, width=40, height=5)
        txt_desc.grid(row=4, column=1, padx=10, pady=10)

        def do_create():
            name = entry_name.get().strip()
            book = entry_book.get().strip()
            vols = [int(v.strip()) for v in entry_vols.get().split(',') if v.strip()]
            batches = [b.strip() for b in entry_batches.get().split(',') if b.strip()]
            desc = txt_desc.get('1.0', tk.END).strip()

            if not name or not book:
                messagebox.showerror("错误", "项目名称和书名为必填项")
                return

            try:
                project = self.project_manager.create_project(
                    creator=self.current_user,
                    project_name=name,
                    book_name=book,
                    volumes=vols,
                    copy_batches=batches,
                    description=desc
                )
                project.assign_user(self.current_user, self.current_user, self.current_role)
                messagebox.showinfo("成功", f"项目创建成功！\n项目ID: {project.project_id}")
                win.destroy()
                self._load_projects_tree()
            except Exception as e:
                messagebox.showerror("创建失败", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="创建", command=do_create, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=10)

    def _on_import_to_project(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        try:
            self.current_project.workflow_engine.permission_manager.check_permission(
                self.current_user, self.current_role, 'import_data')
        except Exception as e:
            messagebox.showerror("权限不足", str(e))
            return

        file_path = filedialog.askopenfilename(
            title="选择古籍抄本CSV数据文件",
            filetypes=[("CSV文件", "*.csv"), ("所有文件", "*.*")]
        )
        if not file_path:
            return

        try:
            df, errors, book_name = validate_csv(file_path)
            if book_name != self.current_project.config.book_name:
                messagebox.showerror("错误", f"导入数据的书名【{book_name}】与项目书名【{self.current_project.config.book_name}】不符")
                return
            analyzer = CollationAnalyzer(df, book_name)
            self.current_project.associate_analyzer(self.current_user, analyzer)
            self.analyzer = analyzer
            self.validation_errors = errors
            self.current_file = file_path
            self.lbl_status.config(text=f"已导入数据到项目: {self.current_project.config.project_name} | 有效: {len(df)}行")
            self._refresh_all()
            if errors:
                messagebox.showwarning("警告", f"导入完成，但有 {len(errors)} 行数据验证失败，已跳过")
        except Exception as e:
            messagebox.showerror("导入失败", str(e))

    def _on_assign_user(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        try:
            self.current_project.workflow_engine.permission_manager.check_permission(
                self.current_user, self.current_role, 'assign_role')
        except Exception as e:
            messagebox.showerror("权限不足", str(e))
            return

        win = tk.Toplevel(self.root)
        win.title("分配项目用户")
        win.geometry("450x200")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="用户名:", style='Subtitle.TLabel').grid(row=0, column=0, sticky=tk.W, padx=10, pady=15)
        entry_user = ttk.Entry(win, width=25)
        entry_user.grid(row=0, column=1, padx=10, pady=15)

        ttk.Label(win, text="角色:", style='Subtitle.TLabel').grid(row=1, column=0, sticky=tk.W, padx=10, pady=15)
        cmb_role = ttk.Combobox(win, values=[r.value for r in Role], width=20, state='readonly')
        cmb_role.current(2)
        cmb_role.grid(row=1, column=1, padx=10, pady=15)

        def do_assign():
            user = entry_user.get().strip()
            role_str = cmb_role.get()
            if not user:
                messagebox.showerror("错误", "请输入用户名")
                return
            role = None
            for r in Role:
                if r.value == role_str:
                    role = r
                    break
            try:
                self.current_project.assign_user(self.current_user, user, role)
                messagebox.showinfo("成功", f"已分配用户 {user} 为 {role.value}")
                win.destroy()
                self._load_members_tree()
                self._load_projects_tree()
            except Exception as e:
                messagebox.showerror("分配失败", str(e))

        btn_frame = ttk.Frame(win)
        btn_frame.grid(row=2, column=0, columnspan=2, pady=20)
        ttk.Button(btn_frame, text="分配", command=do_assign, style='Action.TButton').pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=10)

    def _on_start_project(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        try:
            self.current_project.start(self.current_user)
            self.lbl_status.config(text=f"项目已启动: {self.current_project.config.project_name}")
            self._load_projects_tree()
            self._load_project_detail()
        except Exception as e:
            messagebox.showerror("操作失败", str(e))

    def _on_pause_project(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        try:
            self.current_project.pause(self.current_user)
            self.lbl_status.config(text=f"项目已暂停: {self.current_project.config.project_name}")
            self._load_projects_tree()
            self._load_project_detail()
        except Exception as e:
            messagebox.showerror("操作失败", str(e))

    def _on_project_stats(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择一个项目")
            return
        stats = self.current_project.get_stats()
        msg = f"项目统计 - {self.current_project.config.project_name}\n\n"
        msg += f"总疑点: {stats.get('total_doubts', 0)}\n"
        msg += f"待复核: {stats.get('pending_doubts', 0)}\n"
        msg += f"处理中: {stats.get('processing_doubts', 0)}\n"
        msg += f"已复核: {stats.get('reviewed_doubts', 0)}\n"
        msg += f"已驳回: {stats.get('rejected_doubts', 0)}\n"
        msg += f"已解决: {stats.get('resolved_doubts', 0)}\n"
        msg += f"已失效: {stats.get('invalid_doubts', 0)}\n"
        msg += f"数据记录: {stats.get('total_records', 0)}\n"
        msg += f"项目成员: {stats.get('total_members', 0)}\n"
        messagebox.showinfo("项目统计", msg)

    def _on_project_select(self, event=None):
        selection = self.tree_projects.selection()
        if not selection:
            return
        project_id = self.tree_projects.item(selection[0], 'values')[0]
        self.current_project = self.project_manager.get_project(project_id)
        if self.current_project and self.current_project.analyzer:
            self.analyzer = self.current_project.analyzer
        self.lbl_project_info.config(text=f"【{self.current_project.config.project_name}】")
        self._load_project_detail()
        self._load_doubts_tree()
        self._load_review_tree()
        self._load_citations_tree()
        self._refresh_citation_filters()
        self._refresh_volume_filter()

    def _on_detect_all(self):
        if not self.current_project or not self.current_project.analyzer:
            messagebox.showinfo("提示", "请先选择项目并导入数据")
            return
        try:
            detect_types = []
            if 'selected' in self.chk_detect_wrong.state():
                detect_types.append(CollationType.WRONG_CHAR)
            if 'selected' in self.chk_detect_missing.state():
                detect_types.append(CollationType.MISSING_TEXT)
            if 'selected' in self.chk_detect_extra.state():
                detect_types.append(CollationType.EXTRA_TEXT)
            if 'selected' in self.chk_detect_reversed.state():
                detect_types.append(CollationType.REVERSED_TEXT)
            if 'selected' in self.chk_detect_number.state():
                detect_types.append(CollationType.NUMBER_BREAK)

            if not detect_types:
                messagebox.showinfo("提示", "请至少选择一种检测类型")
                return

            summary = self.current_project.run_doubt_detection(
                operator=self.current_user,
                detect_types=detect_types
            )
            msg = f"疑点检测完成！\n\n"
            msg += f"检测到: {summary.total_detected} 个\n"
            msg += f"新增: {summary.new_created} 个\n"
            msg += f"跳过重复: {summary.duplicates_skipped} 个\n\n"
            msg += "按类型统计:\n"
            for type_name, count in summary.by_type.items():
                msg += f"  {type_name}: {count}个\n"
            self.lbl_status.config(text=f"检测完成: 新增{summary.new_created}个疑点")
            messagebox.showinfo("检测完成", msg)
            self._load_doubts_tree()
            self._load_review_tree()
            self._load_projects_tree()
        except Exception as e:
            messagebox.showerror("检测失败", str(e))

    def _on_detect_volume(self):
        if not self.current_project or not self.current_project.analyzer:
            messagebox.showinfo("提示", "请先选择项目并导入数据")
            return
        vols = self.current_project.analyzer.volumes
        if not vols:
            messagebox.showinfo("提示", "无可检测的卷次")
            return
        win = tk.Toplevel(self.root)
        win.title("按卷检测")
        win.geometry("300x150")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="选择卷次:").pack(pady=15)
        cmb = ttk.Combobox(win, values=[f'第{v}卷' for v in vols], state='readonly', width=15)
        cmb.current(0)
        cmb.pack(pady=5)

        def do_detect():
            v = int(cmb.get().replace('第', '').replace('卷', ''))
            try:
                summary = self.doubt_detector.detect_for_volume(
                    self.current_project.analyzer,
                    self.current_project.project_id,
                    v,
                    self.current_user
                )
                for dr in summary.results:
                    try:
                        self.current_project.workflow_engine.create_doubt(
                            creator=self.current_user,
                            project_id=dr.project_id,
                            collation_type=dr.collation_type,
                            volume=dr.volume,
                            paragraph=dr.paragraph,
                            copy_batch=dr.copy_batch,
                            original_text=dr.original_text,
                            suggested_text=dr.suggested_text,
                            confidence=dr.confidence,
                            reason=dr.reason,
                            rule_id=dr.rule_id
                        )
                    except Exception:
                        pass
                self.lbl_status.config(text=f"第{v}卷检测完成: 新增{summary.new_created}个疑点")
                messagebox.showinfo("完成", f"第{v}卷检测完成\n新增: {summary.new_created}个")
                win.destroy()
                self._load_doubts_tree()
                self._load_review_tree()
            except Exception as e:
                messagebox.showerror("检测失败", str(e))

        ttk.Button(win, text="检测", command=do_detect, style='Action.TButton').pack(pady=10)

    def _on_detection_stats(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        stats = self.current_project.workflow_engine.get_doubt_stats(self.current_project.project_id)
        msg = "疑点统计\n\n"
        for k, v in stats.items():
            msg += f"{k}: {v}\n"
        messagebox.showinfo("疑点统计", msg)

    def _on_doubt_select(self, event=None):
        selection = self.tree_doubts.selection()
        if not selection:
            return
        doubt_id = self.tree_doubts.item(selection[0], 'values')[0]
        self._current_selected_doubt_id = doubt_id
        self._current_selected_citation_id = ''
        if hasattr(self, '_load_recommendations_tree'):
            self._load_recommendations_tree()
        doubt = self.current_project.workflow_engine.get_doubt(doubt_id)
        if not doubt:
            return
        self.txt_doubt_detail.config(state=tk.NORMAL)
        self.txt_doubt_detail.delete('1.0', tk.END)
        content = (f"疑点ID: {doubt.doubt_id}\n"
                   f"类型: {doubt.collation_type}\n"
                   f"位置: 第{doubt.volume}卷 第{doubt.paragraph}段 ({doubt.copy_batch})\n"
                   f"原文: {doubt.original_text}\n"
                   f"建议: {doubt.suggested_text}\n"
                   f"置信度: {doubt.confidence}\n"
                   f"检测原因: {doubt.reason}\n"
                   f"状态: {doubt.status.value}\n"
                   f"创建人: {doubt.created_by}  {doubt.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                   f"指派人: {doubt.assignee or '未指派'}\n"
                   f"失效原因: {doubt.invalid_reason or '无'}\n"
                   f"数据指纹: {doubt.data_fingerprint}")
        self.txt_doubt_detail.insert('1.0', content)
        self.txt_doubt_detail.config(state=tk.DISABLED)

    def _on_review_select(self, event=None):
        selection = self.tree_review.selection()
        if not selection:
            return
        doubt_id = self.tree_review.item(selection[0], 'values')[0]
        self._current_selected_doubt_id = doubt_id
        self._current_selected_citation_id = ''
        if hasattr(self, '_load_recommendations_tree'):
            self._load_recommendations_tree()
        doubt = self.current_project.workflow_engine.get_doubt(doubt_id)
        if not doubt:
            return
        self.lbl_review_detail.config(text=f"疑点: {doubt.doubt_id} [{doubt.status.value}]")
        self.txt_review_detail.config(state=tk.NORMAL)
        self.txt_review_detail.delete('1.0', tk.END)
        content = (f"类型: {doubt.collation_type}    位置: 第{doubt.volume}卷 第{doubt.paragraph}段 ({doubt.copy_batch})\n"
                   f"原文: {doubt.original_text}\n"
                   f"建议: {doubt.suggested_text}\n"
                   f"置信度: {doubt.confidence}    原因: {doubt.reason}\n"
                   f"创建人: {doubt.created_by}    指派人: {doubt.assignee or '未指派'}")
        self.txt_review_detail.insert('1.0', content)
        self.txt_review_detail.config(state=tk.DISABLED)

        self.txt_review_history.config(state=tk.NORMAL)
        self.txt_review_history.delete('1.0', tk.END)
        for h in doubt.review_history:
            time_str = h['timestamp'].strftime('%Y-%m-%d %H:%M:%S')
            self.txt_review_history.insert(tk.END,
                f"{time_str} {h['reviewer']}[{h['reviewer_role']}] {h['action']}: {h['content']}\n")
        self.txt_review_history.config(state=tk.DISABLED)

    def _on_submit_review(self):
        selection = self.tree_review.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择要复核的疑点")
            return
        doubt_id = self.tree_review.item(selection[0], 'values')[0]
        action_str = self.cmb_review_action.get()
        content = self.txt_review_comment.get('1.0', tk.END).strip()
        new_assignee = self.entry_reassign.get().strip() or None

        if not content:
            messagebox.showinfo("提示", "请填写复核意见")
            return

        action = None
        for a in ReviewAction:
            if a.value == action_str:
                action = a
                break

        try:
            doubt = self.current_project.workflow_engine.review_doubt(
                reviewer=self.current_user,
                doubt_id=doubt_id,
                action=action,
                content=content,
                new_assignee=new_assignee
            )
            self.lbl_status.config(text=f"复核成功: {doubt_id} -> {doubt.status.value}")
            self.txt_review_comment.delete('1.0', tk.END)
            self.entry_reassign.delete(0, tk.END)
            self._load_review_tree()
            self._load_doubts_tree()
            self._on_review_select()
        except Exception as e:
            messagebox.showerror("复核失败", str(e))

    def _on_reactivate_doubt(self):
        selection = self.tree_review.selection()
        if not selection:
            messagebox.showinfo("提示", "请选择要重新激活的疑点")
            return
        doubt_id = self.tree_review.item(selection[0], 'values')[0]
        try:
            doubt = self.current_project.workflow_engine.reactivate_doubt(self.current_user, doubt_id)
            self.lbl_status.config(text=f"已重新激活: {doubt_id}")
            self._load_review_tree()
            self._load_doubts_tree()
        except Exception as e:
            messagebox.showerror("操作失败", str(e))

    def _on_select_export_dir(self):
        out_dir = filedialog.askdirectory(title="选择导出目录")
        if out_dir:
            self.lbl_export_dir.config(text=out_dir)

    def _on_do_export(self):
        if not self.current_project or not self.current_project.analyzer:
            messagebox.showinfo("提示", "请先选择项目并导入数据")
            return
        out_dir = self.lbl_export_dir.cget('text')
        if out_dir == '未选择目录':
            messagebox.showinfo("提示", "请先选择导出目录")
            return

        volume = None
        vol_str = self.cmb_export_volume.get()
        if vol_str and vol_str != '全卷':
            volume = int(vol_str.replace('第', '').replace('卷', ''))

        try:
            exporter = CollationExporter(self.current_project)
            results = []

            if 'selected' in self.chk_export_report.state():
                r = exporter.export_collation_report(out_dir, volume, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_variant.state():
                r = exporter.export_variant_list(out_dir, volume, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_review.state():
                r = exporter.export_review_log(out_dir, volume, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_citation.state():
                r = exporter.export_citation_table(out_dir, volume, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_misquote.state():
                r = exporter.export_misquote_list(out_dir, volume, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_audit.state():
                r = exporter.export_audit_trail(out_dir, self.current_user)
                results.append(r)
            if 'selected' in self.chk_export_md.state():
                r = exporter.generate_markdown_report(out_dir, volume, self.current_user)
                results.append(r)

            self.txt_export_preview.config(state=tk.NORMAL)
            self.txt_export_preview.delete('1.0', tk.END)
            self.txt_export_preview.insert(tk.END, "导出完成！\n\n")
            for r in results:
                is_success = r.record_count > 0 and '失败' not in r.description
                status = "✓" if is_success else "✗"
                msg = r.description
                fname = os.path.basename(r.file_path) if r.file_path else r.file_type
                self.txt_export_preview.insert(tk.END, f"{status} {fname}  {msg}\n")
            self.txt_export_preview.config(state=tk.DISABLED)

            self.lbl_status.config(text=f"导出完成: {len(results)}个文件")
            messagebox.showinfo("导出成功", f"共导出 {len(results)} 个文件到:\n{out_dir}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _on_audit_query(self):
        if not self.current_project:
            messagebox.showinfo("提示", "请先选择项目")
            return
        try:
            self.current_project.workflow_engine.permission_manager.check_permission(
                self.current_user, self.current_role, 'view_audit')
        except Exception as e:
            messagebox.showerror("权限不足", str(e))
            return

        user = self.entry_audit_user.get().strip() or None
        op_type_str = self.cmb_audit_type.get()
        op_type = None
        if op_type_str and op_type_str != '全部':
            from audit_trail import OperationType
            for ot in OperationType:
                if ot.value == op_type_str:
                    op_type = ot
                    break

        start_time = None
        end_time = None
        try:
            if self.entry_audit_start.get().strip():
                start_time = datetime.strptime(self.entry_audit_start.get().strip(), '%Y-%m-%d %H:%M:%S')
            if self.entry_audit_end.get().strip():
                end_time = datetime.strptime(self.entry_audit_end.get().strip(), '%Y-%m-%d %H:%M:%S')
        except Exception as e:
            messagebox.showerror("错误", f"时间格式错误，请使用 YYYY-MM-DD HH:MM:SS\n{str(e)}")
            return

        try:
            records = self.current_project.audit_trail.query_records(
                project_id=self.current_project.project_id,
                operator=user,
                operation_type=op_type,
                start_time=start_time,
                end_time=end_time
            )
            records = records[:500]
            self.txt_audit_timeline.config(state=tk.NORMAL)
            self.txt_audit_timeline.delete('1.0', tk.END)
            if not records:
                self.txt_audit_timeline.insert(tk.END, "暂无符合条件的审计记录")
            else:
                for r in records:
                    time_str = r.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                    line = f"{time_str} {r.operator}[{r.operator_role}] {r.operation_type.value}: {r.description}"
                    if r.old_value:
                        line += f"\n    旧值: {r.old_value}"
                    if r.new_value:
                        line += f"\n    新值: {r.new_value}"
                    self.txt_audit_timeline.insert(tk.END, line + "\n\n")
            self.txt_audit_timeline.config(state=tk.DISABLED)
        except Exception as e:
            messagebox.showerror("查询失败", str(e))

    def _reset_audit_filter(self):
        self.entry_audit_user.delete(0, tk.END)
        self.cmb_audit_type.current(0)
        self.entry_audit_start.delete(0, tk.END)
        self.entry_audit_end.delete(0, tk.END)
        self._on_audit_query()

    def _reset_doubt_filter(self):
        self.cmb_doubt_status.current(0)
        self.cmb_doubt_type.current(0)
        if self.cmb_doubt_volume['values']:
            self.cmb_doubt_volume.current(0)
        self._load_doubts_tree()

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

        if not self.current_project:
            try:
                self.project_manager.check_permission(self.current_user, self.current_role, 'create_project')
                project = self.project_manager.create_project(
                    creator=self.current_user,
                    project_name=f"{book_name}校勘项目",
                    book_name=book_name,
                    volumes=list(self.analyzer.volumes),
                    copy_batches=list(self.analyzer.copy_batches),
                    description=f"从文件 {os.path.basename(file_path)} 自动创建"
                )
                project.associate_analyzer(self.current_user, self.analyzer)
                project.assign_user(self.current_user, self.current_user, self.current_role)
                project.start(self.current_user)
                self.current_project = project
                self.lbl_project_info.config(text=f"【{project.config.project_name}】")
            except Exception as e:
                messagebox.showwarning("提示", f"无法自动创建项目：{str(e)}\n将使用独立分析模式")

        total_rows = len(df) + len(errors)
        msg = f"成功导入: {book_name} | 文件: {os.path.basename(file_path)} | 有效: {len(df)}行 / 共{total_rows}行"
        if errors:
            msg += f" | ⚠️ {len(errors)}行验证失败"
        if self.current_project:
            msg += f" | 项目: {self.current_project.config.project_name}"
        self.lbl_status.config(text=msg)

        self._refresh_all()

        if errors:
            self.notebook.select(9)

    def _on_export(self):
        if not self.analyzer:
            messagebox.showinfo("提示", "请先导入数据")
            return

        if self.current_project and self.current_project.analyzer is self.analyzer:
            self.notebook.select(5)
            messagebox.showinfo("提示", "已切换到【校勘结果导出】标签页\n请在该页面选择导出内容和格式")
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
            data_idx = int(self.tree_raw_data.item(row_id, 'tags')[0])

            if self.current_project and self.current_project.analyzer is self.analyzer:
                try:
                    success, err_msg, invalidated_ids = self.current_project.update_analyzer_record(
                        self.current_user, data_idx, col_name, new_val)
                except Exception as e:
                    entry.focus_set()
                    messagebox.showerror("权限不足", str(e), parent=self.root)
                    return
            else:
                success, err_msg = self.analyzer.update_record(data_idx, col_name, new_val)
                invalidated_ids = []

            if success:
                entry.destroy()
                self.tree_raw_data.set(row_id, col_name, self.analyzer.df.iloc[data_idx][col_name])
                msg = f"已修改行{data_idx + 2}的【{col_name}】，统计结果已自动刷新"
                if invalidated_ids:
                    msg += f" | 关联{len(invalidated_ids)}个疑点已失效"
                self.lbl_status.config(text=msg)
                self._load_comparison_tree()
                self._load_missing_info()
                self._load_stats_charts()
                self._load_heatmaps()
                self._load_raw_data_tree()
                self._load_doubts_tree()
                self._load_review_tree()
                self._load_citations_tree()
                self._update_counts_label()
            else:
                entry.focus_set()
                messagebox.showerror("修改失败", err_msg, parent=self.root)

        entry.bind('<Return>', save_edit)
        entry.bind('<Escape>', lambda e: entry.destroy())

    def _delete_selected_row(self):
        if not self.analyzer:
            return
        items = self.tree_raw_data.selection()
        if not items:
            messagebox.showinfo("提示", "请先选择要删除的行")
            return
        if not messagebox.askyesno("确认删除", f"确定删除选中的 {len(items)} 条记录吗？"):
            return
        indices = sorted([int(self.tree_raw_data.item(i, 'tags')[0]) for i in items], reverse=True)

        total_invalidated = 0
        for idx in indices:
            if self.current_project and self.current_project.analyzer is self.analyzer:
                try:
                    success, invalidated_ids = self.current_project.delete_analyzer_record(self.current_user, idx)
                    if not success:
                        messagebox.showerror("删除失败", "权限不足")
                        return
                    total_invalidated += len(invalidated_ids)
                except Exception as e:
                    messagebox.showerror("权限不足", str(e))
                    return
            else:
                self.analyzer.delete_record(idx)

        msg = f"已删除{len(indices)}条记录，统计结果已自动刷新"
        if total_invalidated > 0:
            msg += f" | 关联{total_invalidated}个疑点已失效"
        self.lbl_status.config(text=msg)
        self._refresh_all()

    # ---------- 刷新与渲染 ----------

    def _refresh_all(self):
        self._load_projects_tree()
        self._load_project_detail()
        self._load_members_tree()
        self._refresh_volume_filter()
        self._load_doubts_tree()
        self._load_review_tree()
        self._load_citations_tree()
        self._refresh_citation_filters()
        self._refresh_case_filters()
        self._load_cases_tree()
        self._load_recommendations_tree()
        self._load_comparison_tree()
        self._load_missing_info()
        self._load_stats_charts()
        self._load_heatmaps()
        self._load_raw_data_tree()
        self._load_errors_tree()
        self._update_counts_label()
        self._refresh_export_volume_filter()
        self._refresh_audit_types()

    def _load_projects_tree(self):
        self.tree_projects.delete(*self.tree_projects.get_children())
        for project in self.project_manager.list_projects():
            stats = project.get_stats()
            self.tree_projects.insert('', tk.END, values=(
                project.project_id,
                project.config.project_name,
                project.config.book_name,
                project.config.status.value,
                stats.get('total_doubts', 0),
                stats.get('pending_doubts', 0),
                project.config.created_at.strftime('%Y-%m-%d %H:%M'),
                project.config.created_by
            ))

    def _load_project_detail(self):
        if not self.current_project:
            self.lbl_project_detail.config(text="请选择一个项目查看详情")
            return
        cfg = self.current_project.config
        detail = (f"项目ID: {self.current_project.project_id}\n"
                  f"项目名称: {cfg.project_name}\n"
                  f"书名: {cfg.book_name}\n"
                  f"卷次: {cfg.volumes}\n"
                  f"抄本批次: {cfg.copy_batches}\n"
                  f"状态: {cfg.status.value}\n"
                  f"创建人: {cfg.created_by}\n"
                  f"创建时间: {cfg.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
                  f"描述: {cfg.description or '无'}")
        self.lbl_project_detail.config(text=detail)

        self.txt_project_timeline.config(state=tk.NORMAL)
        self.txt_project_timeline.delete('1.0', tk.END)
        timeline = self.current_project.get_timeline(limit=100)
        if not timeline:
            self.txt_project_timeline.insert(tk.END, "暂无时间线记录")
        else:
            for entry in timeline:
                self.txt_project_timeline.insert(tk.END, f"{entry['time']} {entry['operator']}[{entry['role']}] {entry['action']}: {entry['description']}\n")
        self.txt_project_timeline.config(state=tk.DISABLED)

    def _load_members_tree(self):
        self.tree_members.delete(*self.tree_members.get_children())
        if not self.current_project:
            return
        for user, role in self.current_project.config.assigned_users.items():
            self.tree_members.insert('', tk.END, values=(user, role.value))

    def _load_doubts_tree(self):
        self.tree_doubts.delete(*self.tree_doubts.get_children())
        if not self.current_project:
            return

        try:
            pm = self.current_project.workflow_engine.permission_manager
            pm.set_user_role(self.current_user, self.current_role)
            pm.check_permission(self.current_user, 'view_doubts')
        except Exception:
            return

        doubts = self.current_project.workflow_engine.get_all_doubts(self.current_project.project_id)

        status_filter = self.cmb_doubt_status.get()
        type_filter = self.cmb_doubt_type.get()

        filtered = []
        for d in doubts:
            if status_filter and status_filter != '全部' and d.status.value != status_filter:
                continue
            if type_filter and type_filter != '全部' and d.collation_type != type_filter:
                continue
            filtered.append(d)

        for d in filtered:
            self.tree_doubts.insert('', tk.END, values=(
                d.doubt_id,
                d.collation_type,
                d.volume,
                d.paragraph,
                d.copy_batch,
                d.original_text,
                d.suggested_text,
                f"{d.confidence:.1%}",
                d.status.value,
                d.created_at.strftime('%Y-%m-%d %H:%M'),
                d.assignee or '-'
            ))

    def _load_review_tree(self):
        self.tree_review.delete(*self.tree_review.get_children())
        if not self.current_project:
            return

        try:
            pm = self.current_project.workflow_engine.permission_manager
            pm.set_user_role(self.current_user, self.current_role)
            pm.check_permission(self.current_user, 'review_doubt')
        except Exception:
            return

        doubts = self.current_project.workflow_engine.get_all_doubts(self.current_project.project_id)

        status_filter = self.cmb_review_status.get()
        only_mine = 'selected' in self.chk_only_mine.state()

        filtered = []
        for d in doubts:
            if status_filter and status_filter != '全部' and d.status.value != status_filter:
                continue
            if only_mine and d.assignee != self.current_user:
                continue
            filtered.append(d)

        for d in filtered:
            self.tree_review.insert('', tk.END, values=(
                d.doubt_id,
                d.collation_type,
                d.volume,
                d.paragraph,
                d.copy_batch,
                d.original_text,
                d.suggested_text,
                d.status.value,
                d.assignee or '-'
            ))

    def _refresh_export_volume_filter(self):
        vols = ['全卷']
        if self.analyzer:
            vols += [f'第{v}卷' for v in self.analyzer.volumes]
        self.cmb_export_volume['values'] = vols
        if vols:
            self.cmb_export_volume.current(0)

    def _refresh_audit_types(self):
        from audit_trail import OperationType
        types = ['全部'] + [ot.value for ot in OperationType]
        self.cmb_audit_type['values'] = types
        self.cmb_audit_type.current(0)

    def _refresh_volume_filter(self):
        vols = ['全部'] + [f'第{v}卷' for v in (self.analyzer.volumes if self.analyzer else [])]
        self.cmb_volume['values'] = vols
        self.cmb_volume.current(0)

        doubt_vols = ['全部'] + [f'第{v}卷' for v in (self.analyzer.volumes if self.analyzer else [])]
        self.cmb_doubt_volume['values'] = doubt_vols
        if doubt_vols:
            self.cmb_doubt_volume.current(0)

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
