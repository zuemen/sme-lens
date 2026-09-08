"""Louvain 社群偵測與社群風險比率。"""

from __future__ import annotations

from typing import Any

import community as community_louvain
import networkx as nx


def detect_communities(g: nx.DiGraph, seed: int = 42) -> dict[Any, int]:
    """Louvain 社群偵測（於無向投影圖），回傳 node -> community id。"""
    undirected = nx.Graph(g)
    if undirected.number_of_edges() == 0:
        return {n: i for i, n in enumerate(undirected.nodes())}
    return community_louvain.best_partition(undirected, random_state=seed)


def community_risk_ratio(partition: dict[Any, int], labels: dict[Any, int]) -> dict[int, float]:
    """各社群的已知非法佔比：illicit / (illicit + licit)；無標註成員的社群為 0.0。

    labels：node -> 1（illicit）/ 0（licit）/ -1（unknown，忽略）。
    """
    illicit: dict[int, int] = {}
    labeled: dict[int, int] = {}
    for node, comm in partition.items():
        illicit.setdefault(comm, 0)
        labeled.setdefault(comm, 0)
        label = labels.get(node, -1)
        if label >= 0:
            labeled[comm] += 1
            if label == 1:
                illicit[comm] += 1
    return {c: (illicit[c] / labeled[c] if labeled[c] else 0.0) for c in illicit}
