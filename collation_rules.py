"""
校勘规则库模块：定义校勘类型、检测规则、置信度评分
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum


class CollationType(str, Enum):
    WRONG_CHAR = '错字'
    MISSING_TEXT = '脱文'
    EXTRA_TEXT = '衍文'
    REVERSED_TEXT = '倒文'
    NUMBER_BREAK = '编号断裂'
    UNKNOWN = '未知'


@dataclass
class CollationRule:
    rule_id: str
    name: str
    collation_type: CollationType
    description: str
    enabled: bool = True
    priority: int = 100
    min_confidence: float = 0.6
    extra_params: Dict = field(default_factory=dict)

    def __post_init__(self):
        if self.min_confidence < 0 or self.min_confidence > 1:
            raise ValueError(f"置信度必须在0-1之间: {self.min_confidence}")


@dataclass
class CandidateSuggestion:
    suggestion_id: str
    rule_id: str
    collation_type: CollationType
    confidence: float
    original_text: str
    suggested_text: str
    reason: str
    position: Optional[Tuple[int, int]] = None


class CollationRuleLibrary:
    def __init__(self):
        self._rules: Dict[str, CollationRule] = {}
        self._common_wrong_chars: Dict[str, List[str]] = {}
        self._init_default_rules()
        self._init_common_wrong_chars()

    def _init_default_rules(self):
        self.add_rule(CollationRule(
            rule_id='RULE_WRONG_CHAR_001',
            name='形近字错字检测',
            collation_type=CollationType.WRONG_CHAR,
            description='基于常见形近字对照表检测可能的错字',
            priority=100,
            min_confidence=0.7
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_WRONG_CHAR_002',
            name='音近字错字检测',
            collation_type=CollationType.WRONG_CHAR,
            description='基于常见音近字对照表检测可能的错字',
            priority=90,
            min_confidence=0.65
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_MISSING_001',
            name='上下文脱文检测',
            collation_type=CollationType.MISSING_TEXT,
            description='通过多抄本对比检测可能缺失的文字',
            priority=110,
            min_confidence=0.8
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_MISSING_002',
            name='句式脱文检测',
            collation_type=CollationType.MISSING_TEXT,
            description='基于固定句式、对偶排比等检测可能的脱文',
            priority=85,
            min_confidence=0.6
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_EXTRA_001',
            name='上下文衍文检测',
            collation_type=CollationType.EXTRA_TEXT,
            description='通过多抄本对比检测可能多出的文字',
            priority=110,
            min_confidence=0.8
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_EXTRA_002',
            name='重复字衍文检测',
            collation_type=CollationType.EXTRA_TEXT,
            description='检测可能的抄写重复导致的衍文',
            priority=80,
            min_confidence=0.6
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_REVERSED_001',
            name='二字倒文检测',
            collation_type=CollationType.REVERSED_TEXT,
            description='检测相邻两字顺序颠倒的情况',
            priority=95,
            min_confidence=0.75
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_REVERSED_002',
            name='词组倒文检测',
            collation_type=CollationType.REVERSED_TEXT,
            description='基于固定词组搭配检测可能的倒文',
            priority=85,
            min_confidence=0.7
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_NUMBER_001',
            name='段落编号断裂检测',
            collation_type=CollationType.NUMBER_BREAK,
            description='检测段落编号不连续的情况',
            priority=120,
            min_confidence=0.95
        ))

        self.add_rule(CollationRule(
            rule_id='RULE_NUMBER_002',
            name='卷次编号断裂检测',
            collation_type=CollationType.NUMBER_BREAK,
            description='检测卷次编号不连续的情况',
            priority=120,
            min_confidence=0.95
        ))

    def _init_common_wrong_chars(self):
        self._common_wrong_chars = {
            '习': ['时', '席'],
            '时': ['习', '是'],
            '弟': ['悌', '第'],
            '悌': ['弟', '梯'],
            '仁': ['人', '壬'],
            '人': ['仁', '入'],
            '本': ['立', '木'],
            '立': ['本', '力'],
            '传': ['专', '转'],
            '专': ['传', '砖'],
            '说': ['悦', '乐'],
            '悦': ['说', '月'],
            '三': ['吾', '参'],
            '吾': ['三', '五'],
            '也': ['巳', '己'],
            '己': ['已', '巳'],
            '已': ['己', '以'],
        }

    def add_rule(self, rule: CollationRule) -> bool:
        if rule.rule_id in self._rules:
            return False
        self._rules[rule.rule_id] = rule
        return True

    def remove_rule(self, rule_id: str) -> bool:
        if rule_id in self._rules:
            del self._rules[rule_id]
            return True
        return False

    def get_rule(self, rule_id: str) -> Optional[CollationRule]:
        return self._rules.get(rule_id)

    def get_all_rules(self) -> List[CollationRule]:
        return sorted(self._rules.values(), key=lambda r: (-r.priority, r.rule_id))

    def get_enabled_rules(self) -> List[CollationRule]:
        return [r for r in self.get_all_rules() if r.enabled]

    def get_rules_by_type(self, collation_type: CollationType) -> List[CollationRule]:
        return [r for r in self.get_all_rules() if r.collation_type == collation_type]

    def enable_rule(self, rule_id: str) -> bool:
        rule = self.get_rule(rule_id)
        if rule:
            rule.enabled = True
            return True
        return False

    def disable_rule(self, rule_id: str) -> bool:
        rule = self.get_rule(rule_id)
        if rule:
            rule.enabled = False
            return True
        return False

    def add_wrong_char_pair(self, correct: str, wrong: str):
        if correct not in self._common_wrong_chars:
            self._common_wrong_chars[correct] = []
        if wrong not in self._common_wrong_chars[correct]:
            self._common_wrong_chars[correct].append(wrong)

    def get_wrong_char_candidates(self, char: str) -> List[str]:
        return self._common_wrong_chars.get(char, [])

    def check_wrong_char(self, char_a: str, char_b: str) -> Tuple[bool, float]:
        if char_a == char_b:
            return False, 0.0
        if char_b in self._common_wrong_chars.get(char_a, []):
            return True, 0.85
        if char_a in self._common_wrong_chars.get(char_b, []):
            return True, 0.85
        return False, 0.0

    def get_all_wrong_char_pairs(self) -> Dict[str, List[str]]:
        return dict(self._common_wrong_chars)
