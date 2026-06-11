"""
自动疑点识别模块：基于规则库自动识别错字、脱文、衍文、倒文、编号断裂
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Set
from datetime import datetime
import hashlib

from collation_rules import CollationRuleLibrary, CollationType, CandidateSuggestion
from collation_analyzer import CollationAnalyzer, TextDiff
from workflow_engine import WorkflowEngine, DoubtRecord
from audit_trail import OperationType


@dataclass
class DetectionResult:
    doubt_id: str
    collation_type: str
    volume: int
    paragraph: int
    copy_batch: str
    original_text: str
    suggested_text: str
    confidence: float
    reason: str
    rule_id: str
    created: bool
    message: str


@dataclass
class DetectionSummary:
    total_detected: int = 0
    new_created: int = 0
    duplicates_skipped: int = 0
    by_type: Dict[str, int] = field(default_factory=dict)
    results: List[DetectionResult] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'total_detected': self.total_detected,
            'new_created': self.new_created,
            'duplicates_skipped': self.duplicates_skipped,
            'by_type': self.by_type,
            'results_count': len(self.results)
        }


class DoubtDetector:
    def __init__(self,
                 rule_library: Optional[CollationRuleLibrary] = None,
                 workflow_engine: Optional[WorkflowEngine] = None):
        self.rule_library = rule_library or CollationRuleLibrary()
        self.workflow_engine = workflow_engine or WorkflowEngine()
        self._detection_counter = 0

    def _generate_data_hash(self, *args) -> str:
        content = '|'.join(str(a) for a in args)
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _detect_wrong_chars(self,
                            analyzer: CollationAnalyzer,
                            project_id: str,
                            operator: str) -> List[DetectionResult]:
        results = []
        enabled_rules = self.rule_library.get_rules_by_type(CollationType.WRONG_CHAR)
        enabled_rules = [r for r in enabled_rules if r.enabled]
        if not enabled_rules:
            return results

        copy_batches = analyzer.copy_batches
        if len(copy_batches) < 2:
            return results

        for i in range(len(copy_batches)):
            for j in range(i + 1, len(copy_batches)):
                ca, cb = copy_batches[i], copy_batches[j]
                diffs = analyzer.compute_diffs(ca, cb)

                for diff in diffs:
                    for tag, a_part, b_part in diff.diff_regions:
                        if tag == 'replace' and len(a_part) == len(b_part) == 1:
                            is_wrong, confidence = self.rule_library.check_wrong_char(a_part, b_part)
                            if not is_wrong:
                                for rule in enabled_rules:
                                    if a_part and b_part and a_part != b_part:
                                        confidence = max(confidence, rule.min_confidence)
                                        is_wrong = True
                                        break

                            if is_wrong and confidence >= 0.6:
                                for copy_batch, orig, sugg in [(ca, a_part, b_part), (cb, b_part, a_part)]:
                                    try:
                                        result = self._create_doubt_safe(
                                            creator=operator,
                                            project_id=project_id,
                                            collation_type=CollationType.WRONG_CHAR.value,
                                            volume=self._get_volume_for_para(analyzer, diff.para_id),
                                            paragraph=diff.para_id,
                                            copy_batch=copy_batch,
                                            original_text=orig,
                                            suggested_text=sugg,
                                            confidence=confidence,
                                            reason=f'与{cb if copy_batch == ca else ca}版本对比，疑似错字',
                                            rule_id='RULE_WRONG_CHAR_001',
                                            data_hash=self._generate_data_hash(orig, sugg, copy_batch, diff.para_id)
                                        )
                                        results.append(result)
                                    except ValueError:
                                        pass
        return results

    def _detect_missing_text(self,
                             analyzer: CollationAnalyzer,
                             project_id: str,
                             operator: str) -> List[DetectionResult]:
        results = []
        enabled_rules = self.rule_library.get_rules_by_type(CollationType.MISSING_TEXT)
        enabled_rules = [r for r in enabled_rules if r.enabled]
        if not enabled_rules:
            return results

        copy_batches = analyzer.copy_batches
        if len(copy_batches) < 2:
            return results

        for i in range(len(copy_batches)):
            for j in range(len(copy_batches)):
                if i == j:
                    continue
                ca, cb = copy_batches[i], copy_batches[j]
                diffs = analyzer.compute_diffs(ca, cb)

                for diff in diffs:
                    for tag, a_part, b_part in diff.diff_regions:
                        if tag == 'insert':
                            orig = ''
                            sugg = b_part
                            if a_part:
                                orig = a_part

                            try:
                                result = self._create_doubt_safe(
                                    creator=operator,
                                    project_id=project_id,
                                    collation_type=CollationType.MISSING_TEXT.value,
                                    volume=self._get_volume_for_para(analyzer, diff.para_id),
                                    paragraph=diff.para_id,
                                    copy_batch=ca,
                                    original_text=orig,
                                    suggested_text=sugg,
                                    confidence=0.8,
                                    reason=f'相较于{cb}版本，疑似脱文，缺少内容: [{sugg}]',
                                    rule_id='RULE_MISSING_001',
                                    data_hash=self._generate_data_hash('MISSING', orig, sugg, ca, diff.para_id)
                                )
                                results.append(result)
                            except ValueError:
                                pass
        return results

    def _detect_extra_text(self,
                           analyzer: CollationAnalyzer,
                           project_id: str,
                           operator: str) -> List[DetectionResult]:
        results = []
        enabled_rules = self.rule_library.get_rules_by_type(CollationType.EXTRA_TEXT)
        enabled_rules = [r for r in enabled_rules if r.enabled]
        if not enabled_rules:
            return results

        copy_batches = analyzer.copy_batches
        if len(copy_batches) < 2:
            return results

        for i in range(len(copy_batches)):
            for j in range(len(copy_batches)):
                if i == j:
                    continue
                ca, cb = copy_batches[i], copy_batches[j]
                diffs = analyzer.compute_diffs(ca, cb)

                for diff in diffs:
                    for tag, a_part, b_part in diff.diff_regions:
                        if tag == 'delete':
                            orig = a_part
                            sugg = ''
                            if b_part:
                                sugg = b_part

                            try:
                                result = self._create_doubt_safe(
                                    creator=operator,
                                    project_id=project_id,
                                    collation_type=CollationType.EXTRA_TEXT.value,
                                    volume=self._get_volume_for_para(analyzer, diff.para_id),
                                    paragraph=diff.para_id,
                                    copy_batch=ca,
                                    original_text=orig,
                                    suggested_text=sugg,
                                    confidence=0.8,
                                    reason=f'相较于{cb}版本，疑似衍文，多出内容: [{orig}]',
                                    rule_id='RULE_EXTRA_001',
                                    data_hash=self._generate_data_hash('EXTRA', orig, sugg, ca, diff.para_id)
                                )
                                results.append(result)
                            except ValueError:
                                pass

                        if tag == 'replace' and len(a_part) > len(b_part) and len(b_part) == 0:
                            try:
                                result = self._create_doubt_safe(
                                    creator=operator,
                                    project_id=project_id,
                                    collation_type=CollationType.EXTRA_TEXT.value,
                                    volume=self._get_volume_for_para(analyzer, diff.para_id),
                                    paragraph=diff.para_id,
                                    copy_batch=ca,
                                    original_text=a_part,
                                    suggested_text='',
                                    confidence=0.7,
                                    reason=f'相较于{cb}版本，疑似衍文',
                                    rule_id='RULE_EXTRA_002',
                                    data_hash=self._generate_data_hash('EXTRA2', a_part, ca, diff.para_id)
                                )
                                results.append(result)
                            except ValueError:
                                pass
        return results

    def _detect_reversed_text(self,
                              analyzer: CollationAnalyzer,
                              project_id: str,
                              operator: str) -> List[DetectionResult]:
        results = []
        enabled_rules = self.rule_library.get_rules_by_type(CollationType.REVERSED_TEXT)
        enabled_rules = [r for r in enabled_rules if r.enabled]
        if not enabled_rules:
            return results

        copy_batches = analyzer.copy_batches
        if len(copy_batches) < 2:
            return results

        for i in range(len(copy_batches)):
            for j in range(i + 1, len(copy_batches)):
                ca, cb = copy_batches[i], copy_batches[j]
                diffs = analyzer.compute_diffs(ca, cb)

                for diff in diffs:
                    for tag, a_part, b_part in diff.diff_regions:
                        if tag == 'replace' and len(a_part) == len(b_part) >= 2:
                            if a_part == b_part[::-1]:
                                for copy_batch, orig, sugg in [(ca, a_part, b_part), (cb, b_part, a_part)]:
                                    try:
                                        result = self._create_doubt_safe(
                                            creator=operator,
                                            project_id=project_id,
                                            collation_type=CollationType.REVERSED_TEXT.value,
                                            volume=self._get_volume_for_para(analyzer, diff.para_id),
                                            paragraph=diff.para_id,
                                            copy_batch=copy_batch,
                                            original_text=orig,
                                            suggested_text=sugg,
                                            confidence=0.85,
                                            reason=f'与{cb if copy_batch == ca else ca}版本对比，二字顺序颠倒，疑似倒文',
                                            rule_id='RULE_REVERSED_001',
                                            data_hash=self._generate_data_hash('REVERSED', orig, sugg, copy_batch, diff.para_id)
                                        )
                                        results.append(result)
                                    except ValueError:
                                        pass
        return results

    def _detect_number_breaks(self,
                              analyzer: CollationAnalyzer,
                              project_id: str,
                              operator: str) -> List[DetectionResult]:
        results = []
        enabled_rules = self.rule_library.get_rules_by_type(CollationType.NUMBER_BREAK)
        enabled_rules = [r for r in enabled_rules if r.enabled]
        if not enabled_rules:
            return results

        missing = analyzer.get_missing_paragraphs()
        for (copy_batch, volume), ranges in missing.items():
            for start, end in ranges:
                for para in range(start, end + 1):
                    try:
                        result = self._create_doubt_safe(
                            creator=operator,
                            project_id=project_id,
                            collation_type=CollationType.NUMBER_BREAK.value,
                            volume=volume,
                            paragraph=para,
                            copy_batch=copy_batch,
                            original_text='【缺失】',
                            suggested_text='',
                            confidence=0.95,
                            reason=f'段落编号不连续，第{para}段缺失',
                            rule_id='RULE_NUMBER_001',
                            data_hash=self._generate_data_hash('NUM_BREAK', copy_batch, volume, para)
                        )
                        results.append(result)
                    except ValueError:
                        pass

        volumes = analyzer.volumes
        if len(volumes) > 1:
            expected_volumes = set(range(min(volumes), max(volumes) + 1))
            actual_volumes = set(volumes)
            missing_volumes = sorted(expected_volumes - actual_volumes)
            for vol in missing_volumes:
                try:
                    result = self._create_doubt_safe(
                        creator=operator,
                        project_id=project_id,
                        collation_type=CollationType.NUMBER_BREAK.value,
                        volume=vol,
                        paragraph=0,
                        copy_batch='ALL',
                        original_text='【卷次缺失】',
                        suggested_text='',
                        confidence=0.95,
                        reason=f'卷次编号不连续，第{vol}卷缺失',
                        rule_id='RULE_NUMBER_002',
                        data_hash=self._generate_data_hash('VOL_BREAK', vol)
                    )
                    results.append(result)
                except ValueError:
                    pass

        return results

    def _get_volume_for_para(self, analyzer: CollationAnalyzer, para_id: int) -> int:
        table = analyzer.build_comparison_table()
        if table.empty:
            return 0
        row = table[table['段落编号'] == para_id]
        if not row.empty:
            return int(row.iloc[0]['卷次'])
        return 0

    def _create_doubt_safe(self,
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
                           data_hash: str = '') -> DetectionResult:
        is_duplicate = self.workflow_engine.check_duplicate(
            project_id=project_id,
            volume=volume,
            paragraph=paragraph,
            copy_batch=copy_batch,
            collation_type=collation_type,
            original_text=original_text,
            suggested_text=suggested_text
        )

        if is_duplicate:
            return DetectionResult(
                doubt_id='',
                collation_type=collation_type,
                volume=volume,
                paragraph=paragraph,
                copy_batch=copy_batch,
                original_text=original_text,
                suggested_text=suggested_text,
                confidence=confidence,
                reason=reason,
                rule_id=rule_id,
                created=False,
                message='重复疑点，已跳过'
            )

        try:
            doubt = self.workflow_engine.create_doubt(
                creator=creator,
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
                data_hash=data_hash
            )
            return DetectionResult(
                doubt_id=doubt.doubt_id,
                collation_type=collation_type,
                volume=volume,
                paragraph=paragraph,
                copy_batch=copy_batch,
                original_text=original_text,
                suggested_text=suggested_text,
                confidence=confidence,
                reason=reason,
                rule_id=rule_id,
                created=True,
                message='创建成功'
            )
        except ValueError as e:
            return DetectionResult(
                doubt_id='',
                collation_type=collation_type,
                volume=volume,
                paragraph=paragraph,
                copy_batch=copy_batch,
                original_text=original_text,
                suggested_text=suggested_text,
                confidence=confidence,
                reason=reason,
                rule_id=rule_id,
                created=False,
                message=str(e)
            )

    def detect_all(self,
                   analyzer: CollationAnalyzer,
                   project_id: str,
                   operator: str,
                   detect_types: Optional[List[CollationType]] = None) -> DetectionSummary:
        self.workflow_engine.permission_manager.check_permission(operator, 'detect_doubts')

        if detect_types is None:
            detect_types = [
                CollationType.WRONG_CHAR,
                CollationType.MISSING_TEXT,
                CollationType.EXTRA_TEXT,
                CollationType.REVERSED_TEXT,
                CollationType.NUMBER_BREAK
            ]

        summary = DetectionSummary()

        detection_funcs = {
            CollationType.WRONG_CHAR: self._detect_wrong_chars,
            CollationType.MISSING_TEXT: self._detect_missing_text,
            CollationType.EXTRA_TEXT: self._detect_extra_text,
            CollationType.REVERSED_TEXT: self._detect_reversed_text,
            CollationType.NUMBER_BREAK: self._detect_number_breaks
        }

        for ctype in detect_types:
            if ctype in detection_funcs:
                func = detection_funcs[ctype]
                results = func(analyzer, project_id, operator)
                summary.results.extend(results)
                summary.total_detected += len(results)
                summary.by_type[ctype.value] = len([r for r in results if r.created])
                summary.new_created += len([r for r in results if r.created])
                summary.duplicates_skipped += len([r for r in results if not r.created])

        self.workflow_engine.audit_trail.log(
            operation_type=OperationType.DOUBT_DETECT,
            operator=operator,
            operator_role=self.workflow_engine.permission_manager.get_user_role(operator).value,
            project_id=project_id,
            description=f"自动疑点检测完成: 发现{summary.total_detected}个，新增{summary.new_created}个，跳过重复{summary.duplicates_skipped}个",
            extra=summary.to_dict()
        )

        return summary

    def detect_for_volume(self,
                          analyzer: CollationAnalyzer,
                          project_id: str,
                          volume: int,
                          operator: str,
                          detect_types: Optional[List[CollationType]] = None) -> DetectionSummary:
        full_summary = self.detect_all(analyzer, project_id, operator, detect_types)
        volume_results = [r for r in full_summary.results if r.volume == volume]

        summary = DetectionSummary()
        summary.results = volume_results
        summary.total_detected = len(volume_results)
        summary.new_created = len([r for r in volume_results if r.created])
        summary.duplicates_skipped = len([r for r in volume_results if not r.created])
        for r in volume_results:
            if r.created:
                summary.by_type[r.collation_type] = summary.by_type.get(r.collation_type, 0) + 1

        return summary

    def get_candidate_suggestions(self,
                                  text_a: str,
                                  text_b: str,
                                  collation_type: Optional[CollationType] = None) -> List[CandidateSuggestion]:
        suggestions = []
        self._detection_counter += 1

        if collation_type is None or collation_type == CollationType.WRONG_CHAR:
            if len(text_a) == len(text_b):
                for i, (ca, cb) in enumerate(zip(text_a, text_b)):
                    if ca != cb:
                        is_wrong, confidence = self.rule_library.check_wrong_char(ca, cb)
                        if is_wrong or confidence > 0:
                            suggestions.append(CandidateSuggestion(
                                suggestion_id=f'SUGG-WRONG-{self._detection_counter}-{i}',
                                rule_id='RULE_WRONG_CHAR_001',
                                collation_type=CollationType.WRONG_CHAR,
                                confidence=max(confidence, 0.7),
                                original_text=ca,
                                suggested_text=cb,
                                reason=f'形近/音近字: {ca} → {cb}',
                                position=(i, i + 1)
                            ))

        if collation_type is None or collation_type == CollationType.REVERSED_TEXT:
            if len(text_a) == len(text_b) >= 2 and text_a == text_b[::-1]:
                suggestions.append(CandidateSuggestion(
                    suggestion_id=f'SUGG-REV-{self._detection_counter}',
                    rule_id='RULE_REVERSED_001',
                    collation_type=CollationType.REVERSED_TEXT,
                    confidence=0.85,
                    original_text=text_a,
                    suggested_text=text_b,
                    reason=f'疑似倒文: {text_a} → {text_b}'
                ))

        return suggestions
