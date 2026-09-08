"""企金風險圖樣測試：循環交易、空殼中介、買方集中。"""

from __future__ import annotations

import networkx as nx

from smelens.sna.sme_motifs import detect_cycle_trade


def test_detect_cycle_trade_finds_three_node_cycle():
    """三家公司構成封閉資金環，應命中且只回報一次。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000_000.0)
    g.add_edge("B", "C", amount=980_000.0)
    g.add_edge("C", "A", amount=960_000.0)
    g.add_edge("D", "E", amount=50_000.0)  # 非環，不應命中

    hits = detect_cycle_trade(g, max_len=4, min_amount=100_000.0)

    assert len(hits) == 1
    assert hits[0].motif == "cycle_trade"
    assert hits[0].center == "A"
    assert hits[0].nodes == ["A", "B", "C"]
    assert "封閉資金環" in hits[0].description_zh


def test_detect_cycle_trade_skips_cycle_below_min_amount():
    """環上最小金額低於門檻的零星往來不應誤報。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000.0)
    g.add_edge("B", "A", amount=900.0)

    assert detect_cycle_trade(g, min_amount=100_000.0) == []


def test_detect_cycle_trade_respects_max_len():
    """長度超過 max_len 的環不應命中。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000_000.0)
    g.add_edge("B", "C", amount=1_000_000.0)
    g.add_edge("C", "D", amount=1_000_000.0)
    g.add_edge("D", "A", amount=1_000_000.0)

    assert detect_cycle_trade(g, max_len=3) == []
    assert len(detect_cycle_trade(g, max_len=4)) == 1
