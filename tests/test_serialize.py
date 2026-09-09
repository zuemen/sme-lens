"""圖 → 前端 JSON 序列化測試（純資料轉換，不經 HTTP）。"""

from __future__ import annotations

import networkx as nx

from smelens.api.serialize import graph_to_json, sna_table
from smelens.data import scenario, tron
from smelens.explain.evidence import generate_evidence, run_pipeline


def _payload_for(g: nx.DiGraph):
    """算一次管線與全節點證據，回傳序列化函式需要的四樣東西。"""
    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    evidences = {
        n: generate_evidence(n, g, sna_df, partition, risk_ratios, motif_hits) for n in g.nodes()
    }
    return sna_df, evidences, {h.center for h in motif_hits}


def test_scenario_graph_counts_match() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["node_count"] == 53
    assert payload["meta"]["edge_count"] == 63
    assert len(payload["nodes"]) == 53
    assert len(payload["edges"]) == 63


def test_scenario_nodes_carry_roles_and_scores() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    by_id = {n["id"]: n for n in payload["nodes"]}

    aggregator = by_id["TAggregator01"]
    assert aggregator["role"] == "aggregator"
    assert aggregator["role_zh"] == "集資主錢包"
    assert aggregator["is_motif_center"] is True
    assert 0.0 <= aggregator["score"] <= 1.0
    assert aggregator["narrative_zh"]

    otc = by_id["TOtcOut01"]
    assert otc["role"] == "otc"
    assert otc["is_motif_center"] is False  # 本案主角自身不命中任何圖樣


def test_example_graph_has_no_roles_so_falls_back_to_normal() -> None:
    """範例圖與 TRON 圖沒有 role 屬性，必須落到 normal 而非 None。"""
    g = tron.load_example_graph()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert {n["role"] for n in payload["nodes"]} == {"normal"}
    assert {n["role_zh"] for n in payload["nodes"]} == {"正常交易地址"}


def test_edges_carry_amount_and_timestamp() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    edge = payload["edges"][0]
    assert isinstance(edge["source"], str)
    assert isinstance(edge["target"], str)
    assert isinstance(edge["amount"], float)
    assert isinstance(edge["timestamp"], int)


def test_edges_without_attributes_degrade_cleanly() -> None:
    """缺 amount / timestamp 的邊不得讓序列化爆炸。"""
    g = nx.DiGraph()
    g.add_edge("A", "B")
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["edges"] == [
        {"source": "A", "target": "B", "amount": 0.0, "timestamp": None}
    ]


def test_large_graph_truncated_to_highest_risk_nodes() -> None:
    """超過上限時保留風險最高的節點，並誠實標示已截斷。"""
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=10)
    assert payload["meta"]["truncated"] is True
    assert payload["meta"]["node_count"] == 10
    assert payload["meta"]["total_node_count"] == 53
    assert len(payload["nodes"]) == 10
    scores = [n["score"] for n in payload["nodes"]]
    assert scores == sorted(scores, reverse=True)


def test_truncated_graph_drops_edges_to_removed_nodes() -> None:
    """截斷後不得留下指向已移除節點的邊，否則前端渲染會出現孤兒引用。"""
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=10)
    ids = {n["id"] for n in payload["nodes"]}
    for edge in payload["edges"]:
        assert edge["source"] in ids
        assert edge["target"] in ids
    assert payload["meta"]["edge_count"] == len(payload["edges"])


def test_truncation_keeps_required_node_even_when_low_score() -> None:
    """keep 中的節點無論分數高低都不得被截斷邏輯丟掉。

    修復前：`/credit` 的授信對象、`/screen` 的出金目標與 highlight_path
    節點都可能因分數不夠高而被排除在截斷後的圖之外，產生一份談 A 公司的
    文件卻附上一張沒有 A 的圖。
    """
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    target = scenario.WITHDRAWAL_TARGET

    without_keep = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=3)
    ids_without = {n["id"] for n in without_keep["nodes"]}
    assert target not in ids_without, "本測試前提：小 limit 下若不指定 keep，目標節點會被排除"

    with_keep = graph_to_json(
        g, evidences, sna_df, motif_centers=centers, limit=3, keep={target}
    )
    ids_with = {n["id"] for n in with_keep["nodes"]}
    assert target in ids_with
    # keep 節點也不得留下指向已移除節點的孤兒邊。
    for edge in with_keep["edges"]:
        assert edge["source"] in ids_with
        assert edge["target"] in ids_with


def test_truncation_keeps_multiple_required_nodes_even_beyond_limit() -> None:
    """keep 節點數超過 limit 時，limit 讓步，全部保留而非任意丟棄其中幾個。"""
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    keep_nodes = set(list(g.nodes())[:5])

    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=3, keep=keep_nodes)

    ids = {n["id"] for n in payload["nodes"]}
    assert keep_nodes <= ids
    assert len(ids) >= len(keep_nodes)


def test_graph_under_limit_is_not_marked_truncated() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["truncated"] is False
    assert payload["meta"]["total_node_count"] == 53


def test_meta_carries_story_and_degraded_flag() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, degraded=True)
    assert payload["meta"]["degraded"] is True
    assert "TOtcOut01" in payload["meta"]["story_zh"]


def test_meta_story_is_none_for_graphs_without_one() -> None:
    g = tron.load_example_graph()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["story_zh"] is None
    assert payload["meta"]["degraded"] is False


def test_sna_table_sorted_by_score_and_limited() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, _ = _payload_for(g)
    rows = sna_table(sna_df, evidences, limit=5)
    assert len(rows) == 5
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert set(rows[0]) == {
        "node",
        "in_degree",
        "out_degree",
        "pagerank",
        "kcore",
        "betweenness",
        "score",
    }


def test_sna_table_empty_graph_returns_empty_list() -> None:
    g = nx.DiGraph()
    sna_df, evidences, _ = _payload_for(g)
    assert sna_table(sna_df, evidences) == []
