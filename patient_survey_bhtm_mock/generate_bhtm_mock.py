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
            "主要アウトカムを“クロザピン服用自体の受容性”と“外来導入時の初期通院頻度threshold”に固定。",
            "安全性検証研究の説明希望はこの短縮質問票から外し、受容閾値の測定を優先。",
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
    ("V3N0", "週3回確認: 週3回通院"),
    ("V2N1", "週3回確認: 週2回通院+週1回訪問看護"),
    ("V1N2", "週3回確認: 週1回通院+週2回訪問看護"),
    ("V2N0", "週2回確認: 週2回通院"),
    ("V1N1", "週2回確認: 週1回通院+週1回訪問看護"),
    ("NONE", "どれも難しい"),
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
        participants.append(
            {
                "participant_id": f"P{i:03d}",
                "target_group": target,
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
        vignette.append(
            {
                "participant_id": f"P{i:03d}",
                "inpatient_now_accept": str(int(inpatient_now)),
                "outpatient_now_accept": str(int(outpatient_now)),
                "inpatient_worse_accept": str(int(inpatient_worse)),
                "outpatient_worse_accept": str(int(outpatient_worse)),
            }
        )

        side_effect_impact = min(5, max(1, int(round(RNG.normalvariate(3.1 + 0.45 * past_refusal, 1.0)))))
        score = RNG.random()
        if not outpatient_now and not outpatient_worse:
            th = "NONE" if score < 0.58 else "V1"
        elif score < 0.18 + 0.06 * unmet - 0.04 * (side_effect_impact >= 4):
            th = "V3"
        elif score < 0.45 + 0.08 * unmet:
            th = "V2"
        elif score < 0.84 - 0.05 * (side_effect_impact >= 5):
            th = "V1"
        else:
            th = "NONE"
        max_burden = dict(THRESHOLDS)[th]
        if th == "V3":
            support = weighted_choice([("V3N2", 0.45), ("V3N0", 0.35), ("V2N1", 0.12), ("NONE", 0.08)])
        elif th == "V2":
            support = weighted_choice([("V2N3", 0.18), ("V2N1", 0.34), ("V2N0", 0.24), ("V1N2", 0.16), ("NONE", 0.08)])
        elif th == "V1":
            support = weighted_choice([("V1N4", 0.10), ("V1N2", 0.26), ("V1N1", 0.34), ("V3N0", 0.08), ("NONE", 0.22)])
        else:
            support = weighted_choice([("V3N2", 0.08), ("V2N3", 0.10), ("V1N4", 0.12), ("V1N1", 0.12), ("NONE", 0.58)])
        biggest = weighted_choice(
            [
                ("通院回数", 0.33),
                ("入院になる可能性", 0.23),
                ("採血", 0.15),
                ("副作用への不安", 0.18),
                ("家族・仕事・生活調整", 0.11),
            ]
        )
        threshold.append(
            {
                "participant_id": f"P{i:03d}",
                "clozapine_accept": str(int(outpatient_now or outpatient_worse or th != "NONE")),
                "threshold": th,
                "threshold_label": max_burden,
                "side_effect_impact": str(side_effect_impact),
                "preferred_support_package": support,
                "preferred_support_label": dict(SUPPORT_PACKAGES)[support],
                "biggest_burden": biggest,
            }
        )
        physician_expect = RNG.random() < (0.30 + 0.20 * unmet - 0.10 * past_refusal)
        patient_accept_outpatient = th != "NONE" or support != "NONE"
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
    threshold = data["threshold_responses"]
    gap = data["physician_patient_gap"]

    clozapine_counts = Counter(r["clozapine_accept"] for r in threshold)
    p = FIG / f"bhtm_v{version}_fig1_clozapine_accept.svg"
    bar_svg(
        p,
        "図1. クロザピン服用自体の受容性",
        ["前向きに考えたい", "前向きに考えにくい/保留"],
        [clozapine_counts["1"], clozapine_counts["0"]],
        "人数",
    )
    fig_paths["fig1"] = rel(p)

    total_counts = Counter(r["threshold"] for r in threshold)
    group_counts: dict[str, Counter] = {"全体": total_counts}
    p = FIG / f"bhtm_v{version}_fig2_threshold.svg"
    stacked_svg(p, "図2. 外来導入burden thresholdの分布", group_counts)
    fig_paths["fig2"] = rel(p)

    rows: dict[str, Counter] = defaultdict(Counter)
    for r in threshold:
        rows[participants[r["participant_id"]]["target_group"]][r["threshold"]] += 1
    p = FIG / f"bhtm_v{version}_fig3_threshold_by_group.svg"
    stacked_svg(p, "図3. 対象集団別のburden threshold", dict(rows))
    fig_paths["fig3"] = rel(p)

    burden_counts = Counter(r["side_effect_impact"] for r in threshold)
    ordered = ["1", "2", "3", "4", "5"]
    p = FIG / f"bhtm_v{version}_fig4_burden.svg"
    bar_svg(p, "図4. 副作用可能性が服用判断を妨げる程度", ordered, [burden_counts[k] for k in ordered], "Likert score")
    fig_paths["fig4"] = rel(p)

    support_counts = Counter(r["preferred_support_package"] for r in threshold)
    ordered_s = SUPPORT_PACKAGES
    p = FIG / f"bhtm_v{version}_fig5_recruit.svg"
    stacked_category_svg(p, "図5. 最も前向きに考えやすい外来モニタリング条件", support_counts, ordered_s)
    fig_paths["fig5"] = rel(p)

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
    p = FIG / f"bhtm_v{version}_fig6_gap.svg"
    matrix_svg(p, "図6. 医師予測と患者本人の外来受容性", both, physician_only, patient_only, neither)
    fig_paths["fig6"] = rel(p)
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
    rows = [
        ("解析対象者", f"{n}"),
        ("TRS適格候補", f"{target['TRS適格候補']} ({target['TRS適格候補']/n*100:.1f}%)"),
        ("広い未使用外来患者", f"{target['広い未使用外来患者']} ({target['広い未使用外来患者']/n*100:.1f}%)"),
        ("現在の治療で残る困りごとあり", f"{unmet['あり']} ({unmet['あり']/n*100:.1f}%)"),
        ("主観的困りごと/つらさあり", f"{distress['あり']} ({distress['あり']/n*100:.1f}%)"),
    ]
    return "<table><tr><th>項目</th><th>値</th></tr>" + "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rows) + "</table>"


def figure_mock_html(version: int, data: dict[str, list[dict[str, str]]], figs: dict[str, str]) -> str:
    v = VERSIONS[version]
    visible = ["fig1", "fig2"]
    if version >= 2:
        visible.append("fig3")
    if version >= 3:
        visible.append("fig4")
    if version >= 4:
        visible.append("fig5")
    if version >= 5:
        visible.append("fig6")
    reasons = {
        "fig1": "外来導入レジメン以前に、クロザピン服用そのものを前向きに考えられるかを示す入口の図。Gee 2017やJakobsen 2025で示されたように、患者本人の受容性は医療者の想定より高い可能性があるため、まず服用自体の受容性を切り出す。",
        "fig2": "通院頻度をprimary thresholdとして扱う中核図。訪問看護の有無はここでは動かさず、外来導入を受け入れるために必要な初期通院頻度を示す。",
        "fig3": "対象集団をTRS適格候補と広い未使用外来患者に分けることで、来年度安全性検証研究の潜在対象者と、一般的な潜在ニーズを分けて議論できる。",
        "fig4": "副作用の不安そのものではなく、服用判断への影響度として測定する。クロザピン服用自体の受容性や、高頻度モニタリング/訪問看護選好を修飾する因子として扱う。",
        "fig5": "訪問看護は負担にも安心材料にもなりうるため、通院頻度thresholdとは別にsupport modifierとして提示する。週あたり総モニタリング回数が5回、3回、2回になるよう通院頻度ごとに訪問看護頻度を調整した条件を比較する。",
        "fig6": "患者調査を臨床家調査と接続する図。Jakobsen 2025の示唆に沿い、医師が非受容と想定する患者の中にも外来導入なら受け入れる層がいるかを示す。",
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
        <h2>現在の治療への感じ方</h2>
        <p>現在の治療について、いちばん近いものを選んでください。</p>
        <label class="choice"><input type="radio" name="current_need" value="low"> 症状による困りごとは少ない</label>
        <label class="choice"><input type="radio" name="current_need" value="some"> 症状による困りごとや生活のしづらさがいくらか残っている</label>
        <label class="choice"><input type="radio" name="current_need" value="large"> 症状による困りごとや生活のしづらさが大きい</label>
        <div id="scenarioBox" class="notice hidden"></div>
        <div class="nav"><button class="primary" onclick="nextNeed()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="3">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>クロザピン服用について</h2>
        <p class="scenarioText"></p>
        <p>主治医からクロザピンを勧められたとします。</p>
        <p class="question">クロザピン服用を前向きに考えたいですか？</p>
        {yes_no_choices("clozapine_accept")}
        <div class="nav"><button class="primary" onclick="nextClozapine()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="4">
        <h2>副作用可能性の影響</h2>
        <p>クロザピンの副作用の可能性は、クロザピン服用を前向きに考えるうえで、どの程度妨げになりますか？</p>
        <div class="seg">
          <label><input type="radio" name="side_effect_impact" value="1"> 1. まったく妨げにならない</label>
          <label><input type="radio" name="side_effect_impact" value="2"> 2. あまり妨げにならない</label>
          <label><input type="radio" name="side_effect_impact" value="3"> 3. どちらともいえない</label>
          <label><input type="radio" name="side_effect_impact" value="4"> 4. かなり妨げになる</label>
          <label><input type="radio" name="side_effect_impact" value="5"> 5. 服用を考えられないほど妨げになる</label>
        </div>
        <div class="nav"><button class="primary" onclick="next()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="5">
        <img class="hero" src="{ASSET_PREFIX}/monitoring.png" alt="">
        <h2>通院だけで始める場合</h2>
        <p class="scenarioText"></p>
        <p>入院せず外来でクロザピンを始める場合、以下の通院頻度だけで前向きに考えられるかを選んでください。</p>
        <div class="mini-question">
          <p class="question">最初6週間は週3回通院</p>
          {yes_no_choices("visit3")}
        </div>
        <div class="mini-question">
          <p class="question">最初6週間は週2回通院</p>
          {yes_no_choices("visit2")}
        </div>
        <div class="mini-question">
          <p class="question">最初6週間は週1回通院</p>
          {yes_no_choices("visit1")}
        </div>
        <p class="small">7週目以降も定期通院と採血は続きます。体調に異常があれば、必要時は入院へ切り替えます。</p>
        <div class="nav"><button class="primary" onclick="nextVisit()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="6">
        <img class="hero" src="{ASSET_PREFIX}/outpatient_visit.png" alt="">
        <h2>訪問看護を含む場合</h2>
        <p>通院に訪問看護を組み合わせる場合、最も前向きに考えやすい条件を1つ選んでください。</p>
        <div class="support-grid">
          <label class="choice"><input type="radio" name="support_package" value="V3N2"> 週5回確認: 週3回通院+週2回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="V2N3"> 週5回確認: 週2回通院+週3回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="V1N4"> 週5回確認: 週1回通院+週4回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="V3N0"> 週3回確認: 週3回通院</label>
          <label class="choice"><input type="radio" name="support_package" value="V2N1"> 週3回確認: 週2回通院+週1回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="V1N2"> 週3回確認: 週1回通院+週2回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="V2N0"> 週2回確認: 週2回通院</label>
          <label class="choice"><input type="radio" name="support_package" value="V1N1"> 週2回確認: 週1回通院+週1回訪問看護</label>
          <label class="choice"><input type="radio" name="support_package" value="NONE"> どれも前向きに考えにくい</label>
        </div>
        <div class="nav"><button class="primary" onclick="nextSupport()">次へ</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step optional" data-step="7">
        <h2>前向きに考えにくい理由</h2>
        <p>クロザピン服用や外来導入を前向きに考えにくい理由として、最も近いものを1つ選んでください。</p>
        <label class="choice"><input type="radio" name="biggest_burden" value="effect"> 効果が期待できるか分からない</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="side_effects"> 副作用や忍容性が心配</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="visits"> 通院や訪問看護の回数が負担</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="blood"> 採血が負担</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="stable"> 今の治療のままでよい</label>
        <div class="nav"><button class="primary" onclick="finish()">完了</button><button onclick="prev()">前へ</button></div>
      </section>

      <section class="step" data-step="8">
        <h2>回答ありがとうございました</h2>
        <p>ダミー質問票の確認はここまでです。実際の調査では、この回答内容を保存して解析します。</p>
        <div class="summary">
          <strong>通院頻度threshold:</strong> <span id="thresholdSummary">未回答</span><br>
          <strong>選んだモニタリング条件:</strong> <span id="supportSummary">未回答</span>
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
let supportChoice = null;
let assumedState = null;
const supportLabels = {
  V3N2:'週5回確認: 週3回通院+週2回訪問看護',
  V2N3:'週5回確認: 週2回通院+週3回訪問看護',
  V1N4:'週5回確認: 週1回通院+週4回訪問看護',
  V3N0:'週3回確認: 週3回通院',
  V2N1:'週3回確認: 週2回通院+週1回訪問看護',
  V1N2:'週3回確認: 週1回通院+週2回訪問看護',
  V2N0:'週2回確認: 週2回通院',
  V1N1:'週2回確認: 週1回通院+週1回訪問看護',
  NONE:'どれも前向きに考えにくい'
};
function renderStep(){
  steps.forEach((s,i)=>s.classList.toggle('active', i===current));
  document.getElementById('stepNow').textContent = String(current+1);
  document.getElementById('stepTotal').textContent = String(steps.length);
  document.querySelectorAll('.scenarioText').forEach(el => el.textContent = scenarioText());
  window.scrollTo({top:0, behavior:'smooth'});
}
function next(){ if(current < steps.length-1){ current++; renderStep(); } }
function prev(){
  if(current === 8){ current = supportChoice === 'NONE' ? 7 : 6; renderStep(); return; }
  if(current > 0){ current--; renderStep(); }
}
function nextNeed(){
  const val = document.querySelector('input[name="current_need"]:checked')?.value;
  const box = document.getElementById('scenarioBox');
  if(!val){ box.textContent = 'いちばん近いものを選んでください。'; box.classList.remove('hidden'); return; }
  if(val === 'low'){
    assumedState = Math.random() < 0.5 ? 'some' : 'large';
    box.textContent = scenarioText();
    box.classList.remove('hidden');
  } else {
    assumedState = val;
    box.classList.add('hidden');
  }
  next();
}
function nextClozapine(){
  const val = document.querySelector('input[name="clozapine_accept"]:checked')?.value;
  if(!val){ alert('はい、または、いいえを選んでください。'); return; }
  if(val === 'no'){
    threshold = 'NO_CLOZAPINE';
    document.getElementById('thresholdSummary').textContent = 'クロザピン服用自体を前向きに考えにくい';
    current = 7; renderStep(); return;
  }
  next();
}
function nextVisit(){
  const v3 = document.querySelector('input[name="visit3"]:checked')?.value;
  const v2 = document.querySelector('input[name="visit2"]:checked')?.value;
  const v1 = document.querySelector('input[name="visit1"]:checked')?.value;
  if(!v3 || !v2 || !v1){ alert('3つの通院頻度すべてについて選んでください。'); return; }
  if(v1 === 'yes') threshold = 'V1';
  else if(v2 === 'yes') threshold = 'V2';
  else if(v3 === 'yes') threshold = 'V3';
  else threshold = 'NONE';
  const labels = {V1:'週1回通院なら受容', V2:'週2回通院なら受容', V3:'週3回通院なら受容', NONE:'通院のみ条件は非受容/保留'};
  document.getElementById('thresholdSummary').textContent = labels[threshold];
  next();
}
function nextSupport(){
  const val = document.querySelector('input[name="support_package"]:checked')?.value;
  if(!val){ alert('最も前向きに考えやすい条件を選んでください。'); return; }
  supportChoice = val;
  document.getElementById('supportSummary').textContent = supportLabels[val];
  if(val === 'NONE'){ current = 7; renderStep(); return; }
  current = 8; renderStep();
}
function scenarioText(){
  if(assumedState === 'some') return '以下では「症状による困りごとや生活のしづらさがいくらか残っている」状態で、主治医からクロザピンを勧められたと想像してください。';
  if(assumedState === 'large') return '以下では「症状による困りごとや生活のしづらさが大きい」状態で、主治医からクロザピンを勧められたと想像してください。';
  return '以下では、主治医からクロザピンを勧められた場面を想像してください。';
}
function finish(){
  alert('ダミー質問票です。実際の回答は保存されません。');
}
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
