"""
古籍引文溯源与互证分析模块：
- 引文/典故/重复语段自动识别
- 出处匹配（同书前后卷 + 外部参考文本）
- 互证关系图谱构建
- 疑似误引检测
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set, Any
from enum import Enum
from datetime import datetime
import hashlib
from collections import defaultdict

from collation_analyzer import CollationAnalyzer


class CitationType(str, Enum):
    QUOTATION = '引文'
    ALLUSION = '典故'
    REPETITION = '重复语段'
    MISQUOTE = '疑似误引'


class CitationStatus(str, Enum):
    PENDING = '待确认'
    CONFIRMED = '已确认'
    REJECTED = '已驳回'
    INVALIDATED = '已失效'


class CitationAction(str, Enum):
    CONFIRM = '确认'
    REJECT = '驳回'
    SUPPLEMENT = '补充出处'
    COMMENT = '备注'
    REACTIVATE = '重新激活'


@dataclass
class CitationSource:
    source_book: str
    source_volume: Optional[int] = None
    source_paragraph: Optional[int] = None
    source_copy_batch: Optional[str] = None
    source_text: str = ''
    source_page: str = ''
    source_chapter: str = ''
    note: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'source_book': self.source_book,
            'source_volume': self.source_volume or '',
            'source_paragraph': self.source_paragraph or '',
            'source_copy_batch': self.source_copy_batch or '',
            'source_text': self.source_text,
            'source_page': self.source_page,
            'source_chapter': self.source_chapter,
            'note': self.note
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'CitationSource':
        return cls(
            source_book=d.get('source_book', ''),
            source_volume=int(d['source_volume']) if d.get('source_volume') else None,
            source_paragraph=int(d['source_paragraph']) if d.get('source_paragraph') else None,
            source_copy_batch=d.get('source_copy_batch', ''),
            source_text=d.get('source_text', ''),
            source_page=d.get('source_page', ''),
            source_chapter=d.get('source_chapter', ''),
            note=d.get('note', '')
        )


@dataclass
class CitationMatch:
    match_text: str
    match_book: str
    match_volume: Optional[int] = None
    match_paragraph: Optional[int] = None
    match_copy_batch: Optional[str] = None
    match_similarity: float = 0.0
    match_basis: str = ''
    is_internal: bool = True
    is_suspected_misquote: bool = False
    sources: List[CitationSource] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'match_text': self.match_text,
            'match_book': self.match_book,
            'match_volume': self.match_volume or '',
            'match_paragraph': self.match_paragraph or '',
            'match_copy_batch': self.match_copy_batch or '',
            'match_similarity': self.match_similarity,
            'match_basis': self.match_basis,
            'is_internal': self.is_internal,
            'is_suspected_misquote': self.is_suspected_misquote,
            'sources': [s.to_dict() for s in self.sources]
        }


@dataclass
class CitationRecord:
    citation_id: str
    project_id: str
    citation_type: CitationType
    volume: int
    paragraph: int
    copy_batch: str
    original_text: str
    quoted_text: str
    start_pos: int = 0
    end_pos: int = 0
    confidence: float = 0.0
    match_basis: str = ''
    status: CitationStatus = CitationStatus.PENDING
    matches: List[CitationMatch] = field(default_factory=list)
    confirmed_source: Optional[CitationSource] = None
    created_by: str = ''
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    processing_history: List[Dict[str, Any]] = field(default_factory=list)
    invalidated_reason: str = ''
    data_hash: str = ''
    extra: Dict[str, Any] = field(default_factory=dict)

    @property
    def unique_key(self) -> str:
        return (f'{self.project_id}|{self.volume}|{self.paragraph}|{self.copy_batch}|'
                f'{self.citation_type.value}|{self.quoted_text}')

    @property
    def is_active(self) -> bool:
        return self.status != CitationStatus.INVALIDATED

    def add_history(self, operator: str, action: CitationAction, content: str,
                    operator_role: str = '', extra: Optional[Dict] = None):
        self.processing_history.append({
            'timestamp': datetime.now(),
            'operator': operator,
            'operator_role': operator_role,
            'action': action.value,
            'content': content,
            'extra': extra or {}
        })
        self.updated_at = datetime.now()

    def invalidate(self, reason: str = '关联数据已修改'):
        self.status = CitationStatus.INVALIDATED
        self.invalidated_reason = reason
        self.updated_at = datetime.now()

    def reactivate(self):
        self.status = CitationStatus.PENDING
        self.invalidated_reason = ''
        self.confirmed_by = None
        self.confirmed_at = None
        self.confirmed_source = None
        self.updated_at = datetime.now()

    def confirm(self, operator: str, source: Optional[CitationSource] = None, note: str = ''):
        self.status = CitationStatus.CONFIRMED
        self.confirmed_by = operator
        self.confirmed_at = datetime.now()
        if source:
            self.confirmed_source = source
        self.updated_at = datetime.now()
        self.add_history(operator, CitationAction.CONFIRM, note or '确认引文出处')

    def reject(self, operator: str, reason: str = ''):
        self.status = CitationStatus.REJECTED
        self.confirmed_by = None
        self.confirmed_at = None
        self.confirmed_source = None
        self.updated_at = datetime.now()
        self.add_history(operator, CitationAction.REJECT, reason or '驳回此引文')

    def supplement_source(self, operator: str, source: CitationSource, note: str = ''):
        self.matches.append(CitationMatch(
            match_text=source.source_text,
            match_book=source.source_book,
            match_volume=source.source_volume,
            match_paragraph=source.source_paragraph,
            match_copy_batch=source.source_copy_batch,
            match_similarity=1.0,
            match_basis=f'人工补充: {note or source.note}',
            is_internal=False,
            sources=[source]
        ))
        self.updated_at = datetime.now()
        self.add_history(operator, CitationAction.SUPPLEMENT, note or '补充出处说明',
                         extra={'source': source.to_dict()})

    def to_dict(self) -> Dict[str, Any]:
        return {
            'citation_id': self.citation_id,
            'project_id': self.project_id,
            'citation_type': self.citation_type.value,
            'volume': self.volume,
            'paragraph': self.paragraph,
            'copy_batch': self.copy_batch,
            'original_text': self.original_text,
            'quoted_text': self.quoted_text,
            'start_pos': self.start_pos,
            'end_pos': self.end_pos,
            'confidence': self.confidence,
            'match_basis': self.match_basis,
            'status': self.status.value,
            'matches': [m.to_dict() for m in self.matches],
            'confirmed_source': self.confirmed_source.to_dict() if self.confirmed_source else None,
            'created_by': self.created_by,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'updated_at': self.updated_at.strftime('%Y-%m-%d %H:%M:%S'),
            'confirmed_by': self.confirmed_by or '',
            'confirmed_at': self.confirmed_at.strftime('%Y-%m-%d %H:%M:%S') if self.confirmed_at else '',
            'processing_history': [
                {
                    'timestamp': h['timestamp'].strftime('%Y-%m-%d %H:%M:%S'),
                    'operator': h['operator'],
                    'operator_role': h['operator_role'],
                    'action': h['action'],
                    'content': h['content'],
                    'extra': h.get('extra', {})
                }
                for h in self.processing_history
            ],
            'invalidated_reason': self.invalidated_reason,
            'data_hash': self.data_hash
        }


@dataclass
class CitationDetectionSummary:
    total_detected: int = 0
    new_created: int = 0
    duplicates_skipped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    by_status: Dict[str, int] = field(default_factory=dict)
    misquote_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'total_detected': self.total_detected,
            'new_created': self.new_created,
            'duplicates_skipped': self.duplicates_skipped,
            'by_type': self.by_type,
            'by_status': self.by_status,
            'misquote_count': self.misquote_count
        }


@dataclass
class CitationGraphNode:
    node_id: str
    label: str
    node_type: str
    volume: Optional[int] = None
    paragraph: Optional[int] = None
    copy_batch: Optional[str] = None
    book: str = ''
    text: str = ''

    def to_dict(self) -> Dict[str, Any]:
        return {
            'node_id': self.node_id,
            'label': self.label,
            'node_type': self.node_type,
            'volume': self.volume,
            'paragraph': self.paragraph,
            'copy_batch': self.copy_batch,
            'book': self.book,
            'text': self.text
        }


@dataclass
class CitationGraphEdge:
    edge_id: str
    source_id: str
    target_id: str
    relation: str
    weight: float = 1.0
    similarity: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            'edge_id': self.edge_id,
            'source_id': self.source_id,
            'target_id': self.target_id,
            'relation': self.relation,
            'weight': self.weight,
            'similarity': self.similarity
        }


@dataclass
class CitationGraph:
    nodes: List[CitationGraphNode] = field(default_factory=list)
    edges: List[CitationGraphEdge] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'nodes': [n.to_dict() for n in self.nodes],
            'edges': [e.to_dict() for e in self.edges]
        }


def _compute_similarity(a: str, b: str) -> float:
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


def _generate_ngrams(text: str, n: int = 4) -> List[str]:
    text = text.strip()
    if len(text) < n:
        return [text] if text else []
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def _hash_text(*args) -> str:
    content = '|'.join(str(a) for a in args)
    return hashlib.md5(content.encode('utf-8')).hexdigest()


class CitationAnalyzer:
    def __init__(self, analyzer: Optional[CollationAnalyzer] = None):
        self.analyzer = analyzer
        self.external_references: Dict[str, List[Dict]] = defaultdict(list)
        self._text_index: Dict[Tuple[str, int, int, str], str] = {}
        self._ngram_index: Dict[str, List[Tuple[str, int, int, str]]] = defaultdict(list)
        self._build_index()

    def set_analyzer(self, analyzer: CollationAnalyzer):
        self.analyzer = analyzer
        self._build_index()

    def _build_index(self):
        self._text_index.clear()
        self._ngram_index.clear()
        if not self.analyzer or self.analyzer.df.empty:
            return
        for _, row in self.analyzer.df.iterrows():
            book = str(row.get('书名', ''))
            vol = int(row.get('卷次', 0))
            para = int(row.get('段落编号', 0))
            copy = str(row.get('抄本批次', ''))
            text = str(row.get('原文内容', ''))
            key = (book, vol, para, copy)
            self._text_index[key] = text
            for gram in _generate_ngrams(text, 4):
                self._ngram_index[gram].append(key)

    def add_external_reference(self, book_name: str, text: str,
                               volume: Optional[int] = None,
                               paragraph: Optional[int] = None,
                               chapter: str = '',
                               page: str = ''):
        ref = {
            'book': book_name,
            'text': text,
            'volume': volume,
            'paragraph': paragraph,
            'chapter': chapter,
            'page': page
        }
        self.external_references[book_name].append(ref)

    def _find_internal_matches(self, quoted_text: str,
                               exclude_book: str,
                               exclude_volume: int,
                               exclude_paragraph: int,
                               exclude_copy: str,
                               threshold: float = 0.6) -> List[CitationMatch]:
        matches: List[CitationMatch] = []
        if not quoted_text or len(quoted_text) < 4:
            return matches
        candidate_keys: Set[Tuple[str, int, int, str]] = set()
        for gram in _generate_ngrams(quoted_text, 4):
            for key in self._ngram_index.get(gram, []):
                book, vol, para, copy = key
                if (book == exclude_book and vol == exclude_volume
                        and para == exclude_paragraph and copy == exclude_copy):
                    continue
                candidate_keys.add(key)
        for key in candidate_keys:
            book, vol, para, copy = key
            target_text = self._text_index.get(key, '')
            sim = _compute_similarity(quoted_text, target_text)
            if sim >= threshold:
                is_misquote = self._detect_misquote(quoted_text, target_text)
                matches.append(CitationMatch(
                    match_text=target_text,
                    match_book=book,
                    match_volume=vol,
                    match_paragraph=para,
                    match_copy_batch=copy,
                    match_similarity=sim,
                    match_basis=f'内部文本相似匹配 (相似率={sim:.2%})',
                    is_internal=True,
                    is_suspected_misquote=is_misquote,
                    sources=[CitationSource(
                        source_book=book,
                        source_volume=vol,
                        source_paragraph=para,
                        source_copy_batch=copy,
                        source_text=target_text
                    )]
                ))
        matches.sort(key=lambda m: m.match_similarity, reverse=True)
        return matches[:5]

    def _find_external_matches(self, quoted_text: str,
                                threshold: float = 0.6) -> List[CitationMatch]:
        matches: List[CitationMatch] = []
        if not quoted_text or len(quoted_text) < 4:
            return matches
        for book_name, refs in self.external_references.items():
            for ref in refs:
                target_text = ref.get('text', '')
                sim = _compute_similarity(quoted_text, target_text)
                if sim >= threshold:
                    is_misquote = self._detect_misquote(quoted_text, target_text)
                    matches.append(CitationMatch(
                        match_text=target_text,
                        match_book=book_name,
                        match_volume=ref.get('volume'),
                        match_paragraph=ref.get('paragraph'),
                        match_similarity=sim,
                        match_basis=f'外部参考匹配《{book_name}》(相似率={sim:.2%})',
                        is_internal=False,
                        is_suspected_misquote=is_misquote,
                        sources=[CitationSource(
                            source_book=book_name,
                            source_volume=ref.get('volume'),
                            source_paragraph=ref.get('paragraph'),
                            source_text=target_text,
                            source_chapter=ref.get('chapter', ''),
                            source_page=ref.get('page', '')
                        )]
                    ))
        matches.sort(key=lambda m: m.match_similarity, reverse=True)
        return matches[:3]

    def _detect_misquote(self, quoted: str, source: str) -> bool:
        if not quoted or not source:
            return False
        if len(quoted) < 4 or len(source) < 4:
            return False
        q_stripped = quoted.strip()
        s_stripped = source.strip()
        if q_stripped == s_stripped:
            return False
        sim = _compute_similarity(q_stripped, s_stripped)
        if 0.5 <= sim < 0.85:
            if len(q_stripped) >= 6 and len(s_stripped) >= 6:
                diff_count = sum(1 for a, b in zip(q_stripped, s_stripped) if a != b)
                if diff_count >= max(1, int(min(len(q_stripped), len(s_stripped)) * 0.1)):
                    return True
        return False

    def _detect_repetitions(self) -> List[Dict]:
        repetitions = []
        if not self.analyzer or self.analyzer.df.empty:
            return repetitions
        text_locations: Dict[str, List[Tuple[int, int, str, str]]] = defaultdict(list)
        for _, row in self.analyzer.df.iterrows():
            book = str(row.get('书名', ''))
            vol = int(row.get('卷次', 0))
            para = int(row.get('段落编号', 0))
            copy = str(row.get('抄本批次', ''))
            text = str(row.get('原文内容', ''))
            for n in [8, 10, 12]:
                for i in range(len(text) - n + 1):
                    sub = text[i:i + n]
                    if len(set(sub)) >= 4:
                        text_locations[sub].append((vol, para, copy, book))
        for sub, locs in text_locations.items():
            if len(locs) >= 2:
                unique_locs = list(set(locs))
                if len(unique_locs) >= 2:
                    vols = set(l[0] for l in unique_locs)
                    paras = set(l[1] for l in unique_locs)
                    copies = set(l[2] for l in unique_locs)
                    if len(vols) >= 2 or len(paras) >= 2 or len(copies) >= 2:
                        repetitions.append({
                            'text': sub,
                            'locations': unique_locs,
                            'occurrence_count': len(unique_locs)
                        })
        repetitions.sort(key=lambda r: r['occurrence_count'], reverse=True)
        return repetitions[:100]

    def detect_citations(self,
                         project_id: str,
                         operator: str,
                         book_name: str,
                         volume: Optional[int] = None,
                         copy_batch: Optional[str] = None,
                         detect_types: Optional[List[CitationType]] = None) -> CitationDetectionSummary:
        if not self.analyzer or self.analyzer.df.empty:
            return CitationDetectionSummary()
        if detect_types is None:
            detect_types = [CitationType.QUOTATION, CitationType.REPETITION, CitationType.MISQUOTE]
        summary = CitationDetectionSummary()
        df = self.analyzer.df
        if volume is not None:
            df = df[df['卷次'] == volume]
        if copy_batch:
            df = df[df['抄本批次'] == copy_batch]
        records: List[CitationRecord] = []
        if CitationType.REPETITION in detect_types:
            repetitions = self._detect_repetitions()
            for rep in repetitions:
                for (vol, para, copy, book) in rep['locations']:
                    text = self._text_index.get((book, vol, para, copy), '')
                    start = text.find(rep['text'])
                    if start < 0:
                        continue
                    end = start + len(rep['text'])
                    internal_matches = []
                    for (v2, p2, c2, b2) in rep['locations']:
                        if v2 == vol and p2 == para and c2 == copy and b2 == book:
                            continue
                        target_text = self._text_index.get((b2, v2, p2, c2), '')
                        internal_matches.append(CitationMatch(
                            match_text=target_text,
                            match_book=b2,
                            match_volume=v2,
                            match_paragraph=p2,
                            match_copy_batch=c2,
                            match_similarity=1.0,
                            match_basis=f'重复语段检测 (共出现{rep["occurrence_count"]}次)',
                            is_internal=True,
                            sources=[CitationSource(
                                source_book=b2,
                                source_volume=v2,
                                source_paragraph=p2,
                                source_copy_batch=c2,
                                source_text=target_text
                            )]
                        ))
                    confidence = min(0.95, 0.6 + 0.05 * rep['occurrence_count'])
                    record = CitationRecord(
                        citation_id='',
                        project_id=project_id,
                        citation_type=CitationType.REPETITION,
                        volume=vol,
                        paragraph=para,
                        copy_batch=copy,
                        original_text=text,
                        quoted_text=rep['text'],
                        start_pos=start,
                        end_pos=end,
                        confidence=confidence,
                        match_basis=f'重复语段检测，跨{len(set(l[0] for l in rep["locations"]))}卷，共{rep["occurrence_count"]}处',
                        matches=internal_matches,
                        created_by=operator,
                        data_hash=_hash_text(book, vol, para, copy, rep['text'], 'REPETITION')
                    )
                    records.append(record)
        for _, row in df.iterrows():
            book = str(row.get('书名', ''))
            vol = int(row.get('卷次', 0))
            para = int(row.get('段落编号', 0))
            copy = str(row.get('抄本批次', ''))
            text = str(row.get('原文内容', ''))
            if not text or len(text) < 6:
                continue
            for window_size in [20, 16, 12, 8]:
                if len(text) < window_size:
                    continue
                step = max(1, window_size // 2)
                for i in range(0, len(text) - window_size + 1, step):
                    candidate = text[i:i + window_size]
                    if len(set(candidate)) < 4:
                        continue
                    internal_matches = self._find_internal_matches(
                        candidate, book, vol, para, copy, threshold=0.75
                    )
                    external_matches = self._find_external_matches(candidate, threshold=0.75)
                    all_matches = internal_matches + external_matches
                    if not all_matches:
                        continue
                    has_misquote = any(m.is_suspected_misquote for m in all_matches)
                    max_sim = max(m.match_similarity for m in all_matches)
                    if CitationType.MISQUOTE in detect_types and has_misquote:
                        ctype = CitationType.MISQUOTE
                        confidence = max_sim
                    elif CitationType.QUOTATION in detect_types:
                        ctype = CitationType.QUOTATION
                        confidence = max_sim
                    else:
                        continue
                    basis_parts = []
                    if internal_matches:
                        basis_parts.append(f"内部匹配{len(internal_matches)}处")
                    if external_matches:
                        basis_parts.append(f"外部匹配{len(external_matches)}处")
                    if has_misquote:
                        basis_parts.append("疑似误引")
                    record = CitationRecord(
                        citation_id='',
                        project_id=project_id,
                        citation_type=ctype,
                        volume=vol,
                        paragraph=para,
                        copy_batch=copy,
                        original_text=text,
                        quoted_text=candidate,
                        start_pos=i,
                        end_pos=i + window_size,
                        confidence=confidence,
                        match_basis='; '.join(basis_parts),
                        matches=all_matches,
                        created_by=operator,
                        data_hash=_hash_text(book, vol, para, copy, candidate, ctype.value)
                    )
                    records.append(record)
        seen_keys: Set[str] = set()
        deduped: List[CitationRecord] = []
        for rec in records:
            key = rec.unique_key
            if key in seen_keys:
                summary.duplicates_skipped += 1
                continue
            seen_keys.add(key)
            deduped.append(rec)
        deduped.sort(key=lambda r: r.confidence, reverse=True)
        summary.total_detected = len(deduped)
        summary.by_type = defaultdict(int)
        for rec in deduped:
            summary.by_type[rec.citation_type.value] += 1
            if rec.citation_type == CitationType.MISQUOTE:
                summary.misquote_count += 1
        self._pending_records = deduped
        return summary

    def get_pending_records(self) -> List[CitationRecord]:
        return getattr(self, '_pending_records', [])

    def build_citation_graph(self, citations: List[CitationRecord]) -> CitationGraph:
        graph = CitationGraph()
        node_ids: Set[str] = set()
        edge_ids: Set[str] = set()
        for cite in citations:
            cite_node_id = f'CITE-{cite.citation_id}'
            if cite_node_id not in node_ids:
                graph.nodes.append(CitationGraphNode(
                    node_id=cite_node_id,
                    label=f'{cite.citation_type.value}:{cite.quoted_text[:15]}...',
                    node_type='citation',
                    volume=cite.volume,
                    paragraph=cite.paragraph,
                    copy_batch=cite.copy_batch,
                    book=cite.project_id,
                    text=cite.quoted_text
                ))
                node_ids.add(cite_node_id)
            para_node_id = f'PARA-{cite.project_id}-{cite.volume}-{cite.paragraph}-{cite.copy_batch}'
            if para_node_id not in node_ids:
                graph.nodes.append(CitationGraphNode(
                    node_id=para_node_id,
                    label=f'第{cite.volume}卷第{cite.paragraph}段({cite.copy_batch})',
                    node_type='paragraph',
                    volume=cite.volume,
                    paragraph=cite.paragraph,
                    copy_batch=cite.copy_batch,
                    book=cite.project_id
                ))
                node_ids.add(para_node_id)
            edge1_id = f'{para_node_id}-contains-{cite_node_id}'
            if edge1_id not in edge_ids:
                graph.edges.append(CitationGraphEdge(
                    edge_id=edge1_id,
                    source_id=para_node_id,
                    target_id=cite_node_id,
                    relation='contains',
                    weight=1.0
                ))
                edge_ids.add(edge1_id)
            for match in cite.matches:
                match_node_id = f'MATCH-{match.match_book}-{match.match_volume}-{match.match_paragraph}-{match.match_copy_batch or "ext"}'
                if match_node_id not in node_ids:
                    graph.nodes.append(CitationGraphNode(
                        node_id=match_node_id,
                        label=f'{match.match_book}卷{match.match_volume}段{match.match_paragraph}',
                        node_type='source',
                        volume=match.match_volume,
                        paragraph=match.match_paragraph,
                        copy_batch=match.match_copy_batch,
                        book=match.match_book,
                        text=match.match_text
                    ))
                    node_ids.add(match_node_id)
                edge2_id = f'{cite_node_id}-refs-{match_node_id}'
                if edge2_id not in edge_ids:
                    graph.edges.append(CitationGraphEdge(
                        edge_id=edge2_id,
                        source_id=cite_node_id,
                        target_id=match_node_id,
                        relation='suspected_misquote' if match.is_suspected_misquote else 'cites',
                        weight=match.match_similarity,
                        similarity=match.match_similarity
                    ))
                    edge_ids.add(edge2_id)
        return graph
