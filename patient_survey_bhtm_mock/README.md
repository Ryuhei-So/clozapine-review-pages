# 患者調査 BHTM / Threshold Technique モック

患者調査側をDCEではなく、Vignette比較 + BHTM/Threshold Techniqueとして設計し直したモック。

## 入口

- `index.html`
  - v1〜v5の図表モック・質問票へのリンク集。
- `patient_survey_bhtm_v5_figures_mock.html`
  - 現時点の推奨図表構成。
- `patient_survey_bhtm_v5_questionnaire.html`
  - 現時点の推奨インタラクティブ質問票。

## 5回のブラッシュアップ

1. v1: DCEからBHTM/TTへ置換した最小構成。
2. v2: benefit/harm固定と、入院導入/外来導入の直接選好を分離。
3. v3: adaptive TTとnon-trading responseを実装。
4. v4: 患者の読みやすさを優先し、視覚情報と1画面1判断へ寄せた。
5. v5: 主要アウトカム、外来導入burden threshold、安全性検証研究リクルート、医師判断との接続を統合した最終候補。

## 方法論上の位置づけ

- 主要アウトカム1: 入院導入は非受容/保留だが、外来導入なら受容/前向きの割合。
- 主要アウトカム2: 外来導入burden threshold。
- benefitと重大なharm説明は固定し、外来導入の初期負担パッケージだけを段階的に変える。
- DCEのように多数属性の相対効用を推定するのではなく、患者ごとの受容閾値を直接得る。

## 参照ノート

- `../BHTM_threshold_technique_design_note.html`
- `../Hauber_Coulter_2020_threshold_technique_literature_note.html`
- `../Parikh_2023_HCC_threshold_technique_literature_note.html`
- `../Barrett_2005_benefit_harm_tradeoff_literature_note.html`
- `../ResearchNote_2018_smallest_worthwhile_effect_literature_note.html`

## 生成

```bash
python3 generate_bhtm_mock.py
```

モックデータCSVとSVG図は `mock_data/` 以下に生成される。

