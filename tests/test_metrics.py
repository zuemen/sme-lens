"""SNA 指標測試。"""

import networkx as nx

from smelens.sna import metrics


def test_sna_features(scam_graph: nx.DiGraph) -> None:
    df = metrics.compute_sna_features(scam_graph, betweenness_samples=16, seed=1)
    assert set(df.index) == set(scam_graph.nodes())
    assert list(df.columns) == metrics.SNA_FEATURE_COLUMNS
    assert df.loc["collector", "in_degree"] == 8
    assert df.loc["hub", "out_degree"] == 6
    assert abs(df["pagerank"].sum() - 1.0) < 1e-6
    assert (df["betweenness"] >= 0).all()
    assert (df["kcore"] >= 0).all()


def test_empty_graph() -> None:
    df = metrics.compute_sna_features(nx.DiGraph())
    assert df.empty
