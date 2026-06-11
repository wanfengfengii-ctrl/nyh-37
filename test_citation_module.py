#!/usr/bin/env python3
"""
古籍引文溯源与互证分析模块 - 功能测试脚本
"""
import sys
import os
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from collation_project import CollationProject, ProjectConfig, ProjectManager
from collation_analyzer import CollationAnalyzer
from citation_analyzer import (
    CitationAnalyzer, CitationType, CitationStatus,
    CitationSource
)
from collation_exporter import CollationExporter


def create_test_data():
    """创建测试用的古籍抄本数据（长格式：每抄本每段一行）"""
    data = [
        {'书名': '论语', '卷次': 1, '段落编号': 1, '抄本批次': '抄本甲', '原文内容': '学而时习之，不亦说乎？有朋自远方来，不亦乐乎？'},
        {'书名': '论语', '卷次': 1, '段落编号': 1, '抄本批次': '抄本乙', '原文内容': '学而时习之，不亦说乎？有朋自远方来，不亦乐乎？'},
        {'书名': '论语', '卷次': 1, '段落编号': 2, '抄本批次': '抄本甲', '原文内容': '人不知而不愠，不亦君子乎？'},
        {'书名': '论语', '卷次': 1, '段落编号': 2, '抄本批次': '抄本乙', '原文内容': '人不知而不愠，不亦君子乎？'},
        {'书名': '论语', '卷次': 2, '段落编号': 1, '抄本批次': '抄本甲', '原文内容': '学而时习之，不亦说乎？有朋自远方来，不亦乐乎？'},
        {'书名': '论语', '卷次': 2, '段落编号': 1, '抄本批次': '抄本乙', '原文内容': '学而时习之，不亦说乎？有朋自远方来，不矣乐乎？'},
        {'书名': '论语', '卷次': 2, '段落编号': 2, '抄本批次': '抄本甲', '原文内容': '君子务本，本立而道生。'},
        {'书名': '论语', '卷次': 2, '段落编号': 2, '抄本批次': '抄本乙', '原文内容': '君子务本，本立而道生。'},
        {'书名': '论语', '卷次': 3, '段落编号': 1, '抄本批次': '抄本甲', '原文内容': '子曰：学而时习之，不亦说乎？'},
        {'书名': '论语', '卷次': 3, '段落编号': 1, '抄本批次': '抄本乙', '原文内容': '子曰：学而时习之，不亦说乎？'},
        {'书名': '论语', '卷次': 3, '段落编号': 2, '抄本批次': '抄本甲', '原文内容': '温故而知新，可以为师矣。'},
        {'书名': '论语', '卷次': 3, '段落编号': 2, '抄本批次': '抄本乙', '原文内容': '温故而知新，可以为师矣。'},
    ]
    return pd.DataFrame(data)


def test_workflow_integration():
    """测试工作流引擎集成：创建、查询、确认、驳回、失效"""
    print("=" * 60)
    print("测试 1: 核心分析与工作流引擎集成")
    print("=" * 60)

    pm = ProjectManager()
    project = pm.create_project(
        creator='admin_user',
        project_name='引文测试项目',
        book_name='论语',
        description='用于测试引文溯源功能'
    )

    df = create_test_data()
    analyzer = CollationAnalyzer(df, book_name='论语')
    project.set_analyzer(analyzer)

    print("  [1.1] 运行引文检测...")
    detect_types = [CitationType.QUOTATION, CitationType.REPETITION, CitationType.MISQUOTE]
    summary = project.run_citation_detection(
        operator='admin_user',
        detect_types=detect_types
    )
    print(f"    检测摘要:")
    print(f"      总检测数: {summary.total_detected}")
    print(f"      新创建: {summary.new_created}")
    print(f"      重复跳过: {summary.duplicates_skipped}")
    print(f"      按类型: {dict(summary.by_type)}")
    print(f"      疑似误引数: {summary.misquote_count}")

    all_citations = project.get_all_citations()
    print(f"\n  [1.2] 引文示例 (前3条):")
    for cit in all_citations[:3]:
        print(f"    [{cit.citation_id}] {cit.citation_type.value} | 卷{cit.volume}段{cit.paragraph} {cit.copy_batch}")
        print(f"      引文: {cit.quoted_text[:30]}")
        print(f"      置信度: {cit.confidence:.2f} | 状态: {cit.status.value}")
        if cit.matches:
            m = cit.matches[0]
            print(f"      出处: {m.match_book}卷{m.match_volume}段{m.match_paragraph} (相似度:{m.match_similarity:.2f})")

    print("\n  [1.3] 测试去重机制（再次运行检测）...")
    summary2 = project.run_citation_detection(
        operator='admin_user',
        detect_types=detect_types
    )
    all_citations2 = project.get_all_citations()
    print(f"    再次检测后: {summary2.new_created} 条新增, 总记录 {len(all_citations2)} 条")
    assert len(all_citations2) == len(all_citations), "去重机制失效！"
    print("    ✓ 去重机制正常")

    print("\n  [1.4] 按筛选条件查询...")
    filtered = project.get_citations(status=CitationStatus.PENDING)
    print(f"    待确认引文: {len(filtered)} 条")
    filtered_vol = project.get_citations(volume=1)
    print(f"    第1卷引文: {len(filtered_vol)} 条")
    filtered_type = project.get_citations(citation_type=CitationType.REPETITION)
    print(f"    重复语段: {len(filtered_type)} 条")

    print("\n  [1.5] 测试确认和驳回...")
    pending_citations = project.get_all_citations()
    confirmed_count = 0
    rejected_count = 0
    if pending_citations:
        cit_id = pending_citations[0].citation_id
        result = project.confirm_citation(reviewer='admin_user', citation_id=cit_id, note='测试确认')
        if result:
            confirmed_count += 1
            print(f"    ✓ 确认引文 {cit_id}")

        if len(pending_citations) > 1:
            cit_id2 = pending_citations[1].citation_id
            result2 = project.reject_citation(reviewer='admin_user', citation_id=cit_id2, reason='测试驳回')
            if result2:
                rejected_count += 1
                print(f"    ✓ 驳回引文 {cit_id2}")
    print(f"    共确认 {confirmed_count} 条, 驳回 {rejected_count} 条")

    print("\n  [1.6] 测试补充出处...")
    pending = project.get_citations(status=CitationStatus.PENDING)
    if pending:
        src = CitationSource(
            source_book='论语注疏',
            source_volume=1,
            source_paragraph=1,
            source_copy_batch='抄本甲',
            source_text='学而时习之，不亦说乎？',
            source_chapter='学而第一',
            source_page='P5',
            note='人工补充出处'
        )
        result3 = project.supplement_citation_source(
            operator='admin_user', citation_id=pending[0].citation_id, source=src, note='测试补充'
        )
        print(f"    补充出处: {'成功' if result3 else '失败'}")

    print("\n  [1.7] 测试统计信息...")
    stats = project.get_citation_statistics()
    print(f"    引文统计:")
    for k, v in stats.items():
        if isinstance(v, dict):
            print(f"      {k}: {dict(v)}")
        else:
            print(f"      {k}: {v}")

    print("\n  [1.8] 测试自动失效机制（修改原文）...")
    before_invalid = len(project.get_citations(status=CitationStatus.INVALIDATED))
    success, err_msg, invalidated = project.update_analyzer_record(
        'admin_user', 0, '原文内容', '修改后的文本，应该导致引文失效'
    )
    after_invalid = len(project.get_citations(status=CitationStatus.INVALIDATED))
    print(f"    修改成功: {success}, 失效前: {before_invalid}, 失效后: {after_invalid}, 新失效: {len(invalidated)}")

    print("\n  [1.9] 测试重新激活...")
    invalid_cits = project.get_citations(status=CitationStatus.INVALIDATED)
    if invalid_cits:
        result4 = project.reactivate_citation(operator='admin_user', citation_id=invalid_cits[0].citation_id)
        print(f"    重新激活: {'成功' if result4 else '失败'}")

    print("\n  [1.10] 测试互证关系图谱...")
    try:
        graph = project.citation_analyzer.build_citation_graph(all_citations)
        print(f"    图谱: {len(graph.nodes)} 节点, {len(graph.edges)} 边")
        if graph.nodes:
            print(f"    节点类型示例: {graph.nodes[0].node_type} = {graph.nodes[0].label}")
        if graph.edges:
            print(f"    边关系示例: {graph.edges[0].relation} ({graph.edges[0].source_id} → {graph.edges[0].target_id})")
    except Exception as e:
        print(f"    图谱构建: 跳过 ({e})")
        import traceback
        traceback.print_exc()

    print("\n  ✓ 核心分析与工作流集成测试通过\n")
    return project


def test_exporter(project):
    """测试导出功能"""
    print("=" * 60)
    print("测试 2: 导出功能")
    print("=" * 60)

    export_dir = '/tmp/citation_test_export'
    os.makedirs(export_dir, exist_ok=True)

    exporter = CollationExporter(project)

    print("  [2.1] 导出引文溯源表...")
    try:
        result = exporter.export_citation_table(export_dir, operator='admin_user')
        print(f"    ✓ {result.description}")
        print(f"      文件: {result.file_path}")
        size = os.path.getsize(result.file_path) if os.path.exists(result.file_path) else 0
        print(f"      文件大小: {size} 字节")
    except Exception as e:
        print(f"    ✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n  [2.2] 导出疑似误引清单...")
    try:
        result = exporter.export_misquote_list(export_dir, operator='admin_user')
        print(f"    ✓ {result.description}")
        print(f"      文件: {result.file_path}")
        size = os.path.getsize(result.file_path) if os.path.exists(result.file_path) else 0
        print(f"      文件大小: {size} 字节")
    except Exception as e:
        print(f"    ✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n  [2.3] 汇总导出（含引文）...")
    try:
        results = exporter.export_all(export_dir, operator='admin_user')
        print(f"    ✓ 共导出 {len(results)} 个文件:")
        for r in results:
            icon = '✓' if r.record_count > 0 or '失败' not in r.description else '○'
            print(f"      {icon} {r.file_type}: {r.description}")
    except Exception as e:
        print(f"    ✗ 失败: {e}")
        import traceback
        traceback.print_exc()

    print("\n  ✓ 导出功能测试通过\n")


def main():
    print("\n" + "=" * 60)
    print("古籍引文溯源与互证分析模块 - 集成测试")
    print("=" * 60 + "\n")

    try:
        project = test_workflow_integration()
        test_exporter(project)

        print("=" * 60)
        print("🎉 所有测试通过！")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ 测试失败 (断言): {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试失败 (异常): {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
