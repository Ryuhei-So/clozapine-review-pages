#!/usr/bin/env python3
from __future__ import annotations

import csv
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "mock_data"
FIG = DATA / "figures"
ASSET_PREFIX = "../patient_survey_mock/assets"
RNG = random.Random(20260529)

VERSIONS = {
    1: {
        "label": "v1: DCEからBHTM/TTへ置換した最小構成",
        "focus": "DCEをやめ、入院導入・外来導入のvignette比較と外来負担閾値だけに絞った初期案。",
        "improvements": [
            "Hauber & Coulter 2020に従い、1つのkey attributeを外来導入burden packageとして順序化。",
            "Barrett 2005を参考に、benefit/harmを明示してから受容閾値を尋ねる構成に変更。",
        ],
    },
    2: {
        "label": "v2: benefit/harm固定と直接選好を分離",
        "focus": "Parikh 2023に合わせ、まず同じ効果・安全性説明のもとで入院/外来の直接受容性を聞き、その後にTTへ進む。",
        "improvements": [
            "入院導入の期間、外来導入の7週目以降、異常時入院切替を明示。",
            "“今の状態で提案されたら”と“今より困りごとが強くなった場合”を分けることで唐突さを減らした。",
        ],
    },
    3: {
        "label": "v3: adaptive TTとnon-tradingを実装",
        "focus": "受け入れたら重い側、拒否したら軽い側へ動くのではなく、患者負担を下げながら初めて受け入れる水準を記録する実装に整理。",
        "improvements": [
            "回答負担を下げるため、重い外来条件から軽い条件へ進む単方向TTにした。",
            "どの条件でも受け入れない、どの条件でも受け入れる、わからないをnon-trading/uncertainとして保持。",
        ],
    },
    4: {
        "label": "v4: 患者の読みやすさを優先",
        "focus": "長文説明を避け、イラスト、短いカード、1画面1判断のウィザードへ近づけた版。",
        "improvements": [
            "Health literacyへの配慮として、Hauber & Coulter 2020の注意点に沿い視覚情報と短文説明を増やした。",
            "障壁リストは“全部嫌”になりやすいため、最大の負担を1つだけ選ぶ形式へ変更。",
        ],
    },
    5: {
        "label": "v5: 最終候補",
        "focus": "科学的価値、方法論的妥当性、回答しやすさのバランスを取った現時点の推奨版。",
        "improvements": [
            "臨床家調査のmGAF-Fに基づき、mGAF-F 40以下は現在の状態で回答、41以上は将来TRS相当となった場合の仮想シナリオで回答する2層構造にした。",
            "主要アウトカムを“入院導入と外来導入の受容性”と“外来導入時の初期通院頻度threshold”に固定。",
            "通院のみ条件を拒否した場合は理由を記録し、安全面不安が含まれる場合だけ訪問看護追加モジュールへ進む。",
            "通院頻度ごとに拒否理由を集計し、安全面不安を含む拒否者の中で訪問看護追加がどの程度受容性を改善するかを示す。",
            "医師判断との接続図表を加え、臨床家調査と患者調査を別論文でも接続できる構成にした。",
        ],
    },
}

THRESHOLDS = [
    ("V3", "週3回通院なら受容"),
    ("V2", "週2回通院なら受容"),
    ("V1", "週1回通院なら受容"),
    ("NONE", "通院のみ条件は非受容/保留"),
]

SUPPORT_PACKAGES = [
    ("V3N2", "週5回確認: 週3回通院+週2回訪問看護"),
    ("V2N3", "週5回確認: 週2回通院+週3回訪問看護"),
    ("V1N4", "週5回確認: 週1回通院+週4回訪問看護"),
    ("V2N1", "週3回確認: 週2回通院+週1回訪問看護"),
    ("V1N2", "週3回確認: 週1回通院+週2回訪問看護"),
    ("V1N1", "週2回確認: 週1回通院+週1回訪問看護"),
]

SIDE_EFFECTS = [
    ("sedation", "眠気・だるさ", "比較的よくみられる", "日中の眠気や活動しづらさにつながることがあります。"),
    ("hypersalivation", "よだれ・流涎", "比較的よくみられる", "唾液が増え、夜間や会話中に困ることがあります。"),
    ("weight_metabolic", "体重増加・代謝異常", "比較的よくみられる", "体重、血糖、脂質などを定期的に確認します。"),
    ("constipation", "便秘", "比較的よくみられる・重くなることがある", "早めに対処しないと重くなることがあります。"),
    ("infection_blood", "白血球減少・感染リスク", "まれだが重要", "早く見つけるため、定期的な採血を行います。"),
    ("myocarditis", "心筋炎など重い副作用", "まれだが重要", "発熱、胸痛、息切れなどがあれば早めに相談します。"),
]

SUPPORT_BY_THRESHOLD = {
    "V3": ["V3N2"],
    "V2": ["V2N1", "V2N3"],
    "V1": ["V1N1", "V1N2", "V1N4"],
    "NONE": ["V1N1", "V1N2", "V1N4"],
}

VISIT_REJECTION_REASONS = [
    ("visit_burden", "通院回数・移動の負担が大きい"),
    ("safety_concern", "この通院回数だけでは安全面が不安"),
]

SUPPORT_REFUSAL_REASONS = [
    ("home_nursing_dislike", "訪問看護が入ること自体が嫌"),
    ("nursing_too_frequent", "訪問看護の回数が多すぎる"),
    ("still_safety_concern", "それでも安全面が不安"),
    ("other_unknown", "その他・わからない"),
]


def ensure_dirs() -> None:
    DATA.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    for v in VERSIONS:
        (DATA / f"v{v}").mkdir(exist_ok=True)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def simulate(version: int) -> dict[str, list[dict[str, str]]]:
    n = 180
    participants: list[dict[str, str]] = []
    vignette: list[dict[str, str]] = []
    threshold: list[dict[str, str]] = []
    gap: list[dict[str, str]] = []
    safety: list[dict[str, str]] = []

    for i in range(1, n + 1):
        target = "TRS適格候補" if i <= 86 else "広い未使用外来患者"
        unmet = RNG.random() < (0.72 if target == "TRS適格候補" else 0.46)
        past_refusal = RNG.random() < 0.16
        subjective_distress = RNG.random() < (0.68 if unmet else 0.30)
        age = max(21, min(78, int(RNG.normalvariate(48 if target == "TRS適格候補" else 44, 12))))
        mgaf_function = max(18, min(75, int(RNG.normalvariate(36 if target == "TRS適格候補" else 50, 7))))
        if target == "広い未使用外来患者" and not unmet:
            mgaf_function = max(mgaf_function, int(RNG.normalvariate(55, 5)))
        response_frame = "actual_current" if mgaf_function <= 40 else "hypothetical_future"
        participants.append(
            {
                "participant_id": f"P{i:03d}",
                "target_group": target,
                "clinician_mgaf_function": str(mgaf_function),
                "response_frame": response_frame,
                "age": str(age),
                "sex": RNG.choice(["女性", "男性", "回答しない"]),
                "current_unmet_need": "あり" if unmet else "なし/軽度",
                "subjective_distress": "あり" if subjective_distress else "なし/軽度",
                "past_clozapine_refusal_documented": "あり" if past_refusal else "なし",
            }
        )

        p_inpatient_now = sigmoid(-1.35 + 0.50 * unmet + 0.35 * subjective_distress - 0.45 * past_refusal)
        p_outpatient_now = sigmoid(0.05 + 0.65 * unmet + 0.55 * subjective_distress - 0.30 * past_refusal)
        p_inpatient_worse = min(0.95, p_inpatient_now + 0.22 + 0.12 * subjective_distress)
        p_outpatient_worse = min(0.97, p_outpatient_now + 0.18 + 0.10 * subjective_distress)
        inpatient_now = RNG.random() < p_inpatient_now
        outpatient_now = RNG.random() < p_outpatient_now
        inpatient_worse = RNG.random() < p_inpatient_worse
        outpatient_worse = RNG.random() < p_outpatient_worse
        method_inpatient_accept = inpatient_now if response_frame == "actual_current" else inpatient_worse
        method_outpatient_accept = outpatient_now if response_frame == "actual_current" else outpatient_worse
        clozapine_accept = method_inpatient_accept or method_outpatient_accept
        vignette.append(
            {
                "participant_id": f"P{i:03d}",
                "response_frame": response_frame,
                "inpatient_now_accept": str(int(inpatient_now)),
                "outpatient_now_accept": str(int(outpatient_now)),
                "inpatient_worse_accept": str(int(inpatient_worse)),
                "outpatient_worse_accept": str(int(outpatient_worse)),
                "inpatient_asked_accept": str(int(method_inpatient_accept)),
                "outpatient_asked_accept": str(int(method_outpatient_accept)),
            }
        )

        side_effect_ratings: dict[str, int] = {}
        for key, _, _, _ in SIDE_EFFECTS:
            base = {
                "sedation": 2.8,
                "hypersalivation": 2.4,
                "weight_metabolic": 3.0,
                "constipation": 2.7,
                "infection_blood": 3.3,
                "myocarditis": 3.6,
            }[key]
            side_effect_ratings[key] = min(5, max(1, int(round(RNG.normalvariate(base + 0.35 * past_refusal, 0.9)))))
        max_side_effect_impact = max(side_effect_ratings.values())
        score = RNG.random()
        if not method_outpatient_accept:
            th = "NONE"
        elif score < 0.18 + 0.06 * unmet - 0.04 * (max_side_effect_impact >= 4):
            th = "V3"
        elif score < 0.45 + 0.08 * unmet:
            th = "V2"
        elif score < 0.84 - 0.05 * (max_side_effect_impact >= 5):
            th = "V1"
        else:
            th = "NONE"
        max_burden = dict(THRESHOLDS)[th]
        rejected_visits = {
            "V3": [],
            "V2": ["V3"],
            "V1": ["V3", "V2"],
            "NONE": ["V3", "V2", "V1"],
        }[th]
        if not method_outpatient_accept:
            rejected_visits = []
        visit_reason_values: dict[str, str] = {}
        any_safety_concern = False
        first_safety_concern_visit = None
        for visit_key, _ in THRESHOLDS[:3]:
            rejected = visit_key in rejected_visits
            visit_reason_values[f"visit_rejected_{visit_key.lower()}"] = str(int(rejected))
            selected: set[str] = set()
            reason_pattern = "not_rejected"
            if rejected:
                burden_p = {"V3": 0.72, "V2": 0.56, "V1": 0.40}[visit_key]
                safety_p = {"V3": 0.18, "V2": 0.27, "V1": 0.40}[visit_key] + 0.08 * (max_side_effect_impact >= 4)
                if RNG.random() < burden_p:
                    selected.add("visit_burden")
                if RNG.random() < safety_p:
                    selected.add("safety_concern")
                if not selected:
                    selected.add("visit_burden")
                if "safety_concern" in selected:
                    any_safety_concern = True
                    if first_safety_concern_visit is None:
                        first_safety_concern_visit = visit_key
                if {"visit_burden", "safety_concern"}.issubset(selected):
                    reason_pattern = "both"
                elif "safety_concern" in selected:
                    reason_pattern = "safety_only"
                else:
                    reason_pattern = "burden_only"
            for reason_key, _ in VISIT_REJECTION_REASONS:
                visit_reason_values[f"reason_{visit_key.lower()}_{reason_key}"] = str(int(reason_key in selected))
            visit_reason_values[f"reason_pattern_{visit_key.lower()}"] = reason_pattern

        support_answers: dict[str, str] = {key: "not_asked" for key, _ in SUPPORT_PACKAGES}
        support_refusal_reasons: dict[str, str] = {key: "not_asked" for key, _ in SUPPORT_PACKAGES}
        support_base = first_safety_concern_visit or (th if th in {"V3", "V2", "V1"} else "V1")
        support_eligible = method_outpatient_accept and first_safety_concern_visit is not None
        support_accept_any = False
        support_accept_condition = "none"
        support_final_refusal_reason = "not_asked"
        if support_eligible:
            for support_key in SUPPORT_BY_THRESHOLD[support_base]:
                accept_base = {
                    "V1N1": 0.48,
                    "V1N2": 0.54,
                    "V1N4": 0.42,
                    "V2N1": 0.44,
                    "V2N3": 0.38,
                    "V3N2": 0.34,
                }[support_key]
                accept_prob = accept_base + 0.08 * subjective_distress - 0.05 * (max_side_effect_impact >= 5)
                if RNG.random() < accept_prob:
                    support_answers[support_key] = "accepted"
                    support_accept_any = True
                    support_accept_condition = support_key
                    support_final_refusal_reason = "accepted"
                    break
                support_answers[support_key] = "refused"
                if support_key in {"V1N1", "V2N1"}:
                    reason = weighted_choice(
                        [
                            ("still_safety_concern", 0.48),
                            ("home_nursing_dislike", 0.24),
                            ("nursing_too_frequent", 0.14),
                            ("other_unknown", 0.14),
                        ]
                    )
                else:
                    reason = weighted_choice(
                        [
                            ("nursing_too_frequent", 0.40),
                            ("home_nursing_dislike", 0.24),
                            ("still_safety_concern", 0.22),
                            ("other_unknown", 0.14),
                        ]
                    )
                support_refusal_reasons[support_key] = reason
                support_final_refusal_reason = reason
                if reason != "still_safety_concern":
                    break
        threshold.append(
            {
                "participant_id": f"P{i:03d}",
                "clozapine_accept": str(int(clozapine_accept)),
                "threshold": th,
                "threshold_label": max_burden,
                "any_safety_concern_in_visit_refusal": str(int(any_safety_concern)),
                **visit_reason_values,
                "side_effect_max_impact": str(max_side_effect_impact),
                **{f"side_effect_{key}": str(value) for key, value in side_effect_ratings.items()},
                "support_eligible": str(int(support_eligible)),
                "support_base_visit": support_base if support_eligible else "not_asked",
                **{f"support_{key.lower()}": value for key, value in support_answers.items()},
                **{f"support_{key.lower()}_refusal_reason": value for key, value in support_refusal_reasons.items()},
                "support_accept_any": str(int(support_accept_any)),
                "support_accept_condition": support_accept_condition,
                "support_final_refusal_reason": support_final_refusal_reason,
            }
        )
        physician_expect = RNG.random() < (0.30 + 0.20 * unmet - 0.10 * past_refusal)
        patient_accept_outpatient = method_outpatient_accept and (th != "NONE" or support_accept_any)
        gap.append(
            {
                "participant_id": f"P{i:03d}",
                "physician_expected_outpatient_acceptance": str(int(physician_expect)),
                "patient_outpatient_acceptance": str(int(patient_accept_outpatient)),
            }
        )
        interest_prob = 0.25 + 0.36 * patient_accept_outpatient + 0.15 * subjective_distress - 0.08 * past_refusal
        r = RNG.random()
        if r < interest_prob:
            interest = "説明を聞きたい"
        elif r < interest_prob + 0.28:
            interest = "わからない"
        else:
            interest = "今は希望しない"
        safety.append({"participant_id": f"P{i:03d}", "safety_study_interest": interest})

    return {
        "participants": participants,
        "vignette_responses": vignette,
        "threshold_responses": threshold,
        "physician_patient_gap": gap,
        "safety_study_interest": safety,
    }


def weighted_choice(items: list[tuple[str, float]]) -> str:
    x = RNG.random() * sum(w for _, w in items)
    total = 0.0
    for label, weight in items:
        total += weight
        if x <= total:
            return label
    return items[-1][0]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def bar_svg(path: Path, title: str, labels: list[str], values: list[int], xlab: str = "人数") -> None:
    width, height = 820, 440
    left, top, right, bottom = 240, 58, 44, 54
    plot_w, plot_h = width - left - right, height - top - bottom
    max_v = max(values) if values else 1
    row_h = plot_h / len(labels)
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, (lab, val) in enumerate(zip(labels, values)):
        y = top + i * row_h + row_h * 0.18
        bar_w = plot_w * val / max_v
        parts.append(f'<text x="{left-12}" y="{y+row_h*0.38:.1f}" text-anchor="end" class="label">{esc(lab)}</text>')
        parts.append(f'<rect x="{left}" y="{y:.1f}" width="{bar_w:.1f}" height="{row_h*0.56:.1f}" fill="#2f7d8c"/>')
        parts.append(f'<text x="{left+bar_w+8:.1f}" y="{y+row_h*0.38:.1f}" class="num">{val}</text>')
    parts.append(f'<line x1="{left}" y1="{height-bottom}" x2="{width-right}" y2="{height-bottom}" stroke="#1f2933"/>')
    parts.append(f'<text x="{left + plot_w/2}" y="{height-16}" text-anchor="middle" class="axis">{esc(xlab)}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def stacked_svg(path: Path, title: str, rows: dict[str, Counter]) -> None:
    width, height = 900, 380
    left, top, right, bottom = 190, 68, 42, 80
    plot_w = width - left - right
    row_h = 76
    colors = {"V3": "#0f766e", "V2": "#2f7d8c", "V1": "#8bbbc3", "NONE": "#d8dee4"}
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, (group, counts) in enumerate(rows.items()):
        y = top + i * row_h
        total = sum(counts.values())
        x = left
        parts.append(f'<text x="{left-12}" y="{y+28}" text-anchor="end" class="label">{esc(group)}</text>')
        for key, label in THRESHOLDS:
            val = counts.get(key, 0)
            w = plot_w * val / total if total else 0
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="36" fill="{colors[key]}"/>')
                if w > 48:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+23}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+23}" class="num">n={total}</text>')
    lx, ly = left, height - 58
    for key, label in THRESHOLDS:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        lx += 170
        if lx > width - 180:
            lx = left
            ly += 22
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def paired_svg(path: Path, title: str, labels: list[str], inpatient: list[int], outpatient: list[int]) -> None:
    width, height = 820, 430
    left, top, right, bottom = 230, 62, 44, 60
    plot_w, plot_h = width - left - right, height - top - bottom
    max_v = max(inpatient + outpatient)
    row_h = plot_h / len(labels)
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, lab in enumerate(labels):
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+34}" text-anchor="end" class="label">{esc(lab)}</text>')
        for j, (val, color, dy, name) in enumerate([(inpatient[i], "#9aa6b2", 6, "入院"), (outpatient[i], "#2f7d8c", 34, "外来")]):
            w = plot_w * val / max_v
            parts.append(f'<rect x="{left}" y="{y+dy}" width="{w:.1f}" height="22" fill="{color}"/>')
            parts.append(f'<text x="{left+w+8:.1f}" y="{y+dy+16}" class="num">{val}</text>')
    parts.append(f'<rect x="{left}" y="{height-34}" width="14" height="14" fill="#9aa6b2"/><text x="{left+20}" y="{height-22}" class="legend">入院導入</text>')
    parts.append(f'<rect x="{left+110}" y="{height-34}" width="14" height="14" fill="#2f7d8c"/><text x="{left+130}" y="{height-22}" class="legend">外来導入</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def method_pattern_svg(path: Path, title: str, counts: Counter) -> None:
    labels = [
        ("outpatient_only", "入院は難しいが外来なら前向き"),
        ("both", "入院・外来のどちらも前向き"),
        ("inpatient_only", "入院なら前向き"),
        ("neither", "どちらも前向きに考えにくい"),
    ]
    bar_svg(path, title, [label for _, label in labels], [counts[key] for key, _ in labels], "人数")


def method_pattern_by_frame_svg(path: Path, title: str, rows: dict[str, Counter]) -> None:
    width, height = 960, 420
    left, top, right, bottom = 230, 68, 42, 96
    plot_w = width - left - right
    row_h = 86
    labels = [
        ("outpatient_only", "入院は難しいが外来なら前向き"),
        ("both", "入院・外来のどちらも前向き"),
        ("inpatient_only", "入院なら前向き"),
        ("neither", "どちらも前向きに考えにくい"),
    ]
    colors = {
        "outpatient_only": "#2f7d8c",
        "both": "#0f766e",
        "inpatient_only": "#9aa6b2",
        "neither": "#d8dee4",
    }
    row_labels = {
        "actual_current": "現在の状態で回答",
        "hypothetical_future": "将来TRS相当を想定",
    }
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, key in enumerate(["actual_current", "hypothetical_future"]):
        counts = rows.get(key, Counter())
        total = sum(counts.values())
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+27}" text-anchor="end" class="label">{esc(row_labels[key])}</text>')
        x = left
        if total == 0:
            parts.append(f'<text x="{left}" y="{y+27}" class="axis">該当者なし</text>')
            continue
        for value_key, label in labels:
            val = counts.get(value_key, 0)
            w = plot_w * val / total
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="42" fill="{colors[value_key]}"/>')
                if w > 42:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+28}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+27}" class="num">n={total}</text>')
    lx, ly = left, height - 76
    for key, label in labels:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        ly += 24
        if ly > height - 24:
            ly = height - 76
            lx += 350
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def visit_reason_by_frequency_svg(path: Path, title: str, rows: dict[str, Counter]) -> None:
    width, height = 940, 430
    left, top, right, bottom = 210, 66, 52, 86
    plot_w = width - left - right
    row_h = 72
    colors = {"burden_only": "#2f7d8c", "safety_only": "#c47f4f", "both": "#7a9a3d"}
    labels = [
        ("burden_only", "通院負担のみ"),
        ("safety_only", "安全面不安のみ"),
        ("both", "通院負担+安全面不安"),
    ]
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, (visit_key, visit_label) in enumerate([("v3", "週3回通院"), ("v2", "週2回通院"), ("v1", "週1回通院")]):
        counts = rows.get(visit_key, Counter())
        total = sum(counts.values())
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+27}" text-anchor="end" class="label">{esc(visit_label)}を拒否</text>')
        x = left
        if total == 0:
            parts.append(f'<text x="{left}" y="{y+27}" class="axis">該当者なし</text>')
            continue
        for key, label in labels:
            val = counts.get(key, 0)
            w = plot_w * val / total if total else 0
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="38" fill="{colors[key]}"/>')
                if w > 42:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+25}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+25}" class="num">n={total}</text>')
    lx, ly = left, height - 48
    for key, label in labels:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        lx += 210
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def support_acceptance_by_base_svg(path: Path, title: str, rows: dict[str, Counter]) -> None:
    width, height = 1040, 460
    left, top, right, bottom = 230, 66, 52, 118
    plot_w = width - left - right
    row_h = 72
    colors = {
        "V3N2": "#245b67",
        "V2N1": "#2f7d8c",
        "V2N3": "#5f9ea8",
        "V1N1": "#0f766e",
        "V1N2": "#8bbbc3",
        "V1N4": "#b7d5da",
        "none": "#d8dee4",
    }
    row_options = [
        ("V3", "週3回通院で安全面不安", ["V3N2", "none"]),
        ("V2", "週2回通院で安全面不安", ["V2N1", "V2N3", "none"]),
        ("V1", "週1回通院で安全面不安", ["V1N1", "V1N2", "V1N4", "none"]),
    ]
    label_map = {key: label for key, label in SUPPORT_PACKAGES}
    label_map["none"] = "受容に転じず"
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, (base, label, options) in enumerate(row_options):
        counts = rows.get(base, Counter())
        total = sum(counts.values())
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+27}" text-anchor="end" class="label">{esc(label)}</text>')
        x = left
        if total == 0:
            parts.append(f'<text x="{left}" y="{y+27}" class="axis">該当者なし</text>')
            continue
        for key in options:
            val = counts.get(key, 0)
            w = plot_w * val / total if total else 0
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="38" fill="{colors[key]}"/>')
                if w > 42:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+25}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+25}" class="num">n={total}</text>')
    lx, ly = left, height - 84
    for key in ["V3N2", "V2N1", "V2N3", "V1N1", "V1N2", "V1N4", "none"]:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label_map[key])}</text>')
        ly += 24
        if ly > height - 24:
            ly = height - 84
            lx += 330
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def matrix_svg(path: Path, title: str, both: int, physician_only: int, patient_only: int, neither: int) -> None:
    width, height = 620, 500
    left, top, cell = 150, 120, 150
    vals = [[neither, patient_only], [physician_only, both]]
    colors = [["#eef2f6", "#d4f0f4"], ["#f0e7d8", "#2f7d8c"]]
    parts = [svg_head(width, height), f'<text x="{left}" y="38" class="title">{esc(title)}</text>']
    parts.append(f'<text x="{left+cell}" y="82" text-anchor="middle" class="axis">患者本人: 外来非受容/保留</text>')
    parts.append(f'<text x="{left+cell*2}" y="82" text-anchor="middle" class="axis">患者本人: 外来受容</text>')
    parts.append(f'<text x="40" y="{top+cell*0.5}" class="axis">医師予測: 非受容</text>')
    parts.append(f'<text x="40" y="{top+cell*1.5}" class="axis">医師予測: 受容</text>')
    for r in range(2):
        for c in range(2):
            x, y = left + c * cell, top + r * cell
            parts.append(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" fill="{colors[r][c]}" stroke="#ffffff" stroke-width="3"/>')
            parts.append(f'<text x="{x+cell/2}" y="{y+cell/2+8}" text-anchor="middle" class="big">{vals[r][c]}</text>')
    parts.append(f'<text x="{left}" y="{height-38}" class="note">右上: 医師は非受容と予測したが、患者本人は外来導入を受け入れる層。</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def stacked_category_svg(path: Path, title: str, counts: Counter, labels: list[tuple[str, str]]) -> None:
    width, height = 980, 430
    left, top, right, bottom = 70, 70, 50, 96
    plot_w = width - left - right
    total = sum(counts.values()) or 1
    colors = ["#004d40", "#00695c", "#0f766e", "#2f7d8c", "#5f9ea8", "#8bbbc3", "#b7d5da", "#d7e8eb", "#d8dee4"]
    parts = [svg_head(width, height), f'<text x="{left}" y="32" class="title">{esc(title)}</text>']
    x = left
    for i, (key, label) in enumerate(labels):
        val = counts.get(key, 0)
        w = plot_w * val / total
        if w:
            parts.append(f'<rect x="{x:.1f}" y="{top}" width="{w:.1f}" height="64" fill="{colors[i % len(colors)]}"/>')
            if w > 42:
                parts.append(f'<text x="{x+w/2:.1f}" y="{top+38}" text-anchor="middle" class="inside">{val}</text>')
        x += w
    lx, ly = left, top + 100
    for i, (key, label) in enumerate(labels):
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[i % len(colors)]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        ly += 24
        if ly > height - 42:
            ly = top + 100
            lx += 330
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def mean_bar_svg(path: Path, title: str, labels: list[str], means: list[float], xlab: str = "平均スコア") -> None:
    width, height = 900, 460
    left, top, right, bottom = 260, 58, 58, 56
    plot_w, plot_h = width - left - right, height - top - bottom
    row_h = plot_h / len(labels)
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for tick in range(1, 6):
        x = left + plot_w * (tick - 1) / 4
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{height-bottom}" stroke="#eef2f6"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-bottom+20}" text-anchor="middle" class="axis">{tick}</text>')
    for i, (lab, mean) in enumerate(zip(labels, means)):
        y = top + i * row_h + row_h * 0.22
        w = plot_w * (mean - 1) / 4
        parts.append(f'<text x="{left-12}" y="{y+row_h*0.32:.1f}" text-anchor="end" class="label">{esc(lab)}</text>')
        parts.append(f'<rect x="{left}" y="{y:.1f}" width="{w:.1f}" height="{row_h*0.46:.1f}" fill="#2f7d8c"/>')
        parts.append(f'<text x="{left+w+8:.1f}" y="{y+row_h*0.32:.1f}" class="num">{mean:.1f}</text>')
    parts.append(f'<text x="{left+plot_w/2}" y="{height-12}" text-anchor="middle" class="axis">{esc(xlab)}（1=妨げにならない、5=服用を考えられないほど妨げる）</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def support_direction_svg(path: Path, title: str, rows: dict[str, Counter]) -> None:
    width, height = 980, 560
    left, top, right, bottom = 250, 62, 40, 92
    plot_w = width - left - right
    row_h = 42
    colors = {"positive": "#2f7d8c", "neutral": "#b7d5da", "negative": "#c47f4f", "unsure": "#d8dee4"}
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, (key, label) in enumerate(SUPPORT_PACKAGES):
        counts = rows.get(key, Counter())
        total = sum(counts.values())
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+24}" text-anchor="end" class="label">{esc(label)}</text>')
        x = left
        if total == 0:
            parts.append(f'<text x="{left}" y="{y+24}" class="axis">該当者なし</text>')
            continue
        for direction, direction_label in SUPPORT_DIRECTIONS:
            val = counts.get(direction, 0)
            w = plot_w * val / total
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y+5}" width="{w:.1f}" height="26" fill="{colors[direction]}"/>')
                if w > 38:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+23}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+24}" class="num">n={total}</text>')
    lx, ly = left, height - 58
    for direction, direction_label in SUPPORT_DIRECTIONS:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[direction]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(direction_label)}</text>')
        lx += 180
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def svg_head(width: int, height: int) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">
<style>
.title{{font:700 19px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#1f2933}}
.label{{font:600 14px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#24323d}}
.num{{font:600 13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#24323d}}
.axis,.legend,.note{{font:12px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#52616b}}
.inside{{font:700 13px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:white}}
.big{{font:700 34px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;fill:#1f2933}}
</style>
<rect width="100%" height="100%" fill="white"/>'''


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def make_figures(version: int, data: dict[str, list[dict[str, str]]]) -> dict[str, str]:
    fig_paths: dict[str, str] = {}
    participants = {r["participant_id"]: r for r in data["participants"]}
    vignette = data["vignette_responses"]
    threshold = data["threshold_responses"]
    gap = data["physician_patient_gap"]

    method_counts_by_frame: dict[str, Counter] = {"actual_current": Counter(), "hypothetical_future": Counter()}
    for r in vignette:
        inpatient = r["inpatient_asked_accept"] == "1"
        outpatient = r["outpatient_asked_accept"] == "1"
        if inpatient and outpatient:
            key = "both"
        elif inpatient:
            key = "inpatient_only"
        elif outpatient:
            key = "outpatient_only"
        else:
            key = "neither"
        method_counts_by_frame[r["response_frame"]][key] += 1
    p = FIG / f"bhtm_v{version}_fig1_clozapine_accept.svg"
    method_pattern_by_frame_svg(p, "図1. 回答前提別にみた入院導入・外来導入の受容パターン", method_counts_by_frame)
    fig_paths["fig1"] = rel(p)

    inpatient_accept_ids = {r["participant_id"] for r in vignette if r["inpatient_asked_accept"] == "1"}
    inpatient_decline_ids = {r["participant_id"] for r in vignette if r["inpatient_asked_accept"] == "0"}
    group_counts: dict[str, Counter] = {
        "入院導入を前向きに考える": Counter(r["threshold"] for r in threshold if r["participant_id"] in inpatient_accept_ids),
        "入院導入を前向きに考えにくい": Counter(r["threshold"] for r in threshold if r["participant_id"] in inpatient_decline_ids),
    }
    p = FIG / f"bhtm_v{version}_fig2_threshold.svg"
    stacked_svg(p, "図2. 入院導入受容性別にみた外来通院頻度threshold", group_counts)
    fig_paths["fig2"] = rel(p)

    reason_rows: dict[str, Counter] = {"v3": Counter(), "v2": Counter(), "v1": Counter()}
    for r in threshold:
        for visit in ["v3", "v2", "v1"]:
            if r.get(f"visit_rejected_{visit}") == "1":
                reason_rows[visit][r.get(f"reason_pattern_{visit}")] += 1
    p = FIG / f"bhtm_v{version}_fig3_threshold_by_group.svg"
    visit_reason_by_frequency_svg(p, "図3. 通院頻度別にみた拒否理由", reason_rows)
    fig_paths["fig3"] = rel(p)

    support_eligible_rows = [r for r in threshold if r["support_eligible"] == "1"]
    support_by_base: dict[str, Counter] = {"V3": Counter(), "V2": Counter(), "V1": Counter()}
    for r in support_eligible_rows:
        base = r["support_base_visit"]
        condition = r["support_accept_condition"] if r["support_accept_any"] == "1" else "none"
        support_by_base[base][condition] += 1
    p = FIG / f"bhtm_v{version}_fig4_support_acceptance.svg"
    support_acceptance_by_base_svg(p, "図4. 安全面不安を含む拒否者での訪問看護追加後の受容", support_by_base)
    fig_paths["fig4"] = rel(p)

    support_refusal_counts = Counter(
        r["support_final_refusal_reason"]
        for r in support_eligible_rows
        if r["support_accept_any"] == "0" and r["support_final_refusal_reason"] != "not_asked"
    )
    p = FIG / f"bhtm_v{version}_fig5_support_refusal_reason.svg"
    bar_svg(
        p,
        "図5. 訪問看護追加でも受容に転じない理由",
        [label for _, label in SUPPORT_REFUSAL_REASONS],
        [support_refusal_counts[key] for key, _ in SUPPORT_REFUSAL_REASONS],
        "人数",
    )
    fig_paths["fig5"] = rel(p)

    effect_labels = [f"{label}（{frequency}）" for _, label, frequency, _ in SIDE_EFFECTS]
    effect_means = [
        sum(int(r[f"side_effect_{key}"]) for r in threshold) / len(threshold)
        for key, _, _, _ in SIDE_EFFECTS
    ]
    p = FIG / f"bhtm_v{version}_fig6_side_effects.svg"
    mean_bar_svg(p, "図6. 副作用別にみた服用判断への影響", effect_labels, effect_means)
    fig_paths["fig6"] = rel(p)

    both = physician_only = patient_only = neither = 0
    for r in gap:
        physician = r["physician_expected_outpatient_acceptance"] == "1"
        patient = r["patient_outpatient_acceptance"] == "1"
        if physician and patient:
            both += 1
        elif physician and not patient:
            physician_only += 1
        elif not physician and patient:
            patient_only += 1
        else:
            neither += 1
    p = FIG / f"bhtm_v{version}_fig7_gap.svg"
    matrix_svg(p, "図7. 医師予測と患者本人の外来受容性", both, physician_only, patient_only, neither)
    fig_paths["fig7"] = rel(p)
    return fig_paths


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def write_version_data(version: int, data: dict[str, list[dict[str, str]]]) -> None:
    out = DATA / f"v{version}"
    for name, rows in data.items():
        write_csv(out / f"{name}.csv", rows)


def table_html(data: dict[str, list[dict[str, str]]]) -> str:
    participants = data["participants"]
    n = len(participants)
    target = Counter(r["target_group"] for r in participants)
    unmet = Counter(r["current_unmet_need"] for r in participants)
    distress = Counter(r["subjective_distress"] for r in participants)
    frame = Counter(r["response_frame"] for r in participants)
    mgaf_le40 = sum(1 for r in participants if int(r["clinician_mgaf_function"]) <= 40)
    rows = [
        ("解析対象者", f"{n}"),
        ("TRS適格候補", f"{target['TRS適格候補']} ({target['TRS適格候補']/n*100:.1f}%)"),
        ("広い未使用外来患者", f"{target['広い未使用外来患者']} ({target['広い未使用外来患者']/n*100:.1f}%)"),
        ("臨床家評価mGAF-F 40以下", f"{mgaf_le40} ({mgaf_le40/n*100:.1f}%)"),
        ("現在の状態で回答", f"{frame['actual_current']} ({frame['actual_current']/n*100:.1f}%)"),
        ("将来TRS相当を想定して回答", f"{frame['hypothetical_future']} ({frame['hypothetical_future']/n*100:.1f}%)"),
        ("現在の治療で残る困りごとあり", f"{unmet['あり']} ({unmet['あり']/n*100:.1f}%)"),
        ("主観的困りごと/つらさあり", f"{distress['あり']} ({distress['あり']/n*100:.1f}%)"),
    ]
    return "<table><tr><th>項目</th><th>値</th></tr>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>"


def figure_mock_html(version: int, data: dict[str, list[dict[str, str]]], figs: dict[str, str]) -> str:
    v = VERSIONS[version]
    visible = ["fig1", "fig2", "fig3", "fig4", "fig5", "fig6", "fig7"]
    reasons = {
        "fig1": "回答前提別に、入院導入と外来導入の受容性を比較する中核図。mGAF-F 40以下の実意思決定に近い群と、将来TRS相当となった場合を想定する群を分けることで、企画倒れを避けつつ解釈可能性を保つ。Gee 2017やJakobsen 2025で入院導入が大きな障壁として示されたことを踏まえ、“入院は難しいが外来なら前向き”という潜在ニーズを可視化する。",
        "fig2": "入院導入を前向きに考える人と考えにくい人に分け、外来導入の通院頻度thresholdを示す中核図。入院導入を受け入れうる人でも外来週3回は難しい、あるいは入院導入は難しい人でも外来なら受容に転じる、といった現実的な選好のずれを示す。",
        "fig3": "通院のみ条件を拒否した理由を、週3回・週2回・週1回の各通院頻度ごとに示す図。同じ“拒否”でも、頻度が高いと通院負担が中心なのか、頻度が下がると安全面不安が相対的に増えるのかを確認する。",
        "fig4": "各通院頻度で安全面不安を含む回答をした人に限定し、同じ通院頻度のまま訪問看護を何回上乗せすると受容へ転じるかを示す図。外来導入レジメン改善に直結する実装可能な情報として位置づける。",
        "fig5": "訪問看護を追加しても受容に転じない理由を示す図。訪問看護そのものへの抵抗、回数過多、なお残る安全面不安を分けることで、外来導入レジメン改善の方向を整理する。",
        "fig6": "副作用は単一項目にまとめると解釈しにくいため、眠気、流涎、体重増加、便秘、採血異常・感染リスク、心筋炎などに分けて、服用判断をどの程度妨げるかを測定する。",
        "fig7": "患者調査を臨床家調査と接続する図。Jakobsen 2025の示唆に沿い、医師が非受容と想定する患者の中にも外来導入なら受け入れる層がいるかを示す。",
    }
    links = """
      <a href="../BHTM_threshold_technique_design_note.html">BHTM設計ノート</a>
      <a href="../Hauber_Coulter_2020_threshold_technique_literature_note.html">Hauber & Coulter 2020</a>
      <a href="../Parikh_2023_HCC_threshold_technique_literature_note.html">Parikh 2023</a>
      <a href="../Barrett_2005_benefit_harm_tradeoff_literature_note.html">Barrett 2005</a>
      <a href="../ResearchNote_2018_smallest_worthwhile_effect_literature_note.html">Research Note 2018</a>
    """
    fig_sections = "\n".join(
        f"""<section class="figure-card">
          <img src="{figs[key]}" alt="{key}">
          <p class="reason">{reasons[key]}</p>
        </section>"""
        for key in visible
    )
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>患者調査BHTM 図表モック {version}</title>
  <style>{common_css()}</style>
</head>
<body>
  <header>
    <h1>患者調査BHTM 図表モック {version}</h1>
    <p>{v['label']}</p>
  </header>
  <main>
    <nav class="links">{links}<a href="patient_survey_bhtm_v{version}_questionnaire.html">質問票を見る</a><a href="index.html">一覧へ</a></nav>
    <section>
      <h2>この版の考え方</h2>
      <p>{v['focus']}</p>
      <ul>{''.join(f'<li>{x}</li>' for x in v['improvements'])}</ul>
    </section>
    <section>
      <h2>Table 1. 回答者背景</h2>
      {table_html(data)}
      <p class="reason">患者本人の受容性を解釈するため、対象集団、現在の困りごと、主観的つらさを最小限の背景情報として置く。</p>
    </section>
    {fig_sections}
  </main>
</body>
</html>"""


def questionnaire_html(version: int) -> str:
    v = VERSIONS[version]
    compact = version >= 4
    final = version == 5
    return f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>患者調査BHTM 質問票 {version}</title>
  <style>{questionnaire_css()}</style>
</head>
<body>
  <div id="app">
    <header class="app-head">
      <div>
        <p class="eyebrow">患者調査BHTM インタラクティブ質問票 {version}</p>
        <h1>{v['label']}</h1>
      </div>
      <div class="progress"><span id="stepNow">1</span>/<span id="stepTotal">9</span></div>
    </header>

    <main class="phone-frame">
      <section class="step active" data-step="0">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>この調査について</h2>
        <p>この画面はダミーです。回答は保存されません。クロザピンを外来で始める方法について、どの条件なら前向きに考えられるかを伺います。</p>
        <button class="primary full" onclick="next()">次へ</button>
      </section>

      <section class="step" data-step="1">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>クロザピンについて</h2>
        <p>クロザピンは、複数の抗精神病薬で十分に良くならない統合失調症に使われる薬です。症状や生活のしづらさが改善する可能性があります。</p>
        <p>一方で、血液検査や体調確認が必要です。発熱、胸痛、息切れ、強い便秘などがあれば早めに相談し、必要に応じて入院に切り替えます。</p>
        <div class="nav"><button class="primary" onclick="next()">理解しました</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="2">
        <h2>参加者コード</h2>
        <p>研究スタッフから渡された参加者コードを入力してください。入力されたコードに基づいて、回答していただく前提をシステム側で設定します。</p>
        <label class="field-label" for="participantCode">参加者コード</label>
        <input class="text-input" id="participantCode" name="participant_code" type="text" inputmode="latin" autocomplete="off" placeholder="例: ACT001">
        <div id="scenarioBox" class="notice hidden"></div>
        <p class="small">デモ用コード: <code>ACT001</code> は現在の状態で回答、<code>HYP001</code> は将来TRS相当を想定して回答します。本番では対応表を調査システム側で管理します。</p>
        <div class="nav"><button class="primary" onclick="nextParticipantCode()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="3">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>クロザピン服用について</h2>
        <p class="scenarioText"></p>
        <p>主治医からクロザピンを勧められたとします。</p>
        <p class="question">クロザピン服用を前向きに考えたいですか？</p>
        {yes_no_choices("clozapine_accept")}
        <p class="small">選択すると次へ進みます。</p>
        <div class="nav"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="4">
        <img class="hero" src="{ASSET_PREFIX}/inpatient_start.png" alt="">
        <h2>入院して始める場合</h2>
        <p class="scenarioText"></p>
        <p>主治医から、入院してクロザピンを始める方法を勧められたとします。入院中に薬の調整、採血、体調確認を行います。</p>
        <p class="small">入院期間は施設や状態により異なりますが、ここでは数週間程度の予定入院を想定してください。</p>
        <p class="question">この方法ならクロザピン服用を前向きに考えたいですか？</p>
        {yes_no_choices("inpatient_accept")}
        <p class="small">選択すると次へ進みます。</p>
        <div class="nav"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="5">
        <img class="hero" src="{ASSET_PREFIX}/outpatient_visit.png" alt="">
        <h2>外来で始める場合</h2>
        <p class="scenarioText"></p>
        <p>前の質問で伺った入院して始める方法とは別に、外来で始める方法について伺います。</p>
        <p>主治医から、入院せず外来でクロザピンを始める方法を勧められたとします。通院、採血、体調確認を続けながら開始します。</p>
        <p class="small">体調に異常があれば、必要時は入院へ切り替えます。</p>
        <p class="question">この方法ならクロザピン服用を前向きに考えたいですか？</p>
        {yes_no_choices("outpatient_accept")}
        <p class="small">選択すると次へ進みます。</p>
        <div class="nav"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="6">
        <img class="hero" src="{ASSET_PREFIX}/monitoring.png" alt="">
        <h2>通院だけで始める場合</h2>
        <p class="scenarioText"></p>
        <p>入院せず外来でクロザピンを始める場合、最初6週間の通院頻度について、負担が大きい条件から順に伺います。</p>
        <div class="tt-card">
          <span class="pill" id="visitProgress">1/3</span>
          <h3 id="visitQuestion">最初6週間は週3回通院</h3>
          <p class="small">この条件でクロザピン服用を前向きに考えたいですか？</p>
        </div>
        <p class="small">7週目以降も定期通院と採血は続きます。体調に異常があれば、必要時は入院へ切り替えます。</p>
        <div class="nav"><button class="primary" onclick="answerVisit(true)">はい</button><button onclick="answerVisit(false)">いいえ</button><button onclick="prevVisit()">前へ</button></div>
      </section>

      <section class="step" data-step="7">
        <h2>前向きに考えにくい理由</h2>
        <p><strong id="rejectionVisitLabel">この通院頻度</strong>を前向きに考えにくい理由を選んでください。</p>
        <label class="choice"><input type="checkbox" name="visit_rejection_reason" value="visit_burden"> 通院回数・移動の負担が大きい</label>
        <label class="choice"><input type="checkbox" name="visit_rejection_reason" value="safety_concern"> この通院回数だけでは安全面が不安</label>
        <div class="nav"><button class="primary" onclick="saveVisitReason()">次へ</button><button onclick="current=6; renderStep()">前へ</button></div>
      </section>

      <section class="step" data-step="8">
        <img class="hero" src="{ASSET_PREFIX}/outpatient_visit.png" alt="">
        <h2>訪問看護を加える場合</h2>
        <p>通院だけでは安全面が不安な場合に、同じ通院頻度のまま訪問看護を加える条件を伺います。</p>
        <div class="tt-card">
          <span class="pill" id="supportProgress">1/3</span>
          <h3 id="supportQuestion">週5回確認</h3>
          <p class="small" id="supportDescription"></p>
        </div>
        <p class="question">この条件ならクロザピン服用を前向きに考えたいですか？</p>
        <div class="nav"><button class="primary" onclick="answerSupport(true)">はい</button><button onclick="answerSupport(false)">いいえ</button><button onclick="prevSupport()">前へ</button></div>
      </section>

      <section class="step" data-step="9">
        <h2>訪問看護を加えても前向きに考えにくい理由</h2>
        <p><strong id="supportReasonLabel">この条件</strong>を前向きに考えにくい理由を選んでください。</p>
        <label class="choice"><input type="radio" name="support_refusal_reason" value="home_nursing_dislike"> 訪問看護が入ること自体が嫌</label>
        <label class="choice"><input type="radio" name="support_refusal_reason" value="nursing_too_frequent"> 訪問看護の回数が多すぎる</label>
        <label class="choice"><input type="radio" name="support_refusal_reason" value="still_safety_concern"> それでも安全面が不安</label>
        <label class="choice"><input type="radio" name="support_refusal_reason" value="other_unknown"> その他・わからない</label>
        <p class="small">選択すると次へ進みます。安全面が不安な場合は、より手厚い条件を続けて確認します。</p>
        <div class="nav"><button onclick="prevSupportReason()">前へ</button></div>
      </section>

      <section class="step" data-step="10">
        <h2>副作用可能性の影響</h2>
        <p>以下の副作用の可能性は、クロザピン服用を前向きに考えるうえで、どの程度妨げになりますか？</p>
        <div class="tt-card">
          <span class="pill" id="sideEffectProgress">1/6</span>
          <h3 id="sideEffectLabel">眠気・だるさ</h3>
          <p class="small"><strong id="sideEffectFrequency">比較的よくみられる</strong></p>
          <p class="small" id="sideEffectDescription">日中の眠気や活動しづらさにつながることがあります。</p>
        </div>
        <div class="seg">
          <label><input type="radio" name="side_effect_current" value="1"> 1. まったく妨げにならない</label>
          <label><input type="radio" name="side_effect_current" value="2"> 2. あまり妨げにならない</label>
          <label><input type="radio" name="side_effect_current" value="3"> 3. やや妨げになる</label>
          <label><input type="radio" name="side_effect_current" value="4"> 4. かなり妨げになる</label>
          <label><input type="radio" name="side_effect_current" value="5"> 5. 服用を考えられないほど妨げになる</label>
        </div>
        <p class="small">選択すると次へ進みます。</p>
        <div class="nav"><button onclick="prevSideEffect()">前へ</button></div>
      </section>

      <section class="step" data-step="11">
        <h2>回答ありがとうございました</h2>
        <p>ダミー質問票の確認はここまでです。実際の調査では、この回答内容を保存して解析します。</p>
        <div class="summary">
          <strong>入院導入:</strong> <span id="inpatientSummary">未回答</span><br>
          <strong>外来導入:</strong> <span id="outpatientSummary">未回答</span><br>
          <strong>通院頻度threshold:</strong> <span id="thresholdSummary">未回答</span><br>
          <strong>訪問看護追加:</strong> <span id="supportSummary">該当なし/未回答</span>
        </div>
        <div class="nav"><button class="primary" onclick="finish()">完了</button><button onclick="prev()">前へ</button></div>
      </section>
    </main>
  </div>

  <script>{questionnaire_js(final=final, compact=compact)}</script>
</body>
</html>"""


def acceptance_choices(name: str) -> str:
    return f"""
        <div class="seg">
          <label><input type="radio" name="{name}" value="accept"> 受け入れられる</label>
          <label><input type="radio" name="{name}" value="consider"> 前向きに考える</label>
          <label><input type="radio" name="{name}" value="unsure"> わからない</label>
          <label><input type="radio" name="{name}" value="reject"> 難しい</label>
        </div>"""


def yes_no_choices(name: str) -> str:
    return f"""
        <div class="seg two">
          <label><input type="radio" name="{name}" value="yes"> はい</label>
          <label><input type="radio" name="{name}" value="no"> いいえ</label>
        </div>"""


def questionnaire_js(final: bool, compact: bool) -> str:
    return r"""
const steps = Array.from(document.querySelectorAll('.step'));
let current = 0;
let threshold = null;
let visitIndex = 0;
let sideEffectIndex = 0;
let supportIndex = 0;
let responseFrame = null;
let reasonSource = null;
let currentRejectedVisit = null;
let supportBaseVisit = null;
let inpatientAccept = null;
let outpatientAccept = null;
let participantCode = null;
const participantCodeMap = {
  ACT001: {frame:'actual_current', label:'現在の状態で回答'},
  ACT002: {frame:'actual_current', label:'現在の状態で回答'},
  HYP001: {frame:'hypothetical_future', label:'将来TRS相当を想定して回答'},
  HYP002: {frame:'hypothetical_future', label:'将来TRS相当を想定して回答'}
};
const sideEffects = [
  ['sedation','眠気・だるさ','比較的よくみられる','日中の眠気や活動しづらさにつながることがあります。'],
  ['hypersalivation','よだれ・流涎','比較的よくみられる','唾液が増え、夜間や会話中に困ることがあります。'],
  ['weight_metabolic','体重増加・代謝異常','比較的よくみられる','体重、血糖、脂質などを定期的に確認します。'],
  ['constipation','便秘','比較的よくみられる・重くなることがある','早めに対処しないと重くなることがあります。'],
  ['infection_blood','白血球減少・感染リスク','まれだが重要','早く見つけるため、定期的な採血を行います。'],
  ['myocarditis','心筋炎など重い副作用','まれだが重要','発熱、胸痛、息切れなどがあれば早めに相談します。']
];
const sideEffectAnswers = {};
const visitQuestions = [
  ['V3','最初6週間は週3回通院'],
  ['V2','最初6週間は週2回通院'],
  ['V1','最初6週間は週1回通院']
];
const supportByThreshold = {
  V3: ['V3N2'],
  V2: ['V2N1','V2N3'],
  V1: ['V1N1','V1N2','V1N4'],
  NONE: ['V1N1','V1N2','V1N4']
};
const supportLabels = {
  V3N2:'週5回確認: 週3回通院+週2回訪問看護',
  V2N3:'週5回確認: 週2回通院+週3回訪問看護',
  V1N4:'週5回確認: 週1回通院+週4回訪問看護',
  V2N1:'週3回確認: 週2回通院+週1回訪問看護',
  V1N2:'週3回確認: 週1回通院+週2回訪問看護',
  V1N1:'週2回確認: 週1回通院+週1回訪問看護'
};
const supportRefusalLabels = {
  home_nursing_dislike:'訪問看護が入ること自体が嫌',
  nursing_too_frequent:'訪問看護の回数が多すぎる',
  still_safety_concern:'それでも安全面が不安',
  other_unknown:'その他・わからない'
};
const supportAnswers = {};
const supportRefusalReasons = {};
const visitRejectionReasons = {};
function renderStep(){
  steps.forEach((s,i)=>s.classList.toggle('active', i===current));
  document.getElementById('stepNow').textContent = String(current+1);
  document.getElementById('stepTotal').textContent = String(steps.length);
  document.querySelectorAll('.scenarioText').forEach(el => el.textContent = scenarioText());
  if(current === 6) renderVisitQuestion();
  if(current === 7) renderVisitReason();
  if(current === 8) renderSupportQuestion();
  if(current === 9) renderSupportReason();
  if(current === 10) renderSideEffectQuestion();
  window.scrollTo({top:0, behavior:'smooth'});
}
function wireAutoAdvance(){
  document.getElementById('participantCode')?.addEventListener('keydown', event => {
    if(event.key === 'Enter'){
      event.preventDefault();
      nextParticipantCode();
    }
  });
  document.querySelectorAll('input[name="clozapine_accept"]').forEach(input => input.addEventListener('change', nextClozapine));
  document.querySelectorAll('input[name="inpatient_accept"]').forEach(input => input.addEventListener('change', nextInpatient));
  document.querySelectorAll('input[name="outpatient_accept"]').forEach(input => input.addEventListener('change', nextOutpatient));
  document.querySelectorAll('input[name="side_effect_current"]').forEach(input => input.addEventListener('change', nextSideEffect));
  document.querySelectorAll('input[name="support_refusal_reason"]').forEach(input => input.addEventListener('change', saveSupportReason));
}
function next(){ if(current < steps.length-1){ current++; renderStep(); } }
function prev(){
  if(current === 11){ current = 10; renderStep(); return; }
  if(current === 10 && threshold === 'NO_CLOZAPINE'){ current = 3; renderStep(); return; }
  if(current === 10 && threshold === 'NO_OUTPATIENT'){ current = 5; renderStep(); return; }
  if(current === 10 && supportWasAsked()){ current = 8; renderStep(); return; }
  if(current === 10 && !supportWasAsked()){ current = 6; renderStep(); return; }
  if(current === 8){ current = 7; renderStep(); return; }
  if(current === 7){ current = 6; renderStep(); return; }
  if(current > 0){
    const target = current - 1;
    if(target === 2){
      responseFrame = null;
      participantCode = null;
      document.getElementById('participantCode').value = '';
      const box = document.getElementById('scenarioBox');
      box.textContent = '';
      box.classList.add('hidden');
      resetAfterNeed();
    } else if(target === 3){
      clearChecked('clozapine_accept');
      resetAfterClozapine();
    } else if(target === 4){
      clearChecked('inpatient_accept');
      inpatientAccept = null;
      document.getElementById('inpatientSummary').textContent = '未回答';
      resetAfterInpatient();
    } else if(target === 5){
      clearChecked('outpatient_accept');
      outpatientAccept = null;
      document.getElementById('outpatientSummary').textContent = '未回答';
      resetAfterOutpatient();
    }
    current = target;
    renderStep();
  }
}
function nextParticipantCode(){
  const input = document.getElementById('participantCode');
  const raw = input.value.trim().toUpperCase();
  const box = document.getElementById('scenarioBox');
  const match = participantCodeMap[raw];
  if(!match){
    box.textContent = '参加者コードを確認できませんでした。研究スタッフから渡されたコードを入力してください。';
    box.classList.remove('hidden');
    input.focus();
    return;
  }
  resetAfterNeed();
  participantCode = raw;
  responseFrame = match.frame;
  box.textContent = `${match.label}: ${scenarioText()}`;
  box.classList.remove('hidden');
  next();
}
function renderSideEffectQuestion(){
  const [key, label, frequency, description] = sideEffects[sideEffectIndex];
  document.getElementById('sideEffectProgress').textContent = `${sideEffectIndex + 1}/${sideEffects.length}`;
  document.getElementById('sideEffectLabel').textContent = label;
  document.getElementById('sideEffectFrequency').textContent = frequency;
  document.getElementById('sideEffectDescription').textContent = description;
  document.querySelectorAll('input[name="side_effect_current"]').forEach(input => {
    input.checked = sideEffectAnswers[key] === input.value;
  });
}
function nextSideEffect(){
  const val = document.querySelector('input[name="side_effect_current"]:checked')?.value;
  if(!val){ alert('1つ選んでください。'); return; }
  const [key] = sideEffects[sideEffectIndex];
  sideEffectAnswers[key] = val;
  if(sideEffectIndex < sideEffects.length - 1){
    sideEffectIndex++;
    document.querySelectorAll('input[name="side_effect_current"]').forEach(input => input.checked = false);
    renderSideEffectQuestion();
    return;
  }
  current = 11; renderStep();
}
function prevSideEffect(){
  if(sideEffectIndex > 0){
    sideEffectIndex--;
    renderSideEffectQuestion();
    return;
  }
  if(threshold === 'NO_CLOZAPINE') current = 3;
  else if(threshold === 'NO_OUTPATIENT') current = 5;
  else if(supportWasAsked()) current = 8;
  else current = 6;
  renderStep();
}
function nextClozapine(){
  const val = document.querySelector('input[name="clozapine_accept"]:checked')?.value;
  if(!val){ alert('はい、または、いいえを選んでください。'); return; }
  resetAfterClozapine();
  if(val === 'no'){
    reasonSource = 'clozapine_no';
    threshold = 'NO_CLOZAPINE';
    document.getElementById('thresholdSummary').textContent = 'クロザピン服用自体を前向きに考えにくい';
    current = 10; renderStep(); return;
  }
  next();
}
function nextInpatient(){
  const val = document.querySelector('input[name="inpatient_accept"]:checked')?.value;
  if(!val){ alert('はい、または、いいえを選んでください。'); return; }
  resetAfterInpatient();
  inpatientAccept = val === 'yes';
  document.getElementById('inpatientSummary').textContent = inpatientAccept ? '前向きに考えたい' : '前向きに考えにくい';
  next();
}
function nextOutpatient(){
  const val = document.querySelector('input[name="outpatient_accept"]:checked')?.value;
  if(!val){ alert('はい、または、いいえを選んでください。'); return; }
  resetAfterOutpatient();
  outpatientAccept = val === 'yes';
  document.getElementById('outpatientSummary').textContent = outpatientAccept ? '前向きに考えたい' : '前向きに考えにくい';
  if(!outpatientAccept){
    threshold = 'NO_OUTPATIENT';
    document.getElementById('thresholdSummary').textContent = '外来導入を前向きに考えにくい';
    current = 10;
    renderStep();
    return;
  }
  next();
}
function renderVisitQuestion(){
  const [key, label] = visitQuestions[visitIndex];
  document.getElementById('visitProgress').textContent = `${visitIndex + 1}/${visitQuestions.length}`;
  document.getElementById('visitQuestion').textContent = label;
}
function answerVisit(accepted){
  resetAfterVisit();
  if(accepted){
    threshold = visitQuestions[visitIndex][0];
    setThresholdSummary();
    supportIndex = 0;
    afterVisitSequence();
    return;
  }
  currentRejectedVisit = visitQuestions[visitIndex][0];
  current = 7; renderStep();
}
function prevVisit(){
  if(visitIndex > 0){
    visitIndex--;
    renderVisitQuestion();
    return;
  }
  prev();
}
function setThresholdSummary(){
  const labels = {V1:'週1回通院なら受容', V2:'週2回通院なら受容', V3:'週3回通院なら受容', NONE:'通院のみ条件は非受容/保留'};
  document.getElementById('thresholdSummary').textContent = labels[threshold];
}
function renderVisitReason(){
  const label = visitQuestions.find(v => v[0] === currentRejectedVisit)?.[1] || 'この通院頻度';
  document.getElementById('rejectionVisitLabel').textContent = label;
  document.querySelectorAll('input[name="visit_rejection_reason"]').forEach(input => {
    input.checked = (visitRejectionReasons[currentRejectedVisit] || []).includes(input.value);
  });
}
function saveVisitReason(){
  const reasons = Array.from(document.querySelectorAll('input[name="visit_rejection_reason"]:checked')).map(input => input.value);
  if(reasons.length === 0){ alert('あてはまる理由を1つ以上選んでください。'); return; }
  resetAfterVisitReason();
  visitRejectionReasons[currentRejectedVisit] = reasons;
  if(reasons.includes('safety_concern')){
    supportBaseVisit = currentRejectedVisit;
    current = 8; renderStep();
    return;
  }
  if(visitIndex < visitQuestions.length - 1){
    visitIndex++;
    current = 6; renderStep();
    return;
  }
  threshold = 'NONE';
  setThresholdSummary();
  afterVisitSequence();
}
function safetyConcernRecorded(){
  return Object.values(visitRejectionReasons).some(reasons => reasons.includes('safety_concern'));
}
function supportWasAsked(){
  return Object.keys(supportAnswers).length > 0 || Object.keys(supportRefusalReasons).length > 0;
}
function afterVisitSequence(){
  supportIndex = 0;
  if(safetyConcernRecorded()){
    supportBaseVisit = Object.keys(visitRejectionReasons).find(key => visitRejectionReasons[key].includes('safety_concern')) || threshold;
    current = 8;
    renderStep();
    return;
  }
  current = 10;
  renderStep();
}
function renderSupportQuestion(){
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  const key = options[supportIndex];
  document.getElementById('supportProgress').textContent = `${supportIndex + 1}/${options.length}`;
  document.getElementById('supportQuestion').textContent = supportLabels[key];
  document.getElementById('supportDescription').textContent = '通院だけでは安全面が不安な場合、この条件なら前向きに考えられるかを伺います。';
}
function answerSupport(accepted){
  resetAfterSupport();
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  const key = options[supportIndex];
  supportAnswers[key] = accepted ? 'accepted' : 'refused';
  if(accepted){
    document.getElementById('supportSummary').textContent = `${supportLabels[key]}なら前向きに考えたい`;
    current = 10; renderStep(); return;
  }
  current = 9; renderStep();
}
function prevSupport(){
  if(supportIndex > 0){
    supportIndex--;
    renderSupportQuestion();
    return;
  }
  current = 7; renderStep();
}
function renderSupportReason(){
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  const key = options[supportIndex];
  document.getElementById('supportReasonLabel').textContent = supportLabels[key];
  document.querySelectorAll('input[name="support_refusal_reason"]').forEach(input => {
    input.checked = supportRefusalReasons[key] === input.value;
  });
}
function saveSupportReason(){
  const reason = document.querySelector('input[name="support_refusal_reason"]:checked')?.value;
  if(!reason){ alert('1つ選んでください。'); return; }
  resetAfterSupportReason();
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  const key = options[supportIndex];
  supportRefusalReasons[key] = reason;
  if(reason === 'still_safety_concern' && supportIndex < options.length - 1){
    supportIndex++;
    current = 8; renderStep(); return;
  }
  document.getElementById('supportSummary').textContent = `${supportLabels[key]}でも前向きに考えにくい（理由: ${supportRefusalLabels[reason]}）`;
  current = 10; renderStep();
}
function prevSupportReason(){
  current = 8; renderStep();
}
function clearChecked(name){
  document.querySelectorAll(`input[name="${name}"]`).forEach(input => input.checked = false);
}
function resetAfterNeed(){
  clearChecked('clozapine_accept');
  resetAfterClozapine();
}
function resetAfterClozapine(){
  inpatientAccept = null;
  outpatientAccept = null;
  clearChecked('inpatient_accept');
  clearChecked('outpatient_accept');
  document.getElementById('inpatientSummary').textContent = '未回答';
  document.getElementById('outpatientSummary').textContent = '未回答';
  resetAfterOutpatient();
}
function resetAfterInpatient(){
  outpatientAccept = null;
  clearChecked('outpatient_accept');
  document.getElementById('outpatientSummary').textContent = '未回答';
  resetAfterOutpatient();
}
function resetAfterOutpatient(){
  visitIndex = 0;
  threshold = null;
  currentRejectedVisit = null;
  supportBaseVisit = null;
  document.getElementById('thresholdSummary').textContent = '未回答';
  clearChecked('visit_rejection_reason');
  Object.keys(visitRejectionReasons).forEach(key => delete visitRejectionReasons[key]);
  resetAfterVisitReason();
}
function resetAfterVisit(){
  const currentVisit = visitQuestions[visitIndex]?.[0];
  if(currentVisit){
    delete visitRejectionReasons[currentVisit];
  }
  currentRejectedVisit = null;
  clearChecked('visit_rejection_reason');
  resetAfterVisitReason();
}
function resetAfterVisitReason(){
  supportIndex = 0;
  supportBaseVisit = null;
  Object.keys(supportAnswers).forEach(key => delete supportAnswers[key]);
  Object.keys(supportRefusalReasons).forEach(key => delete supportRefusalReasons[key]);
  document.getElementById('supportSummary').textContent = '該当なし/未回答';
  clearChecked('support_refusal_reason');
  resetAfterSupportReason();
}
function resetAfterSupport(){
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'] || [];
  const key = options[supportIndex];
  if(key){
    delete supportAnswers[key];
    delete supportRefusalReasons[key];
  }
  clearChecked('support_refusal_reason');
  resetAfterSupportReason();
}
function resetAfterSupportReason(){
  sideEffectIndex = 0;
  Object.keys(sideEffectAnswers).forEach(key => delete sideEffectAnswers[key]);
  clearChecked('side_effect_current');
}
function scenarioText(){
  if(responseFrame === 'actual_current') return '以下では、現在のあなたの状態で、主治医からクロザピンを勧められた場面を想像してください。';
  if(responseFrame === 'hypothetical_future') return '以下では、もし今後、症状や生活のしづらさが強くなり、複数の薬でも十分改善せず、主治医からクロザピン導入を勧められた場合を想像してください。';
  return '以下では、主治医からクロザピンを勧められた場面を想像してください。';
}
function finish(){
  alert('ダミー質問票です。実際の回答は保存されません。');
}
wireAutoAdvance();
renderStep();
"""


def common_css() -> str:
    return """
    body{margin:0;background:#f4f6f8;color:#1f2933;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.7}
    header{background:#24323d;color:white;padding:30px 36px}
    header h1{margin:0 0 6px;font-size:28px}
    header p{margin:0;color:#d5dde3}
    main{max-width:1080px;margin:0 auto;padding:24px 18px 56px}
    section{background:white;border:1px solid #d8dee4;border-radius:8px;padding:20px 24px;margin:18px 0}
    h2{margin-top:0;border-bottom:2px solid #eef2f6;padding-bottom:6px}
    table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #d8dee4;padding:8px 10px;text-align:left}
    th{background:#eef2f6}
    img{max-width:100%;height:auto;display:block;margin:0 auto}
    .links{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
    .links a{background:white;border:1px solid #cbd5df;border-radius:999px;padding:6px 12px;color:#245b67;text-decoration:none}
    .figure-card .reason,.reason{border-left:4px solid #2f7d8c;background:#f3f8f9;padding:10px 12px}
    """


def questionnaire_css() -> str:
    return """
    body{margin:0;background:#edf2f5;color:#1f2933;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.6}
    .app-head{position:sticky;top:0;z-index:5;background:#24323d;color:white;padding:12px 14px;display:flex;justify-content:space-between;gap:10px;align-items:center}
    .app-head h1{font-size:15px;margin:0}.eyebrow{font-size:11px;margin:0;color:#cfd8dc}.progress{background:#38515d;padding:6px 10px;border-radius:999px;font-weight:700}
    .phone-frame{max-width:460px;margin:0 auto;padding:10px}
    .step{display:none;background:white;border:1px solid #d8dee4;border-radius:10px;padding:14px;margin:0 0 14px;box-shadow:0 1px 4px rgba(0,0,0,.04)}
    .step.active{display:block}.hero{width:100%;border-radius:8px;margin-bottom:12px;background:#e7edf1}
    h2{font-size:19px;margin:4px 0 10px}h3{font-size:18px;margin:4px 0}.subq,.question{font-weight:700;margin-top:16px}.small{font-size:13px;color:#52616b}
    .choice,.seg label{display:block;border:1px solid #cbd5df;border-radius:8px;padding:12px;margin:8px 0;background:#fbfcfd;font-weight:600}
    input{margin-right:8px}.seg{display:grid;gap:0}.seg.two{grid-template-columns:1fr 1fr;gap:8px}
    .field-label{display:block;font-weight:700;margin-top:12px}.text-input{box-sizing:border-box;width:100%;border:1px solid #9fb3bd;border-radius:8px;padding:13px 12px;font-size:16px;text-transform:uppercase;background:white}
    code{background:#eef2f6;border:1px solid #d8dee4;border-radius:4px;padding:1px 5px}
    button{border:1px solid #9fb3bd;background:white;color:#245b67;border-radius:8px;padding:12px 14px;font-weight:700;font-size:15px}
    .primary{background:#2f7d8c;color:white;border-color:#2f7d8c}
    .full{width:100%}
    .nav{display:grid;grid-template-columns:1fr;gap:8px;margin-top:14px}.nav .primary{order:-1}
    .notice{border-left:4px solid #c2410c;background:#fff7ed;padding:10px;margin:10px 0}.hidden{display:none}
    .tt-card{border:2px solid #2f7d8c;border-radius:12px;padding:14px;background:#f3f8f9}.pill{display:inline-block;background:#2f7d8c;color:white;border-radius:999px;padding:2px 10px;font-weight:700;margin:0 0 4px}
    .summary{background:#eef6f7;border:1px solid #b8d6dc;border-radius:8px;padding:10px;margin-top:14px}
    @media (max-width:420px){.phone-frame{padding:6px}.step{border-radius:0;border-left:0;border-right:0}button{width:100%}.seg.two{grid-template-columns:1fr}}
    """


def write_index() -> None:
    cards = []
    for v, meta in VERSIONS.items():
        cards.append(
            f"""<section>
              <h2>{meta['label']}</h2>
              <p>{meta['focus']}</p>
              <p><a href="patient_survey_bhtm_v{v}_figures_mock.html">図表モック</a> / <a href="patient_survey_bhtm_v{v}_questionnaire.html">質問票</a></p>
            </section>"""
        )
    html = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>患者調査BHTMモック</title><style>{common_css()}</style></head><body><header><h1>患者調査BHTMモック</h1><p>5回ブラッシュアップ版の一覧</p></header><main><nav class="links"><a href="../BHTM_threshold_technique_design_note.html">BHTM設計ノート</a><a href="../Hauber_Coulter_2020_threshold_technique_literature_note.html">Hauber & Coulter 2020</a><a href="../Parikh_2023_HCC_threshold_technique_literature_note.html">Parikh 2023</a><a href="../Barrett_2005_benefit_harm_tradeoff_literature_note.html">Barrett 2005</a></nav>{''.join(cards)}</main></body></html>"""
    (ROOT / "index.html").write_text(html, encoding="utf-8")


def main() -> None:
    ensure_dirs()
    for version in VERSIONS:
        data = simulate(version)
        write_version_data(version, data)
        figs = make_figures(version, data)
        (ROOT / f"patient_survey_bhtm_v{version}_figures_mock.html").write_text(figure_mock_html(version, data, figs), encoding="utf-8")
        (ROOT / f"patient_survey_bhtm_v{version}_questionnaire.html").write_text(questionnaire_html(version), encoding="utf-8")
    write_index()


if __name__ == "__main__":
    main()
