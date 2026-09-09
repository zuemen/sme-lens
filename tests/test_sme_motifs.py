"""企金風險圖樣測試：循環交易、空殼中介、買方集中。"""

from __future__ import annotations

import networkx as nx

from smelens.sna.sme_motifs import (
    detect_all_sme,
    detect_buyer_concentration,
    detect_cycle_trade,
    detect_shell_intermediary,
)


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


def test_detect_cycle_trade_keeps_opposite_direction_cycles_separate():
    """同一組公司間方向相反的兩條資金環是兩筆獨立事證，不得併為一筆。

    以節點集合去重會把 A→B→C→A 與 A→C→B→A 併成一筆而漏報一條循環金流；
    同時本測試釘住 nodes 保留實際流向順序（非字典序）。
    """
    g = nx.DiGraph()
    for u, v in [("A", "B"), ("B", "C"), ("C", "A"), ("A", "C"), ("C", "B"), ("B", "A")]:
        g.add_edge(u, v, amount=1_000_000.0)

    three_node = [h for h in detect_cycle_trade(g, max_len=3, min_amount=100_000.0)
                  if len(h.nodes) == 3]

    assert len(three_node) == 2
    assert {tuple(h.nodes) for h in three_node} == {("A", "B", "C"), ("A", "C", "B")}


def test_detect_shell_intermediary_flags_passthrough_node():
    """錢進來就出去、對手方極少者為空殼；有留存毛利者不是。"""
    g = nx.DiGraph()
    g.add_edge("買方甲", "宏益企業", amount=5_000_000.0)
    g.add_edge("宏益企業", "供應商乙", amount=4_950_000.0)  # 過水比 99%
    g.add_edge("買方甲", "實營公司", amount=5_000_000.0)
    g.add_edge("實營公司", "供應商乙", amount=3_000_000.0)  # 留存 40%，非空殼

    hits = detect_shell_intermediary(g, min_passthrough=0.9, max_counterparties=3)

    assert [h.center for h in hits] == ["宏益企業"]
    assert hits[0].motif == "shell_intermediary"
    assert "過水比" in hits[0].description_zh
    # nodes 的內容要釘死：只放中介本身（漏掉對手方）或只放對手方（漏掉中介）
    # 都會讓下游證據少一半，而僅檢查 center 的斷言抓不到這兩種錯。
    assert hits[0].nodes[0] == "宏益企業", "nodes 首位必須是中介節點本身"
    assert set(hits[0].nodes[1:]) == {"買方甲", "供應商乙"}, "nodes 須含上下游對手方"


def test_detect_shell_intermediary_ignores_many_counterparties():
    """對手方眾多的樞紐是集散中心而非空殼，不應命中。"""
    g = nx.DiGraph()
    for i in range(5):
        g.add_edge(f"進{i}", "樞紐", amount=1_000_000.0)
    g.add_edge("樞紐", "出0", amount=5_000_000.0)

    assert detect_shell_intermediary(g, max_counterparties=3) == []


def test_detect_shell_intermediary_ignores_endpoints():
    """只有進或只有出的端點不構成過水中介。"""
    g = nx.DiGraph()
    g.add_edge("起點", "終點", amount=1_000_000.0)

    assert detect_shell_intermediary(g) == []


def test_detect_buyer_concentration_flags_single_buyer():
    """逾七成收入來自單一買方者命中；收入分散者不命中。"""
    g = nx.DiGraph()
    g.add_edge("大買方", "集中廠商", amount=9_000_000.0)
    g.add_edge("小買方", "集中廠商", amount=1_000_000.0)  # 90% 集中
    g.add_edge("大買方", "分散廠商", amount=3_000_000.0)
    g.add_edge("小買方", "分散廠商", amount=3_500_000.0)  # 54% 集中

    hits = detect_buyer_concentration(g, min_ratio=0.7)

    assert [h.center for h in hits] == ["集中廠商"]
    assert hits[0].motif == "buyer_concentration"
    assert hits[0].nodes == ["集中廠商", "大買方"]


def test_detect_buyer_concentration_respects_min_revenue():
    """營收規模低於門檻者不納入評估，避免對微型往來過度反應。"""
    g = nx.DiGraph()
    g.add_edge("大買方", "微型廠商", amount=50_000.0)
    g.add_edge("小買方", "微型廠商", amount=5_000.0)  # 兩個買方，但總營收僅 55,000

    assert detect_buyer_concentration(g, min_ratio=0.7, min_revenue=1_000_000.0) == []


def test_detect_all_sme_combines_three_motifs():
    """合集應同時涵蓋三種圖樣。"""
    g = nx.DiGraph()
    # 封閉資金環
    g.add_edge("環甲", "環乙", amount=2_000_000.0)
    g.add_edge("環乙", "環甲", amount=1_900_000.0)
    # 空殼過水
    g.add_edge("來源", "空殼", amount=3_000_000.0)
    g.add_edge("空殼", "去向", amount=2_970_000.0)
    g.add_edge("小買方", "去向", amount=30_000.0)  # 去向 有兩個買方，其中一個佔 99%

    motifs = {h.motif for h in detect_all_sme(g)}

    assert "cycle_trade" in motifs
    assert "shell_intermediary" in motifs
    assert "buyer_concentration" in motifs


def test_detect_buyer_concentration_ratio_never_exceeds_100pct_with_negative_edges():
    """折讓／退貨／沖銷會產生負數邊，但回報的集中度不得超過 100%。

    修復前：B1 付 -1000（沖銷）、B2 付 3000，原始加總營收僅 2000，
    B2 一家就佔 150%——算術上不可能的百分比。
    """
    g = nx.DiGraph()
    g.add_edge("B1", "T", amount=-1000.0)
    g.add_edge("B2", "T", amount=3000.0)

    hits = detect_buyer_concentration(g, min_ratio=0.0)

    assert len(hits) == 1
    assert "150%" not in hits[0].description_zh
    assert "來自單一買方" in hits[0].description_zh


def test_detect_buyer_concentration_treats_negative_edge_as_reversal_not_negative_revenue():
    """負數邊視為沖銷，夾到 0，不倒扣既有正向營收。"""
    g = nx.DiGraph()
    g.add_edge("B1", "T", amount=5000.0)
    g.add_edge("B2", "T", amount=-1000.0)

    hits = detect_buyer_concentration(g, min_ratio=0.0)

    # B2 的沖銷夾到 0 後，B1 為唯一有效營收來源，集中度應為 100%（非 >100%）。
    assert hits[0].description_zh.count("100%") == 1


def test_detect_cycle_trade_missing_amount_reports_unknown_not_zero():
    """缺 amount 屬性的邊應誠實標示「金額未知」，不得偽裝成觀測到的 0 元。"""
    g = nx.DiGraph()
    g.add_edge("A", "B")
    g.add_edge("B", "C")
    g.add_edge("C", "A")

    hits = detect_cycle_trade(g, min_amount=0.0)

    assert len(hits) == 1
    assert "環上最小金額 0" not in hits[0].description_zh
    assert "未知" in hits[0].description_zh


def test_detect_cycle_trade_negative_edge_clamped_to_zero_for_threshold():
    """環上有沖銷（負數）邊時，以 0 計入 min_amount 門檻判斷，而非負值。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=-500.0)
    g.add_edge("B", "A", amount=1_000_000.0)

    # min_amount=0：夾到 0 後仍滿足 >= 0，應命中。
    assert len(detect_cycle_trade(g, min_amount=0.0)) == 1


def test_detect_buyer_concentration_ignores_single_observed_buyer():
    """只觀察到一個買方時，100% 集中是圖資不完整的假象，不是客戶結構風險。

    真實供應鏈圖裡大量節點只有一條入邊；若不排除，本圖樣會在整張圖上到處命中，
    把真正該被看見的申請人淹沒。
    """
    g = nx.DiGraph()
    g.add_edge("唯一買方", "廠商", amount=8_000_000.0)

    assert detect_buyer_concentration(g) == []
    assert len(detect_buyer_concentration(g, min_buyers=1)) == 1
