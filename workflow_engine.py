"""
工作流引擎模块：角色权限管理、疑点状态流转、意见历史记录
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Callable, Any
from enum import Enum
from datetime import datetime

from audit_trail import AuditTrail, OperationType


class Role(str, Enum):
    ADMIN = '管理员'
    COLLATOR = '校勘员'
    REVIEWER = '复核员'
    GUEST = '访客'


class DoubtStatus(str, Enum):
    PENDING = '待复核'
    IN_PROGRESS = '处理中'
    REVIEWED = '已复核'
    REJECTED = '已驳回'
    RESOLVED = '已解决'
    INVALIDATED = '已失效'


class ReviewAction(str, Enum):
    ACCEPT = '通过'
    REJECT = '驳回'
    MODIFY = '修改'
    REASSIGN = '转交'
    COMMENT = '备注'


@dataclass
class Permission:
    name: str
    description: str
    roles: Set[Role]


@dataclass
class ReviewComment:
    comment_id: str
    timestamp: datetime
    reviewer: str
    reviewer_role: str
    action: ReviewAction
    content: str
    old_status: Optional[DoubtStatus] = None
    new_status: Optional[DoubtStatus] = None
    assignee: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'comment_id': self.comment_id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'reviewer': self.reviewer,
            'reviewer_role': self.reviewer_role,
            'action': self.action.value,
            'content': self.content,
            'old_status': self.old_status.value if self.old_status else '',
            'new_status': self.new_status.value if self.new_status else '',
            'assignee': self.assignee or ''
        }


@dataclass
class DoubtRecord:
    doubt_id: str
    project_id: str
    collation_type: str
    volume: int
    paragraph: int
    copy_batch: str
    original_text: str
    suggested_text: str
    confidence: float
    reason: str
    rule_id: str
    status: DoubtStatus = DoubtStatus.PENDING
    assignee: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    review_history: List[ReviewComment] = field(default_factory=list)
    resolved_at: Optional[datetime] = None
    invalidated: bool = False
    invalidated_reason: str = ''
    data_hash: str = ''
    extra: Dict = field(default_factory=dict)

    @property
    def created_by(self) -> str:
        return self.extra.get('created_by', '')

    @property
    def invalid_reason(self) -> str:
        return self.invalidated_reason

    @property
    def data_fingerprint(self) -> str:
        return self.data_hash

    @property
    def unique_key(self) -> str:
        return f'{self.project_id}|{self.volume}|{self.paragraph}|{self.copy_batch}|{self.collation_type}|{self.original_text}|{self.suggested_text}'

    @property
    def is_active(self) -> bool:
        return not self.invalidated and self.status != DoubtStatus.RESOLVED

    def add_comment(self, comment: ReviewComment):
        self.review_history.append(comment)
        self.updated_at = datetime.now()

    def invalidate(self, reason: str = '关联数据已修改'):
        self.invalidated = True
        self.invalidated_reason = reason
        old_status = self.status
        self.status = DoubtStatus.INVALIDATED
        self.updated_at = datetime.now()
        return old_status

    def reactivate(self):
        self.invalidated = False
        self.invalidated_reason = ''
        self.status = DoubtStatus.PENDING
        self.resolved_at = None
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'doubt_id': self.doubt_id,
            'project_id': self.project_id,
            'collation_type': self.collation_type,
            'volume': self.volume,
            'paragraph': self.paragraph,
            'copy_batch': self.copy_batch,
            'original_text': self.original_text,
            'suggested_text': self.suggested_text,
            'confidence': self.confidence,
            'reason': self.reason,
            'rule_id': self.rule_id,
            'status': self.status.value,
            'assignee': self.assignee or '',
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'review_history': [c.to_dict() for c in self.review_history],
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if self.resolved_at else '',
            'invalidated': self.invalidated,
            'invalidated_reason': self.invalidated_reason,
            'data_hash': self.data_hash,
            'extra': str(self.extra)
        }


class PermissionManager:
    def __init__(self):
        self._permissions: Dict[str, Permission] = {}
        self._user_roles: Dict[str, Role] = {}
        self._init_default_permissions()

    def _init_default_permissions(self):
        self.add_permission(Permission(
            name='create_project',
            description='创建项目',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='view_project',
            description='查看项目',
            roles={Role.ADMIN, Role.COLLATOR, Role.REVIEWER, Role.GUEST}
        ))
        self.add_permission(Permission(
            name='edit_project',
            description='编辑项目',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='delete_project',
            description='删除项目',
            roles={Role.ADMIN}
        ))
        self.add_permission(Permission(
            name='view_doubts',
            description='查看疑点',
            roles={Role.ADMIN, Role.COLLATOR, Role.REVIEWER, Role.GUEST}
        ))
        self.add_permission(Permission(
            name='import_data',
            description='导入数据',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='edit_data',
            description='编辑数据',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='detect_doubts',
            description='检测疑点',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='create_doubt',
            description='创建疑点',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='edit_doubt',
            description='编辑疑点',
            roles={Role.ADMIN, Role.COLLATOR}
        ))
        self.add_permission(Permission(
            name='review_doubt',
            description='复核疑点',
            roles={Role.ADMIN, Role.REVIEWER}
        ))
        self.add_permission(Permission(
            name='resolve_doubt',
            description='解决疑点',
            roles={Role.ADMIN, Role.REVIEWER}
        ))
        self.add_permission(Permission(
            name='assign_role',
            description='分配角色',
            roles={Role.ADMIN}
        ))
        self.add_permission(Permission(
            name='manage_rules',
            description='管理规则',
            roles={Role.ADMIN}
        ))
        self.add_permission(Permission(
            name='export_data',
            description='导出数据',
            roles={Role.ADMIN, Role.COLLATOR, Role.REVIEWER}
        ))
        self.add_permission(Permission(
            name='view_audit',
            description='查看审计日志',
            roles={Role.ADMIN}
        ))

    def add_permission(self, permission: Permission):
        self._permissions[permission.name] = permission

    def has_permission(self, username: str, permission_name: str) -> bool:
        role = self._user_roles.get(username, Role.GUEST)
        perm = self._permissions.get(permission_name)
        if not perm:
            return False
        return role in perm.roles

    def set_user_role(self, username: str, role: Role):
        self._user_roles[username] = role

    def get_user_role(self, username: str) -> Role:
        return self._user_roles.get(username, Role.GUEST)

    def get_all_roles(self) -> Dict[str, Role]:
        return dict(self._user_roles)

    def check_permission(self, username: str, permission_name: str) -> None:
        if not self.has_permission(username, permission_name):
            role = self.get_user_role(username)
            perm = self._permissions.get(permission_name)
            perm_desc = perm.description if perm else permission_name
            raise PermissionError(f"用户【{username}】(角色: {role.value}) 没有权限执行: {perm_desc}")


class WorkflowEngine:
    def __init__(self, audit_trail: Optional[AuditTrail] = None):
        self.audit_trail = audit_trail or AuditTrail()
        self.permission_manager = PermissionManager()
        self._doubts: Dict[str, DoubtRecord] = {}
        self._unique_keys: Set[str] = set()
        self._comment_counter = 0
        self._doubt_counter = 0

    def _generate_doubt_id(self, project_id: str) -> str:
        self._doubt_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d')
        return f'{project_id}-DBT-{timestamp}-{self._doubt_counter:06d}'

    def _generate_comment_id(self) -> str:
        self._comment_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f'CMT-{timestamp}-{self._comment_counter:06d}'

    def set_user_role(self, admin_user: str, target_user: str, role: Role):
        self.permission_manager.check_permission(admin_user, 'assign_role')
        self.permission_manager.set_user_role(target_user, role)
        self.audit_trail.log(
            operation_type=OperationType.ROLE_ASSIGN,
            operator=admin_user,
            operator_role=self.permission_manager.get_user_role(admin_user).value,
            description=f"将用户【{target_user}】的角色设置为【{role.value}】",
            old_value={'role': self.permission_manager.get_user_role(target_user).value},
            new_value={'role': role.value}
        )

    def create_doubt(self,
                     creator: str,
                     project_id: str,
                     collation_type: str,
                     volume: int,
                     paragraph: int,
                     copy_batch: str,
                     original_text: str,
                     suggested_text: str,
                     confidence: float,
                     reason: str,
                     rule_id: str,
                     data_hash: str = '',
                     extra: Optional[Dict] = None) -> DoubtRecord:
        self.permission_manager.check_permission(creator, 'create_doubt')

        temp_key = f'{project_id}|{volume}|{paragraph}|{copy_batch}|{collation_type}|{original_text}|{suggested_text}'
        if temp_key in self._unique_keys:
            raise ValueError(f"同一疑点已存在，不允许重复创建: {temp_key}")

        doubt_id = self._generate_doubt_id(project_id)
        extra_data = extra or {}
        extra_data['created_by'] = creator
        doubt = DoubtRecord(
            doubt_id=doubt_id,
            project_id=project_id,
            collation_type=collation_type,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            original_text=original_text,
            suggested_text=suggested_text,
            confidence=confidence,
            reason=reason,
            rule_id=rule_id,
            data_hash=data_hash,
            extra=extra_data
        )

        self._doubts[doubt_id] = doubt
        self._unique_keys.add(doubt.unique_key)

        self.audit_trail.log(
            operation_type=OperationType.DOUBT_CREATE,
            operator=creator,
            operator_role=self.permission_manager.get_user_role(creator).value,
            project_id=project_id,
            target_id=doubt_id,
            target_type='DoubtRecord',
            description=f"创建疑点【{collation_type}】: 第{volume}卷第{paragraph}段 ({copy_batch})",
            new_value=doubt.to_dict()
        )

        return doubt

    def get_doubt(self, doubt_id: str) -> Optional[DoubtRecord]:
        return self._doubts.get(doubt_id)

    def get_all_doubts(self, project_id: Optional[str] = None) -> List[DoubtRecord]:
        doubts = list(self._doubts.values())
        if project_id:
            doubts = [d for d in doubts if d.project_id == project_id]
        return sorted(doubts, key=lambda d: (d.volume, d.paragraph, d.created_at), reverse=True)

    def get_doubts_by_status(self, status: DoubtStatus, project_id: Optional[str] = None) -> List[DoubtRecord]:
        doubts = self.get_all_doubts(project_id)
        return [d for d in doubts if d.status == status]

    def get_doubts_by_assignee(self, assignee: str, project_id: Optional[str] = None) -> List[DoubtRecord]:
        doubts = self.get_all_doubts(project_id)
        return [d for d in doubts if d.assignee == assignee]

    def get_doubts_by_volume(self, volume: int, project_id: Optional[str] = None) -> List[DoubtRecord]:
        doubts = self.get_all_doubts(project_id)
        return [d for d in doubts if d.volume == volume]

    def review_doubt(self,
                     reviewer: str,
                     doubt_id: str,
                     action: ReviewAction,
                     content: str,
                     new_assignee: Optional[str] = None) -> DoubtRecord:
        self.permission_manager.check_permission(reviewer, 'review_doubt')

        doubt = self.get_doubt(doubt_id)
        if not doubt:
            raise ValueError(f"疑点不存在: {doubt_id}")

        if doubt.invalidated:
            raise ValueError(f"疑点已失效，无法复核: {doubt_id}")

        old_status = doubt.status
        new_status = old_status

        if action == ReviewAction.ACCEPT:
            new_status = DoubtStatus.REVIEWED
            doubt.assignee = None
        elif action == ReviewAction.REJECT:
            new_status = DoubtStatus.REJECTED
            doubt.assignee = None
        elif action == ReviewAction.MODIFY:
            new_status = DoubtStatus.IN_PROGRESS
        elif action == ReviewAction.REASSIGN:
            if new_assignee:
                doubt.assignee = new_assignee
            new_status = DoubtStatus.PENDING
        elif action == ReviewAction.COMMENT:
            pass

        if old_status != new_status:
            doubt.status = new_status

        comment = ReviewComment(
            comment_id=self._generate_comment_id(),
            timestamp=datetime.now(),
            reviewer=reviewer,
            reviewer_role=self.permission_manager.get_user_role(reviewer).value,
            action=action,
            content=content,
            old_status=old_status,
            new_status=new_status,
            assignee=new_assignee
        )
        doubt.add_comment(comment)
        doubt.updated_at = datetime.now()

        self.audit_trail.log(
            operation_type=OperationType.DOUBT_REVIEW,
            operator=reviewer,
            operator_role=self.permission_manager.get_user_role(reviewer).value,
            project_id=doubt.project_id,
            target_id=doubt_id,
            target_type='DoubtRecord',
            description=f"复核疑点: {action.value} - {content[:50]}",
            old_value={'status': old_status.value},
            new_value={'status': new_status.value, 'action': action.value}
        )

        return doubt

    def resolve_doubt(self, resolver: str, doubt_id: str, resolution: str) -> DoubtRecord:
        self.permission_manager.check_permission(resolver, 'resolve_doubt')

        doubt = self.get_doubt(doubt_id)
        if not doubt:
            raise ValueError(f"疑点不存在: {doubt_id}")

        if doubt.invalidated:
            raise ValueError(f"疑点已失效，无法解决: {doubt_id}")

        old_status = doubt.status
        doubt.status = DoubtStatus.RESOLVED
        doubt.resolved_at = datetime.now()

        comment = ReviewComment(
            comment_id=self._generate_comment_id(),
            timestamp=datetime.now(),
            reviewer=resolver,
            reviewer_role=self.permission_manager.get_user_role(resolver).value,
            action=ReviewAction.ACCEPT,
            content=f'【问题解决】{resolution}',
            old_status=old_status,
            new_status=DoubtStatus.RESOLVED
        )
        doubt.add_comment(comment)

        self.audit_trail.log(
            operation_type=OperationType.DOUBT_RESOLVE,
            operator=resolver,
            operator_role=self.permission_manager.get_user_role(resolver).value,
            project_id=doubt.project_id,
            target_id=doubt_id,
            target_type='DoubtRecord',
            description=f"解决疑点: {resolution[:50]}",
            old_value={'status': old_status.value},
            new_value={'status': DoubtStatus.RESOLVED.value}
        )

        return doubt

    def invalidate_doubts_by_data_change(self,
                                         operator: str,
                                         project_id: str,
                                         volume: Optional[int] = None,
                                         paragraph: Optional[int] = None,
                                         copy_batch: Optional[str] = None,
                                         reason: str = '关联数据已修改') -> List[str]:
        self.permission_manager.check_permission(operator, 'edit_data')

        invalidated_ids = []
        for doubt in self.get_all_doubts(project_id):
            if not doubt.is_active:
                continue
            if volume is not None and doubt.volume != volume:
                continue
            if paragraph is not None and doubt.paragraph != paragraph:
                continue
            if copy_batch is not None and doubt.copy_batch != copy_batch:
                continue

            self._unique_keys.discard(doubt.unique_key)
            old_status = doubt.invalidate(reason)
            invalidated_ids.append(doubt.doubt_id)

            self.audit_trail.log(
                operation_type=OperationType.DOUBT_INVALIDATE,
                operator=operator,
                operator_role=self.permission_manager.get_user_role(operator).value,
                project_id=project_id,
                target_id=doubt.doubt_id,
                target_type='DoubtRecord',
                description=f"疑点因数据修改失效: {reason}",
                old_value={'status': old_status.value if old_status else doubt.status.value},
                new_value={'status': DoubtStatus.INVALIDATED.value}
            )

        return invalidated_ids

    def reactivate_doubt(self, operator: str, doubt_id: str) -> DoubtRecord:
        self.permission_manager.check_permission(operator, 'edit_doubt')

        doubt = self.get_doubt(doubt_id)
        if not doubt:
            raise ValueError(f"疑点不存在: {doubt_id}")

        if doubt.unique_key in self._unique_keys:
            raise ValueError(f"相同疑点已存在，无法重新激活: {doubt.unique_key}")

        doubt.reactivate()
        self._unique_keys.add(doubt.unique_key)

        self.audit_trail.log(
            operation_type=OperationType.DOUBT_UPDATE,
            operator=operator,
            operator_role=self.permission_manager.get_user_role(operator).value,
            project_id=doubt.project_id,
            target_id=doubt_id,
            target_type='DoubtRecord',
            description="重新激活已失效疑点，进入待复核状态"
        )

        return doubt

    def update_doubt(self,
                     operator: str,
                     doubt_id: str,
                     **kwargs) -> DoubtRecord:
        self.permission_manager.check_permission(operator, 'edit_doubt')

        doubt = self.get_doubt(doubt_id)
        if not doubt:
            raise ValueError(f"疑点不存在: {doubt_id}")

        old_values = {}
        for key, value in kwargs.items():
            if hasattr(doubt, key) and key not in ['doubt_id', 'project_id', 'created_at']:
                old_values[key] = getattr(doubt, key)
                setattr(doubt, key, value)

        doubt.updated_at = datetime.now()

        self.audit_trail.log(
            operation_type=OperationType.DOUBT_UPDATE,
            operator=operator,
            operator_role=self.permission_manager.get_user_role(operator).value,
            project_id=doubt.project_id,
            target_id=doubt_id,
            target_type='DoubtRecord',
            description=f"更新疑点信息: {list(kwargs.keys())}",
            old_value=old_values,
            new_value=kwargs
        )

        return doubt

    def get_statistics(self, project_id: Optional[str] = None) -> Dict[str, int]:
        doubts = self.get_all_doubts(project_id)
        stats = {
            'total': len(doubts),
            'pending': 0,
            'in_progress': 0,
            'reviewed': 0,
            'rejected': 0,
            'resolved': 0,
            'invalidated': 0,
            'by_type': {}
        }

        for doubt in doubts:
            status_key = doubt.status.value
            if status_key in stats:
                stats[status_key] += 1
            elif status_key == '待复核':
                stats['pending'] += 1
            elif status_key == '处理中':
                stats['in_progress'] += 1
            elif status_key == '已复核':
                stats['reviewed'] += 1
            elif status_key == '已驳回':
                stats['rejected'] += 1
            elif status_key == '已解决':
                stats['resolved'] += 1
            elif status_key == '已失效':
                stats['invalidated'] += 1

            ctype = doubt.collation_type
            stats['by_type'][ctype] = stats['by_type'].get(ctype, 0) + 1

        return stats

    def check_duplicate(self,
                        project_id: str,
                        volume: int,
                        paragraph: int,
                        copy_batch: str,
                        collation_type: str,
                        original_text: str,
                        suggested_text: str) -> bool:
        key = f'{project_id}|{volume}|{paragraph}|{copy_batch}|{collation_type}|{original_text}|{suggested_text}'
        return key in self._unique_keys

    def clear(self):
        self._doubts.clear()
        self._unique_keys.clear()
        self._comment_counter = 0
        self._doubt_counter = 0
