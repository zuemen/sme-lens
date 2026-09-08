"""圖與風險證據 → 前端可直接渲染的 JSON。

刻意不 import FastAPI：這裡只做資料轉換，可獨立於 HTTP 層測試。
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from smelens.data.scenario import ROLE_ZH

DEFAULT_ROLE = "normal"
SNA_TABLE_LIMIT = 15

# 每個節點的 JSON 實測約 500 bytes（narrative_zh 是多句中文敘事）。
# TronGrid 的真實 2-hop 圖可達 795 節點 → 約 390KB 回應，經冷啟動的 serverless
# 傳輸過慢，且力導向排版在該量級會糊成無法閱讀的毛球。300 落在圖形函式庫
# 舒適的 101–500 canvas 區間。
MAX_GRAPH_NODES = 300


def _retained_nodes(
    g: nx.DiGraph, evidences: dict[Any, dict[str, Any]], limit: int
) -> list[Any]:
    """超過上限時只保留風險分數最高的 limit 個節點。"""
    if g.number_of_nodes() <= limit:
        return list(g.nodes())
    ranked = sorted(
        g.nodes(),
        key=lambda node: (evidences.get(node, {}).get("score", 0.0), str(node)),
        reverse=True,
    )
    return ranked[:limit]


def graph_to_json(
    g: nx.DiGraph,
    evidences: dict[Any, dict[str, Any]],
    sna_df: pd.DataFrame,
    *,
    motif_centers: set[Any],
    degraded: bool = False,
    limit: int = MAX_GRAPH_NODES,
) -> dict[str, Any]:
    """圖 + 全節點證據 → 前端圖譜 JSON。

    只有 scenario 劇本圖的節點有 role 屬性；範例圖與 TronGrid 抓回的真實圖
    一律沒有，會落到 DEFAULT_ROLE。前端因此不能只靠角色著色。

    節點數超過 limit 時依風險分數截斷，並在 meta 標示 truncated 與原始節點數，
    讓前端能誠實告知使用者看到的不是全圖。
    """
    pagerank = sna_df["pagerank"].to_dict() if not sna_df.empty else {}
    retained = _retained_nodes(g, evidences, limit)
    retained_set = set(retained)

    nodes = []
    for node in retained:
        attrs = g.nodes[node]
        evidence = evidences.get(node, {})
        role = attrs.get("role") or DEFAULT_ROLE
        nodes.append(
            {
                "id": str(node),
                "role": role,
                "role_zh": ROLE_ZH.get(role, role),
                "score": evidence.get("score", 0.0),
                "label": evidence.get("label", "low"),
                "is_motif_center": node in motif_centers,
                "pagerank": float(pagerank.get(node, 0.0)),
                "narrative_zh": evidence.get("narrative_zh", ""),
            }
        )

    edges = []
    for source, target, attrs in g.edges(data=True):
        if source not in retained_set or target not in retained_set:
            continue
        timestamp = attrs.get("timestamp")
        edges.append(
            {
                "source": str(source),
                "target": str(target),
                "amount": float(attrs.get("amount", 0.0)),
                "timestamp": int(timestamp) if timestamp is not None else None,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "total_node_count": g.number_of_nodes(),
            "edge_count": len(edges),
            "truncated": len(nodes) < g.number_of_nodes(),
            "story_zh": g.graph.get("story_zh"),
            "degraded": degraded,
        },
    }


def sna_table(
    sna_df: pd.DataFrame,
    evidences: dict[Any, dict[str, Any]],
    limit: int = SNA_TABLE_LIMIT,
) -> list[dict[str, Any]]:
    """依風險分數由高到低排序的 SNA 指標表，供工作台表格使用。"""
    if sna_df.empty:
        return []
    rows = [
        {
            "node": str(node),
            "in_degree": float(row["in_degree"]),
            "out_degree": float(row["out_degree"]),
            "pagerank": float(row["pagerank"]),
            "kcore": float(row["kcore"]),
            "betweenness": float(row["betweenness"]),
            "score": evidences.get(node, {}).get("score", 0.0),
        }
        for node, row in sna_df.iterrows()
    ]
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows[:limit]
