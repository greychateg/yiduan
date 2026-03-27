"""关键词匹配引擎：用户输入 → 八卦评分。"""

import re
from app.data.trigrams import TRIGRAMS, TRIGRAM_ORDER, Trigram

# 否定词前缀
NEGATION_PREFIXES = ["不", "没有", "没", "无", "缺乏", "缺", "别", "非", "未"]


def _has_negation_before(text: str, keyword: str, window: int = 4) -> bool:
    """检查关键词前是否有否定词。"""
    idx = text.find(keyword)
    if idx < 0:
        return False
    prefix = text[max(0, idx - window):idx]
    return any(neg in prefix for neg in NEGATION_PREFIXES)


def _keyword_score(text: str, keyword: str) -> float:
    """单个关键词匹配得分。"""
    if keyword not in text:
        return 0.0
    if _has_negation_before(text, keyword):
        return -0.5  # 否定匹配反向扣分
    return 1.0


def _synonym_score(text: str, keyword: str, synonyms: list[str]) -> float:
    """关键词+同义词匹配得分。"""
    score = _keyword_score(text, keyword)
    if score != 0:
        return score
    for syn in synonyms:
        s = _keyword_score(text, syn)
        if s != 0:
            return s * 0.8  # 同义词权重略低
    return 0.0


def score_trigram_inner(text: str, trigram: Trigram) -> float:
    """评分：用户文本 vs 八卦内在状态关键词。"""
    total = 0.0
    for kw in trigram.inner_keywords:
        syns = trigram.inner_synonyms.get(kw, [])
        total += _synonym_score(text, kw, syns)
    return total


def score_trigram_outer(text: str, trigram: Trigram) -> float:
    """评分：用户文本 vs 八卦外部环境关键词。"""
    total = 0.0
    for kw in trigram.outer_keywords:
        syns = trigram.outer_synonyms.get(kw, [])
        total += _synonym_score(text, kw, syns)
    return total


def match_inner(text: str) -> list[tuple[str, float]]:
    """匹配内在状态，返回按得分排序的八卦列表。"""
    scores = []
    for key in TRIGRAM_ORDER:
        t = TRIGRAMS[key]
        s = score_trigram_inner(text, t)
        scores.append((key, s))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


def match_outer(text: str) -> list[tuple[str, float]]:
    """匹配外部环境，返回按得分排序的八卦列表。"""
    scores = []
    for key in TRIGRAM_ORDER:
        t = TRIGRAMS[key]
        s = score_trigram_outer(text, t)
        scores.append((key, s))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores
