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
            "主要アウトカムを“入院非受容/外来受容”と“外来導入burden threshold”に固定。",
            "安全性検証研究の説明希望は最後に置き、わからないを許容。",
            "医師判断との接続図表を加え、臨床家調査と患者調査を別論文でも接続できる構成にした。",
        ],
    },
}

THRESHOLDS = [
    ("L4", "週3回通院でも受容"),
    ("L3", "週2回通院なら受容"),
    ("L2", "週1回通院なら受容"),
    ("L1", "週1回+支援つきなら受容"),
    ("NONE", "外来導入も非受容/保留"),
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

        score = RNG.random()
        if not outpatient_now and not outpatient_worse:
            th = "NONE" if score < 0.62 else "L1"
        elif score < 0.16 + 0.10 * unmet:
            th = "L4"
        elif score < 0.37 + 0.12 * unmet:
            th = "L3"
        elif score < 0.68 + 0.10 * unmet:
            th = "L2"
        elif score < 0.89:
            th = "L1"
        else:
            th = "NONE"
        max_burden = dict(THRESHOLDS)[th]
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
                "threshold": th,
                "threshold_label": max_burden,
                "biggest_burden": biggest,
            }
        )
        physician_expect = RNG.random() < (0.30 + 0.20 * unmet - 0.10 * past_refusal)
        patient_accept_outpatient = th in {"L4", "L3", "L2", "L1"}
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
    colors = {"L4": "#0f766e", "L3": "#2f7d8c", "L2": "#78aab4", "L1": "#c7dbe0", "NONE": "#d8dee4"}
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
    lx, ly = left, height - 46
    for key, label in THRESHOLDS:
        parts.append(f'<rect x="{lx}" y="{ly}" width="14" height="14" fill="{colors[key]}"/>')
        parts.append(f'<text x="{lx+20}" y="{ly+12}" class="legend">{esc(label)}</text>')
        lx += 158
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
    vignette = data["vignette_responses"]
    participants = {r["participant_id"]: r for r in data["participants"]}
    threshold = data["threshold_responses"]
    gap = data["physician_patient_gap"]
    safety = data["safety_study_interest"]

    labels = ["今の状態で提案", "今より困りごとが強い場合"]
    inpatient = [
        sum(int(r["inpatient_now_accept"]) for r in vignette),
        sum(int(r["inpatient_worse_accept"]) for r in vignette),
    ]
    outpatient = [
        sum(int(r["outpatient_now_accept"]) for r in vignette),
        sum(int(r["outpatient_worse_accept"]) for r in vignette),
    ]
    p = FIG / f"bhtm_v{version}_fig1_vignette.svg"
    paired_svg(p, "図1. 入院導入と外来導入の受容性", labels, inpatient, outpatient)
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

    burden_counts = Counter(r["biggest_burden"] for r in threshold)
    ordered = ["通院回数", "入院になる可能性", "副作用への不安", "採血", "家族・仕事・生活調整"]
    p = FIG / f"bhtm_v{version}_fig4_burden.svg"
    bar_svg(p, "図4. 外来導入で最大の負担と感じる項目", ordered, [burden_counts[k] for k in ordered])
    fig_paths["fig4"] = rel(p)

    safety_counts = Counter(r["safety_study_interest"] for r in safety)
    ordered_s = ["説明を聞きたい", "わからない", "今は希望しない"]
    p = FIG / f"bhtm_v{version}_fig5_recruit.svg"
    bar_svg(p, "図5. 安全性検証研究の説明希望", ordered_s, [safety_counts[k] for k in ordered_s])
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
        "fig1": "Parikh 2023のように、有効性・重大安全性を固定したうえで投与/導入方法の直接選好を先に示す。ここでは、当局向けに重要な「入院なら難しいが外来なら前向き」というニーズを可視化する。",
        "fig2": "Hauber & Coulter 2020のThreshold Techniqueに対応する中核図。個人ごとの受容閾値を分布として示し、外来導入レジメンの負担をどこまで下げる必要があるかを示す。",
        "fig3": "対象集団をTRS適格候補と広い未使用外来患者に分けることで、来年度安全性検証研究の潜在対象者と、一般的な潜在ニーズを分けて議論できる。",
        "fig4": "Barrett 2005が扱ったように、治療選好には副作用だけでなく通院・生活調整などの実務負担が効く。DCEではなくBHTMにしても、最大負担を1項目だけ取ることで患者負担を抑えつつ改善点を拾う。",
        "fig5": "安全性検証研究のリクルート可能性を、選好調査の最後に低圧で確認する。'わからない'を許容し、強い同意取得ではなく説明希望として扱う。",
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
      <div class="progress"><span id="stepNow">1</span>/<span id="stepTotal">8</span></div>
    </header>

    <main class="phone-frame">
      <section class="step active" data-step="0">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>この調査について</h2>
        <p>この画面はダミーです。回答は保存されません。クロザピンを外来で始める方法について、どの条件なら前向きに考えられるかを伺います。</p>
        <button class="primary" onclick="next()">次へ</button>
      </section>

      <section class="step" data-step="1">
        <img class="hero" src="{ASSET_PREFIX}/clozapine_info.png" alt="">
        <h2>クロザピンについて</h2>
        <p>クロザピンは、複数の抗精神病薬で十分に良くならない統合失調症に使われる薬です。症状や生活のしづらさが改善する可能性があります。</p>
        <p>一方で、血液検査や体調確認が必要です。発熱、胸痛、息切れ、強い便秘などがあれば早めに相談し、必要に応じて入院に切り替えます。</p>
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="next()">理解しました</button></div>
      </section>

      <section class="step" data-step="2">
        <h2>対象確認</h2>
        <label class="choice"><input type="radio" name="clozapine_history" value="no"> 現在クロザピンを使用しておらず、過去にも使用したことはない</label>
        <label class="choice"><input type="radio" name="clozapine_history" value="yes"> 現在使用中、または過去に使用したことがある</label>
        <div id="excludeMsg" class="notice hidden">この調査では、クロザピン使用中または使用歴のある方は対象外です。</div>
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="nextEligibility()">次へ</button></div>
      </section>

      <section class="step" data-step="3">
        <h2>現在の治療への感じ方</h2>
        <p>現在の治療について、いちばん近いものを選んでください。</p>
        <label class="choice"><input type="radio" name="current_need" value="good"> 今の治療で困りごとは少なく、治療を大きく変えたいとは思わない</label>
        <label class="choice"><input type="radio" name="current_need" value="stable_unmet"> 大きく悪化はしていないが、症状や生活のしづらさが残っており、もっと良くなりたい</label>
        <label class="choice"><input type="radio" name="current_need" value="worse"> 今の治療では困りごとが大きく、治療の見直しを前向きに考えたい</label>
        <label class="choice"><input type="radio" name="current_need" value="unsure"> わからない</label>
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="next()">次へ</button></div>
      </section>

      <section class="step" data-step="4">
        <img class="hero" src="{ASSET_PREFIX}/inpatient_start.png" alt="">
        <h2>入院して始める場合</h2>
        <p>今の状態で主治医から「クロザピンを始めるなら、まず2〜4週間程度入院して体調確認をしながら始める」と提案された場合、どう感じますか？</p>
        {acceptance_choices("inpatient_now")}
        <p class="subq">今より症状や生活のしづらさが強くなった場合はどうですか？</p>
        {acceptance_choices("inpatient_worse")}
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="next()">次へ</button></div>
      </section>

      <section class="step" data-step="5">
        <img class="hero" src="{ASSET_PREFIX}/outpatient_visit.png" alt="">
        <h2>外来で始める場合</h2>
        <p>同じ効果と安全確認の考え方で、入院せず外来通院で始められる場合、どう感じますか？ 7週目以降も定期通院と採血は続きます。</p>
        {acceptance_choices("outpatient_now")}
        <p class="subq">今より症状や生活のしづらさが強くなった場合はどうですか？</p>
        {acceptance_choices("outpatient_worse")}
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="next()">次へ</button></div>
      </section>

      <section class="step" data-step="6">
        <img class="hero" src="{ASSET_PREFIX}/monitoring.png" alt="">
        <h2>外来導入の条件</h2>
        <p id="ttLead">外来で始める場合、どの条件なら前向きに考えられるかを順番に確認します。</p>
        <div id="ttCard" class="tt-card"></div>
        <div class="nav"><button onclick="ttBack()">前へ</button><button onclick="ttNo()">難しい</button><button class="primary" onclick="ttYes()">前向きに考えられる</button></div>
      </section>

      <section class="step" data-step="7">
        <h2>一番大きい負担</h2>
        <p>外来導入で一番大きい負担になりそうなものを1つ選んでください。</p>
        <label class="choice"><input type="radio" name="biggest_burden" value="visits"> 通院回数</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="blood"> 採血</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="side_effects"> 副作用への不安</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="admission"> 入院に切り替わる可能性</label>
        <label class="choice"><input type="radio" name="biggest_burden" value="life"> 家族・仕事・生活の調整</label>
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="next()">次へ</button></div>
      </section>

      <section class="step" data-step="8">
        <img class="hero" src="{ASSET_PREFIX}/safety_study.png" alt="">
        <h2>安全性検証研究について</h2>
        <p>条件が合えば、来年度の外来導入安全性検証研究について説明を聞きたいですか？</p>
        <label class="choice"><input type="radio" name="safety_interest" value="yes"> 説明を聞きたい</label>
        <label class="choice"><input type="radio" name="safety_interest" value="unsure"> わからない</label>
        <label class="choice"><input type="radio" name="safety_interest" value="no"> 今は希望しない</label>
        <div class="summary">
          <strong>外来導入の受容閾値:</strong> <span id="thresholdSummary">未回答</span>
        </div>
        <div class="nav"><button onclick="prev()">前へ</button><button class="primary" onclick="finish()">完了</button></div>
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


def questionnaire_js(final: bool, compact: bool) -> str:
    return r"""
const steps = Array.from(document.querySelectorAll('.step'));
let current = 0;
const ttLevels = [
  {code:'L4', title:'外来・高頻度確認', body:'最初6週間は週3回通院。診察、採血、体温・脈拍などを確認します。毎日、自宅で体調を確認します。'},
  {code:'L3', title:'外来・標準確認', body:'最初6週間は週2回通院。診察、採血、体調確認を行います。毎日、自宅で体調を確認します。'},
  {code:'L2', title:'外来・低頻度確認', body:'最初6週間は週1回通院。7週目以降も定期通院と採血を続けます。異常時はすぐ相談します。'},
  {code:'L1', title:'外来・支援つき低頻度確認', body:'最初6週間は週1回通院。訪問看護または電話支援が入り、体調確認や連絡を手伝います。採血場所は可能な範囲で相談します。'}
];
let ttIndex = 0;
let ttHistory = [];
let threshold = null;
function renderStep(){
  steps.forEach((s,i)=>s.classList.toggle('active', i===current));
  document.getElementById('stepNow').textContent = String(current+1);
  document.getElementById('stepTotal').textContent = String(steps.length);
  if(current === 6) renderTT();
  window.scrollTo({top:0, behavior:'smooth'});
}
function next(){ if(current < steps.length-1){ current++; renderStep(); } }
function prev(){ if(current > 0){ current--; renderStep(); } }
function nextEligibility(){
  const val = document.querySelector('input[name="clozapine_history"]:checked')?.value;
  const msg = document.getElementById('excludeMsg');
  if(val === 'yes'){ msg.classList.remove('hidden'); return; }
  msg.classList.add('hidden'); next();
}
function renderTT(){
  const card = document.getElementById('ttCard');
  const level = ttLevels[ttIndex];
  card.innerHTML = `<p class="pill">${level.code}</p><h3>${level.title}</h3><p>${level.body}</p><p class="small">すべての条件で、発熱・胸痛・息切れ・強い便秘などがあれば早めに相談し、必要時は入院へ切り替えます。</p>`;
}
function ttYes(){
  threshold = ttLevels[ttIndex].code;
  document.getElementById('thresholdSummary').textContent = `${threshold}: ${ttLevels[ttIndex].title}`;
  current = 7; renderStep();
}
function ttNo(){
  ttHistory.push(ttIndex);
  if(ttIndex < ttLevels.length-1){ ttIndex++; renderTT(); return; }
  threshold = 'NONE';
  document.getElementById('thresholdSummary').textContent = '外来導入も非受容/保留';
  current = 7; renderStep();
}
function ttBack(){
  if(ttHistory.length){ ttIndex = ttHistory.pop(); renderTT(); return; }
  prev();
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
    h2{font-size:19px;margin:4px 0 10px}h3{font-size:18px;margin:4px 0}.subq{font-weight:700;margin-top:16px}.small{font-size:13px;color:#52616b}
    .choice,.seg label{display:block;border:1px solid #cbd5df;border-radius:8px;padding:12px;margin:8px 0;background:#fbfcfd;font-weight:600}
    input{margin-right:8px}.seg{display:grid;gap:0}
    button{border:1px solid #9fb3bd;background:white;color:#245b67;border-radius:8px;padding:12px 14px;font-weight:700;font-size:15px}
    .primary{background:#2f7d8c;color:white;border-color:#2f7d8c}
    .nav{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:14px}.nav .primary:last-child{grid-column:auto}
    .notice{border-left:4px solid #c2410c;background:#fff7ed;padding:10px;margin:10px 0}.hidden{display:none}
    .tt-card{border:2px solid #2f7d8c;border-radius:12px;padding:14px;background:#f3f8f9}.pill{display:inline-block;background:#2f7d8c;color:white;border-radius:999px;padding:2px 10px;font-weight:700;margin:0 0 4px}
    .summary{background:#eef6f7;border:1px solid #b8d6dc;border-radius:8px;padding:10px;margin-top:14px}
    @media (max-width:420px){.phone-frame{padding:6px}.step{border-radius:0;border-left:0;border-right:0}.nav{grid-template-columns:1fr}button{width:100%}}
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

