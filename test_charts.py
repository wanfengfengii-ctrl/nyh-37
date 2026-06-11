"""
图表生成测试脚本
"""
import sys
import os
import matplotlib
matplotlib.use('Agg')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_validator import validate_csv
from collation_analyzer import CollationAnalyzer
from chart_generator import (
    create_volume_diff_chart,
    create_collation_mark_chart,
    create_copy_diff_heatmap,
    create_volume_copy_heatmap
)


def run_chart_tests():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_data.csv')
    output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_output')
    os.makedirs(output_dir, exist_ok=True)

    df, errors, book_name = validate_csv(csv_path)
    analyzer = CollationAnalyzer(df, book_name)

    print("=" * 60)
    print("测试: 各卷异文数量统计图")
    print("=" * 60)
    try:
        vol_stats = analyzer.get_volume_stats()
        fig = create_volume_diff_chart(vol_stats, book_name)
        out_path = os.path.join(output_dir, '1_各卷异文数量统计图.png')
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        print(f"✓ 已保存: {out_path}")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试: 高频校勘类型统计图")
    print("=" * 60)
    try:
        mark_stats = analyzer.get_collation_mark_stats()
        fig = create_collation_mark_chart(mark_stats, book_name)
        out_path = os.path.join(output_dir, '2_高频校勘类型统计图.png')
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        print(f"✓ 已保存: {out_path}")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试: 抄本差异热力图")
    print("=" * 60)
    try:
        fig = create_copy_diff_heatmap(analyzer, book_name)
        out_path = os.path.join(output_dir, '3_抄本差异热力图.png')
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        print(f"✓ 已保存: {out_path}")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试: 卷次×抄本异文累计热力图")
    print("=" * 60)
    try:
        vol_copy_df = analyzer.get_copy_volume_diff_count()
        fig = create_volume_copy_heatmap(vol_copy_df, book_name)
        out_path = os.path.join(output_dir, '4_卷次抄本异文热力图.png')
        fig.savefig(out_path, dpi=150, bbox_inches='tight')
        print(f"✓ 已保存: {out_path}")
    except Exception as e:
        print(f"✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"所有图表已生成并保存至: {output_dir}")
    print("=" * 60)


if __name__ == '__main__':
    run_chart_tests()
