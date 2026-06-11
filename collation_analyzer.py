"""
核心数据处理模块：异文检测、缺段标记、统计计算
"""
import pandas as pd
import difflib
from typing import Dict, List, Tuple, Set, Optional
from collections import Counter


class TextDiff:
    def __init__(self, para_id: int, copy_a: str, copy_b: str,
                 content_a: str, content_b: str, diff_regions: List[Tuple[str, str, str]]):
        self.para_id = para_id
        self.copy_a = copy_a
        self.copy_b = copy_b
        self.content_a = content_a
        self.content_b = content_b
        self.diff_regions = diff_regions


class CollationAnalyzer:
    def __init__(self, df: pd.DataFrame, book_name: str):
        self.df = df.copy()
        self.book_name = book_name
        self.copy_batches: List[str] = sorted(df['抄本批次'].unique().tolist()) if not df.empty else []
        self.volumes: List[int] = sorted(df['卷次'].unique().tolist()) if not df.empty else []
        self._comparison_table: Optional[pd.DataFrame] = None
        self._diff_matrix: Optional[Dict[Tuple[str, str], int]] = None
        self._stats_dirty = True

    def invalidate_stats(self):
        self._stats_dirty = True
        self._comparison_table = None
        self._diff_matrix = None

    def update_record(self, index: int, column: str, value) -> bool:
        if index < 0 or index >= len(self.df):
            return False
        if column not in self.df.columns:
            return False

        if column in ['卷次', '段落编号']:
            try:
                val = int(value)
                if val <= 0:
                    return False
            except (ValueError, TypeError):
                return False
            self.df.at[index, column] = val
        else:
            self.df.at[index, column] = str(value)

        self.copy_batches = sorted(self.df['抄本批次'].unique().tolist())
        self.volumes = sorted(self.df['卷次'].unique().tolist())
        self.invalidate_stats()
        return True

    def delete_record(self, index: int) -> bool:
        if index < 0 or index >= len(self.df):
            return False
        self.df = self.df.drop(index).reset_index(drop=True)
        self.copy_batches = sorted(self.df['抄本批次'].unique().tolist())
        self.volumes = sorted(self.df['卷次'].unique().tolist())
        self.invalidate_stats()
        return True

    def get_missing_paragraphs(self) -> Dict[Tuple[str, int], List[Tuple[int, int]]]:
        """
        获取各抄本各卷的缺失段落区间
        Returns: {(抄本批次, 卷次): [(缺失起始, 缺失结束), ...]}
        """
        missing: Dict[Tuple[str, int], List[Tuple[int, int]]] = {}

        if self.df.empty:
            return missing

        global_max_para = {}
        for vol in self.volumes:
            vol_data = self.df[self.df['卷次'] == vol]
            if not vol_data.empty:
                global_max_para[vol] = int(vol_data['段落编号'].max())

        for copy_batch in self.copy_batches:
            for vol in self.volumes:
                mask = (self.df['抄本批次'] == copy_batch) & (self.df['卷次'] == vol)
                vol_copy_data = self.df[mask]

                max_para = global_max_para.get(vol, 0)
                if max_para == 0:
                    continue

                existing = set(vol_copy_data['段落编号'].astype(int).tolist())
                expected = set(range(1, max_para + 1))
                missing_nums = sorted(expected - existing)

                if not missing_nums:
                    continue

                ranges = []
                start = missing_nums[0]
                prev = missing_nums[0]
                for n in missing_nums[1:]:
                    if n == prev + 1:
                        prev = n
                    else:
                        ranges.append((start, prev))
                        start = n
                        prev = n
                ranges.append((start, prev))

                missing[(copy_batch, vol)] = ranges

        return missing

    def build_comparison_table(self) -> pd.DataFrame:
        """
        构建分卷分段对照表，所有抄本并排比较
        """
        if self._comparison_table is not None and not self._stats_dirty:
            return self._comparison_table

        if self.df.empty:
            self._comparison_table = pd.DataFrame()
            return self._comparison_table

        rows = []
        for vol in self.volumes:
            vol_data = self.df[self.df['卷次'] == vol]
            max_para = int(vol_data['段落编号'].max()) if not vol_data.empty else 0

            for para in range(1, max_para + 1):
                row = {'卷次': vol, '段落编号': para}
                all_present = True

                for copy_batch in self.copy_batches:
                    mask = (vol_data['抄本批次'] == copy_batch) & (vol_data['段落编号'] == para)
                    rec = vol_data[mask]
                    col_content = f'{copy_batch}_内容'
                    col_mark = f'{copy_batch}_校勘标记'
                    if not rec.empty:
                        row[col_content] = rec.iloc[0]['原文内容']
                        row[col_mark] = rec.iloc[0]['校勘标记']
                    else:
                        row[col_content] = '【缺失】'
                        row[col_mark] = ''
                        all_present = False

                row['状态'] = '正常' if all_present else '有缺段'

                contents = []
                for copy_batch in self.copy_batches:
                    col = f'{copy_batch}_内容'
                    c = row.get(col, '')
                    if c and c != '【缺失】':
                        contents.append(c)

                if len(contents) >= 2 and len(set(contents)) > 1:
                    row['异文'] = '有'
                else:
                    row['异文'] = '无'

                rows.append(row)

        result = pd.DataFrame(rows)
        cols = ['卷次', '段落编号']
        for copy_batch in self.copy_batches:
            cols.extend([f'{copy_batch}_内容', f'{copy_batch}_校勘标记'])
        cols.extend(['异文', '状态'])
        existing_cols = [c for c in cols if c in result.columns]
        result = result[existing_cols]

        self._comparison_table = result
        self._stats_dirty = False
        return result

    def compute_diffs(self, copy_a: str, copy_b: str, volume: int = None) -> List[TextDiff]:
        """
        计算两个抄本之间的异文差异
        """
        diffs = []
        table = self.build_comparison_table()
        if table.empty:
            return diffs

        if volume is not None:
            table = table[table['卷次'] == volume]

        col_a = f'{copy_a}_内容'
        col_b = f'{copy_b}_内容'

        if col_a not in table.columns or col_b not in table.columns:
            return diffs

        for _, row in table.iterrows():
            content_a = row.get(col_a, '')
            content_b = row.get(col_b, '')

            if (not content_a or content_a == '【缺失】' or
                    not content_b or content_b == '【缺失】'):
                continue

            if content_a == content_b:
                continue

            regions = self._extract_diff_regions(content_a, content_b)
            diffs.append(TextDiff(
                para_id=int(row['段落编号']),
                copy_a=copy_a, copy_b=copy_b,
                content_a=content_a, content_b=content_b,
                diff_regions=regions
            ))

        return diffs

    def _extract_diff_regions(self, text_a: str, text_b: str) -> List[Tuple[str, str, str]]:
        """
        使用difflib提取差异区域
        Returns: [(差异类型, a部分, b部分), ...]  差异类型: 'replace', 'delete', 'insert'
        """
        regions = []
        sm = difflib.SequenceMatcher(None, text_a, text_b)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == 'equal':
                continue
            a_part = text_a[i1:i2]
            b_part = text_b[j1:j2]
            regions.append((tag, a_part, b_part))
        return regions

    def build_diff_matrix(self) -> Dict[Tuple[str, str], int]:
        """
        构建抄本差异矩阵（两两异文段落数）
        """
        if self._diff_matrix is not None and not self._stats_dirty:
            return self._diff_matrix

        matrix = {}
        n = len(self.copy_batches)
        for i in range(n):
            for j in range(i + 1, n):
                ca, cb = self.copy_batches[i], self.copy_batches[j]
                diffs = self.compute_diffs(ca, cb)
                count = len(diffs)
                matrix[(ca, cb)] = count
                matrix[(cb, ca)] = count

        self._diff_matrix = matrix
        return matrix

    def get_volume_stats(self) -> pd.DataFrame:
        """
        统计每卷的异文数量、缺段情况
        """
        table = self.build_comparison_table()
        if table.empty:
            return pd.DataFrame()

        missing = self.get_missing_paragraphs()
        stats_rows = []

        for vol in self.volumes:
            vol_table = table[table['卷次'] == vol]
            total_paras = len(vol_table)
            diff_paras = len(vol_table[vol_table['异文'] == '有'])

            missing_count = 0
            missing_desc_parts = []
            for copy_batch in self.copy_batches:
                key = (copy_batch, vol)
                if key in missing:
                    ranges = missing[key]
                    copy_missing = sum(e - s + 1 for s, e in ranges)
                    missing_count += copy_missing
                    range_strs = [f"{s}-{e}" if s != e else str(s) for s, e in ranges]
                    missing_desc_parts.append(f"{copy_batch}: {','.join(range_strs)}")

            missing_desc = '; '.join(missing_desc_parts) if missing_desc_parts else '无'

            stats_rows.append({
                '卷次': vol,
                '总段落数': total_paras,
                '异文段落数': diff_paras,
                '异文率(%)': round(diff_paras / total_paras * 100, 2) if total_paras > 0 else 0,
                '缺段总数': missing_count,
                '缺段详情': missing_desc
            })

        return pd.DataFrame(stats_rows)

    def get_collation_mark_stats(self, top_n: int = 20) -> pd.DataFrame:
        """
        统计高频校勘类型
        """
        if self.df.empty:
            return pd.DataFrame()

        all_marks = []
        for _, row in self.df.iterrows():
            mark = str(row.get('校勘标记', '')).strip()
            if mark:
                parts = [p.strip() for p in mark.split(';') if p.strip()]
                all_marks.extend(parts)

        counter = Counter(all_marks)
        rows = [{'校勘类型': k, '频次': v} for k, v in counter.most_common(top_n)]
        return pd.DataFrame(rows)

    def get_copy_volume_diff_count(self) -> pd.DataFrame:
        """
        获取抄本-卷次维度的异文数量（用于热力图）
        """
        if self.df.empty or len(self.copy_batches) < 2:
            return pd.DataFrame()

        rows = []
        for vol in self.volumes:
            row = {'卷次': f'第{vol}卷'}
            for i, ca in enumerate(self.copy_batches):
                total = 0
                for cb in self.copy_batches:
                    if ca != cb:
                        diffs = self.compute_diffs(ca, cb, volume=vol)
                        total += len(diffs)
                row[ca] = total
            rows.append(row)

        return pd.DataFrame(rows)
