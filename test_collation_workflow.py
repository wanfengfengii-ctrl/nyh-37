"""
校勘工作流系统综合测试脚本
测试：规则库、审计跟踪、权限控制、工作流、疑点检测、项目管理、导出功能
"""
import sys
import os
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_validator import validate_csv
from collation_analyzer import CollationAnalyzer
from collation_rules import CollationRuleLibrary, CollationType, CollationRule
from audit_trail import AuditTrail, OperationType
from workflow_engine import WorkflowEngine, Role, DoubtStatus, ReviewAction
from doubt_detector import DoubtDetector
from collation_project import ProjectManager, ProjectStatus
from collation_exporter import CollationExporter


def run_all_tests():
    csv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sample_data.csv')
    df, errors, book_name = validate_csv(csv_path)
    analyzer = CollationAnalyzer(df, book_name)

    print("=" * 80)
    print("校勘工作流系统综合测试")
    print("=" * 80)

    all_passed = True

    # 测试1: 校勘规则库
    print("\n" + "=" * 60)
    print("测试1: 校勘规则库功能")
    print("=" * 60)
    try:
        rule_lib = CollationRuleLibrary()
        all_rules = rule_lib.get_all_rules()
        print(f"✓ 加载默认规则: {len(all_rules)} 条")

        wrong_char_rules = rule_lib.get_rules_by_type(CollationType.WRONG_CHAR)
        print(f"✓ 错字检测规则: {len(wrong_char_rules)} 条")

        enabled_rules = rule_lib.get_enabled_rules()
        print(f"✓ 已启用规则: {len(enabled_rules)} 条")

        is_wrong, conf = rule_lib.check_wrong_char('习', '时')
        assert is_wrong, f"应该识别为错字: 习→时"
        print(f"✓ 错字识别: 习→时 (置信度: {conf:.2f})")

        candidates = rule_lib.get_wrong_char_candidates('弟')
        assert '悌' in candidates, f"弟的候选应包含悌"
        print(f"✓ 错字候选: 弟 → {candidates}")

        rule_lib.disable_rule('RULE_WRONG_CHAR_002')
        rule = rule_lib.get_rule('RULE_WRONG_CHAR_002')
        assert not rule.enabled, "规则应该被禁用"
        print(f"✓ 禁用规则: {rule.name}")

        rule_lib.enable_rule('RULE_WRONG_CHAR_002')
        rule = rule_lib.get_rule('RULE_WRONG_CHAR_002')
        assert rule.enabled, "规则应该被启用"
        print(f"✓ 启用规则: {rule.name}")

        print("✓ 规则库测试全部通过")
    except Exception as e:
        print(f"✗ 规则库测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试2: 审计跟踪
    print("\n" + "=" * 60)
    print("测试2: 审计跟踪功能")
    print("=" * 60)
    try:
        audit = AuditTrail()

        audit.log(
            operation_type=OperationType.LOGIN,
            operator='admin',
            operator_role='管理员',
            description='用户登录系统'
        )
        time.sleep(0.01)

        audit.log(
            operation_type=OperationType.DATA_IMPORT,
            operator='admin',
            operator_role='管理员',
            project_id='PROJ-001',
            description=f'导入数据: {book_name}'
        )

        all_records = audit.get_all_records()
        assert len(all_records) == 2, f"应该有2条记录，实际: {len(all_records)}"
        print(f"✓ 记录操作日志: {len(all_records)} 条")

        proj_records = audit.get_records_by_project('PROJ-001')
        assert len(proj_records) == 1, f"项目记录应该有1条"
        print(f"✓ 按项目查询: {len(proj_records)} 条")

        op_records = audit.get_records_by_operator('admin')
        assert len(op_records) == 2, f"操作人记录应该有2条"
        print(f"✓ 按操作人查询: {len(op_records)} 条")

        type_records = audit.get_records_by_type(OperationType.LOGIN)
        assert len(type_records) == 1, f"登录记录应该有1条"
        print(f"✓ 按操作类型查询: {len(type_records)} 条")

        timeline = audit.get_timeline()
        assert len(timeline) == 2, f"时间线应该有2条"
        print(f"✓ 获取时间线: {len(timeline)} 条")
        for item in timeline:
            print(f"  - {item['time']} {item['operator']}[{item['role']}]: {item['action']} - {item['description']}")

        print("✓ 审计跟踪测试全部通过")
    except Exception as e:
        print(f"✗ 审计跟踪测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试3: 角色权限控制
    print("\n" + "=" * 60)
    print("测试3: 角色权限控制")
    print("=" * 60)
    try:
        workflow = WorkflowEngine()
        pm = workflow.permission_manager

        pm.set_user_role('admin_user', Role.ADMIN)
        pm.set_user_role('collator_user', Role.COLLATOR)
        pm.set_user_role('reviewer_user', Role.REVIEWER)
        pm.set_user_role('guest_user', Role.GUEST)

        assert pm.has_permission('admin_user', 'delete_project'), "管理员应该有删除项目权限"
        print("✓ 管理员权限: 可以删除项目")

        assert not pm.has_permission('collator_user', 'delete_project'), "校勘员不应该有删除项目权限"
        print("✓ 校勘员权限: 不能删除项目")

        assert pm.has_permission('collator_user', 'detect_doubts'), "校勘员应该有检测疑点权限"
        print("✓ 校勘员权限: 可以检测疑点")

        assert pm.has_permission('reviewer_user', 'review_doubt'), "复核员应该有复核疑点权限"
        print("✓ 复核员权限: 可以复核疑点")

        assert not pm.has_permission('reviewer_user', 'edit_data'), "复核员不应该有编辑数据权限"
        print("✓ 复核员权限: 不能编辑数据")

        assert not pm.has_permission('guest_user', 'export_data'), "访客不应该有导出权限"
        print("✓ 访客权限: 不能导出数据")

        try:
            pm.check_permission('guest_user', 'export_data')
            assert False, "应该抛出权限错误"
        except PermissionError as e:
            print(f"✓ 权限拦截正常工作: {e}")

        print("✓ 角色权限测试全部通过")
    except Exception as e:
        print(f"✗ 角色权限测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试4: 工作流引擎 - 疑点创建与重复检测
    print("\n" + "=" * 60)
    print("测试4: 工作流引擎 - 疑点创建与重复检测")
    print("=" * 60)
    try:
        workflow = WorkflowEngine()
        workflow.permission_manager.set_user_role('collator1', Role.COLLATOR)
        workflow.permission_manager.set_user_role('reviewer1', Role.REVIEWER)

        doubt1 = workflow.create_doubt(
            creator='collator1',
            project_id='PROJ-TEST',
            collation_type='错字',
            volume=1,
            paragraph=1,
            copy_batch='宋刊本',
            original_text='习',
            suggested_text='时',
            confidence=0.85,
            reason='形近字错误',
            rule_id='RULE_WRONG_CHAR_001'
        )
        print(f"✓ 创建疑点1: {doubt1.doubt_id} - 状态: {doubt1.status.value}")
        assert doubt1.status == DoubtStatus.PENDING, "初始状态应该是待复核"

        try:
            workflow.create_doubt(
                creator='collator1',
                project_id='PROJ-TEST',
                collation_type='错字',
                volume=1,
                paragraph=1,
                copy_batch='宋刊本',
                original_text='习',
                suggested_text='时',
                confidence=0.85,
                reason='重复创建测试',
                rule_id='RULE_WRONG_CHAR_001'
            )
            assert False, "应该抛出重复疑点错误"
        except ValueError as e:
            print(f"✓ 重复疑点拦截正常工作: {e}")

        is_dup = workflow.check_duplicate(
            project_id='PROJ-TEST',
            volume=1,
            paragraph=1,
            copy_batch='宋刊本',
            collation_type='错字',
            original_text='习',
            suggested_text='时'
        )
        assert is_dup, "应该检测到重复"
        print(f"✓ 重复检测功能正常")

        doubt2 = workflow.create_doubt(
            creator='collator1',
            project_id='PROJ-TEST',
            collation_type='脱文',
            volume=1,
            paragraph=4,
            copy_batch='元抄本',
            original_text='',
            suggested_text='有子曰其为人也孝悌而好犯上者鲜矣',
            confidence=0.9,
            reason='段落缺失',
            rule_id='RULE_MISSING_001'
        )
        print(f"✓ 创建疑点2: {doubt2.doubt_id} - 状态: {doubt2.status.value}")

        all_doubts = workflow.get_all_doubts('PROJ-TEST')
        assert len(all_doubts) == 2, f"应该有2个疑点"
        print(f"✓ 查询所有疑点: {len(all_doubts)} 个")

        pending_doubts = workflow.get_doubts_by_status(DoubtStatus.PENDING, 'PROJ-TEST')
        assert len(pending_doubts) == 2, f"待复核疑点应该有2个"
        print(f"✓ 待复核疑点: {len(pending_doubts)} 个")

        print("✓ 工作流疑点创建测试全部通过")
    except Exception as e:
        print(f"✗ 工作流疑点创建测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试5: 工作流引擎 - 复核流程与状态流转
    print("\n" + "=" * 60)
    print("测试5: 工作流引擎 - 复核流程与状态流转")
    print("=" * 60)
    try:
        workflow = WorkflowEngine()
        workflow.permission_manager.set_user_role('collator1', Role.COLLATOR)
        workflow.permission_manager.set_user_role('reviewer1', Role.REVIEWER)
        workflow.permission_manager.set_user_role('reviewer2', Role.REVIEWER)

        doubt = workflow.create_doubt(
            creator='collator1',
            project_id='PROJ-TEST2',
            collation_type='错字',
            volume=1,
            paragraph=1,
            copy_batch='宋刊本',
            original_text='习',
            suggested_text='时',
            confidence=0.85,
            reason='形近字错误',
            rule_id='RULE_WRONG_CHAR_001'
        )
        print(f"✓ 初始状态: {doubt.status.value}")

        reviewed_doubt = workflow.review_doubt(
            reviewer='reviewer1',
            doubt_id=doubt.doubt_id,
            action=ReviewAction.COMMENT,
            content='需要进一步确认，请核对其他版本'
        )
        assert reviewed_doubt.status == DoubtStatus.PENDING, "备注不改变状态"
        print(f"✓ 添加备注后状态: {reviewed_doubt.status.value} (复核历史: {len(reviewed_doubt.review_history)} 条)")

        reviewed_doubt = workflow.review_doubt(
            reviewer='reviewer1',
            doubt_id=doubt.doubt_id,
            action=ReviewAction.REASSIGN,
            content='请复核员2帮忙确认',
            new_assignee='reviewer2'
        )
        assert reviewed_doubt.assignee == 'reviewer2', "应该转交给reviewer2"
        print(f"✓ 转交后指派人: {reviewed_doubt.assignee}")

        reviewed_doubt = workflow.review_doubt(
            reviewer='reviewer2',
            doubt_id=doubt.doubt_id,
            action=ReviewAction.ACCEPT,
            content='确认为错字，建议校改'
        )
        assert reviewed_doubt.status == DoubtStatus.REVIEWED, "通过后状态应为已复核"
        print(f"✓ 通过后状态: {reviewed_doubt.status.value}")

        resolved_doubt = workflow.resolve_doubt(
            resolver='reviewer1',
            doubt_id=doubt.doubt_id,
            resolution='已按照建议校改，从「习」改为「时」'
        )
        assert resolved_doubt.status == DoubtStatus.RESOLVED, "解决后状态应为已解决"
        assert resolved_doubt.resolved_at is not None, "应该有解决时间"
        print(f"✓ 解决后状态: {resolved_doubt.status.value}")
        print(f"✓ 复核历史共: {len(resolved_doubt.review_history)} 条")
        for h in resolved_doubt.review_history:
            print(f"  - {h.timestamp.strftime('%H:%M:%S')} {h.reviewer}[{h.reviewer_role}] {h.action.value}: {h.content}")

        stats = workflow.get_statistics('PROJ-TEST2')
        print(f"✓ 统计信息: 总{stats['total']}, 待复核{stats['pending']}, 已解决{stats['resolved']}")

        print("✓ 复核流程测试全部通过")
    except Exception as e:
        print(f"✗ 复核流程测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试6: 已复核记录修改后自动失效
    print("\n" + "=" * 60)
    print("测试6: 已复核记录修改后自动失效")
    print("=" * 60)
    try:
        audit = AuditTrail()
        workflow = WorkflowEngine(audit)
        workflow.permission_manager.set_user_role('admin', Role.ADMIN)
        workflow.permission_manager.set_user_role('collator', Role.COLLATOR)
        workflow.permission_manager.set_user_role('reviewer', Role.REVIEWER)

        doubt = workflow.create_doubt(
            creator='collator',
            project_id='PROJ-TEST3',
            collation_type='错字',
            volume=1,
            paragraph=1,
            copy_batch='宋刊本',
            original_text='习',
            suggested_text='时',
            confidence=0.85,
            reason='形近字错误',
            rule_id='RULE_WRONG_CHAR_001'
        )

        reviewed_doubt = workflow.review_doubt(
            reviewer='reviewer',
            doubt_id=doubt.doubt_id,
            action=ReviewAction.ACCEPT,
            content='确认通过'
        )
        assert reviewed_doubt.status == DoubtStatus.REVIEWED, "复核通过"
        print(f"✓ 复核通过: 状态={reviewed_doubt.status.value}")

        invalidated_ids = workflow.invalidate_doubts_by_data_change(
            operator='collator',
            project_id='PROJ-TEST3',
            volume=1,
            paragraph=1,
            copy_batch='宋刊本',
            reason='原始数据被修改'
        )
        assert len(invalidated_ids) == 1, f"应该失效1个疑点，实际: {len(invalidated_ids)}"
        print(f"✓ 数据修改触发失效: {invalidated_ids}")

        invalidated_doubt = workflow.get_doubt(doubt.doubt_id)
        assert invalidated_doubt.invalidated, "疑点应该被标记为失效"
        assert invalidated_doubt.status == DoubtStatus.INVALIDATED, "状态应该是已失效"
        print(f"✓ 失效后状态: {invalidated_doubt.status.value}, 原因: {invalidated_doubt.invalidated_reason}")

        try:
            workflow.review_doubt(
                reviewer='reviewer',
                doubt_id=doubt.doubt_id,
                action=ReviewAction.ACCEPT,
                content='再次复核'
            )
            assert False, "失效的疑点不能复核"
        except ValueError as e:
            print(f"✓ 失效疑点无法复核: {e}")

        reactivated = workflow.reactivate_doubt('collator', doubt.doubt_id)
        assert reactivated.status == DoubtStatus.PENDING, "重新激活后状态应为待复核"
        assert not reactivated.invalidated, "不应该再标记为失效"
        print(f"✓ 重新激活后状态: {reactivated.status.value}")

        print("✓ 自动失效测试全部通过")
    except Exception as e:
        print(f"✗ 自动失效测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试7: 自动疑点识别
    print("\n" + "=" * 60)
    print("测试7: 自动疑点识别")
    print("=" * 60)
    try:
        audit = AuditTrail()
        workflow = WorkflowEngine(audit)
        detector = DoubtDetector(workflow_engine=workflow)
        workflow.permission_manager.set_user_role('collator', Role.COLLATOR)

        summary = detector.detect_all(analyzer, 'PROJ-DETECT', 'collator')
        print(f"✓ 疑点检测完成: 检测到{summary.total_detected}个, "
              f"新增{summary.new_created}个, "
              f"跳过重复{summary.duplicates_skipped}个")
        print(f"✓ 按类型统计:")
        for ctype, count in summary.by_type.items():
            print(f"  - {ctype}: {count}个")

        assert summary.total_detected > 0, "应该检测到至少一些疑点"

        summary2 = detector.detect_all(analyzer, 'PROJ-DETECT', 'collator')
        assert summary2.duplicates_skipped > 0, "第二次检测应该有重复被跳过"
        assert summary2.new_created == 0, "第二次检测不应该新增疑点"
        print(f"✓ 重复检测验证: 跳过{summary2.duplicates_skipped}个重复，新增{summary2.new_created}个")

        print("✓ 自动疑点识别测试全部通过")
    except Exception as e:
        print(f"✗ 自动疑点识别测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试8: 校勘项目管理
    print("\n" + "=" * 60)
    print("测试8: 校勘项目管理")
    print("=" * 60)
    try:
        project_manager = ProjectManager()

        project = project_manager.create_project(
            creator='admin',
            project_name='论语集注校勘项目',
            book_name=book_name,
            description='论语集注多抄本校勘工作',
            volumes=[1, 2],
            copy_batches=['宋刊本', '元抄本', '明抄本']
        )
        print(f"✓ 创建项目: {project.project_id} - {project.config.project_name}")
        assert project.config.status == ProjectStatus.DRAFT, "初始状态应为草稿"

        project.set_analyzer(analyzer)
        print(f"✓ 关联分析器: 抄本{len(project.analyzer.copy_batches)}个, "
              f"卷次{len(project.analyzer.volumes)}卷, "
              f"记录{len(project.analyzer.df)}条")

        project.set_project_status('admin', ProjectStatus.IN_PROGRESS)
        assert project.config.status == ProjectStatus.IN_PROGRESS, "状态应为进行中"
        print(f"✓ 项目状态: {project.config.status.value}")

        project.assign_user('admin', 'collator1', Role.COLLATOR)
        project.assign_user('admin', 'reviewer1', Role.REVIEWER)
        print(f"✓ 分配用户: {len(project.config.assigned_users)} 人")
        for user, role in project.config.assigned_users.items():
            print(f"  - {user}: {role.value}")

        summary = project.run_doubt_detection('collator1')
        print(f"✓ 运行疑点检测: 新增{summary.new_created}个疑点")

        stats = project.get_statistics()
        print(f"✓ 项目统计: 疑点{stats['doubts']['total']}个, "
              f"待复核{stats['doubts']['pending']}个, "
              f"记录{stats['record_count']}条")

        timeline = project.get_timeline(limit=10)
        print(f"✓ 项目时间线: {len(timeline)} 条记录")

        print("✓ 项目管理测试全部通过")
    except Exception as e:
        print(f"✗ 项目管理测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试9: 项目层数据修改触发疑点失效
    print("\n" + "=" * 60)
    print("测试9: 项目层数据修改触发疑点失效")
    print("=" * 60)
    try:
        project_manager = ProjectManager()
        project = project_manager.create_project(
            creator='admin',
            project_name='失效测试项目',
            book_name=book_name
        )
        project.set_analyzer(analyzer)
        project.assign_user('admin', 'collator1', Role.COLLATOR)
        project.assign_user('admin', 'reviewer1', Role.REVIEWER)

        summary = project.run_doubt_detection('collator1')
        assert summary.new_created > 0, "应该创建一些疑点"
        print(f"✓ 初始检测: {summary.new_created} 个疑点")

        pending_before = len(project.get_doubts(status=DoubtStatus.PENDING))
        print(f"✓ 待复核疑点数: {pending_before}")

        success, err_msg, invalidated = project.update_analyzer_record(
            operator='collator1',
            index=0,
            column='原文内容',
            value='修改测试内容'
        )
        assert success, f"修改应该成功: {err_msg}"
        print(f"✓ 修改数据行0，导致 {len(invalidated)} 个疑点失效")

        invalidated_after = len(project.get_doubts(status=DoubtStatus.INVALIDATED))
        assert invalidated_after == len(invalidated), f"失效疑点数量应该匹配"
        print(f"✓ 失效疑点数: {invalidated_after}")

        success, invalidated2 = project.delete_analyzer_record('collator1', 1)
        assert success, "删除应该成功"
        print(f"✓ 删除数据行1，导致 {len(invalidated2)} 个疑点失效")

        print("✓ 项目层数据修改测试全部通过")
    except Exception as e:
        print(f"✗ 项目层数据修改测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试10: 导出功能
    print("\n" + "=" * 60)
    print("测试10: 校勘结果导出")
    print("=" * 60)
    try:
        project_manager = ProjectManager()
        project = project_manager.create_project(
            creator='admin',
            project_name='导出测试项目',
            book_name=book_name
        )
        project.set_analyzer(analyzer)
        project.assign_user('admin', 'collator1', Role.COLLATOR)
        project.assign_user('admin', 'reviewer1', Role.REVIEWER)
        project.assign_user('admin', 'exporter', Role.COLLATOR)

        project.run_doubt_detection('collator1')

        doubts = project.get_doubts(status=DoubtStatus.PENDING)
        if doubts:
            project.review_doubt('reviewer1', doubts[0].doubt_id, ReviewAction.ACCEPT, '测试通过')
            project.resolve_doubt('reviewer1', doubts[0].doubt_id, '测试解决')

        exporter = CollationExporter(project)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = exporter.export_collation_report(tmpdir, operator='exporter')
            assert os.path.exists(result.file_path), f"校勘报告文件应该存在: {result.file_path}"
            print(f"✓ 导出校勘报告: {os.path.basename(result.file_path)} ({result.record_count}条)")

            result = exporter.export_variant_list(tmpdir, operator='exporter')
            assert os.path.exists(result.file_path), f"异文清单文件应该存在"
            print(f"✓ 导出异文清单: {os.path.basename(result.file_path)} ({result.record_count}条)")

            result = exporter.export_review_log(tmpdir, operator='exporter')
            assert os.path.exists(result.file_path), f"复核日志文件应该存在"
            print(f"✓ 导出复核日志: {os.path.basename(result.file_path)} ({result.record_count}条)")

            result = exporter.export_audit_trail(tmpdir, operator='admin')
            assert os.path.exists(result.file_path), f"审计日志文件应该存在"
            print(f"✓ 导出审计日志: {os.path.basename(result.file_path)} ({result.record_count}条)")

            result = exporter.generate_markdown_report(tmpdir, operator='exporter')
            assert os.path.exists(result.file_path), f"Markdown报告文件应该存在"
            print(f"✓ 导出Markdown报告: {os.path.basename(result.file_path)}")

            results = exporter.export_all(tmpdir, operator='exporter')
            print(f"✓ 一键全量导出: {len(results)} 个文件")
            for r in results:
                if r.file_path:
                    print(f"  - {r.file_type}: {os.path.basename(r.file_path)} ({r.record_count}条)")
                else:
                    print(f"  - {r.file_type}: {r.description}")

            vol1_results = exporter.export_all(tmpdir, volume=1, operator='exporter')
            print(f"✓ 按卷导出(第1卷): {len(vol1_results)} 个文件")

        try:
            exporter.export_audit_trail(tmpdir, operator='exporter')
            assert False, "校勘员不应该能导出审计日志"
        except PermissionError as e:
            print(f"✓ 审计日志导出权限控制正常: {e}")

        print("✓ 导出功能测试全部通过")
    except Exception as e:
        print(f"✗ 导出功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    # 测试11: 原有功能不被破坏
    print("\n" + "=" * 60)
    print("测试11: 原有核心功能验证")
    print("=" * 60)
    try:
        analyzer2 = CollationAnalyzer(df, book_name)
        table = analyzer2.build_comparison_table()
        assert not table.empty, "对照表不应该为空"
        print(f"✓ 分卷分段对照表: {table.shape[0]}行 × {table.shape[1]}列")

        diffs = analyzer2.compute_diffs('宋刊本', '元抄本')
        assert len(diffs) > 0, "应该检测到异文"
        print(f"✓ 宋刊本 vs 元抄本 异文段落: {len(diffs)} 处")

        stats = analyzer2.get_volume_stats()
        assert not stats.empty, "卷统计不应该为空"
        print(f"✓ 各卷异文统计: {len(stats)} 卷")

        missing = analyzer2.get_missing_paragraphs()
        print(f"✓ 缺段检测: {len(missing)} 个抄本×卷次组合有缺段")

        old_count = len(analyzer2.build_comparison_table()[analyzer2.build_comparison_table()['异文'] == '有'])
        success, err_msg = analyzer2.update_record(0, '原文内容', '修改测试内容')
        assert success, f"修改应该成功"
        new_count = len(analyzer2.build_comparison_table()[analyzer2.build_comparison_table()['异文'] == '有'])
        assert new_count != old_count, "修改后异文数量应该变化"
        print(f"✓ 数据修改后重新计算: 异文段落 {old_count} → {new_count}")

        print("✓ 原有核心功能验证通过")
    except Exception as e:
        print(f"✗ 原有核心功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ 所有测试通过！校勘工作流系统运行正常。")
    else:
        print("❌ 部分测试失败，请检查上述错误信息。")
    print("=" * 80)

    return all_passed


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)
