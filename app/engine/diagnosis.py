"""诊断引擎：四象系统 — 6爻直接生成 + 变爻 + 变卦。

每条爻由四象之一确定：
- 少阳 (young_yang): 阳爻，稳定，不变
- 太阳 (old_yang): 阳爻，极盛将变（变爻 → 变为阴）
- 少阴 (young_yin): 阴爻，稳定，不变
- 太阴 (old_yin): 阴爻，极盛将变（变爻 → 变为阳）
"""

from dataclasses import dataclass, field
from app.data.trigrams import TRIGRAMS
from app.data.hexagrams import lookup_hexagram, Hexagram
from app.data.yao import get_yao_lines, get_hexagram_lines, YaoLine, TRIGRAM_LINES


# 四象 → 阴阳映射
FOUR_IMAGE_IS_YANG = {
    "young_yang": True,
    "old_yang": True,
    "young_yin": False,
    "old_yin": False,
}

# 四象 → 是否变爻
FOUR_IMAGE_IS_CHANGING = {
    "young_yang": False,
    "old_yang": True,   # 老阳变阴
    "young_yin": False,
    "old_yin": True,    # 老阴变阳
}

FOUR_IMAGE_LABELS = {
    "young_yang": "少阳",
    "old_yang": "太阳",
    "young_yin": "少阴",
    "old_yin": "太阴",
}


@dataclass
class ChangingLine:
    position: int       # 1-6
    reason: str         # 变化原因
    from_yang: bool     # 原始阴阳
    to_yang: bool       # 变化后阴阳
    four_image: str     # old_yang or old_yin


@dataclass
class DiagnosisResult:
    # 主卦
    lower_key: str
    upper_key: str
    hexagram: Hexagram
    yao_lines: list[YaoLine]

    # 四象选择 (6条)
    line_choices: list[str] = field(default_factory=list)  # ["young_yang", "old_yin", ...]

    # 变爻
    changing_lines: list[ChangingLine] = field(default_factory=list)

    # 变卦
    transformed_hexagram: Hexagram | None = None
    transformed_lower_key: str = ""
    transformed_upper_key: str = ""

    # 冲突信息 (保留兼容)
    inner_conflict: bool = False
    outer_conflict: bool = False
    warnings: list[str] = field(default_factory=list)

    # 置信度 (四象系统下固定 1.0)
    lower_confidence: float = 1.0
    upper_confidence: float = 1.0

    # 投资建议
    action_summary: str = ""
    risk_level: str = ""  # 低/中/高/极高


def _lines_to_trigram_key(line1: bool, line2: bool, line3: bool) -> str:
    """三条线 → 三爻key。"""
    target = (line1, line2, line3)
    for key, lines in TRIGRAM_LINES.items():
        if lines == target:
            return key
    return "qian"


def _generate_action_summary(hex: Hexagram, changing_lines: list[ChangingLine],
                              transformed: Hexagram | None) -> str:
    """生成行动摘要。"""
    parts = []
    parts.append(hex.strategy.split("。")[0] + "。")

    n_changing = len(changing_lines)
    if n_changing == 0:
        parts.append("卦象纯净无变爻，当前局势稳定，按既定方向执行。")
    elif n_changing <= 2:
        positions = "、".join([f"第{cl.position}爻({FOUR_IMAGE_LABELS[cl.four_image]})" for cl in changing_lines])
        parts.append(f"变爻在{positions}，局势正在变化中。")
    elif n_changing <= 4:
        parts.append(f"有{n_changing}个变爻，局势高度动荡，谨慎决策。")
    else:
        parts.append(f"有{n_changing}个变爻，几乎全盘变动，以变卦为主参考。")

    if transformed:
        parts.append(f"局势正在向「{transformed.full_name}」方向演变。")

    return " ".join(parts)


def _assess_risk(hex: Hexagram, changing_lines: list[ChangingLine]) -> str:
    """评估风险等级。"""
    risk_score = 0

    # 变爻数量影响风险
    risk_score += len(changing_lines)

    # 太阳(old_yang)变爻比太阴(old_yin)更危险（极盛转衰）
    for cl in changing_lines:
        if cl.four_image == "old_yang":
            risk_score += 1  # 额外加分

    # 危险卦
    dangerous = {29, 47, 36, 23, 4, 39, 3, 64}
    if hex.number in dangerous:
        risk_score += 3

    # 安全卦
    safe = {1, 2, 11, 14, 15, 35, 46, 58}
    if hex.number in safe:
        risk_score -= 1

    if risk_score <= 1:
        return "低"
    elif risk_score <= 3:
        return "中"
    elif risk_score <= 5:
        return "高"
    else:
        return "极高"


def diagnose(line1: str, line2: str, line3: str,
             line4: str, line5: str, line6: str) -> DiagnosisResult:
    """执行四象诊断。

    line1-line6: 每条爻的四象选择
        "young_yang" | "old_yang" | "young_yin" | "old_yin"

    line1 = 初爻 (最底), line6 = 上爻 (最顶)
    lines 1-3 = 下卦(内), lines 4-6 = 上卦(外)
    """
    choices = [line1, line2, line3, line4, line5, line6]

    # 验证输入
    valid_keys = set(FOUR_IMAGE_IS_YANG.keys())
    for i, c in enumerate(choices):
        if c not in valid_keys:
            raise ValueError(f"无效的四象选择: {c} (爻{i+1})")

    # 1. 构建主卦六爻
    primary_lines = [FOUR_IMAGE_IS_YANG[c] for c in choices]

    # 2. 确定上下卦
    lower_key = _lines_to_trigram_key(primary_lines[0], primary_lines[1], primary_lines[2])
    upper_key = _lines_to_trigram_key(primary_lines[3], primary_lines[4], primary_lines[5])

    # 3. 查找卦象
    hexagram = lookup_hexagram(lower_key, upper_key)
    if not hexagram:
        raise ValueError(f"无法查找卦象: {lower_key}, {upper_key}")

    # 4. 获取爻辞
    yao_lines = get_yao_lines(hexagram.number, lower_key, upper_key)

    # 5. 识别变爻
    changing_lines: list[ChangingLine] = []
    warnings: list[str] = []

    position_names = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
    position_meanings = ["起点/基础", "内在核心", "转折/危机", "外部适应", "关键决策", "结果/趋势"]

    for i, choice in enumerate(choices):
        if FOUR_IMAGE_IS_CHANGING[choice]:
            pos = i + 1
            from_yang = FOUR_IMAGE_IS_YANG[choice]
            to_yang = not from_yang
            label = FOUR_IMAGE_LABELS[choice]

            if choice == "old_yang":
                reason = f"{position_names[i]}（{position_meanings[i]}）为太阳：阳极将变阴，盛极必衰，极端积极中隐含反转"
            else:  # old_yin
                reason = f"{position_names[i]}（{position_meanings[i]}）为太阴：阴极将变阳，否极泰来，极端消极中隐含转机"

            changing_lines.append(ChangingLine(
                position=pos,
                reason=reason,
                from_yang=from_yang,
                to_yang=to_yang,
                four_image=choice,
            ))
            warnings.append(reason)

    # 6. 构建变卦
    transformed_hex = None
    trans_lower = ""
    trans_upper = ""

    if changing_lines:
        transformed_lines = primary_lines.copy()
        for cl in changing_lines:
            transformed_lines[cl.position - 1] = cl.to_yang

        trans_lower = _lines_to_trigram_key(
            transformed_lines[0], transformed_lines[1], transformed_lines[2]
        )
        trans_upper = _lines_to_trigram_key(
            transformed_lines[3], transformed_lines[4], transformed_lines[5]
        )
        transformed_hex = lookup_hexagram(trans_lower, trans_upper)

    # 7. 生成摘要和风险评估
    action_summary = _generate_action_summary(hexagram, changing_lines, transformed_hex)
    risk_level = _assess_risk(hexagram, changing_lines)

    return DiagnosisResult(
        lower_key=lower_key,
        upper_key=upper_key,
        hexagram=hexagram,
        yao_lines=yao_lines,
        line_choices=choices,
        changing_lines=changing_lines,
        transformed_hexagram=transformed_hex,
        transformed_lower_key=trans_lower,
        transformed_upper_key=trans_upper,
        inner_conflict=False,
        outer_conflict=False,
        warnings=warnings,
        lower_confidence=1.0,
        upper_confidence=1.0,
        action_summary=action_summary,
        risk_level=risk_level,
    )
