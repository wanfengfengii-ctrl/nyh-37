"""
审计跟踪模块：记录所有操作的时间线，支持追溯和审计
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from enum import Enum
from datetime import datetime
import json


class OperationType(str, Enum):
    PROJECT_CREATE = '项目创建'
    PROJECT_UPDATE = '项目更新'
    PROJECT_DELETE = '项目删除'
    DATA_IMPORT = '数据导入'
    DATA_UPDATE = '数据修改'
    DATA_DELETE = '数据删除'
    DOUBT_DETECT = '疑点检测'
    DOUBT_CREATE = '疑点创建'
    DOUBT_UPDATE = '疑点更新'
    DOUBT_REVIEW = '疑点复核'
    DOUBT_INVALIDATE = '疑点失效'
    DOUBT_RESOLVE = '疑点解决'
    ROLE_ASSIGN = '角色分配'
    RULE_UPDATE = '规则更新'
    EXPORT = '数据导出'
    LOGIN = '登录'
    LOGOUT = '登出'
    OTHER = '其他操作'


@dataclass
class AuditRecord:
    record_id: str
    timestamp: datetime
    operation_type: OperationType
    operator: str
    operator_role: str
    project_id: Optional[str] = None
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    description: str = ''
    old_value: Optional[Dict] = None
    new_value: Optional[Dict] = None
    extra: Dict = field(default_factory=dict)
    ip_address: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'record_id': self.record_id,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'operation_type': self.operation_type.value,
            'operator': self.operator,
            'operator_role': self.operator_role,
            'project_id': self.project_id,
            'target_id': self.target_id,
            'target_type': self.target_type,
            'description': self.description,
            'old_value': json.dumps(self.old_value, ensure_ascii=False) if self.old_value else '',
            'new_value': json.dumps(self.new_value, ensure_ascii=False) if self.new_value else '',
            'extra': json.dumps(self.extra, ensure_ascii=False),
            'ip_address': self.ip_address
        }


class AuditTrail:
    def __init__(self):
        self._records: List[AuditRecord] = []
        self._counter = 0

    def _generate_record_id(self) -> str:
        self._counter += 1
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        return f'AUD-{timestamp}-{self._counter:06d}'

    def log(self,
            operation_type: OperationType,
            operator: str,
            operator_role: str,
            project_id: Optional[str] = None,
            target_id: Optional[str] = None,
            target_type: Optional[str] = None,
            description: str = '',
            old_value: Optional[Dict] = None,
            new_value: Optional[Dict] = None,
            extra: Optional[Dict] = None,
            ip_address: str = '') -> AuditRecord:
        record = AuditRecord(
            record_id=self._generate_record_id(),
            timestamp=datetime.now(),
            operation_type=operation_type,
            operator=operator,
            operator_role=operator_role,
            project_id=project_id,
            target_id=target_id,
            target_type=target_type,
            description=description,
            old_value=old_value,
            new_value=new_value,
            extra=extra or {},
            ip_address=ip_address
        )
        self._records.append(record)
        return record

    def get_all_records(self) -> List[AuditRecord]:
        return sorted(self._records, key=lambda r: r.timestamp, reverse=True)

    def get_records_by_project(self, project_id: str) -> List[AuditRecord]:
        return [r for r in self.get_all_records() if r.project_id == project_id]

    def get_records_by_operator(self, operator: str) -> List[AuditRecord]:
        return [r for r in self.get_all_records() if r.operator == operator]

    def get_records_by_type(self, operation_type: OperationType) -> List[AuditRecord]:
        return [r for r in self.get_all_records() if r.operation_type == operation_type]

    def get_records_by_target(self, target_id: str, target_type: Optional[str] = None) -> List[AuditRecord]:
        records = [r for r in self.get_all_records() if r.target_id == target_id]
        if target_type:
            records = [r for r in records if r.target_type == target_type]
        return records

    def get_records_by_time_range(self, start_time: datetime, end_time: datetime) -> List[AuditRecord]:
        return [r for r in self.get_all_records() if start_time <= r.timestamp <= end_time]

    def query_records(self,
                      project_id: Optional[str] = None,
                      operator: Optional[str] = None,
                      operation_type: Optional[OperationType] = None,
                      target_id: Optional[str] = None,
                      start_time: Optional[datetime] = None,
                      end_time: Optional[datetime] = None) -> List[AuditRecord]:
        records = self.get_all_records()
        if project_id:
            records = [r for r in records if r.project_id == project_id]
        if operator:
            records = [r for r in records if r.operator == operator]
        if operation_type:
            records = [r for r in records if r.operation_type == operation_type]
        if target_id:
            records = [r for r in records if r.target_id == target_id]
        if start_time:
            records = [r for r in records if r.timestamp >= start_time]
        if end_time:
            records = [r for r in records if r.timestamp <= end_time]
        return records

    def get_timeline(self, project_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        records = self.get_records_by_project(project_id) if project_id else self.get_all_records()
        records = records[:limit]
        return [
            {
                'time': r.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
                'operator': r.operator,
                'role': r.operator_role,
                'action': r.operation_type.value,
                'description': r.description,
                'record_id': r.record_id
            }
            for r in records
        ]

    def to_list(self) -> List[Dict]:
        return [r.to_dict() for r in self._records]

    def clear(self):
        self._records.clear()
        self._counter = 0

    def __len__(self) -> int:
        return len(self._records)
