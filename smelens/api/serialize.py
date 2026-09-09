"""圖與風險證據 → 前端可直接渲染的 JSON。

刻意不 import FastAPI：這裡只做資料轉換，可獨立於 HTTP 層測試。
"""

from __future__ import annotations

from collections.abc import Mapping
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
    g: nx.DiGraph,
    evidences: dict[Any, dict[str, Any]],
    limit: int,
    *,
    keep: set[Any] | None = None,
) -> list[Any]:
    """超過上限時保留風險分數最高的節點，但 keep 中的節點無論分數一律保留。

    keep 用來確保「這份回應是關於誰的」不會被截斷邏輯意外丟掉——例如
    `/credit` 的授信對象，或 `/screen` 的出金目標與其 highlight_path。純以
    分數排序截斷完全可能把這些節點排在 limit 之外：分數高不代表就是使用者
    問的那家公司。若 keep 本身就超過 limit，limit 讓步——保留目標永遠優先
    於維持精確的節點數上限，回應會誠實標示比 limit 更大的 node_count。
    """
    keep = {node for node in (keep or set()) if node in g}
    if g.number_of_nodes() <= limit:
        return list(g.nodes())
    ranked = sorted(
        g.nodes(),
        key=lambda node: (evidences.get(node, {}).get("score", 0.0), str(node)),
        reverse=True,
    )
    remaining_slots = max(limit - len(keep), 0)
    fill = [node for node in ranked if node not in keep][:remaining_slots]
    # keep 節點置前：下游（例如高亮路徑重建）不應假設順序，但穩定的置前順序
    # 讓除錯時更容易在輸出裡一眼找到目標節點。
    ordered_keep = [node for node in ranked if node in keep]
    return ordered_keep + fill


def graph_to_json(
    g: nx.DiGraph,
    evidences: dict[Any, dict[str, Any]],
    sna_df: pd.DataFrame,
    *,
    motif_centers: set[Any],
    degraded: bool = False,
    limit: int = MAX_GRAPH_NODES,
    role_zh: Mapping[str, str] | None = None,
    keep: set[Any] | None = None,
) -> dict[str, Any]:
    """圖 + 全節點證據 → 前端圖譜 JSON。

    只有 scenario 劇本圖的節點有 role 屬性；範例圖與 TronGrid 抓回的真實圖
    一律沒有，會落到 DEFAULT_ROLE。前端因此不能只靠角色著色。

    節點數超過 limit 時依風險分數截斷，並在 meta 標示 truncated 與原始節點數，
    讓前端能誠實告知使用者看到的不是全圖。

    keep：無論分數高低都必須留下的節點集合（例如本次查詢的對象、高亮路徑
    上的節點）。截斷是為了控制回應大小，不該連「這份回應是關於誰」都截掉。

    role_zh：角色代碼 → 中文名稱的對照表。預設為 AML 劇本的 ROLE_ZH；企金
    劇本圖須傳入 sme_scenario.ROLE_ZH，否則角色會回退成英文鍵。
    """
    role_names = ROLE_ZH if role_zh is None else role_zh
    pagerank = sna_df["pagerank"].to_dict() if not sna_df.empty else {}
    retained = _retained_nodes(g, evidences, limit, keep=keep)
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
                "role_zh": role_names.get(role, role),
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
