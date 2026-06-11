"""
校勘项目管理模块：按书名/卷次/抄本批次管理校勘项目
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from datetime import datetime
import pandas as pd
import hashlib

from collation_analyzer import CollationAnalyzer
from collation_rules import CollationRuleLibrary, CollationType
from workflow_engine import WorkflowEngine, Role, DoubtStatus, ReviewAction, DoubtRecord
from doubt_detector import DoubtDetector, DetectionSummary
from audit_trail import AuditTrail, OperationType
from citation_analyzer import CitationAnalyzer, CitationType as CitationTypeEnum, CitationDetectionSummary


class ProjectStatus(str, Enum):
    DRAFT = '草稿'
    IN_PROGRESS = '进行中'
    PAUSED = '已暂停'
    COMPLETED = '已完成'
    ARCHIVED = '已归档'


@dataclass
class ProjectConfig:
    project_id: str
    project_name: str
    book_name: str
    volumes: List[int] = field(default_factory=list)
    copy_batches: List[str] = field(default_factory=list)
    description: str = ''
    created_by: str = ''
    created_at: datetime = field(default_factory=datetime.now)
    status: ProjectStatus = ProjectStatus.DRAFT
    enabled_rule_ids: Set[str] = field(default_factory=set)
    assigned_users: Dict[str, Role] = field(default_factory=dict)
    extra: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'project_id': self.project_id,
            'project_name': self.project_name,
            'book_name': self.book_name,
            'volumes': ','.join(str(v) for v in self.volumes),
            'copy_batches': ','.join(self.copy_batches),
            'description': self.description,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'status': self.status.value,
            'enabled_rules': ','.join(self.enabled_rule_ids),
            'assigned_users': str(self.assigned_users)
        }


class CollationProject:
    def __init__(self,
                 config: ProjectConfig,
                 analyzer: Optional[CollationAnalyzer] = None,
                 rule_library: Optional[CollationRuleLibrary] = None,
                 workflow_engine: Optional[WorkflowEngine] = None,
                 doubt_detector: Optional[DoubtDetector] = None,
                 audit_trail: Optional[AuditTrail] = None,
                 citation_analyzer: Optional[CitationAnalyzer] = None):
        self.config = config
        self.analyzer = analyzer
        self.rule_library = rule_library or CollationRuleLibrary()
        self.audit_trail = audit_trail or AuditTrail()
        self.workflow_engine = workflow_engine or WorkflowEngine(self.audit_trail)
        self.doubt_detector = doubt_detector or DoubtDetector(self.rule_library, self.workflow_engine)
        self.citation_analyzer = citation_analyzer or CitationAnalyzer(analyzer)
        self._counter = 0

        if not config.enabled_rule_ids:
            self.config.enabled_rule_ids = {r.rule_id for r in self.rule_library.get_enabled_rules()}

        for username, role in config.assigned_users.items():
            self.workflow_engine.permission_manager.set_user_role(username, role)

    @property
    def project_id(self) -> str:
        return self.config.project_id

    @property
    def book_name(self) -> str:
        return self.config.book_name

    def set_analyzer(self, analyzer: CollationAnalyzer):
        if analyzer.book_name != self.book_name:
            raise ValueError(f"分析器书名【{analyzer.book_name}】与项目书名【{self.book_name}】不匹配")
        self.analyzer = analyzer
        self.citation_analyzer.set_analyzer(analyzer)
        self.config.volumes = sorted(set(self.config.volumes) | set(analyzer.volumes))
        self.config.copy_batches = sorted(set(self.config.copy_batches) | set(analyzer.copy_batches))

    def update_config(self, operator: str, **kwargs) -> bool:
        self.workflow_engine.permission_manager.check_permission(operator, 'edit_project')

        old_values = {}
        for key, value in kwargs.items():
            if hasattr(self.config, key) and key not in ['project_id', 'book_name', 'created_at', 'created_by']:
                old_values[key] = getattr(self.config, key)
                setattr(self.config, key, value)

        if old_values:
            self.audit_trail.log(
                operation_type=OperationType.PROJECT_UPDATE,
                operator=operator,
                operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
                project_id=self.project_id,
                target_id=self.project_id,
                target_type='ProjectConfig',
                description=f"更新项目配置: {list(old_values.keys())}",
                old_value=old_values,
                new_value=kwargs
            )
            return True
        return False

    def set_project_status(self, operator: str, status: ProjectStatus):
        self.workflow_engine.permission_manager.check_permission(operator, 'edit_project')
        old_status = self.config.status
        self.config.status = status
        self.audit_trail.log(
            operation_type=OperationType.PROJECT_UPDATE,
            operator=operator,
            operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=self.project_id,
            target_id=self.project_id,
            target_type='ProjectConfig',
            description=f"项目状态变更: {old_status.value} → {status.value}",
            old_value={'status': old_status.value},
            new_value={'status': status.value}
        )

    def start(self, operator: str):
        self.set_project_status(operator, ProjectStatus.IN_PROGRESS)

    def pause(self, operator: str):
        self.set_project_status(operator, ProjectStatus.PAUSED)

    def associate_analyzer(self, operator: str, analyzer: CollationAnalyzer):
        self.workflow_engine.permission_manager.check_permission(operator, 'import_data')
        self.set_analyzer(analyzer)
        self.audit_trail.log(
            operation_type=OperationType.DATA_IMPORT,
            operator=operator,
            operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=self.project_id,
            description=f"关联分析器数据: {analyzer.book_name} ({len(analyzer.df)}条记录)"
        )

    def get_stats(self) -> Dict[str, any]:
        stats = {
            'total_doubts': 0,
            'pending_doubts': 0,
            'processing_doubts': 0,
            'reviewed_doubts': 0,
            'rejected_doubts': 0,
            'resolved_doubts': 0,
            'invalid_doubts': 0,
            'total_records': len(self.analyzer.df) if self.analyzer else 0,
            'total_members': len(self.config.assigned_users),
            'by_type': {},
            'by_status': {},
            'total_citations': 0,
            'pending_citations': 0,
            'confirmed_citations': 0,
            'rejected_citations': 0,
            'invalid_citations': 0,
            'misquote_citations': 0
        }
        doubts = self.workflow_engine.get_all_doubts(self.project_id)
        for d in doubts:
            stats['total_doubts'] += 1
            status_key = d.status.value
            type_key = d.collation_type
            stats['by_status'][status_key] = stats['by_status'].get(status_key, 0) + 1
            stats['by_type'][type_key] = stats['by_type'].get(type_key, 0) + 1
            if d.status == DoubtStatus.PENDING:
                stats['pending_doubts'] += 1
            elif d.status == DoubtStatus.IN_PROGRESS:
                stats['processing_doubts'] += 1
            elif d.status == DoubtStatus.REVIEWED:
                stats['reviewed_doubts'] += 1
            elif d.status == DoubtStatus.REJECTED:
                stats['rejected_doubts'] += 1
            elif d.status == DoubtStatus.RESOLVED:
                stats['resolved_doubts'] += 1
            elif d.status == DoubtStatus.INVALID:
                stats['invalid_doubts'] += 1
        cite_stats = self.workflow_engine.get_citation_statistics(self.project_id)
        stats['total_citations'] = cite_stats.get('total', 0)
        stats['pending_citations'] = cite_stats.get('pending', 0)
        stats['confirmed_citations'] = cite_stats.get('confirmed', 0)
        stats['rejected_citations'] = cite_stats.get('rejected', 0)
        stats['invalid_citations'] = cite_stats.get('invalidated', 0)
        stats['misquote_citations'] = cite_stats.get('misquote_count', 0)
        return stats

    def assign_user(self, admin_user: str, username: str, role: Role):
        self.workflow_engine.set_user_role(admin_user, username, role)
        self.config.assigned_users[username] = role

    def remove_user(self, admin_user: str, username: str):
        self.workflow_engine.permission_manager.check_permission(admin_user, 'assign_role')
        if username in self.config.assigned_users:
            del self.config.assigned_users[username]
            self.workflow_engine.permission_manager._user_roles.pop(username, None)
            self.audit_trail.log(
                operation_type=OperationType.ROLE_ASSIGN,
                operator=admin_user,
                operator_role=self.workflow_engine.permission_manager.get_user_role(admin_user).value,
                project_id=self.project_id,
                description=f"移除用户【{username}】的项目权限"
            )

    def enable_rule(self, operator: str, rule_id: str) -> bool:
        self.workflow_engine.permission_manager.check_permission(operator, 'manage_rules')
        if self.rule_library.enable_rule(rule_id):
            self.config.enabled_rule_ids.add(rule_id)
            self.audit_trail.log(
                operation_type=OperationType.RULE_UPDATE,
                operator=operator,
                operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
                project_id=self.project_id,
                target_id=rule_id,
                target_type='CollationRule',
                description=f"启用校勘规则: {rule_id}"
            )
            return True
        return False

    def disable_rule(self, operator: str, rule_id: str) -> bool:
        self.workflow_engine.permission_manager.check_permission(operator, 'manage_rules')
        if self.rule_library.disable_rule(rule_id):
            self.config.enabled_rule_ids.discard(rule_id)
            self.audit_trail.log(
                operation_type=OperationType.RULE_UPDATE,
                operator=operator,
                operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
                project_id=self.project_id,
                target_id=rule_id,
                target_type='CollationRule',
                description=f"禁用校勘规则: {rule_id}"
            )
            return True
        return False

    def run_doubt_detection(self,
                            operator: str,
                            volumes: Optional[List[int]] = None,
                            detect_types: Optional[List[CollationType]] = None) -> DetectionSummary:
        if not self.analyzer:
            raise ValueError("项目尚未关联分析器，请先导入数据")

        if volumes:
            total_summary = DetectionSummary()
            for vol in volumes:
                vol_summary = self.doubt_detector.detect_for_volume(
                    self.analyzer, self.project_id, vol, operator, detect_types
                )
                total_summary.results.extend(vol_summary.results)
                total_summary.total_detected += vol_summary.total_detected
                total_summary.new_created += vol_summary.new_created
                total_summary.duplicates_skipped += vol_summary.duplicates_skipped
                for k, v in vol_summary.by_type.items():
                    total_summary.by_type[k] = total_summary.by_type.get(k, 0) + v
            return total_summary
        else:
            return self.doubt_detector.detect_all(
                self.analyzer, self.project_id, operator, detect_types
            )

    def update_analyzer_record(self,
                               operator: str,
                               index: int,
                               column: str,
                               value) -> Tuple[bool, str, List[str]]:
        self.workflow_engine.permission_manager.check_permission(operator, 'edit_data')

        if not self.analyzer:
            return False, "项目尚未关联分析器", []

        row = self.analyzer.df.iloc[index]
        volume = int(row['卷次'])
        paragraph = int(row['段落编号'])
        copy_batch = str(row['抄本批次'])

        old_row = row.to_dict()

        success, err_msg = self.analyzer.update_record(index, column, value)
        if not success:
            return False, err_msg, []

        new_row = self.analyzer.df.iloc[index].to_dict()
        changed_cols = [k for k in old_row if old_row[k] != new_row[k]]

        invalidated_doubt_ids = self.workflow_engine.invalidate_doubts_by_data_change(
            operator=operator,
            project_id=self.project_id,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            reason=f"原始数据被修改: {changed_cols}"
        )

        invalidated_citation_ids = self.workflow_engine.invalidate_citations_by_data_change(
            operator=operator,
            project_id=self.project_id,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            reason=f"原始数据被修改: {changed_cols}"
        )

        all_invalidated_ids = invalidated_doubt_ids + invalidated_citation_ids

        self.audit_trail.log(
            operation_type=OperationType.DATA_UPDATE,
            operator=operator,
            operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=self.project_id,
            target_id=f'record-{index}',
            target_type='DataRecord',
            description=f"修改数据行{index + 2}的【{column}】，导致{len(invalidated_doubt_ids)}个疑点、{len(invalidated_citation_ids)}个引文溯源失效",
            old_value=old_row,
            new_value=new_row,
            extra={'invalidated_doubts': invalidated_doubt_ids, 'invalidated_citations': invalidated_citation_ids}
        )

        return True, "", all_invalidated_ids

    def delete_analyzer_record(self, operator: str, index: int) -> Tuple[bool, List[str]]:
        self.workflow_engine.permission_manager.check_permission(operator, 'edit_data')

        if not self.analyzer:
            return False, []

        row = self.analyzer.df.iloc[index]
        volume = int(row['卷次'])
        paragraph = int(row['段落编号'])
        copy_batch = str(row['抄本批次'])
        old_row = row.to_dict()

        invalidated_doubt_ids = self.workflow_engine.invalidate_doubts_by_data_change(
            operator=operator,
            project_id=self.project_id,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            reason=f"关联数据行被删除"
        )

        invalidated_citation_ids = self.workflow_engine.invalidate_citations_by_data_change(
            operator=operator,
            project_id=self.project_id,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            reason=f"关联数据行被删除"
        )

        all_invalidated_ids = invalidated_doubt_ids + invalidated_citation_ids

        success = self.analyzer.delete_record(index)
        if success:
            self.audit_trail.log(
                operation_type=OperationType.DATA_DELETE,
                operator=operator,
                operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
                project_id=self.project_id,
                target_id=f'record-{index}',
                target_type='DataRecord',
                description=f"删除数据行{index + 2}，导致{len(invalidated_doubt_ids)}个疑点、{len(invalidated_citation_ids)}个引文溯源失效",
                old_value=old_row,
                extra={'invalidated_doubts': invalidated_doubt_ids, 'invalidated_citations': invalidated_citation_ids}
            )

        return success, all_invalidated_ids

    def get_doubts(self,
                   status: Optional[DoubtStatus] = None,
                   volume: Optional[int] = None,
                   assignee: Optional[str] = None) -> List[DoubtRecord]:
        if status:
            doubts = self.workflow_engine.get_doubts_by_status(status, self.project_id)
        elif volume:
            doubts = self.workflow_engine.get_doubts_by_volume(volume, self.project_id)
        elif assignee:
            doubts = self.workflow_engine.get_doubts_by_assignee(assignee, self.project_id)
        else:
            doubts = self.workflow_engine.get_all_doubts(self.project_id)
        return doubts

    def review_doubt(self,
                     reviewer: str,
                     doubt_id: str,
                     action: ReviewAction,
                     content: str,
                     new_assignee: Optional[str] = None) -> DoubtRecord:
        return self.workflow_engine.review_doubt(reviewer, doubt_id, action, content, new_assignee)

    def resolve_doubt(self, resolver: str, doubt_id: str, resolution: str) -> DoubtRecord:
        return self.workflow_engine.resolve_doubt(resolver, doubt_id, resolution)

    def reactivate_doubt(self, operator: str, doubt_id: str) -> DoubtRecord:
        return self.workflow_engine.reactivate_doubt(operator, doubt_id)

    def run_citation_detection(self,
                                  operator: str,
                                  volume: Optional[int] = None,
                                  copy_batch: Optional[str] = None,
                                  detect_types: Optional[List[CitationTypeEnum]] = None) -> CitationDetectionSummary:
        self.workflow_engine.permission_manager.check_permission(operator, 'detect_citations')
        if not self.analyzer:
            raise ValueError("项目尚未关联分析器，请先导入数据")
        summary = self.citation_analyzer.detect_citations(
            project_id=self.project_id,
            operator=operator,
            book_name=self.book_name,
            volume=volume,
            copy_batch=copy_batch,
            detect_types=detect_types
        )
        created_count = 0
        for record in self.citation_analyzer.get_pending_records():
            try:
                self.workflow_engine.create_citation(operator, record)
                created_count += 1
            except ValueError:
                pass
        summary.new_created = created_count
        self.audit_trail.log(
            operation_type=OperationType.CITATION_DETECT,
            operator=operator,
            operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=self.project_id,
            target_type='CitationDetection',
            description=f"引文检测完成: 检测到{summary.total_detected}条，新增{summary.new_created}条，跳过重复{summary.duplicates_skipped}条"
        )
        return summary

    def get_citations(self,
                       status=None,
                       citation_type=None,
                       volume: Optional[int] = None,
                       copy_batch: Optional[str] = None):
        return self.workflow_engine.get_citations_by_filters(
            self.project_id, status, citation_type, volume, copy_batch
        )

    def get_all_citations(self):
        return self.workflow_engine.get_all_citations(self.project_id)

    def confirm_citation(self, reviewer: str, citation_id: str, source=None, note: str = ''):
        return self.workflow_engine.confirm_citation(reviewer, citation_id, source, note)

    def reject_citation(self, reviewer: str, citation_id: str, reason: str = ''):
        return self.workflow_engine.reject_citation(reviewer, citation_id, reason)

    def supplement_citation_source(self, operator: str, citation_id: str, source, note: str = ''):
        return self.workflow_engine.supplement_citation_source(operator, citation_id, source, note)

    def reactivate_citation(self, operator: str, citation_id: str):
        return self.workflow_engine.reactivate_citation(operator, citation_id)

    def get_citation_statistics(self) -> Dict:
        return self.workflow_engine.get_citation_statistics(self.project_id)

    def get_statistics(self) -> Dict:
        doubt_stats = self.workflow_engine.get_statistics(self.project_id)

        volume_stats = {}
        if self.analyzer:
            vol_stats_df = self.analyzer.get_volume_stats()
            if not vol_stats_df.empty:
                for _, row in vol_stats_df.iterrows():
                    vol = int(row['卷次'])
                    volume_stats[vol] = {
                        'total_paragraphs': int(row['总段落数']),
                        'diff_paragraphs': int(row['异文段落数']),
                        'diff_rate': float(row['异文率(%)']),
                        'missing_count': int(row['缺段总数'])
                    }

        return {
            'project': self.config.to_dict(),
            'doubts': doubt_stats,
            'volumes': volume_stats,
            'copy_batches': self.analyzer.copy_batches if self.analyzer else [],
            'record_count': len(self.analyzer.df) if self.analyzer else 0,
            'audit_count': len(self.audit_trail.get_records_by_project(self.project_id))
        }

    def get_timeline(self, limit: int = 100) -> List[Dict]:
        return self.audit_trail.get_timeline(self.project_id, limit)

    def has_permission(self, username: str, permission_name: str) -> bool:
        return self.workflow_engine.permission_manager.has_permission(username, permission_name)

    def get_user_role(self, username: str) -> Role:
        return self.workflow_engine.permission_manager.get_user_role(username)


class ProjectManager:
    def __init__(self, audit_trail: Optional[AuditTrail] = None):
        self._projects: Dict[str, CollationProject] = {}
        self.audit_trail = audit_trail or AuditTrail()
        self._counter = 0

    def _generate_project_id(self) -> str:
        self._counter += 1
        timestamp = datetime.now().strftime('%Y%m%d')
        return f'PROJ-{timestamp}-{self._counter:04d}'

    def create_project(self,
                       creator: str,
                       project_name: str,
                       book_name: str,
                       volumes: Optional[List[int]] = None,
                       copy_batches: Optional[List[str]] = None,
                       description: str = '',
                       analyzer: Optional[CollationAnalyzer] = None) -> CollationProject:
        project_id = self._generate_project_id()

        config = ProjectConfig(
            project_id=project_id,
            project_name=project_name,
            book_name=book_name,
            volumes=volumes or [],
            copy_batches=copy_batches or [],
            description=description,
            created_by=creator,
            status=ProjectStatus.DRAFT
        )

        project = CollationProject(
            config=config,
            analyzer=analyzer,
            audit_trail=self.audit_trail
        )

        project.workflow_engine.permission_manager.set_user_role(creator, Role.ADMIN)
        config.assigned_users[creator] = Role.ADMIN

        self._projects[project_id] = project

        self.audit_trail.log(
            operation_type=OperationType.PROJECT_CREATE,
            operator=creator,
            operator_role=Role.ADMIN.value,
            project_id=project_id,
            target_id=project_id,
            target_type='CollationProject',
            description=f"创建校勘项目: {project_name} ({book_name})",
            new_value=config.to_dict()
        )

        return project

    def get_project(self, project_id: str) -> Optional[CollationProject]:
        return self._projects.get(project_id)

    def get_all_projects(self) -> List[CollationProject]:
        return sorted(self._projects.values(), key=lambda p: p.config.created_at, reverse=True)

    def get_projects_by_book(self, book_name: str) -> List[CollationProject]:
        return [p for p in self.get_all_projects() if p.book_name == book_name]

    def get_projects_by_user(self, username: str) -> List[CollationProject]:
        return [p for p in self.get_all_projects() if username in p.config.assigned_users]

    def list_projects(self) -> List[CollationProject]:
        return self.get_all_projects()

    def check_permission(self, operator: str, role: Role, permission: str):
        if not hasattr(self, '_tmp_permission_manager'):
            from workflow_engine import PermissionManager
            self._tmp_permission_manager = PermissionManager()
        self._tmp_permission_manager.set_user_role(operator, role)
        self._tmp_permission_manager.check_permission(operator, permission)

    def delete_project(self, operator: str, project_id: str) -> bool:
        project = self.get_project(project_id)
        if not project:
            return False

        project.workflow_engine.permission_manager.check_permission(operator, 'delete_project')

        del self._projects[project_id]

        self.audit_trail.log(
            operation_type=OperationType.PROJECT_DELETE,
            operator=operator,
            operator_role=project.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=project_id,
            target_id=project_id,
            target_type='CollationProject',
            description=f"删除校勘项目: {project.config.project_name}"
        )

        return True

    def __len__(self) -> int:
        return len(self._projects)
