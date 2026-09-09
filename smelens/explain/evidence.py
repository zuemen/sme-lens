"""風險證據產生器：整合 SNA 指標、社群歸屬與圖樣命中 → 結構化 JSON 與中文調查敘事。

核心理念：每個風險判定都附帶可稽核的結構證據，而非黑箱分數。
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

import networkx as nx
import pandas as pd

from smelens.sna.community import community_risk_ratio, detect_communities
from smelens.sna.metrics import compute_sna_features
from smelens.sna.motifs import MotifHit, detect_all

_LABEL_ZH = {"high": "高風險", "medium": "中風險", "low": "低風險"}

PipelineResult = tuple[pd.DataFrame, dict[Any, int], dict[int, float], list[MotifHit]]


def run_pipeline(g: nx.DiGraph) -> PipelineResult:
    """對整張圖執行 SNA → 社群 → 圖樣偵測，回傳評分所需的全部中間結果。"""
    sna_df = compute_sna_features(g)
    partition = detect_communities(g)
    motif_hits = detect_all(g)
    labels = {n: d.get("label", -1) for n, d in g.nodes(data=True)}
    if all(v < 0 for v in labels.values()):
        # 無標註圖（如 TRON 即時圖）：以圖樣命中中心作為疑似非法的代理標註。
        # 全節點都要標（命中為 1、其餘為 0），社群風險比才會是「該社群有多少比例的
        # 成員是命中中心」這個有鑑別力的比例；只標命中者會讓分母等於分子，任何含命中
        # 的社群一律得到 1.0，等於對整個社群加一個無資訊的常數並灌高嚴重度。
        labels = dict.fromkeys(g.nodes(), 0)
        for hit in motif_hits:
            labels[hit.center] = 1
    risk_ratios = community_risk_ratio(partition, labels)
    return sna_df, partition, risk_ratios, motif_hits


def generate_evidence(
    node: Any,
    g: nx.DiGraph,
    sna_df: pd.DataFrame,
    partition: dict[Any, int],
    risk_ratios: dict[int, float],
    motif_hits: list[MotifHit],
    model_score: float | None = None,
) -> dict[str, Any]:
    """對單一節點產生結構化風險證據。

    score = 0.5×圖樣命中 + 0.3×中心性百分位均值 + 0.2×社群風險比；
    若提供 GNN model_score，改為 0.5×模型 + 0.5×規則分數。
    """
    if node not in sna_df.index:
        raise KeyError(f"節點 {node} 不在圖中")

    # 嚴格小於：平手值不灌水（真實圖多數節點 betweenness=0/degree=1，
    # 若用 <=，這批節點會被算進第 85+ 百分位並產生「結構顯著異常」的錯誤敘事）
    percentiles = {
        col: float((sna_df[col] < sna_df.at[node, col]).mean() * 100)
        for col in sna_df.columns
    }
    comm = partition.get(node, -1)
    risk_ratio = float(risk_ratios.get(comm, 0.0))
    # 只計中心節點：fan-in 的 nodes 含所有來源地址（即被害人），
    # 周邊成員若同權計分，打款給詐騙地址的被害人會被連坐升級為中風險
    node_hits = [h for h in motif_hits if h.center == node]

    centrality_mean = sum(percentiles.values()) / len(percentiles) / 100
    rule_score = 0.5 * (1.0 if node_hits else 0.0) + 0.3 * centrality_mean + 0.2 * risk_ratio
    score = 0.5 * model_score + 0.5 * rule_score if model_score is not None else rule_score
    score = min(max(score, 0.0), 1.0)
    label = "high" if score >= 0.7 else "medium" if score >= 0.4 else "low"
    top_features = sorted(percentiles, key=lambda c: percentiles[c], reverse=True)[:3]

    narrative: list[str] = [f"地址/交易 {node} 綜合風險評分 {score:.2f}（{_LABEL_ZH[label]}）。"]
    if node_hits:
        narrative.append("命中詐騙圖樣：" + "；".join(h.description_zh for h in node_hits))
    top = top_features[0]
    if percentiles[top] >= 90:
        level = "顯著異常"
    elif percentiles[top] >= 70:
        level = "偏高"
    else:
        level = "未見明顯異常"
    narrative.append(f"其 {top} 指標位於全圖第 {percentiles[top]:.0f} 百分位，結構位置{level}。")
    narrative.append(f"所屬社群 #{comm} 已知非法佔比 {risk_ratio:.0%}。")
    if model_score is not None:
        narrative.append(f"GNN 模型判定非法機率 {model_score:.2f}。")

    return {
        "score": round(score, 4),
        "label": label,
        "top_features": top_features,
        "centrality_percentile": {k: round(v, 2) for k, v in percentiles.items()},
        "community_risk_ratio": round(risk_ratio, 4),
        "motif_hits": [asdict(h) for h in node_hits],
        "narrative_zh": "".join(narrative),
    }
