#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
古籍校勘知识库与智能判例推荐模块 - 单元测试
"""

import sys
import os
import unittest
from datetime import datetime
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from case_library import (
    CaseSourceType, CaseStatus, CaseCategory, RecommendationStatus,
    CaseResolution, CollationCase, SimilarityScore, CaseRecommendation,
    CaseFilter, RecommendationFilter, CaseLibrary
)
from workflow_engine import WorkflowEngine, Role, DoubtStatus, DoubtRecord
from citation_analyzer import CitationRecord, CitationType, CitationStatus
from collation_project import CollationProject, ProjectConfig, ProjectStatus


class TestCaseLibrary(unittest.TestCase):
    """测试判例库核心模块"""

    def setUp(self):
        self.library = CaseLibrary()
        self.sample_resolution = CaseResolution(
            conclusion='确认为脱字，应补入"之"字',
            basis='《史记》三家注本均有"之"字，上下文意通顺',
            reference_sources=[{'source_book': '史记会注考证', 'source_volume': 1,
                                'source_paragraph': 5, 'source_text': '此处当有"之"字'}],
            final_text='先王之制',
            notes='经三位专家复核确认'
        )

    def test_01_create_case_basic(self):
        """测试创建基本判例"""
        case = self.library.create_case(
            project_id='test-proj-001',
            book_name='史记',
            volume=1,
            paragraph=5,
            copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR,
            source_type=CaseSourceType.DOUBT,
            original_text='先王制',
            variant_text='先王之制',
            confidence=0.95,
            created_by='tester',
            resolution=self.sample_resolution,
            rule_id='RULE_001',
            description='疑似脱字',
            source_record_id='doubt-001',
            tags=['脱字', '史记', '甲本']
        )
        self.assertIsNotNone(case.case_id)
        self.assertEqual(case.book_name, '史记')
        self.assertEqual(case.category, CaseCategory.WRONG_CHAR)
        self.assertEqual(case.status, CaseStatus.ACTIVE)
        self.assertEqual(case.usage_count, 0)
        self.assertEqual(case.accept_count, 0)
        print(f"✅ 测试通过: 创建判例 {case.case_id}")

    def test_02_create_case_duplicate_prevention(self):
        """测试判例去重机制"""
        case1 = self.library.create_case(
            project_id='test-proj-001',
            book_name='史记',
            volume=1, paragraph=10, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR,
            source_type=CaseSourceType.DOUBT,
            original_text='ABCD', variant_text='ABXD',
            confidence=0.9, created_by='tester'
        )
        case2 = self.library.create_case(
            project_id='test-proj-001',
            book_name='史记',
            volume=1, paragraph=10, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR,
            source_type=CaseSourceType.DOUBT,
            original_text='ABCD', variant_text='ABXD',
            confidence=0.9, created_by='tester2'
        )
        self.assertEqual(case1.case_id, case2.case_id)
        print(f"✅ 测试通过: 判例去重机制正常 - 返回已有判例 {case1.case_id}")

    def test_03_filter_cases(self):
        """测试多维度筛选"""
        for i in range(10):
            desc = f'特有的描述关键字{i}_XYZ'
            self.library.create_case(
                project_id=f'test-proj-{i % 2}',
                book_name='汉书' if i % 2 else '史记',
                volume=i + 1, paragraph=i + 1,
                copy_batch='甲本' if i < 5 else '乙本',
                category=CaseCategory.WRONG_CHAR if i % 3 == 0 else CaseCategory.MISSING_TEXT,
                source_type=CaseSourceType.DOUBT,
                original_text=f'普通文本{i}', variant_text=f'异文{i}',
                description=desc,
                confidence=0.5 + i * 0.05,
                created_by='tester',
                resolution=CaseResolution(
                    conclusion=f'结论{i}',
                    basis=f'依据{i}'
                )
            )

        f = CaseFilter(book_name='史记')
        cases = self.library.filter_cases(f)
        self.assertTrue(all(c.book_name == '史记' for c in cases))
        print(f"✅ 测试通过: 按书名筛选 - 返回{len(cases)}条")

        f2 = CaseFilter(category=CaseCategory.WRONG_CHAR)
        cases2 = self.library.filter_cases(f2)
        self.assertTrue(all(c.category == CaseCategory.WRONG_CHAR for c in cases2))
        print(f"✅ 测试通过: 按类型筛选 - 返回{len(cases2)}条")

        f3 = CaseFilter(keyword='特有的描述关键字3_XYZ')
        cases3 = self.library.filter_cases(f3)
        self.assertEqual(len(cases3), 1)
        self.assertEqual(cases3[0].description, '特有的描述关键字3_XYZ')
        print(f"✅ 测试通过: 关键词筛选 - 返回{len(cases3)}条")

    def test_04_case_lifecycle(self):
        """测试判例生命周期（失效/重新激活）"""
        case = self.library.create_case(
            project_id='test-proj-001', book_name='后汉书',
            volume=1, paragraph=1, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.MANUAL,
            original_text='test', variant_text='test2',
            confidence=0.8, created_by='tester'
        )
        self.assertEqual(case.status, CaseStatus.ACTIVE)

        self.library.invalidate_case(case.case_id, 'tester', '测试失效')
        updated = self.library.get_case(case.case_id)
        self.assertEqual(updated.status, CaseStatus.INVALIDATED)
        self.assertEqual(updated.invalidated_reason, '测试失效')
        print(f"✅ 测试通过: 判例失效 - {case.case_id}")

        self.library.reactivate_case(case.case_id, 'tester')
        updated2 = self.library.get_case(case.case_id)
        self.assertEqual(updated2.status, CaseStatus.ACTIVE)
        print(f"✅ 测试通过: 判例重新激活 - {case.case_id}")

    def test_05_find_similar_cases(self):
        """测试相似案例检索"""
        self.library.create_case(
            project_id='test-proj-001', book_name='史记',
            volume=5, paragraph=10, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.DOUBT,
            original_text='先王之制法度', variant_text='先王制法度',
            confidence=0.95, created_by='tester'
        )
        self.library.create_case(
            project_id='test-proj-001', book_name='史记',
            volume=3, paragraph=5, copy_batch='甲本',
            category=CaseCategory.MISSING_TEXT, source_type=CaseSourceType.DOUBT,
            original_text='ABCDEFG', variant_text='ABCDEFGH',
            confidence=0.9, created_by='tester'
        )

        target = {
            'original_text': '先王之制法度',
            'book_name': '史记',
            'volume': 5,
            'category': CaseCategory.WRONG_CHAR
        }
        similar = self.library.find_similar_cases(target, project_id='test-proj-001', top_k=5)
        self.assertGreater(len(similar), 0)
        best_case, best_score = similar[0]
        self.assertGreater(best_score.overall, 0.5)
        print(f"✅ 测试通过: 相似案例检索 - 最佳匹配 {best_case.case_id}, 相似度 {best_score.overall:.2%}")

    def test_06_recommendation_workflow(self):
        """测试推荐生成与决策工作流"""
        case = self.library.create_case(
            project_id='test-proj-001', book_name='史记',
            volume=10, paragraph=20, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.DOUBT,
            original_text='天下之大事', variant_text='天下大事',
            confidence=0.92, created_by='tester',
            resolution=self.sample_resolution
        )

        target = {
            'book_name': '史记',
            'volume': 10,
            'paragraph': 20,
            'copy_batch': '甲本',
            'original_text': '天下之大事',
            'variant_text': '天下大事',
            'category': CaseCategory.WRONG_CHAR
        }
        recs = self.library.generate_recommendations(
            target_record_id='new-doubt-001',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-001',
            top_k=3
        )
        self.assertGreater(len(recs), 0)
        rec = recs[0]
        self.assertEqual(rec.status, RecommendationStatus.PENDING)
        self.assertEqual(rec.target_record_id, 'new-doubt-001')
        print(f"✅ 测试通过: 推荐生成 - {rec.recommendation_id}, 相似度{rec.similarity.overall:.2%}")

        self.library.accept_recommendation(rec.recommendation_id, 'reviewer', '测试采纳')
        accepted = self.library.get_recommendation(rec.recommendation_id)
        self.assertEqual(accepted.status, RecommendationStatus.ACCEPTED)
        self.assertEqual(accepted.decided_by, 'reviewer')
        case_updated = self.library.get_case(case.case_id)
        self.assertEqual(case_updated.usage_count, 1)
        self.assertEqual(case_updated.accept_count, 1)
        print(f"✅ 测试通过: 推荐采纳 - {rec.recommendation_id}")

    def test_07_recommendation_reject_and_modify(self):
        """测试推荐驳回和修订"""
        case = self.library.create_case(
            project_id='test-proj-002', book_name='汉书',
            volume=2, paragraph=3, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.DOUBT,
            original_text='汉书记载', variant_text='汉书记载文字',
            confidence=0.88, created_by='tester'
        )
        target = {
            'book_name': '汉书',
            'volume': 2, 'paragraph': 3, 'copy_batch': '甲本',
            'original_text': '汉书记载', 'variant_text': '汉书记载文字',
            'category': CaseCategory.WRONG_CHAR
        }
        recs = self.library.generate_recommendations(
            target_record_id='target-002',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-002'
        )
        rec1 = recs[0]

        self.library.reject_recommendation(rec1.recommendation_id, 'reviewer', '不适用此情况')
        rejected = self.library.get_recommendation(rec1.recommendation_id)
        self.assertEqual(rejected.status, RecommendationStatus.REJECTED)
        case1 = self.library.get_case(case.case_id)
        self.assertEqual(case1.usage_count, 1)
        self.assertEqual(case1.accept_count, 0)
        print(f"✅ 测试通过: 推荐驳回 - {rec1.recommendation_id}")

        recs2 = self.library.generate_recommendations(
            target_record_id='target-003',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-002'
        )
        rec2 = recs2[0]
        modified_content = {
            'conclusion': '修订后的结论',
            'basis': '修订后的依据',
            'final_text': '修订后的文本',
            'note': '做了一些调整'
        }
        self.library.modify_recommendation(rec2.recommendation_id, 'reviewer', modified_content, '修订备注')
        modified_rec = self.library.get_recommendation(rec2.recommendation_id)
        self.assertEqual(modified_rec.status, RecommendationStatus.MODIFIED)
        self.assertIsNotNone(modified_rec.modified_content)
        case2 = self.library.get_case(case.case_id)
        self.assertEqual(case2.usage_count, 2)
        self.assertEqual(case2.accept_count, 1)
        print(f"✅ 测试通过: 推荐修订 - {rec2.recommendation_id}")

    def test_08_recommendation_duplicate_prevention(self):
        """测试推荐去重"""
        case = self.library.create_case(
            project_id='test-proj-003', book_name='三国志',
            volume=1, paragraph=1, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.DOUBT,
            original_text='三国', variant_text='三国演义',
            confidence=0.7, created_by='tester'
        )
        target = {
            'book_name': '三国志',
            'volume': 1, 'paragraph': 1, 'copy_batch': '甲本',
            'original_text': '三国', 'variant_text': '三国演义',
            'category': CaseCategory.WRONG_CHAR
        }
        recs1 = self.library.generate_recommendations(
            target_record_id='target-unique-001',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-003'
        )
        recs2 = self.library.generate_recommendations(
            target_record_id='target-unique-001',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-003'
        )
        self.assertEqual(len(recs2), 0)
        print(f"✅ 测试通过: 推荐去重机制正常")

    def test_09_invalidate_recommendations(self):
        """测试推荐自动失效（原文/判例修改后）"""
        case = self.library.create_case(
            project_id='test-proj-004', book_name='宋书',
            volume=1, paragraph=1, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR, source_type=CaseSourceType.DOUBT,
            original_text='宋书原文', variant_text='宋书异文',
            confidence=0.85, created_by='tester'
        )
        target = {
            'book_name': '宋书',
            'volume': 1, 'paragraph': 1, 'copy_batch': '甲本',
            'original_text': '宋书原文', 'variant_text': '宋书异文',
            'category': CaseCategory.WRONG_CHAR
        }
        recs = self.library.generate_recommendations(
            target_record_id='target-to-invalidate-001',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-004'
        )
        self.assertEqual(recs[0].status, RecommendationStatus.PENDING)

        inv_ids = self.library.invalidate_recommendations_for_target(
            'target-to-invalidate-001', '原始数据被修改'
        )
        self.assertGreater(len(inv_ids), 0)
        inv_rec = self.library.get_recommendation(recs[0].recommendation_id)
        self.assertEqual(inv_rec.status, RecommendationStatus.INVALIDATED)
        self.assertEqual(inv_rec.invalidated_reason, '原始数据被修改')
        print(f"✅ 测试通过: 原文修改后推荐自动失效")

        recs2 = self.library.generate_recommendations(
            target_record_id='target-to-invalidate-002',
            target_record_type='doubt',
            target=target,
            project_id='test-proj-004'
        )
        inv_ids2 = self.library.invalidate_recommendations_for_case(
            case.case_id, '关联判例被修改'
        )
        self.assertGreater(len(inv_ids2), 0)
        print(f"✅ 测试通过: 判例修改后推荐自动失效")

    def test_10_create_case_from_doubt_and_citation(self):
        """测试从疑点和引文记录沉淀判例"""
        doubt = DoubtRecord(
            doubt_id='doubt-for-case-001',
            project_id='test-sediment',
            collation_type='错字',
            volume=5, paragraph=12, copy_batch='甲本',
            original_text='错误原文', suggested_text='正确原文',
            confidence=0.9, reason='检测到可能的错别字',
            rule_id='RULE_TEST',
            status=DoubtStatus.RESOLVED,
            data_hash='fp12345',
            extra={'created_by': 'system'}
        )

        case = self.library.create_case_from_doubt(
            doubt, book_name='南齐书',
            resolution=CaseResolution(
                conclusion='确认是错字',
                basis='对校众本',
                final_text='正确原文'
            ),
            created_by='expert'
        )
        self.assertEqual(case.source_type, CaseSourceType.DOUBT)
        self.assertEqual(case.source_record_id, 'doubt-for-case-001')
        print(f"✅ 测试通过: 从疑点沉淀判例 - {case.case_id}")

        citation = CitationRecord(
            citation_id='cit-for-case-001',
            project_id='test-sediment',
            citation_type=CitationType.ALLUSION,
            volume=3, paragraph=7, copy_batch='甲本',
            original_text='语出典故处', quoted_text='典故原文',
            start_pos=0, end_pos=10,
            confidence=0.88, match_basis='文字匹配',
            status=CitationStatus.CONFIRMED,
            created_by='system',
            data_hash='hashcit123'
        )
        case2 = self.library.create_case_from_citation(
            citation, book_name='南齐书',
            resolution=CaseResolution(
                conclusion='确认为典故引用',
                basis='典故与《庄子》原文一致',
                reference_sources=[{'source_book': '庄子', 'source_chapter': '逍遥游'}]
            ),
            created_by='expert'
        )
        self.assertEqual(case2.source_type, CaseSourceType.CITATION)
        self.assertEqual(case2.source_record_id, 'cit-for-case-001')
        print(f"✅ 测试通过: 从引文沉淀判例 - {case2.case_id}")

    def test_11_statistics(self):
        """测试统计信息生成"""
        lib2 = CaseLibrary()
        for i in range(5):
            lib2.create_case(
                project_id='stat-proj', book_name='梁书',
                volume=i + 1, paragraph=i + 1, copy_batch='甲本',
                category=CaseCategory.WRONG_CHAR if i % 2 else CaseCategory.MISSING_TEXT,
                source_type=CaseSourceType.DOUBT,
                original_text=f'A{i}', variant_text=f'B{i}',
                confidence=0.7 + i * 0.05, created_by='tester'
            )
        stats = lib2.get_statistics('stat-proj')
        self.assertEqual(stats['total_cases'], 5)
        self.assertEqual(stats['active_cases'], 5)
        self.assertIn('错字', stats['by_category'])
        self.assertIn('异文疑点', stats['by_source_type'])
        print(f"✅ 测试通过: 统计信息生成 - 判例总数{stats['total_cases']}")


class TestWorkflowEngineIntegration(unittest.TestCase):
    """测试工作流引擎集成"""

    def setUp(self):
        self.engine = WorkflowEngine()

    def test_01_permissions(self):
        """测试判例库权限"""
        pm = self.engine.permission_manager
        pm.set_user_role('admin', Role.ADMIN)
        self.assertTrue(pm.has_permission('admin', 'view_cases'))
        self.assertTrue(pm.has_permission('admin', 'create_case'))
        self.assertTrue(pm.has_permission('admin', 'edit_case'))
        self.assertTrue(pm.has_permission('admin', 'invalidate_case'))
        self.assertTrue(pm.has_permission('admin', 'view_recommendations'))
        self.assertTrue(pm.has_permission('admin', 'decide_recommendation'))
        self.assertTrue(pm.has_permission('admin', 'generate_recommendations'))

        pm.set_user_role('reviewer1', Role.REVIEWER)
        self.assertTrue(pm.has_permission('reviewer1', 'view_cases'))
        self.assertTrue(pm.has_permission('reviewer1', 'view_recommendations'))
        self.assertTrue(pm.has_permission('reviewer1', 'decide_recommendation'))
        print("✅ 测试通过: 判例库权限配置正常")

    def test_02_engine_case_library_exists(self):
        """测试工作流引擎是否正确初始化了判例库"""
        self.assertIsNotNone(self.engine.case_library)
        self.assertIsInstance(self.engine.case_library, CaseLibrary)

        case = self.engine.case_library.create_case(
            project_id='eng-test', book_name='陈书',
            volume=1, paragraph=1, copy_batch='甲本',
            category=CaseCategory.WRONG_CHAR,
            source_type=CaseSourceType.MANUAL,
            original_text='陈', variant_text='陈书',
            confidence=0.7, created_by='admin'
        )
        self.assertIsNotNone(case)
        self.assertIsNotNone(case.case_id)

        got = self.engine.get_case(case.case_id)
        self.assertEqual(got.book_name, '陈书')

        cases = self.engine.get_all_cases('eng-test')
        self.assertGreaterEqual(len(cases), 1)

        self.engine.permission_manager.set_user_role('admin', Role.ADMIN)
        self.engine.invalidate_case('admin', case.case_id, '测试')
        got2 = self.engine.get_case(case.case_id)
        self.assertEqual(got2.status, CaseStatus.INVALIDATED)
        print(f"✅ 测试通过: 工作流引擎判例操作 - {case.case_id}")

    def test_03_engine_statistics(self):
        """测试引擎层统计"""
        self.engine.permission_manager.set_user_role('admin', Role.ADMIN)
        stats = self.engine.get_case_statistics('non-existent')
        self.assertIn('total_cases', stats)
        self.assertEqual(stats['total_cases'], 0)
        print(f"✅ 测试通过: 工作流引擎统计查询正常")


def run_all_tests():
    print("=" * 70)
    print("古籍校勘知识库与智能判例推荐模块 - 单元测试")
    print("=" * 70)
    print()

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestCaseLibrary))
    suite.addTests(loader.loadTestsFromTestCase(TestWorkflowEngineIntegration))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    print()
    print("=" * 70)
    if result.wasSuccessful():
        print("🎉 所有测试通过！")
    else:
        print(f"⚠️  测试失败: {len(result.failures)}个失败, {len(result.errors)}个错误")
    print("=" * 70)
    return result.wasSuccessful()


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
