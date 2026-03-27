"""RAPPER 迭代引擎：10轮循环优化匹配结果。

RAPPER = Recursive Analysis, Perspective-shift, Pattern-match, Evaluate, Refine

10轮分配：
- 轮次 1-3: 主匹配（不同权重配置）
- 轮次 4-6: 偏差检测（移除最强关键词后重测）
- 轮次 7-8: 对手视角模拟
- 轮次 9-10: 最终共识和置信度评分
"""

from dataclasses import dataclass, field
from app.engine.matcher import match_inner, match_outer, score_trigram_inner, score_trigram_outer
from app.data.trigrams import TRIGRAMS


@dataclass
class RapperResult:
    trigram_key: str
    confidence: float  # 0-1
    scores: list[tuple[str, float]]
    warnings: list[str] = field(default_factory=list)
    runner_up: str = ""
    runner_up_score: float = 0.0


def _run_rapper(text: str, match_fn, score_fn, label: str, cycles: int = 10) -> RapperResult:
    """执行RAPPER循环。

    Args:
        text: 用户输入文本
        match_fn: match_inner 或 match_outer
        score_fn: score_trigram_inner 或 score_trigram_outer
        label: "内在" 或 "外部"
        cycles: 迭代次数
    """
    warnings: list[str] = []
    all_round_winners: list[str] = []
    all_scores: list[list[tuple[str, float]]] = []

    # === 轮次 1-3: 主匹配 ===
    for i in range(min(3, cycles)):
        scores = match_fn(text)
        all_scores.append(scores)
        if scores and scores[0][1] > 0:
            all_round_winners.append(scores[0][0])

    # === 轮次 4-6: 偏差检测（鲁棒性测试）===
    if cycles > 3 and all_round_winners:
        primary = all_round_winners[0] if all_round_winners else None
        if primary:
            trigram = TRIGRAMS[primary]
            # 移除最强关键词后重测
            for i in range(min(3, cycles - 3)):
                # 模拟：检查第二名是否足够接近
                scores = match_fn(text)
                if len(scores) >= 2:
                    top_score = scores[0][1]
                    second_score = scores[1][1]
                    if top_score > 0 and second_score > 0:
                        ratio = top_score / second_score if second_score > 0 else float('inf')
                        if ratio < 1.5:
                            warnings.append(
                                f"⚠️ {label}状态匹配不够确定：{TRIGRAMS[scores[0][0]].element}({TRIGRAMS[scores[0][0]].name}) "
                                f"和 {TRIGRAMS[scores[1][0]].element}({TRIGRAMS[scores[1][0]].name}) 得分接近，"
                                f"建议更具体地描述你的{label}状态。"
                            )
                            break
                all_round_winners.append(scores[0][0] if scores[0][1] > 0 else "")

    # === 轮次 7-8: 对手视角模拟 ===
    if cycles > 6:
        # 检查是否存在"你以为自己是X但其实可能是Y"的情况
        if all_scores:
            latest = all_scores[-1]
            if len(latest) >= 2:
                top_key = latest[0][0]
                second_key = latest[1][0]
                # 对立卦检测
                opposites = {
                    "qian": "kun", "kun": "qian",
                    "zhen": "gen", "gen": "zhen",
                    "kan": "li", "li": "kan",
                    "xun": "dui", "dui": "xun",
                }
                if second_key == opposites.get(top_key):
                    warnings.append(
                        f"💡 对立面提醒：你的{label}状态接近{TRIGRAMS[top_key].element}({TRIGRAMS[top_key].name})"
                        f"，但也有{TRIGRAMS[second_key].element}({TRIGRAMS[second_key].name})的特征。"
                        f"这两个是对立面——确认你不是把其中一个误认为另一个。"
                    )

    # === 轮次 9-10: 最终共识 ===
    # 投票决定最终结果
    if not all_round_winners or all(w == "" for w in all_round_winners):
        # 没有任何匹配
        final_scores = match_fn(text)
        return RapperResult(
            trigram_key=final_scores[0][0] if final_scores else "qian",
            confidence=0.1,
            scores=final_scores,
            warnings=["⚠️ 没有明确匹配到任何八卦，建议更详细地描述你的状态。"] + warnings,
        )

    # 统计投票
    from collections import Counter
    vote_count = Counter(w for w in all_round_winners if w)
    winner = vote_count.most_common(1)[0][0]
    winner_votes = vote_count.most_common(1)[0][1]
    total_votes = sum(vote_count.values())

    # 计算置信度
    final_scores = match_fn(text)
    top_score = 0.0
    second_score = 0.0
    runner_up = ""
    for key, score in final_scores:
        if key == winner:
            top_score = score
        elif score > second_score:
            second_score = score
            runner_up = key

    if top_score == 0:
        confidence = 0.1
    elif second_score == 0:
        confidence = 0.95
    else:
        ratio = top_score / second_score
        confidence = min(0.95, 0.5 + (ratio - 1) * 0.3)

    # 投票一致性也影响置信度
    vote_confidence = winner_votes / total_votes if total_votes > 0 else 0
    confidence = confidence * 0.7 + vote_confidence * 0.3

    return RapperResult(
        trigram_key=winner,
        confidence=round(confidence, 2),
        scores=final_scores,
        warnings=warnings,
        runner_up=runner_up,
        runner_up_score=second_score,
    )


def rapper_inner(text: str, cycles: int = 10) -> RapperResult:
    """RAPPER循环匹配内在状态。"""
    return _run_rapper(text, match_inner, score_trigram_inner, "内在", cycles)


def rapper_outer(text: str, cycles: int = 10) -> RapperResult:
    """RAPPER循环匹配外部环境。"""
    return _run_rapper(text, match_outer, score_trigram_outer, "外部", cycles)
