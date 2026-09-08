"""詐騙圖樣偵測測試。"""

import networkx as nx

from smelens.sna import motifs


def test_fan_in_hits_collector(scam_graph: nx.DiGraph) -> None:
    hits = motifs.detect_fan_in(scam_graph, min_degree=5, window_seconds=3600)
    assert [h.center for h in hits] == ["collector"]
    assert "collector" in hits[0].nodes
    assert "扇入" in hits[0].description_zh


def test_fan_out_hits_hub(scam_graph: nx.DiGraph) -> None:
    hits = motifs.detect_fan_out(scam_graph, min_degree=5, window_seconds=3600)
    assert [h.center for h in hits] == ["hub"]
    assert "分散" in hits[0].description_zh


def test_peeling_chain(scam_graph: nx.DiGraph) -> None:
    hits = motifs.detect_peeling_chain(scam_graph, min_hops=3, keep_ratio=0.8)
    assert len(hits) == 1
    assert hits[0].center == "p0"
    for node in ("p0", "p1", "p2", "p3", "p4"):
        assert node in hits[0].nodes
    assert "剝洋蔥" in hits[0].description_zh


def test_normal_nodes_not_hit(scam_graph: nx.DiGraph) -> None:
    centers = {h.center for h in motifs.detect_all(scam_graph)}
    assert centers.isdisjoint({"n0", "n1", "n2"})


def test_fan_in_without_timestamps() -> None:
    g = nx.DiGraph()
    for i in range(6):
        g.add_edge(f"s{i}", "c")  # 無 timestamp / amount 屬性
    hits = motifs.detect_fan_in(g, min_degree=5, window_seconds=3600)
    assert [h.center for h in hits] == ["c"]


def test_gather_scatter() -> None:
    g = nx.DiGraph()
    t0 = 1_700_000_000
    for i in range(6):
        g.add_edge(f"in{i}", "mixer", amount=50.0, timestamp=t0 + i * 30)
    for i in range(6):
        g.add_edge("mixer", f"out{i}", amount=48.0, timestamp=t0 + 300 + i * 30)
    hits = motifs.detect_gather_scatter(g, min_degree=5, window_seconds=3600)
    assert [h.center for h in hits] == ["mixer"]
    assert "集散" in hits[0].description_zh


def test_gather_scatter_requires_both_sides(scam_graph: nx.DiGraph) -> None:
    # collector 只有集資（out=1）、hub 只有分散（in=1），皆不構成集散
    hits = motifs.detect_gather_scatter(scam_graph, min_degree=5, window_seconds=3600)
    assert hits == []


def test_gather_scatter_rejects_scatter_before_gather() -> None:
    g = nx.DiGraph()
    t0 = 1_700_000_000
    for i in range(6):
        g.add_edge("hub", f"out{i}", timestamp=t0 + i * 10)  # 先全部流出
    for i in range(6):
        g.add_edge(f"in{i}", "hub", timestamp=t0 + 10_000 + i * 10)  # 才有流入
    assert motifs.detect_gather_scatter(g, min_degree=5, window_seconds=None) == []


def test_slow_fan_in_excluded_by_window() -> None:
    g = nx.DiGraph()
    for i in range(6):
        g.add_edge(f"s{i}", "c", timestamp=i * 7200)  # 每 2 小時一筆
    assert motifs.detect_fan_in(g, min_degree=5, window_seconds=600) == []
    assert len(motifs.detect_fan_in(g, min_degree=5, window_seconds=None)) == 1
