"""SNA 節點特徵：in/out degree、PageRank、k-core、近似 betweenness。"""

from __future__ import annotations

import networkx as nx
import pandas as pd

SNA_FEATURE_COLUMNS = ["in_degree", "out_degree", "pagerank", "kcore", "betweenness"]


def compute_sna_features(
    g: nx.DiGraph, betweenness_samples: int = 64, seed: int = 42
) -> pd.DataFrame:
    """對交易圖計算 SNA 指標，回傳 index=節點、欄位=SNA_FEATURE_COLUMNS 的 DataFrame。

    betweenness 以 k 個樣本源點近似（k = min(betweenness_samples, 節點數)），
    大圖上遠快於精確計算；k-core 於無向去自環投影圖上計算。
    """
    nodes = list(g.nodes())
    if not nodes:
        return pd.DataFrame(columns=SNA_FEATURE_COLUMNS)

    in_degree = dict(g.in_degree())
    out_degree = dict(g.out_degree())
    pagerank = nx.pagerank(g, alpha=0.85)

    undirected = nx.Graph(g)
    undirected.remove_edges_from(nx.selfloop_edges(undirected))
    kcore = nx.core_number(undirected)

    k = min(betweenness_samples, len(nodes))
    betweenness = nx.betweenness_centrality(g, k=k, seed=seed)

    return pd.DataFrame(
        {
            "in_degree": [in_degree.get(n, 0) for n in nodes],
            "out_degree": [out_degree.get(n, 0) for n in nodes],
            "pagerank": [pagerank.get(n, 0.0) for n in nodes],
            "kcore": [kcore.get(n, 0) for n in nodes],
            "betweenness": [betweenness.get(n, 0.0) for n in nodes],
        },
        index=nodes,
    )
