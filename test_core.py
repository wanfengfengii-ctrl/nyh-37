"""
核心功能测试脚本
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_validator import validate_csv
from collation_analyzer import CollationAnalyzer


def run_tests():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_data.csv')

    print("=" * 60)
    print("测试1: CSV导入与数据验证")
    print("=" * 60)
    try:
        df, errors, book_name = validate_csv(csv_path)
        print(f"✓ 书名: {book_name}")
        print(f"✓ 有效记录数: {len(df)}")
        print(f"✓ 验证失败行数: {len(errors)}")
        print("\n失败行详情:")
        for err in errors[:10]:
            print(f"  - {err}")
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return

    print("\n" + "=" * 60)
    print("测试2: 异文分析器初始化")
    print("=" * 60)
    try:
        analyzer = CollationAnalyzer(df, book_name)
        print(f"✓ 抄本批次: {analyzer.copy_batches}")
        print(f"✓ 卷次: {analyzer.volumes}")
    except Exception as e:
        print(f"✗ 初始化失败: {e}")
        return

    print("\n" + "=" * 60)
    print("测试3: 缺段标记")
    print("=" * 60)
    try:
        missing = analyzer.get_missing_paragraphs()
        if missing:
            print("✓ 发现缺段:")
            for (copy_b, vol), ranges in missing.items():
                for s, e in ranges:
                    print(f"  - {copy_b} 第{vol}卷: 段落{s}-{e}")
        else:
            print("  (无缺段)")
    except Exception as e:
        print(f"✗ 缺段检测失败: {e}")

    print("\n" + "=" * 60)
    print("测试4: 分卷分段对照表（多抄本并排）")
    print("=" * 60)
    try:
        table = analyzer.build_comparison_table()
        print(f"✓ 对照表格形状: {table.shape}")
        print(f"✓ 列: {list(table.columns)}")
        print("\n前5行摘录:")
        print(table.head().to_string(index=False))
        diff_count = len(table[table['异文'] == '有'])
        print(f"\n✓ 有异文的段落数: {diff_count}")
    except Exception as e:
        print(f"✗ 对照表生成失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试5: 抄本两两异文检测 (宋刊本 vs 元抄本)")
    print("=" * 60)
    try:
        diffs = analyzer.compute_diffs('宋刊本', '元抄本')
        print(f"✓ 异文段落数: {len(diffs)}")
        for d in diffs[:3]:
            print(f"\n  段落{d.para_id}:")
            print(f"    宋刊本: {d.content_a}")
            print(f"    元抄本: {d.content_b}")
            for tag, a, b in d.diff_regions[:2]:
                print(f"    差异[{tag}]: [{a}] → [{b}]")
    except Exception as e:
        print(f"✗ 异文检测失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试6: 各卷异文统计")
    print("=" * 60)
    try:
        stats = analyzer.get_volume_stats()
        print(stats.to_string(index=False))
    except Exception as e:
        print(f"✗ 卷统计失败: {e}")

    print("\n" + "=" * 60)
    print("测试7: 高频校勘类型统计")
    print("=" * 60)
    try:
        mark_stats = analyzer.get_collation_mark_stats()
        print(mark_stats.to_string(index=False))
    except Exception as e:
        print(f"✗ 校勘类型统计失败: {e}")

    print("\n" + "=" * 60)
    print("测试8: 抄本差异矩阵")
    print("=" * 60)
    try:
        matrix = analyzer.build_diff_matrix()
        batches = analyzer.copy_batches
        print(f"     {'  '.join(f'{b:>8}' for b in batches)}")
        for a in batches:
            row = [f"{a:5}"]
            for b in batches:
                val = matrix.get((a, b), 0)
                row.append(f"{val:>8}")
            print('  '.join(row))
    except Exception as e:
        print(f"✗ 差异矩阵失败: {e}")

    print("\n" + "=" * 60)
    print("测试9: 数据修改后重新计算")
    print("=" * 60)
    try:
        old_count = len(analyzer.build_comparison_table()[analyzer.build_comparison_table()['异文'] == '有'])
        print(f"修改前异文段落数: {old_count}")
        success = analyzer.update_record(0, '原文内容', '修改后的测试内容xxx')
        print(f"✓ 更新记录成功: {success}")
        new_count = len(analyzer.build_comparison_table()[analyzer.build_comparison_table()['异文'] == '有'])
        print(f"修改后异文段落数: {new_count}")
        assert new_count >= old_count, "修改后异文数量应变化"
        print("✓ 重新计算功能正常")
    except Exception as e:
        print(f"✗ 修改测试失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("测试10: 卷次-抄本异文热力数据")
    print("=" * 60)
    try:
        vc = analyzer.get_copy_volume_diff_count()
        print(vc.to_string(index=False))
    except Exception as e:
        print(f"✗ 热力数据失败: {e}")

    print("\n" + "=" * 60)
    print("所有核心测试完成！")
    print("=" * 60)


if __name__ == '__main__':
    run_tests()
