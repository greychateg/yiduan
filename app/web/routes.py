"""Flask 路由。"""

import hashlib
import datetime
from flask import Flask, render_template, request, jsonify
from app.data.trigrams import TRIGRAMS, TRIGRAM_ORDER
from app.data.roles import (
    ROLES, ROLE_ORDER, FOUR_IMAGE_LABELS,
)
from app.data.role_interpretations import get_role_interpretation
from app.data.hexagrams import ONE_LINERS, HEXAGRAM_LOOKUP, HEXAGRAM_DETAILS, Hexagram
from app.data.yao import get_yao_lines
from app.engine.diagnosis import diagnose, FOUR_IMAGE_IS_YANG


def _compute_primary_line(n_changing, changing_lines, hexagram, transformed, yao_lines, line_choices):
    """根据传统变爻规则计算主爻。

    规则：
    - 0 变爻: 看主卦卦辞
    - 1 变爻: 看那一爻的爻辞
    - 2 变爻: 看下面（位置数字小的）那一爻
    - 3 变爻: 看主卦卦辞 + 变卦卦辞
    - 4 变爻: 看变卦中不变的下面那一爻
    - 5 变爻: 看变卦中不变的那一爻
    - 6 变爻: 看变卦卦辞（乾坤特殊：看用九/用六）
    """
    result = {
        "rule": "",
        "focus_position": None,
        "focus_text": "",
        "description": "",
    }

    if n_changing == 0:
        result["rule"] = "zero"
        result["description"] = "无变爻，以主卦卦辞为主"
        result["focus_text"] = hexagram.gua_ci or hexagram.core_meaning
    elif n_changing == 1:
        cl = changing_lines[0]
        result["rule"] = "one"
        result["focus_position"] = cl.position
        yao = next((y for y in yao_lines if y.position == cl.position), None)
        result["description"] = f"一个变爻，以第{cl.position}爻爻辞为主"
        result["focus_text"] = yao.classical + "——" + yao.interpretation if yao else ""
    elif n_changing == 2:
        # 看下面那一爻（位置数字小的）
        positions = sorted([cl.position for cl in changing_lines])
        focus_pos = positions[0]
        result["rule"] = "two"
        result["focus_position"] = focus_pos
        yao = next((y for y in yao_lines if y.position == focus_pos), None)
        result["description"] = f"两个变爻，以下方第{focus_pos}爻为主"
        result["focus_text"] = yao.classical + "——" + yao.interpretation if yao else ""
    elif n_changing == 3:
        result["rule"] = "three"
        result["description"] = "三个变爻，主卦卦辞与变卦卦辞并看"
        main_ci = hexagram.gua_ci or hexagram.core_meaning
        trans_ci = (transformed.gua_ci or transformed.core_meaning) if transformed else ""
        result["focus_text"] = f"主卦：{main_ci}\n变卦：{trans_ci}"
    elif n_changing == 4:
        # 看变卦中不变的爻（下面那个）
        changing_positions = {cl.position for cl in changing_lines}
        unchanged = sorted([i for i in range(1, 7) if i not in changing_positions])
        if unchanged:
            focus_pos = unchanged[0]
            result["rule"] = "four"
            result["focus_position"] = focus_pos
            result["description"] = f"四个变爻，以变卦中不变的第{focus_pos}爻为主"
            result["focus_text"] = f"关注变卦第{focus_pos}爻的稳定含义"
        else:
            result["rule"] = "four"
            result["description"] = "四个变爻，以变卦卦辞为主"
    elif n_changing == 5:
        # 看变卦中唯一不变的那一爻
        changing_positions = {cl.position for cl in changing_lines}
        unchanged = [i for i in range(1, 7) if i not in changing_positions]
        if unchanged:
            focus_pos = unchanged[0]
            result["rule"] = "five"
            result["focus_position"] = focus_pos
            result["description"] = f"五个变爻，以变卦中唯一不变的第{focus_pos}爻为主"
            result["focus_text"] = f"关注变卦第{focus_pos}爻——唯一不变的锚点"
        else:
            result["rule"] = "five"
            result["description"] = "五个变爻，以变卦卦辞为主"
    elif n_changing == 6:
        result["rule"] = "six"
        if hexagram.number == 1:
            result["description"] = "六爻全变（乾），看用九"
            result["focus_text"] = "用九：见群龙无首，吉。——不执着于做领头羊，反而大吉。"
        elif hexagram.number == 2:
            result["description"] = "六爻全变（坤），看用六"
            result["focus_text"] = "用六：利永贞。——永远保持柔顺正道。"
        else:
            result["description"] = "六爻全变，以变卦卦辞为主"
            if transformed:
                result["focus_text"] = transformed.gua_ci or transformed.core_meaning
            else:
                result["focus_text"] = ""

    return result


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../../static",
    )

    @app.after_request
    def add_no_cache(response):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

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
        """返回角色数据供前端渲染（含每角色专属问题和选项）。"""
        yao_labels = ["初爻", "二爻", "三爻", "四爻", "五爻", "上爻"]
        yao_stages = ["起始", "内核", "转折", "外应", "主位", "终局"]
        result = []
        for key in ROLE_ORDER:
            r = ROLES[key]
            questions_data = []
            for idx, q in enumerate(r.questions):
                questions_data.append({
                    "title": q.title,
                    "options": q.options,
                    "yao_label": yao_labels[idx],
                    "yao_stage": yao_stages[idx],
                })
            result.append({
                "key": r.key,
                "name": r.name,
                "icon": r.icon,
                "subtitle": r.subtitle,
                "questions": questions_data,
                "blind_spots": r.blind_spots,
            })
        return jsonify({
            "roles": result,
        })

    @app.route("/api/daily")
    def daily_hexagram():
        """今日一卦：基于日期的确定性随机卦象。"""
        today = datetime.date.today().isoformat()
        seed = hashlib.md5(today.encode()).hexdigest()

        # 用seed生成6爻
        four_images = ["young_yang", "old_yang", "young_yin", "old_yin"]
        weights = [3, 1, 3, 1]  # 传统概率
        lines = []
        for i in range(6):
            # 用seed的不同部分生成每爻
            chunk = int(seed[i*4:(i+1)*4], 16)
            total_weight = sum(weights)
            r = chunk % total_weight
            cumul = 0
            chosen = four_images[0]
            for j, w in enumerate(weights):
                cumul += w
                if r < cumul:
                    chosen = four_images[j]
                    break
            lines.append(chosen)

        try:
            result = diagnose(*lines)
        except Exception as e:
            return jsonify({"error": str(e)}), 500

        h = result.hexagram
        from app.data.hexagrams import ONE_LINERS as _ol
        return jsonify({
            "date": today,
            "hexagram": {
                "number": h.number,
                "name": h.name,
                "full_name": h.full_name,
                "symbols": h.symbols,
                "one_liner": h.one_liner or _ol.get(h.number, ""),
                "gua_ci": h.gua_ci or "",
                "strategy": h.strategy,
                "risk": h.risk,
            },
            "changing_count": len(result.changing_lines),
            "transformed": {
                "full_name": result.transformed_hexagram.full_name,
                "one_liner": result.transformed_hexagram.one_liner or _ol.get(result.transformed_hexagram.number, ""),
            } if result.transformed_hexagram else None,
        })

    @app.route("/api/hexagrams")
    def get_hexagrams():
        """返回全部64卦基本信息，供卦典页面使用。"""
        result = []
        for (lower_key, upper_key), entry in HEXAGRAM_LOOKUP.items():
            number, name, full_name, symbols = entry
            h = HEXAGRAM_DETAILS.get(number)
            one_liner = ""
            gua_ci = ""
            if h:
                one_liner = h.one_liner or ONE_LINERS.get(number, "")
                gua_ci = h.gua_ci or ""
            else:
                one_liner = ONE_LINERS.get(number, "")
            result.append({
                "number": number,
                "name": name,
                "full_name": full_name,
                "symbols": symbols,
                "one_liner": one_liner,
                "gua_ci": gua_ci,
            })
        # Deduplicate by number (some entries may map to the same hexagram)
        seen = {}
        deduped = []
        for item in result:
            if item["number"] not in seen:
                seen[item["number"]] = True
                deduped.append(item)
        deduped.sort(key=lambda x: x["number"])
        return jsonify(deduped)

    @app.route("/api/hexagram/<int:number>")
    def get_hexagram_detail(number):
        """返回单个卦象的完整信息，包括爻辞。"""
        # Find hexagram by number
        h = HEXAGRAM_DETAILS.get(number)
        if not h:
            # Search in lookup table
            found = None
            for (lower_key, upper_key), entry in HEXAGRAM_LOOKUP.items():
                if entry[0] == number:
                    found = (lower_key, upper_key, entry)
                    break
            if not found:
                return jsonify({"error": f"卦象 {number} 不存在"}), 404
            lower_key, upper_key, entry = found
            from app.data.hexagrams import lookup_hexagram as _lookup
            h = _lookup(lower_key, upper_key)
            if not h:
                return jsonify({"error": f"卦象 {number} 不存在"}), 404

        # Get yao lines
        yao_lines = get_yao_lines(h.number, h.lower, h.upper)
        yao_data = []
        for y in yao_lines:
            yao_data.append({
                "position": y.position,
                "is_yang": y.is_yang,
                "classical": y.classical,
                "interpretation": y.interpretation,
                "advice": y.advice,
            })

        return jsonify({
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
            "one_liner": h.one_liner or ONE_LINERS.get(h.number, ""),
            "is_detailed": h.is_detailed,
            "yao_lines": yao_data,
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

        # 获取角色专属卦象解读
        role_interp = get_role_interpretation(role_key, h.number)
        role_interpretation_data = {
            "core_bridge": role_interp.core_bridge,
            "action": role_interp.action,
            "warning": role_interp.warning,
            "is_template": role_interp.is_template,
        }

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
                "one_liner": th.one_liner or ONE_LINERS.get(th.number, ""),
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

        # 主爻判断逻辑 (传统易经规则)
        n_changing = len(result.changing_lines)
        primary_line_info = _compute_primary_line(
            n_changing, result.changing_lines, h, result.transformed_hexagram,
            result.yao_lines, result.line_choices
        )

        # 变卦过渡描述
        transition_meaning = ""
        if result.transformed_hexagram:
            th = result.transformed_hexagram
            t_liner = th.one_liner or ONE_LINERS.get(th.number, "")
            h_liner = h.one_liner or ONE_LINERS.get(h.number, "")
            transition_meaning = (
                f"从「{h.full_name}」走向「{th.full_name}」"
                + f"——从\u201c{h_liner}\u201d到\u201c{t_liner}\u201d。"
            )

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
                "one_liner": h.one_liner or ONE_LINERS.get(h.number, ""),
            },
            "role_interpretation": role_interpretation_data,
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
            "primary_line": primary_line_info,
            "transition_meaning": transition_meaning,
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
