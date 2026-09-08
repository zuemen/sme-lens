"""規則式詐騙圖樣偵測：集資扇入（fan-in）、快速分散（fan-out）、剝洋蔥鏈（peeling chain）。

邊屬性慣例：amount（USDT 金額）、timestamp（Unix 秒）。
兩者皆為選配——缺 timestamp 時時間窗條件退化為純結構比對。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import networkx as nx


@dataclass
class MotifHit:
    """單一圖樣命中結果。"""

    motif: str
    center: Any
    nodes: list[Any] = field(default_factory=list)
    description_zh: str = ""


def _max_distinct_in_window(
    events: list[tuple[float | None, Any]], window_seconds: float | None
) -> int:
    """滑動時間窗內最多的 distinct 對手方數；無時間資訊時全部視為同一窗。"""
    if window_seconds is None or any(ts is None for ts, _ in events):
        return len({peer for _, peer in events})
    events = sorted(events, key=lambda e: e[0])
    best = 0
    left = 0
    for right in range(len(events)):
        while events[right][0] - events[left][0] > window_seconds:
            left += 1
        best = max(best, len({peer for _, peer in events[left : right + 1]}))
    return best


def detect_fan_in(
    g: nx.DiGraph, min_degree: int = 5, window_seconds: float | None = None
) -> list[MotifHit]:
    """短時間窗內 ≥min_degree 個來源匯入同一節點（集資）。"""
    hits: list[MotifHit] = []
    for node in g.nodes():
        events = [(d.get("timestamp"), u) for u, _, d in g.in_edges(node, data=True)]
        if len({p for _, p in events}) < min_degree:
            continue
        count = _max_distinct_in_window(events, window_seconds)
        if count >= min_degree:
            sources = sorted({p for _, p in events}, key=str)
            hits.append(
                MotifHit(
                    motif="fan_in",
                    center=node,
                    nodes=[node, *sources],
                    description_zh=(
                        f"節點 {node} 於短時間窗內接收來自 {count} 個不同地址的資金匯入，"
                        "符合集資扇入（fan-in）圖樣。"
                    ),
                )
            )
    return hits


def detect_fan_out(
    g: nx.DiGraph, min_degree: int = 5, window_seconds: float | None = None
) -> list[MotifHit]:
    """單節點於短時間窗內拆分至 ≥min_degree 個地址（分散）。"""
    hits: list[MotifHit] = []
    for node in g.nodes():
        events = [(d.get("timestamp"), v) for _, v, d in g.out_edges(node, data=True)]
        if len({p for _, p in events}) < min_degree:
            continue
        count = _max_distinct_in_window(events, window_seconds)
        if count >= min_degree:
            targets = sorted({p for _, p in events}, key=str)
            hits.append(
                MotifHit(
                    motif="fan_out",
                    center=node,
                    nodes=[node, *targets],
                    description_zh=(
                        f"節點 {node} 於短時間窗內快速拆分資金至 {count} 個不同地址，"
                        "符合快速分散（fan-out）圖樣。"
                    ),
                )
            )
    return hits


def _peel_next(g: nx.DiGraph, node: Any, keep_ratio: float) -> Any | None:
    """若 node 呈「單筆大額轉出＋至少一筆小額剝離」，回傳大額轉出的目標節點。"""
    out = list(g.out_edges(node, data=True))
    if len(out) < 2:
        return None
    amounts = [d.get("amount", 0.0) for _, _, d in out]
    total = sum(amounts)
    if total <= 0:
        return None
    best = max(range(len(out)), key=lambda i: amounts[i])
    if amounts[best] / total >= keep_ratio:
        return out[best][1]
    return None


def _is_proper_suffix(short: list[Any], long: list[Any]) -> bool:
    return len(short) < len(long) and long[-len(short) :] == short


def detect_peeling_chain(
    g: nx.DiGraph, min_hops: int = 3, keep_ratio: float = 0.8
) -> list[MotifHit]:
    """連續 ≥min_hops 跳、每跳保留 ≥keep_ratio 大額轉出＋小額剝離的鏈。"""
    chains: list[list[Any]] = []
    for start in g.nodes():
        path = [start]
        seen = {start}
        current = start
        while True:
            nxt = _peel_next(g, current, keep_ratio)
            if nxt is None or nxt in seen:
                break
            path.append(nxt)
            seen.add(nxt)
            current = nxt
        if len(path) - 1 >= min_hops:
            chains.append(path)
    maximal = [c for c in chains if not any(_is_proper_suffix(c, other) for other in chains)]
    return [
        MotifHit(
            motif="peeling_chain",
            center=chain[0],
            nodes=list(chain),
            description_zh=(
                f"自節點 {chain[0]} 起連續 {len(chain) - 1} 跳，每跳保留大額轉出並剝離小額，"
                "符合剝洋蔥鏈（peeling chain）圖樣。"
            ),
        )
        for chain in maximal
    ]


def detect_gather_scatter(
    g: nx.DiGraph, min_degree: int = 5, window_seconds: float | None = None
) -> list[MotifHit]:
    """集散圖樣（gather-scatter / smurfing）：同一節點先自 ≥min_degree 個來源集資，
    再拆分至 ≥min_degree 個目標——AML typology 文獻中 layering 的典型結構。

    有 timestamp 時另要求「最早流入不晚於最後流出」的時間順序。
    """
    hits: list[MotifHit] = []
    for node in g.nodes():
        in_events = [(d.get("timestamp"), u) for u, _, d in g.in_edges(node, data=True)]
        out_events = [(d.get("timestamp"), v) for _, v, d in g.out_edges(node, data=True)]
        if len({p for _, p in in_events}) < min_degree:
            continue
        if len({p for _, p in out_events}) < min_degree:
            continue
        in_count = _max_distinct_in_window(in_events, window_seconds)
        out_count = _max_distinct_in_window(out_events, window_seconds)
        if in_count < min_degree or out_count < min_degree:
            continue
        in_ts = [ts for ts, _ in in_events if ts is not None]
        out_ts = [ts for ts, _ in out_events if ts is not None]
        if in_ts and out_ts and min(in_ts) > max(out_ts):
            continue  # 全部流出都早於任何流入，不構成先集資後分散
        peers = sorted({p for _, p in in_events} | {p for _, p in out_events}, key=str)
        hits.append(
            MotifHit(
                motif="gather_scatter",
                center=node,
                nodes=[node, *peers],
                description_zh=(
                    f"節點 {node} 先自 {in_count} 個來源集中資金、再拆分至 "
                    f"{out_count} 個地址，符合集散（gather-scatter/smurfing）圖樣。"
                ),
            )
        )
    return hits


def detect_all(
    g: nx.DiGraph,
    min_degree: int = 5,
    window_seconds: float | None = 3600.0,
    min_hops: int = 3,
    keep_ratio: float = 0.8,
) -> list[MotifHit]:
    """一次執行全部圖樣偵測。"""
    return [
        *detect_fan_in(g, min_degree, window_seconds),
        *detect_fan_out(g, min_degree, window_seconds),
        *detect_gather_scatter(g, min_degree, window_seconds),
        *detect_peeling_chain(g, min_hops, keep_ratio),
    ]
