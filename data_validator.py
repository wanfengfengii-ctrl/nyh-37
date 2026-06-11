"""
数据验证模块：CSV导入、字段校验、失败行记录
"""
import pandas as pd
import os
from typing import Tuple, List, Dict, Any


REQUIRED_COLUMNS = ['书名', '抄本批次', '卷次', '段落编号', '原文内容', '校勘标记']


class ValidationError:
    def __init__(self, row_index: int, reason: str, data: dict = None):
        self.row_index = row_index
        self.reason = reason
        self.data = data or {}

    def __repr__(self):
        return f"行{self.row_index}: {self.reason}"


def validate_csv(file_path: str) -> Tuple[pd.DataFrame, List[ValidationError], str]:
    """
    验证并导入CSV文件

    Returns:
        (有效数据DataFrame, 错误列表, 当前书名)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    try:
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
    except Exception as e:
        raise ValueError(f"CSV解析失败: {str(e)}")

    errors: List[ValidationError] = []

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        raise ValueError(f"缺少必要列: {', '.join(missing_cols)}")

    book_names = df['书名'].dropna().unique()
    if len(book_names) == 0:
        raise ValueError("数据中未包含任何书名")

    current_book = book_names[0]
    if len(book_names) > 1:
        for idx, row in df.iterrows():
            if row.get('书名', '') and row['书名'] != current_book:
                errors.append(ValidationError(
                    idx + 2,
                    f"不同书目的数据不能直接合并比较：'{row['书名']}' 与当前书名 '{current_book}' 不同，已跳过",
                    row.to_dict()
                ))

    valid_rows = []
    seen_paragraphs: Dict[Tuple[str, int, int], int] = {}

    for idx, row in df.iterrows():
        row_num = idx + 2
        row_dict = row.to_dict()

        book_name = str(row_dict.get('书名', '')).strip()
        copy_batch = str(row_dict.get('抄本批次', '')).strip()
        volume_str = str(row_dict.get('卷次', '')).strip()
        para_str = str(row_dict.get('段落编号', '')).strip()
        content = str(row_dict.get('原文内容', '')).strip()
        coll_mark = str(row_dict.get('校勘标记', '')).strip()

        if not book_name:
            errors.append(ValidationError(row_num, "书名为空", row_dict))
            continue

        if book_name != current_book:
            continue

        if not copy_batch:
            errors.append(ValidationError(row_num, "抄本批次为空", row_dict))
            continue

        if not volume_str:
            errors.append(ValidationError(row_num, "卷次为空", row_dict))
            continue

        try:
            volume = int(volume_str)
            if volume <= 0:
                errors.append(ValidationError(row_num, f"卷次必须为正整数，当前值: {volume_str}", row_dict))
                continue
        except ValueError:
            errors.append(ValidationError(row_num, f"卷次格式错误，不是有效整数: {volume_str}", row_dict))
            continue

        if not para_str:
            errors.append(ValidationError(row_num, "段落编号为空", row_dict))
            continue

        try:
            paragraph = int(para_str)
            if paragraph <= 0:
                errors.append(ValidationError(row_num, f"段落编号必须为正整数，当前值: {para_str}", row_dict))
                continue
        except ValueError:
            errors.append(ValidationError(row_num, f"段落编号格式错误，不是有效整数: {para_str}", row_dict))
            continue

        key = (copy_batch, volume, paragraph)
        if key in seen_paragraphs:
            errors.append(ValidationError(
                row_num,
                f"同一抄本({copy_batch})同一卷次({volume})内段落编号({paragraph})重复，首次出现于行{seen_paragraphs[key]}",
                row_dict
            ))
            continue
        seen_paragraphs[key] = row_num

        if not content:
            errors.append(ValidationError(row_num, "原文内容为空", row_dict))
            continue

        valid_rows.append({
            '书名': book_name,
            '抄本批次': copy_batch,
            '卷次': volume,
            '段落编号': paragraph,
            '原文内容': content,
            '校勘标记': coll_mark
        })

    result_df = pd.DataFrame(valid_rows)
    if not result_df.empty:
        result_df = result_df.sort_values(['抄本批次', '卷次', '段落编号']).reset_index(drop=True)

    return result_df, errors, current_book
