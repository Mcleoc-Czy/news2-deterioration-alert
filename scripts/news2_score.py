#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NEWS2 评分计算脚本（SpO2 量表 1）

教学用途，依据 references/news2-scoring.md。不得用于真实临床决策。

设计原则（对应课堂「模型做语义判断，脚本做确定性规则」）：
  - 缺项不补 0，返回 incomplete，由 Agent 提示补测
  - 数值不合理不评分，返回 implausible，由 Agent 提示复测
  - 只输出评分与报警级别，不输出诊断或治疗建议

用法：
  python3 news2_score.py --rr 22 --spo2 94 --oxygen air --sbp 108 --hr 104 --acvpu A --temp 38.3
  python3 news2_score.py --json '{"rr":22,"spo2":94,"oxygen":"air","sbp":108,"hr":104,"acvpu":"A","temp":38.3}'
  python3 news2_score.py --selftest
"""

import argparse
import json
import sys

# ---------- 合理范围（超出则不评分，提示复测） ----------
PLAUSIBLE = {
    "rr":   (0, 80),      # 次/分
    "spo2": (50, 100),    # %
    "sbp":  (30, 300),    # mmHg
    "hr":   (10, 300),    # 次/分
    "temp": (25.0, 45.0), # 摄氏度
}

FIELD_LABELS = {
    "rr": "呼吸频率",
    "spo2": "SpO2（量表 1）",
    "oxygen": "吸氧情况",
    "sbp": "收缩压",
    "hr": "心率",
    "acvpu": "意识（ACVPU）",
    "temp": "体温",
}

REQUIRED_FIELDS = ["rr", "spo2", "oxygen", "sbp", "hr", "acvpu", "temp"]


# ---------- 逐项评分 ----------
def score_rr(v):
    if v <= 8:
        return 3
    if v <= 11:
        return 1
    if v <= 20:
        return 0
    if v <= 24:
        return 2
    return 3


def score_spo2(v):
    if v <= 91:
        return 3
    if v <= 93:
        return 2
    if v <= 95:
        return 1
    return 0


def score_oxygen(v):
    """v: 'air' / 'oxygen'（或中文 空气 / 吸氧）"""
    s = str(v).strip().lower()
    if s in ("air", "空气", "room air", "ra", "no", "false"):
        return 0
    if s in ("oxygen", "o2", "吸氧", "yes", "true"):
        return 2
    raise ValueError("吸氧情况只接受 air / oxygen")


def score_sbp(v):
    if v <= 90:
        return 3
    if v <= 100:
        return 2
    if v <= 110:
        return 1
    if v <= 219:
        return 0
    return 3


def score_hr(v):
    if v <= 40:
        return 3
    if v <= 50:
        return 1
    if v <= 90:
        return 0
    if v <= 110:
        return 1
    if v <= 130:
        return 2
    return 3


def score_acvpu(v):
    """A=0；C/V/P/U=3"""
    s = str(v).strip().upper()
    if s in ("A", "ALERT", "清醒"):
        return 0
    if s in ("C", "V", "P", "U", "CONFUSION", "VOICE", "PAIN", "UNRESPONSIVE"):
        return 3
    raise ValueError("意识只接受 A / C / V / P / U")


def score_temp(v):
    if v <= 35.0:
        return 3
    if v <= 36.0:
        return 1
    if v <= 38.0:
        return 0
    if v <= 39.0:
        return 1
    return 2


SCORERS = {
    "rr": score_rr,
    "spo2": score_spo2,
    "oxygen": score_oxygen,
    "sbp": score_sbp,
    "hr": score_hr,
    "acvpu": score_acvpu,
    "temp": score_temp,
}


# ---------- 报警级别 ----------
def alert_level(total, has_single_three):
    """判定顺序：>=7 → 5-6 → 单项3分 → 1-4 → 0，命中即停"""
    if total >= 7:
        return {
            "level": "高",
            "monitoring": "持续监测",
            "response": "急救响应阈值（emergency response）：立即通知负责医疗团队，"
                        "紧急评估是否需要重症监护团队介入；在具备高级监护能力的环境中提供临床照护",
            "need_sbar": True,
        }
    if total >= 5:
        return {
            "level": "中",
            "monitoring": "每小时",
            "response": "紧急响应阈值（urgent response）：立即通知负责医疗团队，"
                        "由具备急症患者照护能力的临床人员进行紧急床旁评估；在具备监护条件的环境中提供临床照护",
            "need_sbar": True,
        }
    if has_single_three:
        return {
            "level": "低–中",
            "monitoring": "每小时",
            "response": "护士通知负责医疗团队，由医生评估是否需要升级",
            "need_sbar": True,
        }
    if total >= 1:
        return {
            "level": "低",
            "monitoring": "每 4–6 小时",
            "response": "由注册护士评估，决定是否增加监测频率或上报",
            "need_sbar": False,
        }
    return {
        "level": "无报警",
        "monitoring": "每 12 小时",
        "response": "常规监测",
        "need_sbar": False,
    }


# ---------- 主计算 ----------
def calculate(data):
    # 1. 缺项检查——不补 0
    missing = [f for f in REQUIRED_FIELDS if data.get(f) in (None, "")]
    if missing:
        return {
            "status": "incomplete",
            "missing": [FIELD_LABELS[f] for f in missing],
            "message": "存在缺失评分项，不计算总分。请补测后重新评分，严禁按 0 分处理。",
        }

    # 2. 数值合理性检查
    implausible = []
    for f, (lo, hi) in PLAUSIBLE.items():
        try:
            v = float(data[f])
        except (TypeError, ValueError):
            implausible.append(f"{FIELD_LABELS[f]}（无法识别为数值：{data[f]}）")
            continue
        if not (lo <= v <= hi):
            implausible.append(f"{FIELD_LABELS[f]}={data[f]}（合理范围 {lo}–{hi}）")
    if implausible:
        return {
            "status": "implausible",
            "implausible": implausible,
            "message": "存在不合理数值，不计算总分。请核对记录并复测。",
        }

    # 3. 逐项评分
    scores = {}
    try:
        for f in REQUIRED_FIELDS:
            v = data[f]
            if f in ("oxygen", "acvpu"):
                scores[f] = SCORERS[f](v)
            else:
                scores[f] = SCORERS[f](float(v))
    except ValueError as e:
        return {"status": "invalid", "message": str(e)}

    total = sum(scores.values())
    singles = [FIELD_LABELS[f] for f, s in scores.items() if s == 3]
    alert = alert_level(total, bool(singles))

    result = {
        "status": "ok",
        "scores": {FIELD_LABELS[f]: scores[f] for f in REQUIRED_FIELDS},
        "total": total,
        "single_three": singles,
        "alert_level": alert["level"],
        "min_monitoring": alert["monitoring"],
        "clinical_response": alert["response"],
        "need_sbar": alert["need_sbar"],
        "source": "RCP NEWS2 (2017)；见 references/news2-scoring.md",
    }

    # 低血氧强制提示
    if float(data["spo2"]) <= 91:
        result["spo2_alert"] = (
            "SpO2 ≤91%：立即检查指夹位置并复测，同时床旁评估；复测确认前不得视为伪差忽略。"
        )
    return result


# ---------- 自测 ----------
def selftest():
    cases = [
        ("正常", dict(rr=16, spo2=98, oxygen="air", sbp=120, hr=70, acvpu="A", temp=36.8), 0, "无报警"),
        ("示例病例", dict(rr=22, spo2=94, oxygen="air", sbp=108, hr=104, acvpu="A", temp=38.3), 6, "中"),
        ("单项3分", dict(rr=26, spo2=98, oxygen="air", sbp=120, hr=70, acvpu="A", temp=36.8), 3, "低–中"),
        ("仅吸氧", dict(rr=16, spo2=98, oxygen="oxygen", sbp=120, hr=70, acvpu="A", temp=36.8), 2, "低"),
        ("意识改变", dict(rr=16, spo2=98, oxygen="air", sbp=120, hr=70, acvpu="C", temp=36.8), 3, "低–中"),
        ("0分边界上限", dict(rr=20, spo2=96, oxygen="air", sbp=111, hr=90, acvpu="A", temp=38.0), 0, "无报警"),
        ("刚越边界", dict(rr=21, spo2=95, oxygen="air", sbp=110, hr=91, acvpu="A", temp=38.1), 6, "中"),
        ("低血氧", dict(rr=18, spo2=72, oxygen="air", sbp=120, hr=70, acvpu="A", temp=36.8), 3, "低–中"),
    ]
    ok = True
    for name, data, exp_total, exp_level in cases:
        r = calculate(data)
        got_total, got_level = r.get("total"), r.get("alert_level")
        passed = got_total == exp_total and got_level == exp_level
        ok = ok and passed
        mark = "PASS" if passed else "FAIL"
        print(f"[{mark}] {name}: 总分 {got_total}（期望 {exp_total}），级别 {got_level}（期望 {exp_level}）")

    # 缺项与不合理值
    r = calculate(dict(rr=18, spo2=97, oxygen="air", hr=80, acvpu="A", temp=36.8))
    p = r["status"] == "incomplete"
    ok = ok and p
    print(f"[{'PASS' if p else 'FAIL'}] 缺收缩压: status={r['status']}")

    r = calculate(dict(rr=18, spo2=97, oxygen="air", sbp=120, hr=400, acvpu="A", temp=36.8))
    p = r["status"] == "implausible"
    ok = ok and p
    print(f"[{'PASS' if p else 'FAIL'}] 心率400: status={r['status']}")

    print("\n全部通过" if ok else "\n存在失败用例")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="NEWS2 评分计算（教学用，SpO2 量表 1）")
    ap.add_argument("--rr", type=float, help="呼吸频率 次/分")
    ap.add_argument("--spo2", type=float, help="SpO2 %%")
    ap.add_argument("--oxygen", help="air 或 oxygen")
    ap.add_argument("--sbp", type=float, help="收缩压 mmHg")
    ap.add_argument("--hr", type=float, help="心率 次/分")
    ap.add_argument("--acvpu", help="A / C / V / P / U")
    ap.add_argument("--temp", type=float, help="体温 ℃")
    ap.add_argument("--json", help="以 JSON 字符串一次传入全部参数")
    ap.add_argument("--selftest", action="store_true", help="运行内置自测")
    args = ap.parse_args()

    if args.selftest:
        sys.exit(selftest())

    if args.json:
        data = json.loads(args.json)
    else:
        data = {f: getattr(args, f) for f in REQUIRED_FIELDS}

    print(json.dumps(calculate(data), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
