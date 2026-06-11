"""
古籍校勘知识库与智能判例推荐模块：
- 历史校勘判例沉淀（异文、引文、误引、补充出处、复核结论）
- 相似案例检索（多维度相似度计算）
- 处理建议推荐（处理结论、采用依据、参考出处）
- 人工采纳/驳回/修订
- 多维度筛选
- 去重与自动失效机制
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from enum import Enum
from datetime import datetime
import hashlib
from collections import defaultdict


class CaseSourceType(str, Enum):
    DOUBT = '异文疑点'
    CITATION = '引文溯源'
    MISQUOTE = '误引修正'
    SUPPLEMENT = '出处补充'
    MANUAL = '人工录入'


class CaseStatus(str, Enum):
    ACTIVE = '有效'
    INVALIDATED = '已失效'
    ARCHIVED = '已归档'


class RecommendationStatus(str, Enum):
    PENDING = '待处理'
    ACCEPTED = '已采纳'
    REJECTED = '已驳回'
    MODIFIED = '已修订'
    INVALIDATED = '已失效'


class CaseCategory(str, Enum):
    WRONG_CHAR = '错字'
    MISSING_TEXT = '脱文'
    EXTRA_TEXT = '衍文'
    REVERSED_TEXT = '倒文'
    NUMBER_BREAK = '编号断裂'
    QUOTATION = '引文'
    ALLUSION = '典故'
    REPETITION = '重复语段'
    MISQUOTE = '疑似误引'
    OTHER = '其他'


@dataclass
class CaseResolution:
    conclusion: str
    basis: str
    reference_sources: List[Dict[str, Any]] = field(default_factory=list)
    final_text: str = ''
    notes: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'conclusion': self.conclusion,
            'basis': self.basis,
            'reference_sources': self.reference_sources,
            'final_text': self.final_text,
            'notes': self.notes
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CaseResolution':
        return cls(
            conclusion=d.get('conclusion', ''),
            basis=d.get('basis', ''),
            reference_sources=d.get('reference_sources', []),
            final_text=d.get('final_text', ''),
            notes=d.get('notes', '')
        )


@dataclass
class CollationCase:
    case_id: str
    project_id: str
    book_name: str
    source_type: CaseSourceType
    category: CaseCategory
    volume: Optional[int] = None
    paragraph: Optional[int] = None
    copy_batch: Optional[str] = None
    original_text: str = ''
    variant_text: str = ''
    quoted_text: str = ''
    confidence: float = 0.0
    rule_id: str = ''
    description: str = ''
    resolution: Optional[CaseResolution] = None
    status: CaseStatus = CaseStatus.ACTIVE
    source_record_id: str = ''
    created_by: str = ''
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    resolved_by: str = ''
    resolved_at: Optional[datetime] = None
    invalidated_reason: str = ''
    data_hash: str = ''
    tags: List[str] = field(default_factory=list)
    usage_count: int = 0
    accept_count: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        text_parts = [self.original_text, self.variant_text, self.quoted_text]
        text_key = '|'.join(p for p in text_parts if p)
        return (f'{self.project_id}|{self.book_name}|{self.source_type.value}|'
                f'{self.category.value}|{self.volume or ""}|{self.paragraph or ""}|'
                f'{self.copy_batch or ""}|{text_key}')

    @property
    def fingerprint(self) -> str:
        return _hash_text(
            self.book_name, self.source_type.value, self.category.value,
            self.original_text, self.variant_text, self.quoted_text
        )

    @property
    def is_active(self) -> bool:
        return self.status == CaseStatus.ACTIVE

    def to_dict(self) -> Dict[str, Any]:
        return {
            'case_id': self.case_id,
            'project_id': self.project_id,
            'book_name': self.book_name,
            'source_type': self.source_type.value,
            'category': self.category.value,
            'volume': self.volume or '',
            'paragraph': self.paragraph or '',
            'copy_batch': self.copy_batch or '',
            'original_text': self.original_text,
            'variant_text': self.variant_text,
            'quoted_text': self.quoted_text,
            'confidence': self.confidence,
            'rule_id': self.rule_id,
            'description': self.description,
            'resolution': self.resolution.to_dict() if self.resolution else None,
            'status': self.status.value,
            'source_record_id': self.source_record_id,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'resolved_by': self.resolved_by,
            'resolved_at': self.resolved_at.strftime('%Y-%m-%d %H:%M:%S') if self.resolved_at else '',
            'invalidated_reason': self.invalidated_reason,
            'data_hash': self.data_hash,
            'tags': ','.join(self.tags),
            'usage_count': self.usage_count,
            'accept_count': self.accept_count,
            'extra': str(self.extra)
        }

    def invalidate(self, reason: str = '关联数据已修改'):
        self.status = CaseStatus.INVALIDATED
        self.invalidated_reason = reason
        self.updated_at = datetime.now()

    def reactivate(self):
        self.status = CaseStatus.ACTIVE
        self.invalidated_reason = ''
        self.updated_at = datetime.now()

    def record_usage(self, accepted: bool):
        self.usage_count += 1
        if accepted:
            self.accept_count += 1
        self.updated_at = datetime.now()


@dataclass
class SimilarityScore:
    overall: float = 0.0
    text_similarity: float = 0.0
    category_match: float = 0.0
    book_match: float = 0.0
    volume_proximity: float = 0.0
    source_type_match: float = 0.0
    rule_match: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            'overall': self.overall,
            'text_similarity': self.text_similarity,
            'category_match': self.category_match,
            'book_match': self.book_match,
            'volume_proximity': self.volume_proximity,
            'source_type_match': self.source_type_match,
            'rule_match': self.rule_match
        }


@dataclass
class CaseRecommendation:
    recommendation_id: str
    target_record_id: str
    target_record_type: str
    case_id: str
    project_id: str
    similarity: SimilarityScore
    reason: str
    status: RecommendationStatus = RecommendationStatus.PENDING
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    decided_by: str = ''
    decided_at: Optional[datetime] = None
    modified_content: Optional[Dict[str, Any]] = None
    operation_history: List[Dict[str, Any]] = field(default_factory=list)
    auto_invalidated: bool = False
    invalidated_reason: str = ''

    @property
    def unique_key(self) -> str:
        return f'{self.target_record_id}|{self.target_record_type}|{self.case_id}'

    def to_dict(self) -> Dict[str, Any]:
        return {
            'recommendation_id': self.recommendation_id,
            'target_record_id': self.target_record_id,
            'target_record_type': self.target_record_type,
            'case_id': self.case_id,
            'project_id': self.project_id,
            'similarity': self.similarity.to_dict(),
            'reason': self.reason,
            'status': self.status.value,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'decided_by': self.decided_by,
            'decided_at': self.decided_at.strftime('%Y-%m-%d %H:%M:%S') if self.decided_at else '',
            'modified_content': self.modified_content,
            'operation_history': self.operation_history,
            'auto_invalidated': self.auto_invalidated,
            'invalidated_reason': self.invalidated_reason
        }

    def add_operation(self, operator: str, action: str, content: str,
                      operator_role: str = '', extra: Optional[Dict] = None):
        self.operation_history.append({
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'operator': operator,
            'operator_role': operator_role,
            'action': action,
            'content': content,
            'extra': extra or {}
        })
        self.updated_at = datetime.now()

    def accept(self, operator: str, operator_role: str = '', note: str = ''):
        self.status = RecommendationStatus.ACCEPTED
        self.decided_by = operator
        self.decided_at = datetime.now()
        self.add_operation(operator, 'ACCEPT', note or '采纳此推荐', operator_role)

    def reject(self, operator: str, operator_role: str = '', reason: str = ''):
        self.status = RecommendationStatus.REJECTED
        self.decided_by = operator
        self.decided_at = datetime.now()
        self.add_operation(operator, 'REJECT', reason or '驳回此推荐', operator_role)

    def modify_and_accept(self, operator: str, modified: Dict[str, Any],
                          operator_role: str = '', note: str = ''):
        self.status = RecommendationStatus.MODIFIED
        self.decided_by = operator
        self.decided_at = datetime.now()
        self.modified_content = modified
        self.add_operation(operator, 'MODIFY', note or '修订后采纳', operator_role,
                           extra={'modified': modified})

    def invalidate(self, reason: str = '关联数据或判例已修改'):
        self.status = RecommendationStatus.INVALIDATED
        self.auto_invalidated = True
        self.invalidated_reason = reason
        self.updated_at = datetime.now()


@dataclass
class CaseFilter:
    book_name: Optional[str] = None
    volume: Optional[int] = None
    copy_batch: Optional[str] = None
    category: Optional[CaseCategory] = None
    source_type: Optional[CaseSourceType] = None
    status: Optional[CaseStatus] = None
    tags: Optional[List[str]] = None
    project_id: Optional[str] = None
    keyword: Optional[str] = None
    min_confidence: Optional[float] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


@dataclass
class RecommendationFilter:
    project_id: Optional[str] = None
    target_record_id: Optional[str] = None
    case_id: Optional[str] = None
    status: Optional[RecommendationStatus] = None
    min_similarity: Optional[float] = None
    operator: Optional[str] = None


def _hash_text(*args) -> str:
    content = '|'.join(str(a) for a in args)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


def _compute_text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    a = a.strip()
    b = b.strip()
    if a == b:
        return 1.0
    len_a, len_b = len(a), len(b)
    if len_a == 0 or len_b == 0:
        return 0.0
    if len_a > len_b:
        a, b = b, a
        len_a, len_b = len_b, len_a
    max_common = 0
    for i in range(len_a):
        for j in range(i + 1, len_a + 1):
            sub = a[i:j]
            if len(sub) > max_common and sub in b:
                max_common = len(sub)
    if max_common == 0:
        return 0.0
    return (2.0 * max_common) / (len_a + len_b)


def _generate_ngrams(text: str, n: int = 3) -> Set[str]:
    text = text.strip()
    if len(text) < n:
        return {text} if text else set()
    return {text[i:i + n] for i in range(len(text) - n + 1)}


class CaseLibrary:
    def __init__(self):
        self._cases: Dict[str, CollationCase] = {}
        self._case_unique_keys: Set[str] = set()
        self._recommendations: Dict[str, CaseRecommendation] = {}
        self._recommendation_unique_keys: Set[str] = set()
        self._case_counter = 0
        self._recommendation_counter = 0
        self._ngram_index: Dict[str, Set[str]] = defaultdict(set)
        self._fingerprint_index: Dict[str, Set[str]] = defaultdict(set)

    def _generate_case_id(self, project_id: str) -> str:
        self._case_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d')
        return f'{project_id}-CASE-{timestamp}-{self._case_counter:06d}'

    def _generate_recommendation_id(self, project_id: str) -> str:
        self._recommendation_counter += 1
        timestamp = datetime.now().strftime('%Y%m%d')
        return f'{project_id}-REC-{timestamp}-{self._recommendation_counter:06d}'

    def _index_case(self, case: CollationCase):
        texts = [case.original_text, case.variant_text, case.quoted_text, case.description]
        all_text = ' '.join(t for t in texts if t)
        for gram in _generate_ngrams(all_text, 3):
            self._ngram_index[gram].add(case.case_id)
        fp = case.fingerprint
        self._fingerprint_index[fp].add(case.case_id)

    def _unindex_case(self, case: CollationCase):
        texts = [case.original_text, case.variant_text, case.quoted_text, case.description]
        all_text = ' '.join(t for t in texts if t)
        for gram in _generate_ngrams(all_text, 3):
            if case.case_id in self._ngram_index.get(gram, set()):
                self._ngram_index[gram].discard(case.case_id)
        fp = case.fingerprint
        if case.case_id in self._fingerprint_index.get(fp, set()):
            self._fingerprint_index[fp].discard(case.case_id)

    def create_case(self,
                    project_id: str,
                    book_name: str,
                    source_type: CaseSourceType,
                    category: CaseCategory,
                    created_by: str,
                    original_text: str = '',
                    variant_text: str = '',
                    quoted_text: str = '',
                    volume: Optional[int] = None,
                    paragraph: Optional[int] = None,
                    copy_batch: Optional[str] = None,
                    confidence: float = 0.0,
                    rule_id: str = '',
                    description: str = '',
                    resolution: Optional[CaseResolution] = None,
                    source_record_id: str = '',
                    data_hash: str = '',
                    tags: Optional[List[str]] = None,
                    extra: Optional[Dict[str, Any]] = None) -> CollationCase:
        temp_case = CollationCase(
            case_id='',
            project_id=project_id,
            book_name=book_name,
            source_type=source_type,
            category=category,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            original_text=original_text,
            variant_text=variant_text,
            quoted_text=quoted_text,
            confidence=confidence,
            rule_id=rule_id,
            description=description,
            resolution=resolution,
            source_record_id=source_record_id,
            data_hash=data_hash,
            tags=tags or [],
            extra=extra or {}
        )

        if temp_case.unique_key in self._case_unique_keys:
            existing = [c for c in self._cases.values() if c.unique_key == temp_case.unique_key]
            if existing:
                return existing[0]

        case_id = self._generate_case_id(project_id)
        case = CollationCase(
            case_id=case_id,
            project_id=project_id,
            book_name=book_name,
            source_type=source_type,
            category=category,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            original_text=original_text,
            variant_text=variant_text,
            quoted_text=quoted_text,
            confidence=confidence,
            rule_id=rule_id,
            description=description,
            resolution=resolution,
            created_by=created_by,
            source_record_id=source_record_id,
            data_hash=data_hash,
            tags=tags or [],
            extra=extra or {}
        )

        self._cases[case_id] = case
        self._case_unique_keys.add(case.unique_key)
        self._index_case(case)

        return case

    def create_case_from_doubt(self,
                               doubt_record: Any,
                               book_name: str,
                               created_by: str,
                               resolution: Optional[CaseResolution] = None,
                               extra_notes: str = '') -> CollationCase:
        from workflow_engine import DoubtStatus
        cat_map = {
            '错字': CaseCategory.WRONG_CHAR,
            '脱文': CaseCategory.MISSING_TEXT,
            '衍文': CaseCategory.EXTRA_TEXT,
            '倒文': CaseCategory.REVERSED_TEXT,
            '编号断裂': CaseCategory.NUMBER_BREAK
        }
        category = cat_map.get(doubt_record.collation_type, CaseCategory.OTHER)

        if resolution is None and doubt_record.status == DoubtStatus.RESOLVED:
            conclusion_parts = []
            for comment in reversed(doubt_record.review_history):
                if comment.content:
                    conclusion_parts.append(comment.content)
                    break
            resolution = CaseResolution(
                conclusion=doubt_record.status.value,
                basis='; '.join(conclusion_parts) if conclusion_parts else doubt_record.reason,
                final_text=doubt_record.suggested_text,
                notes=extra_notes
            )

        return self.create_case(
            project_id=doubt_record.project_id,
            book_name=book_name,
            source_type=CaseSourceType.DOUBT,
            category=category,
            created_by=created_by,
            original_text=doubt_record.original_text,
            variant_text=doubt_record.suggested_text,
            volume=doubt_record.volume,
            paragraph=doubt_record.paragraph,
            copy_batch=doubt_record.copy_batch,
            confidence=doubt_record.confidence,
            rule_id=doubt_record.rule_id,
            description=doubt_record.reason,
            resolution=resolution,
            source_record_id=doubt_record.doubt_id,
            data_hash=doubt_record.data_hash,
            tags=[doubt_record.collation_type]
        )

    def create_case_from_citation(self,
                                  citation_record: Any,
                                  book_name: str,
                                  created_by: str,
                                  resolution: Optional[CaseResolution] = None,
                                  extra_notes: str = '') -> CollationCase:
        from citation_analyzer import CitationStatus, CitationType
        cat_map = {
            CitationType.QUOTATION: CaseCategory.QUOTATION,
            CitationType.ALLUSION: CaseCategory.ALLUSION,
            CitationType.REPETITION: CaseCategory.REPETITION,
            CitationType.MISQUOTE: CaseCategory.MISQUOTE
        }
        category = cat_map.get(citation_record.citation_type, CaseCategory.OTHER)
        source_type = (CaseSourceType.MISQUOTE
                       if citation_record.citation_type == CitationType.MISQUOTE
                       else CaseSourceType.CITATION)

        if resolution is None and citation_record.status in (CitationStatus.CONFIRMED, CitationStatus.REJECTED):
            ref_sources = []
            if citation_record.confirmed_source:
                ref_sources.append(citation_record.confirmed_source.to_dict())
            for m in citation_record.matches:
                ref_sources.extend([s.to_dict() for s in m.sources])

            resolution = CaseResolution(
                conclusion=citation_record.status.value,
                basis=citation_record.match_basis,
                reference_sources=ref_sources,
                notes=extra_notes
            )

        return self.create_case(
            project_id=citation_record.project_id,
            book_name=book_name,
            source_type=source_type,
            category=category,
            created_by=created_by,
            original_text=citation_record.original_text,
            quoted_text=citation_record.quoted_text,
            volume=citation_record.volume,
            paragraph=citation_record.paragraph,
            copy_batch=citation_record.copy_batch,
            confidence=citation_record.confidence,
            description=citation_record.match_basis,
            resolution=resolution,
            source_record_id=citation_record.citation_id,
            data_hash=citation_record.data_hash,
            tags=[citation_record.citation_type.value]
        )

    def get_case(self, case_id: str) -> Optional[CollationCase]:
        return self._cases.get(case_id)

    def get_all_cases(self, project_id: Optional[str] = None) -> List[CollationCase]:
        cases = list(self._cases.values())
        if project_id:
            cases = [c for c in cases if c.project_id == project_id]
        return sorted(cases, key=lambda c: c.created_at, reverse=True)

    def filter_cases(self, f: CaseFilter) -> List[CollationCase]:
        cases = self.get_all_cases(f.project_id)
        result = []
        for c in cases:
            if f.book_name and c.book_name != f.book_name:
                continue
            if f.volume is not None and c.volume != f.volume:
                continue
            if f.copy_batch and c.copy_batch != f.copy_batch:
                continue
            if f.category and c.category != f.category:
                continue
            if f.source_type and c.source_type != f.source_type:
                continue
            if f.status and c.status != f.status:
                continue
            if f.min_confidence is not None and c.confidence < f.min_confidence:
                continue
            if f.tags:
                if not all(t in c.tags for t in f.tags):
                    continue
            if f.keyword:
                kw = f.keyword.lower()
                searchable = ' '.join([
                    c.original_text, c.variant_text, c.quoted_text,
                    c.description, c.book_name
                ]).lower()
                if kw not in searchable and (c.resolution and kw not in c.resolution.conclusion.lower()
                                             and kw not in c.resolution.basis.lower()):
                    continue
            if f.date_from and c.created_at < f.date_from:
                continue
            if f.date_to and c.created_at > f.date_to:
                continue
            result.append(c)
        return result

    def _compute_similarity(self,
                            target: Dict[str, Any],
                            case: CollationCase) -> SimilarityScore:
        score = SimilarityScore()

        target_texts = []
        for key in ['original_text', 'variant_text', 'quoted_text', 'description']:
            if target.get(key):
                target_texts.append(str(target[key]))
        target_all = ' '.join(target_texts)

        case_texts = [case.original_text, case.variant_text, case.quoted_text, case.description]
        case_all = ' '.join(t for t in case_texts if t)

        score.text_similarity = _compute_text_similarity(target_all, case_all)

        target_category = target.get('category')
        if target_category:
            if isinstance(target_category, CaseCategory):
                score.category_match = 1.0 if target_category == case.category else 0.0
            else:
                score.category_match = 1.0 if str(target_category) == case.category.value else 0.0

        target_book = target.get('book_name', '')
        score.book_match = 1.0 if target_book and target_book == case.book_name else 0.0

        target_vol = target.get('volume')
        if target_vol is not None and case.volume is not None:
            diff = abs(int(target_vol) - int(case.volume))
            score.volume_proximity = max(0.0, 1.0 - diff / 10.0)
        else:
            score.volume_proximity = 0.0

        target_source = target.get('source_type')
        if target_source:
            if isinstance(target_source, CaseSourceType):
                score.source_type_match = 1.0 if target_source == case.source_type else 0.2
            else:
                score.source_type_match = 1.0 if str(target_source) == case.source_type.value else 0.2
        else:
            score.source_type_match = 0.3

        target_rule = target.get('rule_id', '')
        score.rule_match = 1.0 if target_rule and case.rule_id and target_rule == case.rule_id else 0.0

        weights = {
            'text_similarity': 0.40,
            'category_match': 0.20,
            'book_match': 0.15,
            'volume_proximity': 0.10,
            'source_type_match': 0.10,
            'rule_match': 0.05
        }
        score.overall = (
            score.text_similarity * weights['text_similarity']
            + score.category_match * weights['category_match']
            + score.book_match * weights['book_match']
            + score.volume_proximity * weights['volume_proximity']
            + score.source_type_match * weights['source_type_match']
            + score.rule_match * weights['rule_match']
        )

        return score

    def find_similar_cases(self,
                           target: Dict[str, Any],
                           project_id: Optional[str] = None,
                           top_k: int = 10,
                           threshold: float = 0.2) -> List[Tuple[CollationCase, SimilarityScore]]:
        candidate_ids: Set[str] = set()

        target_texts = []
        for key in ['original_text', 'variant_text', 'quoted_text', 'description']:
            if target.get(key):
                target_texts.append(str(target[key]))
        target_all = ' '.join(target_texts)
        for gram in _generate_ngrams(target_all, 3):
            candidate_ids.update(self._ngram_index.get(gram, set()))

        if not candidate_ids:
            fp = _hash_text(
                target.get('book_name', ''),
                target.get('source_type', ''),
                target.get('category', ''),
                target.get('original_text', ''),
                target.get('variant_text', ''),
                target.get('quoted_text', '')
            )
            candidate_ids.update(self._fingerprint_index.get(fp, set()))

        if not candidate_ids:
            candidates = self.get_all_cases(project_id)
        else:
            candidates = [self._cases[cid] for cid in candidate_ids if cid in self._cases]
            if project_id:
                candidates = [c for c in candidates if c.project_id == project_id]

        candidates = [c for c in candidates if c.is_active]

        scored = []
        for case in candidates:
            sim = self._compute_similarity(target, case)
            if sim.overall >= threshold:
                scored.append((case, sim))

        scored.sort(key=lambda x: x[1].overall, reverse=True)
        return scored[:top_k]

    def generate_recommendations(self,
                                 target_record_id: str,
                                 target_record_type: str,
                                 target: Dict[str, Any],
                                 project_id: str,
                                 top_k: int = 5,
                                 threshold: float = 0.25) -> List[CaseRecommendation]:
        similar = self.find_similar_cases(target, project_id, top_k=top_k, threshold=threshold)

        recommendations = []
        for case, sim in similar:
            uniq_key = f'{target_record_id}|{target_record_type}|{case.case_id}'
            if uniq_key in self._recommendation_unique_keys:
                existing = [r for r in self._recommendations.values()
                            if r.unique_key == uniq_key and r.status != RecommendationStatus.INVALIDATED]
                if existing:
                    continue

            reason_parts = []
            if sim.text_similarity >= 0.5:
                reason_parts.append(f'文本相似度{sim.text_similarity:.0%}')
            if sim.category_match >= 1.0:
                reason_parts.append('校勘类型相同')
            if sim.book_match >= 1.0:
                reason_parts.append('同书')
            if sim.volume_proximity >= 0.8:
                reason_parts.append('卷次接近')
            if not reason_parts:
                reason_parts.append(f'综合相似度{sim.overall:.0%}')

            rec_id = self._generate_recommendation_id(project_id)
            rec = CaseRecommendation(
                recommendation_id=rec_id,
                target_record_id=target_record_id,
                target_record_type=target_record_type,
                case_id=case.case_id,
                project_id=project_id,
                similarity=sim,
                reason='；'.join(reason_parts)
            )
            self._recommendations[rec_id] = rec
            self._recommendation_unique_keys.add(rec.unique_key)
            recommendations.append(rec)

        return recommendations

    def generate_recommendations_for_doubt(self,
                                           doubt_record: Any,
                                           book_name: str,
                                           top_k: int = 5) -> List[CaseRecommendation]:
        from workflow_engine import DoubtStatus
        target = {
            'original_text': doubt_record.original_text,
            'variant_text': doubt_record.suggested_text,
            'volume': doubt_record.volume,
            'paragraph': doubt_record.paragraph,
            'copy_batch': doubt_record.copy_batch,
            'category': doubt_record.collation_type,
            'book_name': book_name,
            'source_type': CaseSourceType.DOUBT.value,
            'rule_id': doubt_record.rule_id,
            'description': doubt_record.reason
        }
        return self.generate_recommendations(
            target_record_id=doubt_record.doubt_id,
            target_record_type='DoubtRecord',
            target=target,
            project_id=doubt_record.project_id,
            top_k=top_k
        )

    def generate_recommendations_for_citation(self,
                                              citation_record: Any,
                                              book_name: str,
                                              top_k: int = 5) -> List[CaseRecommendation]:
        target = {
            'original_text': citation_record.original_text,
            'quoted_text': citation_record.quoted_text,
            'volume': citation_record.volume,
            'paragraph': citation_record.paragraph,
            'copy_batch': citation_record.copy_batch,
            'category': citation_record.citation_type.value,
            'book_name': book_name,
            'source_type': (CaseSourceType.MISQUOTE.value
                            if citation_record.citation_type.value == '疑似误引'
                            else CaseSourceType.CITATION.value),
            'description': citation_record.match_basis
        }
        return self.generate_recommendations(
            target_record_id=citation_record.citation_id,
            target_record_type='CitationRecord',
            target=target,
            project_id=citation_record.project_id,
            top_k=top_k
        )

    def get_recommendation(self, rec_id: str) -> Optional[CaseRecommendation]:
        return self._recommendations.get(rec_id)

    def get_recommendations_for_target(self,
                                       target_record_id: str,
                                       target_record_type: Optional[str] = None,
                                       status: Optional[RecommendationStatus] = None) -> List[CaseRecommendation]:
        recs = []
        for r in self._recommendations.values():
            if r.target_record_id != target_record_id:
                continue
            if target_record_type and r.target_record_type != target_record_type:
                continue
            if status and r.status != status:
                continue
            recs.append(r)
        recs.sort(key=lambda r: r.similarity.overall, reverse=True)
        return recs

    def get_all_recommendations(self, project_id: Optional[str] = None) -> List[CaseRecommendation]:
        recs = list(self._recommendations.values())
        if project_id:
            recs = [r for r in recs if r.project_id == project_id]
        return sorted(recs, key=lambda r: r.created_at, reverse=True)

    def filter_recommendations(self, f: RecommendationFilter) -> List[CaseRecommendation]:
        recs = self.get_all_recommendations(f.project_id)
        result = []
        for r in recs:
            if f.target_record_id and r.target_record_id != f.target_record_id:
                continue
            if f.case_id and r.case_id != f.case_id:
                continue
            if f.status and r.status != f.status:
                continue
            if f.min_similarity is not None and r.similarity.overall < f.min_similarity:
                continue
            if f.operator:
                if r.decided_by != f.operator:
                    has_op = any(h.get('operator') == f.operator for h in r.operation_history)
                    if not has_op:
                        continue
            result.append(r)
        return result

    def accept_recommendation(self, rec_id: str, operator: str,
                              operator_role: str = '', note: str = '') -> Optional[CaseRecommendation]:
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None
        case = self.get_case(rec.case_id)
        if case:
            case.record_usage(accepted=True)
        rec.accept(operator, operator_role, note)
        return rec

    def reject_recommendation(self, rec_id: str, operator: str,
                              operator_role: str = '', reason: str = '') -> Optional[CaseRecommendation]:
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None
        case = self.get_case(rec.case_id)
        if case:
            case.record_usage(accepted=False)
        rec.reject(operator, operator_role, reason)
        return rec

    def modify_recommendation(self, rec_id: str, operator: str, modified: Dict[str, Any],
                              operator_role: str = '', note: str = '') -> Optional[CaseRecommendation]:
        rec = self.get_recommendation(rec_id)
        if not rec:
            return None
        case = self.get_case(rec.case_id)
        if case:
            case.record_usage(accepted=True)
        rec.modify_and_accept(operator, modified, operator_role, note)
        return rec

    def invalidate_recommendations_for_target(self,
                                              target_record_id: str,
                                              reason: str = '原始记录已修改') -> List[str]:
        invalidated = []
        for rec in self._recommendations.values():
            if rec.target_record_id == target_record_id and rec.status in (
                    RecommendationStatus.PENDING, RecommendationStatus.ACCEPTED,
                    RecommendationStatus.MODIFIED):
                rec.invalidate(reason)
                invalidated.append(rec.recommendation_id)
        return invalidated

    def invalidate_recommendations_for_case(self,
                                            case_id: str,
                                            reason: str = '判例已修改或失效') -> List[str]:
        invalidated = []
        for rec in self._recommendations.values():
            if rec.case_id == case_id and rec.status in (
                    RecommendationStatus.PENDING, RecommendationStatus.ACCEPTED,
                    RecommendationStatus.MODIFIED):
                rec.invalidate(reason)
                invalidated.append(rec.recommendation_id)
        return invalidated

    def update_case(self, case_id: str, operator: str, **kwargs) -> Optional[CollationCase]:
        case = self.get_case(case_id)
        if not case:
            return None
        self._unindex_case(case)
        for key, value in kwargs.items():
            if hasattr(case, key) and key not in ['case_id', 'project_id', 'created_at']:
                setattr(case, key, value)
        case.updated_at = datetime.now()
        self._index_case(case)
        self.invalidate_recommendations_for_case(case_id, '判例内容已修改')
        return case

    def invalidate_case(self, case_id: str, operator: str,
                        reason: str = '关联数据已修改') -> Optional[CollationCase]:
        case = self.get_case(case_id)
        if not case:
            return None
        case.invalidate(reason)
        self.invalidate_recommendations_for_case(case_id, reason)
        return case

    def reactivate_case(self, case_id: str, operator: str) -> Optional[CollationCase]:
        case = self.get_case(case_id)
        if not case:
            return None
        if case.unique_key in self._case_unique_keys and case.status == CaseStatus.ACTIVE:
            return case
        case.reactivate()
        if case.unique_key not in self._case_unique_keys:
            self._case_unique_keys.add(case.unique_key)
        return case

    def get_statistics(self, project_id: Optional[str] = None) -> Dict[str, Any]:
        cases = self.get_all_cases(project_id)
        recs = self.get_all_recommendations(project_id)

        stats = {
            'total_cases': len(cases),
            'active_cases': 0,
            'invalidated_cases': 0,
            'archived_cases': 0,
            'by_source_type': defaultdict(int),
            'by_category': defaultdict(int),
            'total_recommendations': len(recs),
            'pending_recommendations': 0,
            'accepted_recommendations': 0,
            'rejected_recommendations': 0,
            'modified_recommendations': 0,
            'invalidated_recommendations': 0,
            'accept_rate': 0.0
        }

        for c in cases:
            if c.status == CaseStatus.ACTIVE:
                stats['active_cases'] += 1
            elif c.status == CaseStatus.INVALIDATED:
                stats['invalidated_cases'] += 1
            elif c.status == CaseStatus.ARCHIVED:
                stats['archived_cases'] += 1
            stats['by_source_type'][c.source_type.value] += 1
            stats['by_category'][c.category.value] += 1

        decided = 0
        accepted = 0
        for r in recs:
            if r.status == RecommendationStatus.PENDING:
                stats['pending_recommendations'] += 1
            elif r.status == RecommendationStatus.ACCEPTED:
                stats['accepted_recommendations'] += 1
                decided += 1
                accepted += 1
            elif r.status == RecommendationStatus.REJECTED:
                stats['rejected_recommendations'] += 1
                decided += 1
            elif r.status == RecommendationStatus.MODIFIED:
                stats['modified_recommendations'] += 1
                decided += 1
                accepted += 1
            elif r.status == RecommendationStatus.INVALIDATED:
                stats['invalidated_recommendations'] += 1

        if decided > 0:
            stats['accept_rate'] = accepted / decided

        stats['by_source_type'] = dict(stats['by_source_type'])
        stats['by_category'] = dict(stats['by_category'])
        return stats

    def clear(self):
        self._cases.clear()
        self._case_unique_keys.clear()
        self._recommendations.clear()
        self._recommendation_unique_keys.clear()
        self._case_counter = 0
        self._recommendation_counter = 0
        self._ngram_index.clear()
        self._fingerprint_index.clear()
