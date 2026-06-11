"""
Bug修复验证测试脚本
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_validator import validate_csv
from collation_analyzer import CollationAnalyzer


def run_bugfix_tests():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_data.csv')
    df, errors, book_name = validate_csv(csv_path)
    analyzer = CollationAnalyzer(df, book_name)

    initial_len = len(analyzer.df)
    first_row = analyzer.df.iloc[0]

    print("=" * 60)
    print("Bug1验证: 修改后重新计算状态标记")
    print("=" * 60)
    old_table = analyzer.build_comparison_table()
    old_dirty = analyzer._stats_dirty
    print(f"修改前 _stats_dirty = {old_dirty}")
    ok, msg = analyzer.update_record(0, '原文内容', 'Bug1测试修改内容')
    print(f"update_record返回: ok={ok}, msg='{msg}'")
    print(f"修改后 _stats_dirty = {analyzer._stats_dirty}  (应为 True)")
    assert analyzer._stats_dirty is True, "Bug1未修复: 标记未失效"
    new_table = analyzer.build_comparison_table()
    assert len(new_table[new_table['异文'] == '有']) != len(old_table[old_table['异文'] == '有']), \
        "Bug1未修复: 对照表未变化"
    print("✓ Bug1验证通过: 修改后统计标记失效，下次取用时重新计算")

    print("\n" + "=" * 60)
    print("Bug2验证: 同一抄本同一卷重复段落编号应被拦截")
    print("=" * 60)
    analyzer2 = CollationAnalyzer(df.copy(), book_name)
    idx0_copy = analyzer2.df.iloc[0]['抄本批次']
    idx0_vol = analyzer2.df.iloc[0]['卷次']
    idx0_para = analyzer2.df.iloc[0]['段落编号']

    idx1 = 1
    target_copy = idx0_copy
    target_vol = idx0_vol
    target_para = idx0_para
    print(f"尝试将第{idx1 + 2}行的(抄本,卷,段)修改为与第0行相同: ({target_copy}, {target_vol}, {target_para})")

    ok, msg = analyzer2.update_record(idx1, '抄本批次', target_copy)
    if not ok:
        print(f"  修改抄本批次失败: {msg}")
    else:
        ok, msg = analyzer2.update_record(idx1, '卷次', target_vol)
        if not ok:
            print(f"  修改卷次失败: {msg}")
        else:
            ok, msg = analyzer2.update_record(idx1, '段落编号', target_para)

    print(f"最终拦截结果: ok={ok}, msg='{msg}'")
    assert not ok and "重复" in msg, f"Bug2未修复: 应该拦截重复段号但实际通过 (ok={ok})"
    print("✓ Bug2验证通过: 重复段落编号被成功拦截")

    print("\n" + "=" * 60)
    print("Bug3验证: 修改书名到另一本书应被拦截")
    print("=" * 60)
    analyzer3 = CollationAnalyzer(df.copy(), book_name)
    print(f"当前书名: {analyzer3.book_name}")
    ok, msg = analyzer3.update_record(0, '书名', '孟子集注')
    print(f"修改书名返回: ok={ok}, msg='{msg}'")
    assert not ok and "不同书目" in msg, f"Bug3未修复: 应该拦截不同书名但实际通过 (ok={ok})"
    assert analyzer3.book_name == book_name, "Bug3未修复: analyzer.book_name被改变了"
    assert analyzer3.df.iloc[0]['书名'] == book_name, "Bug3未修复: 行内书名被改动"
    print("✓ Bug3验证通过: 不同书名被成功拦截")

    print("\n" + "=" * 60)
    print("Bug4验证: 非法卷次和段落编号应返回明确错误信息")
    print("=" * 60)
    analyzer4 = CollationAnalyzer(df.copy(), book_name)

    print("测试: 卷次 = 'abc'")
    ok, msg = analyzer4.update_record(0, '卷次', 'abc')
    print(f"  ok={ok}, msg='{msg}'")
    assert not ok and "格式错误" in msg, "Bug4未修复: 卷次非数字无明确错误"

    print("测试: 卷次 = -5")
    ok, msg = analyzer4.update_record(0, '卷次', -5)
    print(f"  ok={ok}, msg='{msg}'")
    assert not ok and "正整数" in msg, "Bug4未修复: 卷次负整数无明确错误"

    print("测试: 段落编号 = 'xyz'")
    ok, msg = analyzer4.update_record(0, '段落编号', 'xyz')
    print(f"  ok={ok}, msg='{msg}'")
    assert not ok and "格式错误" in msg, "Bug4未修复: 段号非数字无明确错误"

    print("测试: 段落编号 = 0")
    ok, msg = analyzer4.update_record(0, '段落编号', 0)
    print(f"  ok={ok}, msg='{msg}'")
    assert not ok and "正整数" in msg, "Bug4未修复: 段号为0无明确错误"

    print("测试: 书名为空")
    ok, msg = analyzer4.update_record(0, '书名', '  ')
    print(f"  ok={ok}, msg='{msg}'")
    assert not ok and "不能为空" in msg, "Bug4未修复: 书名为空无明确错误"

    print("✓ Bug4验证通过: 所有非法输入均返回了明确的错误信息")

    print("\n" + "=" * 60)
    print("全部4个Bug修复验证通过！")
    print("=" * 60)


if __name__ == '__main__':
    run_bugfix_tests()
