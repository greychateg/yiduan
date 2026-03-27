"""Flask 路由。"""

from flask import Flask, render_template, request, jsonify
from app.data.trigrams import TRIGRAMS, TRIGRAM_ORDER
from app.data.roles import (
    ROLES, ROLE_ORDER, UNIVERSAL_OPTIONS, UNIVERSAL_QUESTIONS,
    FOUR_IMAGE_LABELS,
)
from app.engine.diagnosis import diagnose, FOUR_IMAGE_IS_YANG


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../../static",
    )

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/api/trigrams")
    def get_trigrams():
        """返回八卦数据供前端渲染选项卡片。"""
        result = []
        for key in TRIGRAM_ORDER:
            t = TRIGRAMS[key]
            result.append({
                "key": t.key,
                "name": t.name,
                "element": t.element,
                "symbol": t.symbol,
                "nature": t.nature,
            })
        return jsonify(result)

    @app.route("/api/roles")
    def get_roles():
        """返回角色数据供前端渲染。"""
        result = []
        for key in ROLE_ORDER:
            r = ROLES[key]
            result.append({
                "key": r.key,
                "name": r.name,
                "icon": r.icon,
                "subtitle": r.subtitle,
                "hints": r.hints,
                "blind_spots": r.blind_spots,
            })
        return jsonify({
            "roles": result,
            "questions": UNIVERSAL_QUESTIONS,
            "options": UNIVERSAL_OPTIONS,
        })

    @app.route("/diagnose", methods=["POST"])
    def do_diagnose():
        data = request.get_json(force=True)

        role_key = data.get("role", "investor")

        # 接受 line1-line6 参数
        line_keys = []
        for i in range(1, 7):
            val = data.get(f"line{i}", "")
            if not val:
                return jsonify({"error": f"请完成第{i}爻的选择"}), 400
            if val not in FOUR_IMAGE_IS_YANG:
                return jsonify({"error": f"无效的四象选择: {val}"}), 400
            line_keys.append(val)

        try:
            result = diagnose(*line_keys)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        h = result.hexagram
        lower_t = TRIGRAMS[result.lower_key]
        upper_t = TRIGRAMS[result.upper_key]

        # 获取角色信息
        role = ROLES.get(role_key, ROLES["investor"])

        # 六爻数据
        yao_data = []
        for y in result.yao_lines:
            yao_data.append({
                "position": y.position,
                "is_yang": y.is_yang,
                "classical": y.classical,
                "interpretation": y.interpretation,
                "advice": y.advice,
            })

        # 变爻数据
        changing_data = []
        for cl in result.changing_lines:
            changing_data.append({
                "position": cl.position,
                "reason": cl.reason,
                "from_yang": cl.from_yang,
                "to_yang": cl.to_yang,
                "four_image": cl.four_image,
            })

        # 变卦数据
        transformed_data = None
        if result.transformed_hexagram:
            th = result.transformed_hexagram
            transformed_data = {
                "number": th.number,
                "name": th.name,
                "full_name": th.full_name,
                "symbols": th.symbols,
                "structure": th.structure,
                "core_meaning": th.core_meaning,
                "strategy": th.strategy,
                "direction": th.direction,
                "gua_ci": th.gua_ci or "",
            }

        # 角色专属自省
        role_blind_spots = role.blind_spots

        # 卦象反思问题
        reflection_questions = getattr(h, 'reflection_questions', []) if hasattr(h, 'reflection_questions') else []

        # 对立卦分析
        opposites = {
            "qian": "kun", "kun": "qian",
            "zhen": "gen", "gen": "zhen",
            "kan": "li", "li": "kan",
            "xun": "dui", "dui": "xun",
        }
        opp_lower = opposites.get(result.lower_key, "kun")
        opp_upper = opposites.get(result.upper_key, "qian")
        from app.data.hexagrams import lookup_hexagram
        opp_hex = lookup_hexagram(opp_lower, opp_upper)
        contrast_text = ""
        if opp_hex:
            contrast_text = (
                f"你的诊断结果是「{h.full_name}」，但如果情况其实是「{opp_hex.full_name}」呢？"
                f"那意味着：{opp_hex.strategy.split('。')[0]}。"
                f"想想看，有没有可能你的内在和外部状态恰好相反？"
            )

        # 四象选择摘要
        line_choices_data = []
        for i, choice in enumerate(result.line_choices):
            line_choices_data.append({
                "position": i + 1,
                "four_image": choice,
                "label": FOUR_IMAGE_LABELS[choice],
                "is_yang": FOUR_IMAGE_IS_YANG[choice],
            })

        return jsonify({
            "hexagram": {
                "number": h.number,
                "name": h.name,
                "full_name": h.full_name,
                "symbols": h.symbols,
                "structure": h.structure,
                "core_meaning": h.core_meaning,
                "situation": h.situation,
                "strategy": h.strategy,
                "risk": h.risk,
                "direction": h.direction,
                "gua_ci": h.gua_ci or "",
                "trade_analogy": h.trade_analogy or "",
                "key_yao": h.key_yao or "",
                "is_detailed": h.is_detailed,
                "reflection_questions": reflection_questions,
            },
            "lower": {
                "key": result.lower_key,
                "name": lower_t.name,
                "element": lower_t.element,
                "symbol": lower_t.symbol,
            },
            "upper": {
                "key": result.upper_key,
                "name": upper_t.name,
                "element": upper_t.element,
                "symbol": upper_t.symbol,
            },
            "line_choices": line_choices_data,
            "role": role_key,
            "yao_lines": yao_data,
            "changing_lines": changing_data,
            "transformed": transformed_data,
            "warnings": result.warnings,
            "inner_conflict": result.inner_conflict,
            "outer_conflict": result.outer_conflict,
            "lower_confidence": result.lower_confidence,
            "upper_confidence": result.upper_confidence,
            "action_summary": result.action_summary,
            "risk_level": result.risk_level,
            "bias": {
                "inner": lower_t.inner_bias,
                "outer": upper_t.outer_bias,
                "opponent": (
                    '如果你的竞争对手来看这件事，'
                    '他会怎么描述你的内在状态和外部环境？'
                    '他可能把你放在哪一卦？'
                ),
                "cross_domain": (
                    '找一个不同行业或不同时期的类似案例。'
                    '那个案例里，内外状态的组合跟你的判断一致吗？'
                ),
                "blind_spots": role_blind_spots,
                "contrast": contrast_text,
                "reflection_questions": reflection_questions,
            },
        })

    return app
