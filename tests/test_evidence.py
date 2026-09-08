"""可解釋證據產生器測試。"""

import json

import networkx as nx
import pytest

from smelens.explain.evidence import generate_evidence, run_pipeline


def test_collector_evidence(scam_graph: nx.DiGraph) -> None:
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    ev = generate_evidence("collector", scam_graph, sna_df, partition, risk_ratios, hits)
    assert 0.0 <= ev["score"] <= 1.0
    assert ev["motif_hits"]
    assert ev["centrality_percentile"]["pagerank"] >= 50
    assert "collector" in ev["narrative_zh"]
    assert "扇入" in ev["narrative_zh"]
    json.dumps(ev, ensure_ascii=False)  # 必須可 JSON 序列化


def test_normal_node_scores_lower(scam_graph: nx.DiGraph) -> None:
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    ev_bad = generate_evidence("collector", scam_graph, sna_df, partition, risk_ratios, hits)
    ev_ok = generate_evidence("n1", scam_graph, sna_df, partition, risk_ratios, hits)
    assert ev_ok["score"] < ev_bad["score"]
    assert not ev_ok["motif_hits"]


def test_model_score_blend(scam_graph: nx.DiGraph) -> None:
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    ev = generate_evidence(
        "n1", scam_graph, sna_df, partition, risk_ratios, hits, model_score=1.0
    )
    assert ev["score"] >= 0.5
    assert "GNN" in ev["narrative_zh"]


def test_tied_minimum_percentile_not_inflated(scam_graph: nx.DiGraph) -> None:
    """平手值不得灌水：betweenness=0 的普通節點須落在低百分位（<= 用法的 bug）。"""
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    ev = generate_evidence("src0", scam_graph, sna_df, partition, risk_ratios, hits)
    assert ev["centrality_percentile"]["betweenness"] < 50
    # 全圖最小值（嚴格小於）應為第 0 百分位
    min_col = sna_df["betweenness"].idxmin()
    ev_min = generate_evidence(min_col, scam_graph, sna_df, partition, risk_ratios, hits)
    assert ev_min["centrality_percentile"]["betweenness"] == 0.0


def test_motif_periphery_not_scored(scam_graph: nx.DiGraph) -> None:
    """fan-in 來源（被害人角色）不在圖樣中心，不得計圖樣分。"""
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    ev = generate_evidence("src0", scam_graph, sna_df, partition, risk_ratios, hits)
    assert ev["motif_hits"] == []
    ev_center = generate_evidence(
        "collector", scam_graph, sna_df, partition, risk_ratios, hits
    )
    assert ev_center["motif_hits"]
    assert ev["score"] < ev_center["score"]


def test_unknown_node_raises(scam_graph: nx.DiGraph) -> None:
    sna_df, partition, risk_ratios, hits = run_pipeline(scam_graph)
    with pytest.raises(KeyError):
        generate_evidence("ghost", scam_graph, sna_df, partition, risk_ratios, hits)
