"""授信意見書產生器：把圖結構證據轉成行員可覆核的授信意見。

設計原則：**不輸出黑箱分數**。每一個判定都附帶結構證據（命中圖樣、中心性
百分位、對手多樣性、集團曝險）與中文敘事，讓授信人員能覆核、能寫進徵信
報告、能對監理交代。分數只是敘事的索引，不是結論本身。
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import networkx as nx
import pandas as pd

from smelens.explain.evidence import PipelineResult
from smelens.sna.community import community_risk_ratio, detect_communities
from smelens.sna.metrics import compute_sna_features
from smelens.sna.sme_motifs import detect_all_sme

_LABEL_ZH = {"watch": "關注", "caution": "留意", "normal": "正常"}

_RECOMMENDATION_ZH = {
    "watch": "建議暫緩核貸，先行實地查核關係人交易與主要買方合約之真實性。",
    "caution": "建議核貸但調降額度並縮短覆審週期，要求補提主要買方合約與出貨憑證。",
    "normal": "結構面未見異常，得依既有授信條件辦理。",
}


def run_sme_pipeline(g: nx.DiGraph) -> PipelineResult:
    """企金版分析管線：SNA → 社群 → 企金圖樣，回傳四元組。

    與 `smelens.explain.evidence.run_pipeline` 的唯一差異是圖樣集合——企金
    三圖樣取代詐騙圖樣。社群風險比以圖樣命中中心作為代理標註（企業關係圖
    無 licit/illicit 真值標註，與 ChainLens 處理 TRON 即時圖的慣例一致）。
    """
    sna_df = compute_sna_features(g)
    partition = detect_communities(g)
    motif_hits = detect_all_sme(g)
    labels = {hit.center: 1 for hit in motif_hits}
    risk_ratios = community_risk_ratio(partition, labels)
    return sna_df, partition, risk_ratios, motif_hits


def counterparty_diversity(g: nx.DiGraph, node: Any) -> float:
    """交易對手多樣性（0–1）：買方金額分布的正規化熵。

    單一買方 → 0；n 個買方平均分攤 → 1。無收入者回傳 0。
    企金意義：這是「客戶集中度」的連續版本，比二元的圖樣命中更適合放進
    信用分計算——集中度是程度問題，不是有無問題。
    """
    amounts: dict[Any, float] = {}
    for u, _, data in g.in_edges(node, data=True):
        amounts[u] = amounts.get(u, 0.0) + float(data.get("amount", 0.0))
    total = sum(amounts.values())
    if total <= 0:
        return 0.0
    shares = [amount / total for amount in amounts.values() if amount > 0]
    if len(shares) < 2:
        return 0.0
    entropy = -sum(share * math.log(share) for share in shares)
    return round(entropy / math.log(len(shares)), 4)


def network_credit(g: nx.DiGraph, node: Any, sna_df: pd.DataFrame) -> float:
    """網絡信用分（0–1，愈高信用愈佳）。

    = 0.5 × 結構中心性百分位均值 + 0.5 × 交易對手多樣性

    企金意義：在供應鏈網絡中位置愈核心、交易對手愈分散的企業，現金流韌性
    愈高——這是財報看不到、但關係圖看得到的信用證據，正是「沒有漂亮財報
    的好公司」得以被看見的依據。

    百分位採**嚴格小於**：真實圖上多數節點的 betweenness 為 0、degree 為 1，
    若用小於等於，這批節點會被算進第 85+ 百分位而虛胖成「結構核心」。
    """
    percentiles = {
        column: float((sna_df[column] < sna_df.at[node, column]).mean())
        for column in sna_df.columns
    }
    centrality = sum(percentiles.values()) / len(percentiles)
    return round(0.5 * centrality + 0.5 * counterparty_diversity(g, node), 4)


def generate_credit_opinion(
    node: Any,
    g: nx.DiGraph,
    sna_df: pd.DataFrame,
    partition: dict[Any, int],
    risk_ratios: dict[int, float],
    motif_hits: list[Any],
    *,
    group_id: int | None = None,
    group_exposure_twd: float | None = None,
    model_score: float | None = None,
) -> dict[str, Any]:
    """對單一企業產生授信意見書。

    attention_score = 0.5 × 圖樣命中 + 0.3 × (1 − 網絡信用) + 0.2 × 社群風險比；
    提供 GNN model_score 時改為 0.5 × 模型 + 0.5 × 規則分數（與 ChainLens
    的模型／規則融合慣例一致）。

    **圖樣歸屬規則**：一般圖樣只計 center，避免周邊成員連坐；但 cycle_trade
    例外——封閉資金環上的**每一個**成員都是循環交易的參與者，不是被動的
    對手方，故環上成員全部引用。
    """
    if node not in sna_df.index:
        raise KeyError(f"企業 {node} 不在關係圖中")

    relevant = [
        hit
        for hit in motif_hits
        if hit.center == node or (hit.motif == "cycle_trade" and node in hit.nodes)
    ]
    credit = network_credit(g, node, sna_df)
    diversity = counterparty_diversity(g, node)
    community = partition.get(node, -1)
    risk_ratio = float(risk_ratios.get(community, 0.0))
    percentiles = {
        column: round(float((sna_df[column] < sna_df.at[node, column]).mean() * 100), 2)
        for column in sna_df.columns
    }

    rule_score = 0.5 * (1.0 if relevant else 0.0) + 0.3 * (1.0 - credit) + 0.2 * risk_ratio
    score = 0.5 * model_score + 0.5 * rule_score if model_score is not None else rule_score
    score = min(max(score, 0.0), 1.0)
    label = "watch" if score >= 0.7 else "caution" if score >= 0.4 else "normal"

    narrative: list[str] = [
        f"企業 {node} 網絡信用分 {credit:.2f}、授信關注分數 {score:.2f}"
        f"（{_LABEL_ZH[label]}）。"
    ]
    if relevant:
        narrative.append("命中企金風險圖樣：" + "；".join(h.description_zh for h in relevant))
    else:
        narrative.append("未命中任何企金風險圖樣。")
    narrative.append(
        f"交易對手多樣性 {diversity:.2f}"
        f"（{'買方高度集中' if diversity < 0.5 else '買方結構分散'}）。"
    )
    if group_id is not None:
        exposure_text = (
            f"，該集團授信曝險合計 {group_exposure_twd:,.0f} 元"
            if group_exposure_twd is not None
            else ""
        )
        narrative.append(f"歸戶集團編號 #{group_id}{exposure_text}。")
    if model_score is not None:
        narrative.append(f"GNN 模型判定違約機率 {model_score:.2f}。")

    return {
        "target": str(node),
        "attention_score": round(score, 4),
        "network_credit": credit,
        "label": label,
        "label_zh": _LABEL_ZH[label],
        "counterparty_diversity": diversity,
        "centrality_percentile": percentiles,
        "community_risk_ratio": round(risk_ratio, 4),
        "group_id": group_id,
        "group_exposure_twd": group_exposure_twd,
        "motif_hits": [asdict(hit) for hit in relevant],
        "narrative_zh": "".join(narrative),
        "recommendation_zh": _RECOMMENDATION_ZH[label],
    }
