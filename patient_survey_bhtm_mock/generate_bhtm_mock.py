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
            "参加者コードで回答前提と有効性/副作用の提示順を内部設定し、提示順によるプライミングを探索できるようにした。",
            "クロザピン服用意向の前に、有効性の十分性評価と副作用別の服用判断への影響を取得する。",
            "主要アウトカムを“入院導入と外来導入の受容性”と“外来導入時の初期通院頻度threshold”に固定。",
            "抽象的な外来導入Yes/Noは削除し、外来導入受容性は週3/週2/週1通院条件のいずれかを受容したかで定義する。",
            "通院のみthresholdを先に決め、その通院頻度を固定したうえで、診察と訪問看護を合わせた確認頻度のthresholdを高頻度から順に尋ねる。",
            "訪問看護は安全面不安への救済分岐ではなく、医師が安全上必要と判断しうる確認頻度を患者が受容できるかを測る別thresholdとして扱う。",
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
    "V2": ["V2N3", "V2N1"],
    "V1": ["V1N4", "V1N2", "V1N1"],
    "NONE": [],
}

SUPPORT_THRESHOLD_LABELS = {
    "V3N2": "週5回確認まで受容（週3通院+週2訪問）",
    "V2N3": "週5回確認まで受容（週2通院+週3訪問）",
    "V1N4": "週5回確認まで受容（週1通院+週4訪問）",
    "V2N1": "週3回確認まで受容（週2通院+週1訪問）",
    "V1N2": "週3回確認まで受容（週1通院+週2訪問）",
    "V1N1": "週2回確認まで受容（週1通院+週1訪問）",
    "SNONE": "訪問看護追加は非受容/保留",
}

BACKGROUND_OPTIONS = {
    "day_activity": ["就労中", "就学中", "福祉的就労", "デイケア等", "主に自宅", "その他"],
    "day_activity_frequency": ["週0-1日", "週2-3日", "週4日以上", "該当なし"],
    "living_arrangement": ["一人暮らし", "家族等と同居", "施設・グループホーム", "その他"],
    "family_support": ["受けられる", "少し受けられる", "ほぼ受けられない", "同居なし"],
    "caregiving_role": ["なし", "子どものケア", "親・配偶者等のケア", "その他"],
    "travel_time_one_way": ["30分未満", "30-60分", "60-90分", "90分以上"],
    "transport": ["自分で運転", "公共交通", "家族送迎", "福祉交通・タクシー", "徒歩・自転車", "その他"],
    "home_nursing_current": ["あり", "過去あり", "なし"],
    "main_income_source": ["就労収入", "障害年金", "生活保護", "家族支援", "その他", "答えたくない"],
    "public_assistance": ["あり", "なし", "答えたくない"],
    "economic_strain": ["困っていない", "少し困る", "かなり困る", "答えたくない"],
}


def ensure_dirs() -> None:
    DATA.mkdir(exist_ok=True)
    FIG.mkdir(exist_ok=True)
    for v in VERSIONS:
        (DATA / f"v{v}").mkdir(exist_ok=True)


def sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


def simulate(version: int) -> dict[str, list[dict[str, str]]]:
    n = 180
    n_physicians = 48
    physicians: list[dict[str, str]] = []
    for j in range(1, n_physicians + 1):
        years = max(2, min(36, int(RNG.normalvariate(13, 7))))
        initiations = max(0, int(RNG.expovariate(1 / 4.5) + (3 if years > 15 else 0)))
        current_clozapine = max(0, int(RNG.expovariate(1 / 3.2) + (2 if initiations >= 5 else 0)))
        specialist = years >= 6 and RNG.random() < 0.78
        designated = years >= 5 and RNG.random() < 0.72
        outpatient_recommendation_rate = min(0.95, max(0.05, RNG.normalvariate(0.45 + 0.012 * initiations, 0.16)))
        stably_unwell_reason_rate = min(0.85, max(0.02, RNG.normalvariate(0.28 - 0.006 * initiations, 0.12)))
        expected_refusal_reason_rate = min(0.90, max(0.05, RNG.normalvariate(0.42 - 0.004 * current_clozapine, 0.14)))
        physicians.append(
            {
                "physician_id": f"D{j:02d}",
                "psychiatry_experience_years": str(years),
                "psychiatry_specialist": str(int(specialist)),
                "designated_mental_health_physician": str(int(designated)),
                "clozapine_initiation_cases": str(initiations),
                "current_clozapine_patients": str(current_clozapine),
                "outpatient_recommendation_rate": f"{outpatient_recommendation_rate:.3f}",
                "stably_unwell_reason_rate": f"{stably_unwell_reason_rate:.3f}",
                "expected_refusal_reason_rate": f"{expected_refusal_reason_rate:.3f}",
            }
        )
    participants: list[dict[str, str]] = []
    vignette: list[dict[str, str]] = []
    threshold: list[dict[str, str]] = []
    gap: list[dict[str, str]] = []
    safety: list[dict[str, str]] = []

    for i in range(1, n + 1):
        physician = physicians[(i - 1) % n_physicians]
        target = "TRS適格候補" if i <= 86 else "広い未使用外来患者"
        unmet = RNG.random() < (0.72 if target == "TRS適格候補" else 0.46)
        past_refusal = RNG.random() < 0.16
        subjective_distress = RNG.random() < (0.68 if unmet else 0.30)
        age = max(21, min(78, int(RNG.normalvariate(48 if target == "TRS適格候補" else 44, 12))))
        mgaf_function = max(18, min(75, int(RNG.normalvariate(36 if target == "TRS適格候補" else 50, 7))))
        if target == "広い未使用外来患者" and not unmet:
            mgaf_function = max(mgaf_function, int(RNG.normalvariate(55, 5)))
        response_frame = "actual_current" if mgaf_function <= 40 else "hypothetical_future"
        info_order = RNG.choice(["efficacy_first", "side_effect_first"])
        living_arrangement = RNG.choices(
            BACKGROUND_OPTIONS["living_arrangement"],
            weights=[0.32, 0.48, 0.14, 0.06],
            k=1,
        )[0]
        family_support = (
            RNG.choices(["受けられる", "少し受けられる", "ほぼ受けられない"], weights=[0.42, 0.38, 0.20], k=1)[0]
            if living_arrangement == "家族等と同居"
            else "同居なし"
        )
        day_activity = RNG.choices(
            BACKGROUND_OPTIONS["day_activity"],
            weights=[0.18, 0.02, 0.18, 0.18, 0.38, 0.06],
            k=1,
        )[0]
        day_activity_frequency = (
            RNG.choices(["週0-1日", "週2-3日", "週4日以上"], weights=[0.22, 0.42, 0.36], k=1)[0]
            if day_activity not in {"主に自宅", "その他"}
            else "該当なし"
        )
        main_income_source = RNG.choices(
            BACKGROUND_OPTIONS["main_income_source"],
            weights=[0.18, 0.36, 0.18, 0.14, 0.08, 0.06],
            k=1,
        )[0]
        public_assistance = "あり" if main_income_source == "生活保護" else RNG.choices(["なし", "答えたくない"], weights=[0.92, 0.08], k=1)[0]
        participants.append(
            {
                "participant_id": f"P{i:03d}",
                "physician_id": physician["physician_id"],
                "target_group": target,
                "clinician_mgaf_function": str(mgaf_function),
                "response_frame": response_frame,
                "info_order": info_order,
                "age": str(age),
                "sex": RNG.choice(["女性", "男性", "回答しない"]),
                "current_unmet_need": "あり" if unmet else "なし/軽度",
                "subjective_distress": "あり" if subjective_distress else "なし/軽度",
                "past_clozapine_refusal_documented": "あり" if past_refusal else "なし",
                "day_activity": day_activity,
                "day_activity_frequency": day_activity_frequency,
                "living_arrangement": living_arrangement,
                "family_support": family_support,
                "caregiving_role": RNG.choices(BACKGROUND_OPTIONS["caregiving_role"], weights=[0.78, 0.08, 0.10, 0.04], k=1)[0],
                "travel_time_one_way": RNG.choices(BACKGROUND_OPTIONS["travel_time_one_way"], weights=[0.44, 0.38, 0.14, 0.04], k=1)[0],
                "transport": RNG.choices(BACKGROUND_OPTIONS["transport"], weights=[0.18, 0.32, 0.18, 0.12, 0.16, 0.04], k=1)[0],
                "home_nursing_current": RNG.choices(BACKGROUND_OPTIONS["home_nursing_current"], weights=[0.26, 0.13, 0.61], k=1)[0],
                "main_income_source": main_income_source,
                "public_assistance": public_assistance,
                "economic_strain": RNG.choices(BACKGROUND_OPTIONS["economic_strain"], weights=[0.35, 0.38, 0.20, 0.07], k=1)[0],
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
        efficacy_sufficiency = min(5, max(1, int(round(RNG.normalvariate(3.1 + 0.45 * unmet + 0.25 * subjective_distress, 0.9)))))
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
        support_answers: dict[str, str] = {key: "not_asked" for key, _ in SUPPORT_PACKAGES}
        support_base = th if th in {"V3", "V2", "V1"} else "not_asked"
        support_eligible = method_outpatient_accept and th in {"V3", "V2", "V1"}
        support_accept_any = False
        support_accept_condition = "SNONE"
        if support_eligible:
            for support_key in SUPPORT_BY_THRESHOLD[th]:
                accept_base = {
                    "V3N2": 0.30,
                    "V2N3": 0.34,
                    "V1N4": 0.30,
                    "V2N1": 0.46,
                    "V1N2": 0.48,
                    "V1N1": 0.58,
                }[support_key]
                accept_prob = accept_base + 0.08 * subjective_distress - 0.05 * (max_side_effect_impact >= 5)
                if RNG.random() < accept_prob:
                    support_answers[support_key] = "accepted"
                    support_accept_any = True
                    support_accept_condition = support_key
                    break
                support_answers[support_key] = "refused"
        threshold.append(
            {
                "participant_id": f"P{i:03d}",
                "clozapine_accept": str(int(clozapine_accept)),
                "threshold": th,
                "threshold_label": max_burden,
                "efficacy_sufficiency": str(efficacy_sufficiency),
                "side_effect_max_impact": str(max_side_effect_impact),
                **{f"side_effect_{key}": str(value) for key, value in side_effect_ratings.items()},
                "support_eligible": str(int(support_eligible)),
                "support_base_visit": support_base,
                **{f"support_{key.lower()}": value for key, value in support_answers.items()},
                "support_accept_any": str(int(support_accept_any)),
                "support_accept_condition": support_accept_condition,
                "support_threshold_label": SUPPORT_THRESHOLD_LABELS[support_accept_condition],
            }
        )
        # In the revised questionnaire, outpatient initiation acceptance is
        # defined by accepting at least one concrete outpatient visit-frequency
        # condition, not by an abstract outpatient yes/no item.
        vignette[-1]["outpatient_asked_accept"] = str(int(th != "NONE"))
        low_experience = int(physician["clozapine_initiation_cases"]) < 3
        stably_style = float(physician["stably_unwell_reason_rate"]) > 0.30
        refusal_style = float(physician["expected_refusal_reason_rate"]) > 0.45
        physician_expect_prob = (
            0.25
            + 0.20 * unmet
            - 0.10 * past_refusal
            + 0.20 * float(physician["outpatient_recommendation_rate"])
            - 0.10 * low_experience
            - 0.08 * stably_style
            - 0.07 * refusal_style
        )
        physician_expect = RNG.random() < min(0.85, max(0.05, physician_expect_prob))
        patient_accept_outpatient = th != "NONE" or support_accept_any
        gap.append(
            {
                "participant_id": f"P{i:03d}",
                "physician_id": physician["physician_id"],
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
        "physicians": physicians,
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
    colors = {"burden_only": "#2f7d8c", "safety_only": "#c47f4f"}
    labels = [
        ("burden_only", "通院負担のみ"),
        ("safety_only", "安全面不安のみ"),
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


SUPPORT_LEVELS = [
    ("S5", "週5回確認まで受容"),
    ("S3", "週3回確認まで受容"),
    ("S2", "週2回確認まで受容"),
    ("SNONE", "訪問看護追加は非受容/保留"),
]


def support_level(condition: str) -> str:
    if condition in {"V3N2", "V2N3", "V1N4"}:
        return "S5"
    if condition in {"V2N1", "V1N2"}:
        return "S3"
    if condition == "V1N1":
        return "S2"
    return "SNONE"


def support_threshold_rows_svg(path: Path, title: str, rows: dict[str, Counter], row_labels: dict[str, str]) -> None:
    width, height = 940, 380 + max(0, len(rows) - 2) * 46
    left, top, right, bottom = 230, 66, 52, 92
    plot_w = width - left - right
    row_h = 68
    colors = {"S5": "#245b67", "S3": "#2f7d8c", "S2": "#8bbbc3", "SNONE": "#d8dee4"}
    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for i, key in enumerate(rows.keys()):
        counts = rows[key]
        total = sum(counts.values())
        y = top + i * row_h
        parts.append(f'<text x="{left-12}" y="{y+27}" text-anchor="end" class="label">{esc(row_labels.get(key, key))}</text>')
        x = left
        if total == 0:
            parts.append(f'<text x="{left}" y="{y+27}" class="axis">該当者なし</text>')
            continue
        for level_key, _ in SUPPORT_LEVELS:
            val = counts.get(level_key, 0)
            w = plot_w * val / total if total else 0
            if w > 0:
                parts.append(f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="38" fill="{colors[level_key]}"/>')
                if w > 42:
                    parts.append(f'<text x="{x+w/2:.1f}" y="{y+25}" text-anchor="middle" class="inside">{val}</text>')
            x += w
        parts.append(f'<text x="{left+plot_w+8}" y="{y+25}" class="num">n={total}</text>')
    lx, ly = left, height - 58
    for level_key, label in SUPPORT_LEVELS:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[level_key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        lx += 210
        if lx > width - 190:
            lx = left
            ly += 24
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


def univariate_or(exposed: list[bool], outcome: list[bool]) -> tuple[float, float, float, int, int]:
    a = sum(1 for e, y in zip(exposed, outcome) if e and y)
    b = sum(1 for e, y in zip(exposed, outcome) if e and not y)
    c = sum(1 for e, y in zip(exposed, outcome) if not e and y)
    d = sum(1 for e, y in zip(exposed, outcome) if not e and not y)
    # Haldane-Anscombe correction keeps mock estimates finite.
    aa, bb, cc, dd = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    log_or = math.log((aa * dd) / (bb * cc))
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / dd)
    return math.exp(log_or), math.exp(log_or - 1.96 * se), math.exp(log_or + 1.96 * se), a, a + b


def forest_or_svg(path: Path, title: str, rows: list[dict[str, str | float | int]]) -> None:
    width, height = 1040, 92 + 42 * len(rows)
    left, top, right, bottom = 310, 58, 230, 54
    plot_w = width - left - right
    xmin, xmax = 0.25, 4.0
    log_min, log_max = math.log(xmin), math.log(xmax)

    def x_pos(value: float) -> float:
        value = min(max(value, xmin), xmax)
        return left + plot_w * (math.log(value) - log_min) / (log_max - log_min)

    parts = [svg_head(width, height), f'<text x="{left}" y="30" class="title">{esc(title)}</text>']
    for tick in [0.25, 0.5, 1, 2, 4]:
        x = x_pos(tick)
        stroke = "#1f2933" if tick == 1 else "#e5eaf0"
        parts.append(f'<line x1="{x:.1f}" y1="{top-10}" x2="{x:.1f}" y2="{height-bottom}" stroke="{stroke}" stroke-width="{1.4 if tick == 1 else 1}"/>')
        parts.append(f'<text x="{x:.1f}" y="{height-22}" text-anchor="middle" class="axis">{tick:g}</text>')
    for i, row in enumerate(rows):
        y = top + i * 42
        if row.get("header"):
            parts.append(f'<text x="{left-12}" y="{y+6}" text-anchor="end" class="label">{esc(str(row["label"]))}</text>')
            parts.append(f'<line x1="{left}" y1="{y+12}" x2="{width-right}" y2="{y+12}" stroke="#d8dee4"/>')
            continue
        label = str(row["label"])
        orv = float(row["or"])
        lo = float(row["lo"])
        hi = float(row["hi"])
        n_event = int(row["events"])
        n_exp = int(row["exposed_n"])
        x1, x2, xm = x_pos(lo), x_pos(hi), x_pos(orv)
        parts.append(f'<text x="{left-12}" y="{y+6}" text-anchor="end" class="label">{esc(label)}</text>')
        parts.append(f'<line x1="{x1:.1f}" y1="{y}" x2="{x2:.1f}" y2="{y}" stroke="#2f7d8c" stroke-width="2"/>')
        parts.append(f'<circle cx="{xm:.1f}" cy="{y}" r="5.5" fill="#2f7d8c"/>')
        parts.append(f'<text x="{left+plot_w+18}" y="{y+5}" class="num">{orv:.2f} ({lo:.2f}-{hi:.2f})</text>')
        parts.append(f'<text x="{width-right+122}" y="{y+5}" class="axis">{n_event}/{n_exp}</text>')
    parts.append(f'<text x="{left+plot_w/2}" y="{height-8}" text-anchor="middle" class="axis">Odds ratio（対数軸）</text>')
    parts.append(f'<text x="{left+plot_w+18}" y="{top-24}" class="axis">OR (95% CI)</text>')
    parts.append(f'<text x="{width-right+122}" y="{top-24}" class="axis">該当者中の過小評価</text>')
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
    physicians = {r["physician_id"]: r for r in data["physicians"]}
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

    support_overall = Counter()
    for r in threshold:
        if r["support_eligible"] == "1":
            support_overall[support_level(r["support_accept_condition"])] += 1
    p = FIG / f"bhtm_v{version}_fig3_threshold_by_group.svg"
    support_threshold_rows_svg(
        p,
        "図3. 訪問看護を含む確認頻度threshold",
        {"overall": support_overall},
        {"overall": "外来導入受容者"},
    )
    fig_paths["fig3"] = rel(p)

    support_by_visit: dict[str, Counter] = {"V3": Counter(), "V2": Counter(), "V1": Counter()}
    for r in threshold:
        if r["support_eligible"] == "1":
            support_by_visit[r["support_base_visit"]][support_level(r["support_accept_condition"])] += 1
    p = FIG / f"bhtm_v{version}_fig4_support_acceptance.svg"
    support_threshold_rows_svg(
        p,
        "図4. 通院頻度threshold別にみた訪問看護確認頻度threshold",
        support_by_visit,
        {"V3": "週3回通院受容", "V2": "週2回通院受容", "V1": "週1回通院受容"},
    )
    fig_paths["fig4"] = rel(p)

    support_by_frame: dict[str, Counter] = {"actual_current": Counter(), "hypothetical_future": Counter()}
    for r in threshold:
        if r["support_eligible"] == "1":
            frame_key = participants[r["participant_id"]]["response_frame"]
            support_by_frame[frame_key][support_level(r["support_accept_condition"])] += 1
    p = FIG / f"bhtm_v{version}_fig5_support_by_frame.svg"
    support_threshold_rows_svg(
        p,
        "図5. 回答前提別にみた訪問看護確認頻度threshold",
        support_by_frame,
        {"actual_current": "現在の状態で回答", "hypothetical_future": "将来TRS相当を想定"},
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

    threshold_by_id = {r["participant_id"]: r for r in threshold}
    vignette_by_id = {r["participant_id"]: r for r in vignette}
    underestimation = [
        r["physician_expected_outpatient_acceptance"] == "0" and r["patient_outpatient_acceptance"] == "1"
        for r in gap
    ]
    ids = [r["participant_id"] for r in gap]
    factor_specs: list[tuple[str, list[bool]]] = [
        ("現在の状態で回答", [participants[pid]["response_frame"] == "actual_current" for pid in ids]),
        ("臨床家評価mGAF-F 40以下", [int(participants[pid]["clinician_mgaf_function"]) <= 40 for pid in ids]),
        ("現在治療で困りごとあり", [participants[pid]["current_unmet_need"] == "あり" for pid in ids]),
        ("主観的困りごと/つらさあり", [participants[pid]["subjective_distress"] == "あり" for pid in ids]),
        ("入院導入は前向きに考えにくい", [vignette_by_id[pid]["inpatient_asked_accept"] == "0" for pid in ids]),
        ("外来週1回通院なら受容", [threshold_by_id[pid]["threshold"] == "V1" for pid in ids]),
        ("週5回確認まで受容", [support_level(threshold_by_id[pid]["support_accept_condition"]) == "S5" for pid in ids]),
        ("副作用懸念が強い（最大4以上）", [int(threshold_by_id[pid]["side_effect_max_impact"]) >= 4 for pid in ids]),
        ("有効性は十分（4以上）", [int(threshold_by_id[pid]["efficacy_sufficiency"]) >= 4 for pid in ids]),
        ("過去拒否記載あり", [participants[pid]["past_clozapine_refusal_documented"] == "あり" for pid in ids]),
        ("日中活動あり", [participants[pid]["day_activity"] in {"就労中", "就学中", "福祉的就労", "デイケア等"} for pid in ids]),
        ("同居家族から支援あり", [participants[pid]["family_support"] == "受けられる" for pid in ids]),
        ("ケア役割あり", [participants[pid]["caregiving_role"] != "なし" for pid in ids]),
        ("通院片道60分以上", [participants[pid]["travel_time_one_way"] in {"60-90分", "90分以上"} for pid in ids]),
        ("訪問看護を現在利用", [participants[pid]["home_nursing_current"] == "あり" for pid in ids]),
        ("生活保護あり", [participants[pid]["public_assistance"] == "あり" for pid in ids]),
        ("経済的にかなり困る", [participants[pid]["economic_strain"] == "かなり困る" for pid in ids]),
    ]
    physician_factor_specs: list[tuple[str, list[bool]]] = [
        ("精神科経験15年以上", [int(physicians[participants[pid]["physician_id"]]["psychiatry_experience_years"]) >= 15 for pid in ids]),
        ("精神科専門医", [physicians[participants[pid]["physician_id"]]["psychiatry_specialist"] == "1" for pid in ids]),
        ("精神保健指定医", [physicians[participants[pid]["physician_id"]]["designated_mental_health_physician"] == "1" for pid in ids]),
        ("クロザピン導入3例以上", [int(physicians[participants[pid]["physician_id"]]["clozapine_initiation_cases"]) >= 3 for pid in ids]),
        ("現在担当クロザピン患者3名以上", [int(physicians[participants[pid]["physician_id"]]["current_clozapine_patients"]) >= 3 for pid in ids]),
        ("医師の外来導入推奨率が高い", [float(physicians[participants[pid]["physician_id"]]["outpatient_recommendation_rate"]) >= 0.50 for pid in ids]),
        ("stably unwell理由選択率が高い", [float(physicians[participants[pid]["physician_id"]]["stably_unwell_reason_rate"]) >= 0.30 for pid in ids]),
        ("患者拒否見込み理由選択率が高い", [float(physicians[participants[pid]["physician_id"]]["expected_refusal_reason_rate"]) >= 0.45 for pid in ids]),
    ]
    or_rows: list[dict[str, str | float | int]] = [{"label": "A. 患者要因", "header": 1}]
    for label, exposed in factor_specs:
        orv, lo, hi, events, exposed_n = univariate_or(exposed, underestimation)
        or_rows.append({"label": label, "or": orv, "lo": lo, "hi": hi, "events": events, "exposed_n": exposed_n})
    or_rows.append({"label": "B. 医師要因", "header": 1})
    for label, exposed in physician_factor_specs:
        orv, lo, hi, events, exposed_n = univariate_or(exposed, underestimation)
        or_rows.append({"label": label, "or": orv, "lo": lo, "hi": hi, "events": events, "exposed_n": exposed_n})
    p = FIG / f"bhtm_v{version}_fig8_underestimation_factors.svg"
    forest_or_svg(p, "図8. 医師が外来導入受容性を過小評価しやすい患者・医師要因", or_rows)
    fig_paths["fig8"] = rel(p)
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

    def count_row(label: str, field: str, key: str) -> tuple[str, str]:
        count = sum(1 for r in participants if r[field] == key)
        return label, f"{count} ({count/n*100:.1f}%)"

    def count_if(label: str, predicate) -> tuple[str, str]:
        count = sum(1 for r in participants if predicate(r))
        return label, f"{count} ({count/n*100:.1f}%)"

    rows = [
        ("解析対象者", f"{n}"),
        ("TRS適格候補", f"{target['TRS適格候補']} ({target['TRS適格候補']/n*100:.1f}%)"),
        ("広い未使用外来患者", f"{target['広い未使用外来患者']} ({target['広い未使用外来患者']/n*100:.1f}%)"),
        ("臨床家評価mGAF-F 40以下", f"{mgaf_le40} ({mgaf_le40/n*100:.1f}%)"),
        ("現在の状態で回答", f"{frame['actual_current']} ({frame['actual_current']/n*100:.1f}%)"),
        ("将来TRS相当を想定して回答", f"{frame['hypothetical_future']} ({frame['hypothetical_future']/n*100:.1f}%)"),
        ("現在の治療で残る困りごとあり", f"{unmet['あり']} ({unmet['あり']/n*100:.1f}%)"),
        ("主観的困りごと/つらさあり", f"{distress['あり']} ({distress['あり']/n*100:.1f}%)"),
        count_if("日中活動あり（就労/就学/福祉的就労/デイケア等）", lambda r: r["day_activity"] in {"就労中", "就学中", "福祉的就労", "デイケア等"}),
        count_row("福祉的就労", "day_activity", "福祉的就労"),
        count_row("デイケア等", "day_activity", "デイケア等"),
        count_row("主に自宅", "day_activity", "主に自宅"),
        count_row("週4日以上の日中活動", "day_activity_frequency", "週4日以上"),
        count_row("一人暮らし", "living_arrangement", "一人暮らし"),
        count_row("家族等と同居", "living_arrangement", "家族等と同居"),
        count_row("同居家族から支援を受けられる", "family_support", "受けられる"),
        count_if("本人が誰かのケアを担っている", lambda r: r["caregiving_role"] != "なし"),
        count_if("通院片道60分以上", lambda r: r["travel_time_one_way"] in {"60-90分", "90分以上"}),
        count_row("通院手段: 公共交通", "transport", "公共交通"),
        count_row("通院手段: 家族送迎", "transport", "家族送迎"),
        count_row("訪問看護を現在利用", "home_nursing_current", "あり"),
        count_row("主な収入源: 障害年金", "main_income_source", "障害年金"),
        count_row("生活保護あり", "public_assistance", "あり"),
        count_row("経済的にかなり困る", "economic_strain", "かなり困る"),
    ]
    return "<table><tr><th>項目</th><th>値</th></tr>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>"


def figure_mock_html(version: int, data: dict[str, list[dict[str, str]]], figs: dict[str, str]) -> str:
    v = VERSIONS[version]
    visible = ["fig1", "fig2", "fig3", "fig4", "fig5", "fig6", "fig7", "fig8"]
    reasons = {
        "fig1": "回答前提別に、入院導入と外来導入の受容性を比較する中核図。外来導入受容性は抽象的なYes/Noではなく、週3/週2/週1通院条件のいずれかを受容した場合として定義する。mGAF-F 40以下の実意思決定に近い群と、将来TRS相当となった場合を想定する群を分けることで、企画倒れを避けつつ解釈可能性を保つ。Gee 2017やJakobsen 2025で入院導入が大きな障壁として示されたことを踏まえ、“入院は難しいが外来なら前向き”という潜在ニーズを可視化する。",
        "fig2": "入院導入を前向きに考える人と考えにくい人に分け、外来導入の通院頻度thresholdを示す中核図。入院導入を受け入れうる人でも外来週3回は難しい、あるいは入院導入は難しい人でも外来なら受容に転じる、といった現実的な選好のずれを示す。",
        "fig3": "外来導入を受容しうる人について、通院に訪問看護を加えた総確認頻度をどこまで受け入れられるかを示す図。安全に必要な頻度は医師が判断する前提で、その頻度を患者が受容可能かを直接把握する。",
        "fig4": "先に確定した通院頻度thresholdごとに、訪問看護を加えた確認頻度thresholdを示す図。週3回通院を受容する人、週2回なら受容する人、週1回なら受容する人で、追加モニタリングへの許容度が異なるかを確認する。",
        "fig5": "現在の状態で回答した群と、将来TRS相当を想定して回答した群で、訪問看護を含む確認頻度thresholdがどう異なるかを示す図。即時候補者と潜在ニーズ層の違いを分けて解釈するために置く。",
        "fig6": "副作用は単一項目にまとめると解釈しにくいため、眠気、流涎、体重増加、便秘、採血異常・感染リスク、心筋炎などに分けて、服用判断をどの程度妨げるかを測定する。",
        "fig7": "患者調査を臨床家調査と接続する図。Jakobsen 2025の示唆に沿い、医師が非受容と想定する患者の中にも外来導入なら受け入れる層がいるかを示す。",
        "fig8": "図7の右上象限、すなわち「医師は外来導入を受け入れにくいと予測したが、患者本人は外来導入を受け入れる」層に関連する患者要因と医師要因を単変量ORで示す。因果推論ではなく、医師判断だけでは見落とされやすい患者像と、見落としが起きやすい医師側の判断スタイルを探索的に記述する目的で置く。医師要因は臨床家調査と患者調査を主治医単位でリンクできる場合に解析する。",
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
        <p class="small">デモ用コード: <code>ACT001</code>/<code>ACT002</code> は現在の状態で回答、<code>HYP001</code>/<code>HYP002</code> は将来TRS相当を想定して回答します。末尾001/002で有効性と副作用の提示順が変わります。本番では対応表を調査システム側で管理します。</p>

        <div class="background-block">
          <h3>生活・通院背景</h3>
          <p class="small">生年月日、性別、診断などは電子カルテから取得します。ここでは入院・通院・訪問看護の負担に関係する項目だけ伺います。</p>
          <label class="field-label" for="dayActivity">日中活動</label>
          <select class="select-input bg-required" id="dayActivity" name="day_activity">
            <option value="">選択してください</option>
            <option>就労中</option><option>就学中</option><option>福祉的就労</option><option>デイケア等</option><option>主に自宅</option><option>その他</option>
          </select>
          <label class="field-label" for="dayActivityFrequency">日中活動の頻度</label>
          <select class="select-input bg-required" id="dayActivityFrequency" name="day_activity_frequency">
            <option value="">選択してください</option>
            <option>週0-1日</option><option>週2-3日</option><option>週4日以上</option><option>該当なし</option>
          </select>
          <label class="field-label" for="livingArrangement">同居状況</label>
          <select class="select-input bg-required" id="livingArrangement" name="living_arrangement">
            <option value="">選択してください</option>
            <option>一人暮らし</option><option>家族等と同居</option><option>施設・グループホーム</option><option>その他</option>
          </select>
          <label class="field-label" for="familySupport">同居家族からの支援</label>
          <select class="select-input bg-required" id="familySupport" name="family_support">
            <option value="">選択してください</option>
            <option>受けられる</option><option>少し受けられる</option><option>ほぼ受けられない</option><option>同居なし</option>
          </select>
          <label class="field-label" for="caregivingRole">本人が誰かのケアを担っていますか</label>
          <select class="select-input bg-required" id="caregivingRole" name="caregiving_role">
            <option value="">選択してください</option>
            <option>なし</option><option>子どものケア</option><option>親・配偶者等のケア</option><option>その他</option>
          </select>
          <label class="field-label" for="travelTimeOneWay">通院にかかる片道時間</label>
          <select class="select-input bg-required" id="travelTimeOneWay" name="travel_time_one_way">
            <option value="">選択してください</option>
            <option>30分未満</option><option>30-60分</option><option>60-90分</option><option>90分以上</option>
          </select>
          <label class="field-label" for="transport">主な通院手段</label>
          <select class="select-input bg-required" id="transport" name="transport">
            <option value="">選択してください</option>
            <option>自分で運転</option><option>公共交通</option><option>家族送迎</option><option>福祉交通・タクシー</option><option>徒歩・自転車</option><option>その他</option>
          </select>
          <label class="field-label" for="homeNursingCurrent">訪問看護の現在利用</label>
          <select class="select-input bg-required" id="homeNursingCurrent" name="home_nursing_current">
            <option value="">選択してください</option>
            <option>あり</option><option>過去あり</option><option>なし</option>
          </select>
          <label class="field-label" for="mainIncomeSource">主な収入源</label>
          <select class="select-input bg-required" id="mainIncomeSource" name="main_income_source">
            <option value="">選択してください</option>
            <option>就労収入</option><option>障害年金</option><option>生活保護</option><option>家族支援</option><option>その他</option><option>答えたくない</option>
          </select>
          <label class="field-label" for="publicAssistance">生活保護</label>
          <select class="select-input bg-required" id="publicAssistance" name="public_assistance">
            <option value="">選択してください</option>
            <option>あり</option><option>なし</option><option>答えたくない</option>
          </select>
          <label class="field-label" for="economicStrain">経済的余裕</label>
          <select class="select-input bg-required" id="economicStrain" name="economic_strain">
            <option value="">選択してください</option>
            <option>困っていない</option><option>少し困る</option><option>かなり困る</option><option>答えたくない</option>
          </select>
        </div>
        <div class="nav"><button class="primary" onclick="nextParticipantCode()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="3">
        <img class="hero" id="infoStepHero1" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2 id="infoStepTitle1">クロザピンの情報</h2>
        <div id="infoStepBody1"></div>
        <div class="nav" id="infoStepNav1"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="4">
        <img class="hero" id="infoStepHero2" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2 id="infoStepTitle2">クロザピンの情報</h2>
        <div id="infoStepBody2"></div>
        <div class="nav" id="infoStepNav2"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="5">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>クロザピン服用について</h2>
        <p class="scenarioText"></p>
        <p>ここまでの有効性、副作用、採血・体調確認の説明を踏まえてお答えください。</p>
        <p class="question">クロザピンという薬を使うこと自体を前向きに考えたいですか？</p>
        {yes_no_choices("clozapine_accept")}
        <p class="small">選択すると次へ進みます。</p>
        <div class="nav"><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="6">
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

      <section class="step" data-step="7">
        <img class="hero" src="{ASSET_PREFIX}/monitoring.png" alt="">
        <h2>通院だけで始める場合</h2>
        <p class="scenarioText"></p>
        <p>ここからは、入院せず外来でクロザピンを始める具体的な条件について伺います。最初6週間の通院頻度について、負担が大きい条件から順に伺います。</p>
        <div class="tt-card">
          <span class="pill" id="visitProgress">1/3</span>
          <h3 id="visitQuestion">最初6週間は週3回通院</h3>
          <p class="small">この条件でクロザピン服用を前向きに考えたいですか？</p>
        </div>
        <p class="small">7週目以降も定期通院と採血は続きます。体調に異常があれば、必要時は入院へ切り替えます。</p>
        <div class="nav"><button class="primary" onclick="answerVisit(true)">はい</button><button onclick="answerVisit(false)">いいえ</button><button onclick="prevVisit()">前へ</button></div>
      </section>

      <section class="step" data-step="8">
        <img class="hero" src="{ASSET_PREFIX}/outpatient_visit.png" alt="">
        <h2>訪問看護を加えて確認する場合</h2>
        <p>安全に必要な確認頻度は医師が判断します。ここでは、先ほど受け入れられると答えた通院頻度を固定したまま、訪問看護を加えた確認頻度をどこまで受け入れられるかを伺います。</p>
        <div class="tt-card">
          <span class="pill" id="supportProgress">1/3</span>
          <h3 id="supportQuestion">週5回確認</h3>
          <p class="small" id="supportDescription"></p>
        </div>
        <div id="supportChoices"></div>
        <div class="nav"><button onclick="prevSupport()">前へ</button></div>
      </section>

      <section class="step" data-step="9">
        <h2>回答ありがとうございました</h2>
        <p>ダミー質問票の確認はここまでです。実際の調査では、この回答内容を保存して解析します。</p>
        <div class="summary">
          <strong>入院導入:</strong> <span id="inpatientSummary">未回答</span><br>
          <strong>外来導入の通院条件:</strong> <span id="thresholdSummary">未回答</span><br>
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
let supportBaseVisit = null;
let inpatientAccept = null;
let participantCode = null;
let infoOrder = null;
let effectivenessAnswer = null;
const participantCodeMap = {
  ACT001: {frame:'actual_current', order:'efficacy_first', label:'現在の状態で回答'},
  ACT002: {frame:'actual_current', order:'side_effect_first', label:'現在の状態で回答'},
  HYP001: {frame:'hypothetical_future', order:'efficacy_first', label:'将来TRS相当を想定して回答'},
  HYP002: {frame:'hypothetical_future', order:'side_effect_first', label:'将来TRS相当を想定して回答'}
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
  V2: ['V2N3','V2N1'],
  V1: ['V1N4','V1N2','V1N1'],
  NONE: []
};
const supportLabels = {
  V3N2:'週5回確認: 週3回通院+週2回訪問看護',
  V2N3:'週5回確認: 週2回通院+週3回訪問看護',
  V1N4:'週5回確認: 週1回通院+週4回訪問看護',
  V2N1:'週3回確認: 週2回通院+週1回訪問看護',
  V1N2:'週3回確認: 週1回通院+週2回訪問看護',
  V1N1:'週2回確認: 週1回通院+週1回訪問看護'
};
const supportAnswers = {};
function renderStep(){
  steps.forEach((s,i)=>s.classList.toggle('active', i===current));
  document.getElementById('stepNow').textContent = String(current+1);
  document.getElementById('stepTotal').textContent = String(steps.length);
  document.querySelectorAll('.scenarioText').forEach(el => el.textContent = scenarioText());
  if(current === 3 || current === 4) renderInfoStep(current);
  if(current === 7) renderVisitQuestion();
  if(current === 8) renderSupportQuestion();
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
}
function next(){ if(current < steps.length-1){ current++; renderStep(); } }
function prev(){
  if(current === 9){
    if(threshold === 'NO_CLOZAPINE') current = 5;
    else if(supportEligible()) current = 8;
    else current = 7;
    renderStep(); return;
  }
  if(current === 8){ current = 7; renderStep(); return; }
  if(current > 0){
    const target = current - 1;
    if(target === 2){
      responseFrame = null;
      participantCode = null;
      infoOrder = null;
      document.getElementById('participantCode').value = '';
      const box = document.getElementById('scenarioBox');
      box.textContent = '';
      box.classList.add('hidden');
      resetAfterNeed();
    } else if(target === 3){
      resetInfoAnswers();
      resetAfterNeed();
    } else if(target === 4){
      clearChecked('clozapine_accept');
      resetAfterClozapine();
    } else if(target === 5){
      clearChecked('inpatient_accept');
      inpatientAccept = null;
      document.getElementById('inpatientSummary').textContent = '未回答';
      resetAfterInpatient();
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
  if(!validateBackgroundFields()) return;
  resetAfterNeed();
  participantCode = raw;
  responseFrame = match.frame;
  infoOrder = match.order;
  box.textContent = `${match.label}: ${scenarioText()}`;
  box.classList.remove('hidden');
  next();
}
function validateBackgroundFields(){
  const missing = Array.from(document.querySelectorAll('.bg-required')).filter(el => !el.value);
  if(missing.length){
    missing[0].focus();
    alert('生活・通院背景で未回答の項目があります。');
    return false;
  }
  return true;
}
function firstInfoKind(){
  return infoOrder === 'side_effect_first' ? 'side_effect' : 'efficacy';
}
function infoKindForStep(step){
  const first = firstInfoKind();
  if(step === 3) return first;
  return first === 'efficacy' ? 'side_effect' : 'efficacy';
}
function renderInfoStep(step){
  const kind = infoKindForStep(step);
  const suffix = step === 3 ? '1' : '2';
  document.getElementById(`infoStepHero${suffix}`)?.setAttribute('src', kind === 'efficacy' ? '../patient_survey_mock/assets/clozapine_info.png' : '../patient_survey_mock/assets/monitoring.png');
  if(kind === 'efficacy') renderEfficacyQuestion(suffix);
  else renderSideEffectQuestion(suffix);
}
function renderEfficacyQuestion(suffix){
  document.getElementById(`infoStepTitle${suffix}`).textContent = '期待される有効性';
  document.getElementById(`infoStepBody${suffix}`).innerHTML = `
    <p class="scenarioText">${scenarioText()}</p>
    <p>クロザピンは、複数の抗精神病薬で十分に改善しない統合失調症に対して、症状や生活のしづらさを改善する可能性がある薬です。</p>
    <p>すべての人に十分効くわけではありませんが、他の治療で改善が乏しい場合に、改善を期待して検討されます。</p>
    <p class="question">このような改善可能性は、クロザピンを試す理由としてどの程度十分だと思いますか？</p>
    <div class="seg">
      <label><input type="radio" name="efficacy_sufficiency" value="1"> 1. まったく十分ではない</label>
      <label><input type="radio" name="efficacy_sufficiency" value="2"> 2. あまり十分ではない</label>
      <label><input type="radio" name="efficacy_sufficiency" value="3"> 3. どちらともいえない</label>
      <label><input type="radio" name="efficacy_sufficiency" value="4"> 4. ある程度十分だと思う</label>
      <label><input type="radio" name="efficacy_sufficiency" value="5"> 5. 十分だと思う</label>
    </div>
    <p class="small">選択すると次へ進みます。</p>
  `;
  document.getElementById(`infoStepNav${suffix}`).innerHTML = '<button onclick="prev()">前へ</button>';
  document.querySelectorAll('input[name="efficacy_sufficiency"]').forEach(input => {
    input.checked = effectivenessAnswer === input.value;
    input.addEventListener('change', () => {
      effectivenessAnswer = input.value;
      next();
    });
  });
}
function renderSideEffectQuestion(suffix){
  document.getElementById(`infoStepTitle${suffix}`).textContent = '副作用可能性の影響';
  const [key, label, frequency, description] = sideEffects[sideEffectIndex];
  document.getElementById(`infoStepBody${suffix}`).innerHTML = `
    <p>以下の副作用の可能性は、クロザピン服用を前向きに考えるうえで、どの程度妨げになりますか？</p>
    <div class="tt-card">
      <span class="pill">${sideEffectIndex + 1}/${sideEffects.length}</span>
      <h3>${label}</h3>
      <p class="small"><strong>${frequency}</strong></p>
      <p class="small">${description}</p>
    </div>
    <div class="seg">
      <label><input type="radio" name="side_effect_current" value="1"> 1. まったく妨げにならない</label>
      <label><input type="radio" name="side_effect_current" value="2"> 2. あまり妨げにならない</label>
      <label><input type="radio" name="side_effect_current" value="3"> 3. やや妨げになる</label>
      <label><input type="radio" name="side_effect_current" value="4"> 4. かなり妨げになる</label>
      <label><input type="radio" name="side_effect_current" value="5"> 5. 服用を考えられないほど妨げになる</label>
    </div>
    <p class="small">選択すると次へ進みます。</p>
  `;
  document.getElementById(`infoStepNav${suffix}`).innerHTML = '<button onclick="prevSideEffect()">前へ</button>';
  document.querySelectorAll('input[name="side_effect_current"]').forEach(input => {
    input.checked = sideEffectAnswers[key] === input.value;
    input.addEventListener('change', nextSideEffect);
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
    renderStep();
    return;
  }
  next();
}
function prevSideEffect(){
  if(sideEffectIndex > 0){
    sideEffectIndex--;
    renderStep();
    return;
  }
  prev();
  renderStep();
}
function nextClozapine(){
  const val = document.querySelector('input[name="clozapine_accept"]:checked')?.value;
  if(!val){ alert('はい、または、いいえを選んでください。'); return; }
  resetAfterClozapine();
  if(val === 'no'){
    threshold = 'NO_CLOZAPINE';
    document.getElementById('thresholdSummary').textContent = 'クロザピン服用自体を前向きに考えにくい';
    current = 9; renderStep(); return;
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
    supportBaseVisit = threshold;
    current = 8;
    renderStep();
    return;
  }
  if(visitIndex < visitQuestions.length - 1){
    visitIndex++;
    renderStep();
    return;
  }
  threshold = 'NONE';
  setThresholdSummary();
  current = 9;
  renderStep();
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
function supportEligible(){
  return ['V3','V2','V1'].includes(threshold);
}
function renderSupportQuestion(){
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  if(!options.length){
    current = 9;
    renderStep();
    return;
  }
  const key = options[supportIndex];
  document.getElementById('supportProgress').textContent = `${supportIndex + 1}/${options.length}`;
  document.getElementById('supportQuestion').textContent = supportLabels[key];
  const choices = document.getElementById('supportChoices');
  document.getElementById('supportDescription').textContent = '医師からこの確認頻度が安全上必要だと説明された場合を想像してください。';
  choices.innerHTML = `
    <p class="question">この条件までなら、クロザピン服用を前向きに考えたいですか？</p>
    <div class="seg">
      <label><input type="radio" name="support_current" value="accepted"> はい</label>
      <label><input type="radio" name="support_current" value="refused"> いいえ</label>
      <label><input type="radio" name="support_current" value="unsure"> わからない</label>
    </div>
    <p class="small">「いいえ」または「わからない」の場合は、確認頻度を少なくした条件へ進みます。</p>
  `;
  document.querySelectorAll('input[name="support_current"]').forEach(input => {
    input.checked = supportAnswers[key] === input.value;
    input.onchange = () => answerSupport(input.value);
  });
}
function answerSupport(answer){
  resetAfterSupport();
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'];
  const key = options[supportIndex];
  supportAnswers[key] = answer;
  if(answer === 'accepted'){
    document.getElementById('supportSummary').textContent = `${supportLabels[key]}なら前向きに考えたい`;
    current = 9; renderStep(); return;
  }
  if(supportIndex < options.length - 1){
    supportIndex++;
    renderSupportQuestion();
    return;
  }
  document.getElementById('supportSummary').textContent = '訪問看護追加は前向きに考えにくい/不明';
  current = 9; renderStep();
}
function prevSupport(){
  if(supportIndex > 0){
    supportIndex--;
    renderSupportQuestion();
    return;
  }
  current = 7;
  renderStep();
}
function clearChecked(name){
  document.querySelectorAll(`input[name="${name}"]`).forEach(input => input.checked = false);
}
function resetAfterNeed(){
  resetInfoAnswers();
  clearChecked('clozapine_accept');
  resetAfterClozapine();
}
function resetAfterClozapine(){
  inpatientAccept = null;
  clearChecked('inpatient_accept');
  document.getElementById('inpatientSummary').textContent = '未回答';
  resetAfterOutpatient();
}
function resetAfterInpatient(){
  resetAfterOutpatient();
}
function resetAfterOutpatient(){
  visitIndex = 0;
  threshold = null;
  supportBaseVisit = null;
  document.getElementById('thresholdSummary').textContent = '未回答';
  resetAfterVisit();
}
function resetAfterVisit(){
  supportIndex = 0;
  supportBaseVisit = null;
  Object.keys(supportAnswers).forEach(key => delete supportAnswers[key]);
  document.getElementById('supportSummary').textContent = '該当なし/未回答';
  clearChecked('support_current');
}
function resetAfterSupport(){
  const options = supportByThreshold[supportBaseVisit || threshold || 'NONE'] || [];
  for(let i = supportIndex; i < options.length; i++){
    delete supportAnswers[options[i]];
  }
  clearChecked('support_current');
}
function resetInfoAnswers(){
  sideEffectIndex = 0;
  effectivenessAnswer = null;
  Object.keys(sideEffectAnswers).forEach(key => delete sideEffectAnswers[key]);
  clearChecked('side_effect_current');
  clearChecked('efficacy_sufficiency');
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
    .select-input{box-sizing:border-box;width:100%;border:1px solid #9fb3bd;border-radius:8px;padding:12px;font-size:16px;background:white}
    .background-block{border-top:1px solid #d8dee4;margin-top:14px;padding-top:10px}
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
