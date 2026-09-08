"""社群偵測與風險比率測試。"""

import networkx as nx

from smelens.sna import community as comm


def test_partition_covers_all_nodes(scam_graph: nx.DiGraph) -> None:
    partition = comm.detect_communities(scam_graph)
    assert set(partition) == set(scam_graph.nodes())


def test_fan_in_star_mostly_same_community(scam_graph: nx.DiGraph) -> None:
    partition = comm.detect_communities(scam_graph)
    same = sum(partition[f"src{i}"] == partition["collector"] for i in range(8))
    assert same >= 5  # 星狀結構多數來源與中心同社群


def test_community_risk_ratio() -> None:
    ratios = comm.community_risk_ratio(
        {"a": 0, "b": 0, "c": 1}, {"a": 1, "b": 0, "c": 0}
    )
    assert ratios == {0: 0.5, 1: 0.0}


def test_risk_ratio_ignores_unknown() -> None:
    ratios = comm.community_risk_ratio({"a": 0, "b": 0}, {"a": -1, "b": -1})
    assert ratios == {0: 0.0}
