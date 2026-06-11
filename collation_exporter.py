"""
校勘结果导出模块：支持按卷导出校勘报告、异文清单、复核日志
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from datetime import datetime
import os
import pandas as pd

from collation_project import CollationProject
from collation_analyzer import CollationAnalyzer
from citation_analyzer import CitationType
from workflow_engine import DoubtStatus, DoubtRecord
from audit_trail import AuditRecord, OperationType
from collation_rules import CollationType


@dataclass
class ExportResult:
    file_path: str
    file_type: str
    record_count: int
    description: str


class CollationExporter:
    def __init__(self, project: CollationProject):
        self.project = project
        self._encoding = 'utf-8-sig'

    def _ensure_dir(self, output_dir: str):
        if not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

    def _safe_filename(self, name: str) -> str:
        invalid_chars = '<>:"/\\|?*'
        for ch in invalid_chars:
            name = name.replace(ch, '_')
        return name.strip()

    def export_collation_report(self,
                                output_dir: str,
                                volume: Optional[int] = None,
                                operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_data')

        self._ensure_dir(output_dir)

        analyzer = self.project.analyzer
        if not analyzer:
            raise ValueError("项目尚未关联分析器")

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_校勘报告_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        records = []
        doubts = self.project.get_doubts()
        if volume:
            doubts = [d for d in doubts if d.volume == volume]

        for doubt in doubts:
            review_comments = '; '.join([
                f'{c.timestamp.strftime("%Y-%m-%d %H:%M:%S")} [{c.reviewer}] {c.action.value}: {c.content}'
                for c in doubt.review_history
            ]) if doubt.review_history else ''

            records.append({
                '疑点编号': doubt.doubt_id,
                '校勘类型': doubt.collation_type,
                '卷次': doubt.volume,
                '段落编号': doubt.paragraph,
                '抄本批次': doubt.copy_batch,
                '原文': doubt.original_text,
                '建议校改': doubt.suggested_text,
                '置信度': f'{doubt.confidence:.2f}',
                '检测理由': doubt.reason,
                '状态': doubt.status.value,
                '指派人': doubt.assignee or '',
                '是否失效': '是' if doubt.invalidated else '否',
                '失效原因': doubt.invalidated_reason,
                '创建时间': doubt.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                '更新时间': doubt.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                '解决时间': doubt.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if doubt.resolved_at else '',
                '复核历史': review_comments
            })

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出校勘报告: {filename} ({len(records)}条)",
            extra={'file': filename, 'volume': volume, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='校勘报告',
            record_count=len(records),
            description=f'校勘报告已导出: {len(records)}条疑点记录'
        )

    def export_variant_list(self,
                            output_dir: str,
                            volume: Optional[int] = None,
                            operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_data')

        self._ensure_dir(output_dir)

        analyzer = self.project.analyzer
        if not analyzer:
            raise ValueError("项目尚未关联分析器")

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_异文清单_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        table = analyzer.build_comparison_table()
        if table.empty:
            raise ValueError("对照表为空，无法导出异文清单")

        if volume:
            table = table[table['卷次'] == volume]

        diff_table = table[table['异文'] == '有'].copy()

        content_cols = [c for c in diff_table.columns if '_内容' in c]
        mark_cols = [c for c in diff_table.columns if '_校勘标记' in c]

        records = []
        for _, row in diff_table.iterrows():
            vol = int(row['卷次'])
            para = int(row['段落编号'])

            contents = {}
            for col in content_cols:
                copy_batch = col.replace('_内容', '')
                contents[copy_batch] = row.get(col, '')

            marks = {}
            for col in mark_cols:
                copy_batch = col.replace('_校勘标记', '')
                marks[copy_batch] = row.get(col, '')

            copy_batches = list(contents.keys())
            for i in range(len(copy_batches)):
                for j in range(i + 1, len(copy_batches)):
                    ca, cb = copy_batches[i], copy_batches[j]
                    text_a = contents.get(ca, '')
                    text_b = contents.get(cb, '')

                    if text_a and text_b and text_a != '【缺失】' and text_b != '【缺失】' and text_a != text_b:
                        diff_regions = self._extract_simple_diffs(text_a, text_b)
                        for diff_type, orig, sugg in diff_regions:
                            records.append({
                                '卷次': vol,
                                '段落编号': para,
                                '抄本A': ca,
                                '抄本B': cb,
                                '差异类型': self._map_diff_type(diff_type),
                                '抄本A原文': orig,
                                '抄本B原文': sugg,
                                '抄本A校勘标记': marks.get(ca, ''),
                                '抄本B校勘标记': marks.get(cb, ''),
                                '完整段落A': text_a,
                                '完整段落B': text_b
                            })

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出异文清单: {filename} ({len(records)}条)",
            extra={'file': filename, 'volume': volume, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='异文清单',
            record_count=len(records),
            description=f'异文清单已导出: {len(records)}条异文记录'
        )

    def export_review_log(self,
                          output_dir: str,
                          volume: Optional[int] = None,
                          operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_data')

        self._ensure_dir(output_dir)

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_复核日志_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        records = []
        doubts = self.project.get_doubts()
        if volume:
            doubts = [d for d in doubts if d.volume == volume]

        for doubt in doubts:
            for comment in doubt.review_history:
                records.append({
                    '日志编号': comment.comment_id,
                    '疑点编号': doubt.doubt_id,
                    '校勘类型': doubt.collation_type,
                    '卷次': doubt.volume,
                    '段落编号': doubt.paragraph,
                    '抄本批次': doubt.copy_batch,
                    '复核时间': comment.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                    '复核人': comment.reviewer,
                    '复核角色': comment.reviewer_role,
                    '复核操作': comment.action.value,
                    '复核意见': comment.content,
                    '原状态': comment.old_status.value if comment.old_status else '',
                    '新状态': comment.new_status.value if comment.new_status else '',
                    '转交给': comment.assignee or ''
                })

        timeline = self.project.get_timeline(limit=10000)
        for item in timeline:
            if item.get('action') in ['数据修改', '数据删除', '疑点失效']:
                records.append({
                    '日志编号': item.get('record_id', ''),
                    '疑点编号': '',
                    '校勘类型': '',
                    '卷次': '',
                    '段落编号': '',
                    '抄本批次': '',
                    '复核时间': item.get('time', ''),
                    '复核人': item.get('operator', ''),
                    '复核角色': item.get('role', ''),
                    '复核操作': item.get('action', ''),
                    '复核意见': item.get('description', ''),
                    '原状态': '',
                    '新状态': '',
                    '转交给': ''
                })

        records.sort(key=lambda r: r['复核时间'], reverse=True)

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出复核日志: {filename} ({len(records)}条)",
            extra={'file': filename, 'volume': volume, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='复核日志',
            record_count=len(records),
            description=f'复核日志已导出: {len(records)}条操作记录'
        )

    def export_citation_table(self,
                              output_dir: str,
                              volume: Optional[int] = None,
                              operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_citations')

        self._ensure_dir(output_dir)

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_引文溯源表_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        records = []
        citations = self.project.get_all_citations()
        if volume:
            citations = [c for c in citations if c.volume == volume]

        for cit in citations:
            source_info = []
            for match in cit.matches:
                for src in match.sources:
                    loc_parts = []
                    if src.source_book:
                        loc_parts.append(f"书名:{src.source_book}")
                    if src.source_volume:
                        loc_parts.append(f"卷次:{src.source_volume}")
                    if src.source_paragraph:
                        loc_parts.append(f"段落:{src.source_paragraph}")
                    if src.source_copy_batch:
                        loc_parts.append(f"抄本:{src.source_copy_batch}")
                    if src.source_chapter:
                        loc_parts.append(f"章:{src.source_chapter}")
                    if src.source_page:
                        loc_parts.append(f"页:{src.source_page}")
                    loc = '; '.join(loc_parts) if loc_parts else '未标注'
                    src_txt = src.source_text or ''
                    if len(src_txt) > 50:
                        src_txt = src_txt[:47] + '...'
                    source_info.append(
                        f"[{match.match_basis}] {loc} | "
                        f"相似度:{match.match_similarity:.2f} | "
                        f"原文:{src_txt}"
                    )

            sources_str = ' | '.join(source_info) if source_info else '未匹配出处'

            review_comments = '; '.join([
                f'{h.get("timestamp", "")} [{h.get("operator", "")}] '
                f'{h.get("action", "")}: {h.get("content", "")}'
                for h in cit.processing_history
            ]) if cit.processing_history else ''

            extra_notes = ''
            if cit.extra:
                extra_notes = str(cit.extra)

            records.append({
                '引文编号': cit.citation_id,
                '引文类型': cit.citation_type.value,
                '书名': self.project.book_name,
                '卷次': cit.volume,
                '段落编号': cit.paragraph,
                '抄本批次': cit.copy_batch,
                '引文原文': cit.quoted_text,
                '上下文': cit.original_text,
                '置信度': f'{cit.confidence:.2f}',
                '匹配依据': sources_str,
                '状态': cit.status.value,
                '确认人': cit.confirmed_by or '',
                '确认时间': cit.confirmed_at.strftime('%Y-%m-%d %H:%M:%S') if cit.confirmed_at else '',
                '创建人': cit.created_by,
                '创建时间': cit.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                '更新时间': cit.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
                '失效原因': cit.invalidated_reason or '',
                '备注': extra_notes,
                '处理历史': review_comments
            })

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出引文溯源表: {filename} ({len(records)}条)",
            extra={'file': filename, 'volume': volume, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='引文溯源表',
            record_count=len(records),
            description=f'引文溯源表已导出: {len(records)}条引文记录'
        )

    def export_misquote_list(self,
                             output_dir: str,
                             volume: Optional[int] = None,
                             operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_citations')

        self._ensure_dir(output_dir)

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_疑似误引清单_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        records = []
        citations = self.project.get_all_citations()
        misquotes = [c for c in citations if c.citation_type == CitationType.MISQUOTE]
        if volume:
            misquotes = [c for c in misquotes if c.volume == volume]

        for cit in misquotes:
            for match in cit.matches:
                if not match.is_suspected_misquote:
                    continue
                for src in match.sources:
                    diff_str = match.match_basis or '未检测到具体差异'

                    records.append({
                        '引文编号': cit.citation_id,
                        '书名': self.project.book_name,
                        '卷次': cit.volume,
                        '段落编号': cit.paragraph,
                        '抄本批次': cit.copy_batch,
                        '抄本文本': cit.quoted_text,
                        '出处来源': '内部匹配' if match.is_internal else '外部匹配',
                        '出处书名': src.source_book or '',
                        '出处卷次': src.source_volume or '',
                        '出处段落': src.source_paragraph or '',
                        '出处抄本': src.source_copy_batch or '',
                        '出处原文': src.source_text or '',
                        '相似度': f'{match.match_similarity:.2f}',
                        '差异详情': diff_str,
                        '状态': cit.status.value,
                        '创建时间': cit.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    })

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出疑似误引清单: {filename} ({len(records)}条)",
            extra={'file': filename, 'volume': volume, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='疑似误引清单',
            record_count=len(records),
            description=f'疑似误引清单已导出: {len(records)}条疑似误引记录'
        )

    def export_audit_trail(self,
                           output_dir: str,
                           operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'view_audit')

        self._ensure_dir(output_dir)

        book_name = self._safe_filename(self.project.book_name)
        filename = f'{book_name}_审计日志_{datetime.now().strftime("%Y%m%d%H%M%S")}.csv'
        file_path = os.path.join(output_dir, filename)

        audit_records = self.project.audit_trail.get_records_by_project(self.project.project_id)
        records = [r.to_dict() for r in audit_records]

        df = pd.DataFrame(records)
        df.to_csv(file_path, index=False, encoding=self._encoding)

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出审计日志: {filename} ({len(records)}条)",
            extra={'file': filename, 'count': len(records)}
        )

        return ExportResult(
            file_path=file_path,
            file_type='审计日志',
            record_count=len(records),
            description=f'审计日志已导出: {len(records)}条操作记录'
        )

    def export_all(self,
                   output_dir: str,
                   volume: Optional[int] = None,
                   operator: str = 'system') -> List[ExportResult]:
        results = []

        try:
            results.append(self.export_collation_report(output_dir, volume, operator))
        except Exception as e:
            results.append(ExportResult('', '校勘报告', 0, f'导出失败: {str(e)}'))

        try:
            results.append(self.export_variant_list(output_dir, volume, operator))
        except Exception as e:
            results.append(ExportResult('', '异文清单', 0, f'导出失败: {str(e)}'))

        try:
            results.append(self.export_review_log(output_dir, volume, operator))
        except Exception as e:
            results.append(ExportResult('', '复核日志', 0, f'导出失败: {str(e)}'))

        try:
            results.append(self.export_citation_table(output_dir, volume, operator))
        except Exception as e:
            results.append(ExportResult('', '引文溯源表', 0, f'导出失败: {str(e)}'))

        try:
            results.append(self.export_misquote_list(output_dir, volume, operator))
        except Exception as e:
            results.append(ExportResult('', '疑似误引清单', 0, f'导出失败: {str(e)}'))

        try:
            results.append(self.export_audit_trail(output_dir, operator))
        except Exception as e:
            results.append(ExportResult('', '审计日志', 0, f'导出失败: {str(e)}'))

        try:
            analyzer = self.project.analyzer
            if analyzer:
                book_name = self._safe_filename(self.project.book_name)
                vol_suffix = f'_第{volume}卷' if volume else '_全卷'

                comp_table = analyzer.build_comparison_table()
                if volume and not comp_table.empty:
                    comp_table = comp_table[comp_table['卷次'] == volume]
                comp_filename = f'{book_name}{vol_suffix}_分卷分段对照表.csv'
                comp_file_path = os.path.join(output_dir, comp_filename)
                comp_table.to_csv(comp_file_path, index=False, encoding=self._encoding)
                results.append(ExportResult(comp_file_path, '分卷分段对照表', len(comp_table), '对照表已导出'))

                vol_stats = analyzer.get_volume_stats()
                if volume and not vol_stats.empty:
                    vol_stats = vol_stats[vol_stats['卷次'] == volume]
                stats_filename = f'{book_name}{vol_suffix}_各卷异文统计.csv'
                stats_file_path = os.path.join(output_dir, stats_filename)
                vol_stats.to_csv(stats_file_path, index=False, encoding=self._encoding)
                results.append(ExportResult(stats_file_path, '各卷异文统计', len(vol_stats), '统计数据已导出'))
        except Exception as e:
            results.append(ExportResult('', '其他数据', 0, f'导出失败: {str(e)}'))

        return results

    def _extract_simple_diffs(self, text_a: str, text_b: str) -> List[Tuple[str, str, str]]:
        import difflib
        regions = []
        sm = difflib.SequenceMatcher(None, text_a, text_b)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            a_part = text_a[i1:i2]
            b_part = text_b[j1:j2]
            regions.append((tag, a_part, b_part))
        return regions

    def _map_diff_type(self, tag: str) -> str:
        type_map = {
            'replace': '替换',
            'delete': '删除',
            'insert': '插入'
        }
        return type_map.get(tag, tag)

    def generate_markdown_report(self,
                                 output_dir: str,
                                 volume: Optional[int] = None,
                                 operator: str = 'system') -> ExportResult:
        self.project.workflow_engine.permission_manager.check_permission(operator, 'export_data')

        self._ensure_dir(output_dir)

        book_name = self._safe_filename(self.project.book_name)
        vol_suffix = f'_第{volume}卷' if volume else '_全卷'
        filename = f'{book_name}{vol_suffix}_校勘报告书_{datetime.now().strftime("%Y%m%d%H%M%S")}.md'
        file_path = os.path.join(output_dir, filename)

        stats = self.project.get_statistics()
        doubts = self.project.get_doubts()
        if volume:
            doubts = [d for d in doubts if d.volume == volume]

        doubt_stats = stats.get('doubts', {})
        by_type = doubt_stats.get('by_type', {})

        md_content = []
        md_content.append(f'# 《{self.project.book_name}》校勘报告书')
        md_content.append('')
        md_content.append(f'- **项目名称**: {self.project.config.project_name}')
        md_content.append(f'- **项目编号**: {self.project.project_id}')
        md_content.append(f'- **导出时间**: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
        md_content.append(f'- **导出人**: {operator}')
        md_content.append(f'- **卷次范围**: {"第" + str(volume) + "卷" if volume else "全卷"}')
        md_content.append('')

        md_content.append('## 一、项目概况')
        md_content.append('')
        md_content.append(f'- **书名**: {self.project.book_name}')
        md_content.append(f'- **抄本批次**: {", ".join(stats.get("copy_batches", []))}')
        md_content.append(f'- **总记录数**: {stats.get("record_count", 0)} 条')
        md_content.append(f'- **项目状态**: {self.project.config.status.value}')
        md_content.append('')

        md_content.append('## 二、疑点统计')
        md_content.append('')
        md_content.append('| 疑点类型 | 数量 | 占比 |')
        md_content.append('|---------|------|------|')
        total_doubts = doubt_stats.get('total', 0)
        for ctype, count in sorted(by_type.items(), key=lambda x: -x[1]):
            pct = f'{count / total_doubts * 100:.1f}%' if total_doubts > 0 else '0%'
            md_content.append(f'| {ctype} | {count} | {pct} |')
        md_content.append('| **合计** | **' + str(total_doubts) + '** | **100%** |')
        md_content.append('')

        md_content.append('## 三、状态分布')
        md_content.append('')
        md_content.append('| 状态 | 数量 |')
        md_content.append('|------|------|')
        status_map = {
            'pending': '待复核',
            'in_progress': '处理中',
            'reviewed': '已复核',
            'rejected': '已驳回',
            'resolved': '已解决',
            'invalidated': '已失效'
        }
        for key, label in status_map.items():
            count = doubt_stats.get(key, 0)
            md_content.append(f'| {label} | {count} |')
        md_content.append('')

        md_content.append('## 四、疑点详情')
        md_content.append('')

        if doubts:
            current_vol = None
            for doubt in sorted(doubts, key=lambda d: (d.volume, d.paragraph)):
                if doubt.volume != current_vol:
                    current_vol = doubt.volume
                    md_content.append(f'### 第{doubt.volume}卷')
                    md_content.append('')

                md_content.append(f'#### 疑点 [{doubt.doubt_id}] - {doubt.collation_type}')
                md_content.append('')
                md_content.append(f'- **段落**: 第{doubt.paragraph}段')
                md_content.append(f'- **抄本**: {doubt.copy_batch}')
                md_content.append(f'- **状态**: {doubt.status.value}')
                md_content.append(f'- **置信度**: {doubt.confidence:.2f}')
                md_content.append(f'- **原文**: `{doubt.original_text}`')
                md_content.append(f'- **建议**: `{doubt.suggested_text}`')
                md_content.append(f'- **理由**: {doubt.reason}')
                if doubt.invalidated:
                    md_content.append(f'- **⚠️ 已失效**: {doubt.invalidated_reason}')
                md_content.append('')

                if doubt.review_history:
                    md_content.append('**复核历史**:')
                    md_content.append('')
                    for comment in doubt.review_history:
                        md_content.append(f'> [{comment.timestamp.strftime("%Y-%m-%d %H:%M:%S")}] '
                                         f'**{comment.reviewer}** ({comment.reviewer_role}) '
                                         f'- *{comment.action.value}*: {comment.content}')
                    md_content.append('')
        else:
            md_content.append('*暂无疑点记录*')
            md_content.append('')

        md_content.append('## 五、操作时间线')
        md_content.append('')
        timeline = self.project.get_timeline(limit=50)
        if timeline:
            for item in timeline:
                md_content.append(f'- [{item["time"]}] **{item["operator"]}** ({item["role"]}) - {item["action"]}: {item["description"]}')
        else:
            md_content.append('*暂无操作记录*')
        md_content.append('')

        md_content.append('---')
        md_content.append(f'*本报告由古籍校勘系统自动生成于 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}*')

        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_content))

        self.project.audit_trail.log(
            operation_type=OperationType.EXPORT,
            operator=operator,
            operator_role=self.project.get_user_role(operator).value,
            project_id=self.project.project_id,
            description=f"导出Markdown校勘报告书: {filename}",
            extra={'file': filename, 'volume': volume}
        )

        return ExportResult(
            file_path=file_path,
            file_type='Markdown校勘报告',
            record_count=len(doubts),
            description=f'Markdown校勘报告书已导出'
        )
