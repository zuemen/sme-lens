"""企金風險圖樣偵測：循環交易、空殼中介、買方集中。

與 `smelens.sna.motifs`（詐騙金流圖樣）的分工：該模組服務防詐分支，
本模組服務企金授信分支，兩者共用 `MotifHit` 結構以便同一套證據產生器
與圖譜著色邏輯能同時消費。

邊屬性慣例：`amount`（新台幣元）、`timestamp`（Unix 秒）。
邊方向 u → v 表示 **u 付款給 v**，故 v 的收入為其 in-edges 金額總和。
"""

from __future__ import annotations

import networkx as nx

from smelens.sna.motifs import MotifHit


def detect_cycle_trade(
    g: nx.DiGraph, max_len: int = 4, min_amount: float = 0.0
) -> list[MotifHit]:
    """偵測長度 2..max_len 的封閉資金環（循環交易／資金迴流）。

    企金意義：A→B→C→A 的封閉資金環在正常商流中罕見——正常交易的錢會
    流向供應鏈下游或轉為薪資、稅負而離開網絡。封閉環常見於循環開票虛增
    營收，或關係人之間資金迴流以粉飾財報周轉率。

    環上**最小**金額須 >= min_amount 才計入，避免零星小額往來構成的環誤報。

    `nodes` 保留環的**實際流向順序**（旋轉至 center 起始以確保結果穩定），
    因為授信意見書與圖譜著色要能重建「錢是照哪條路繞回來的」——那條路徑
    本身就是證據，排序後會消失。

    此處**不自行去重**：`nx.simple_cycles` 已保證每個環只回傳一次（實測單向
    三角環回傳 1 次），而以節點集合去重會把 A→B→C→A 與 A→C→B→A 這兩條方向
    相反、彼此獨立的資金環誤併為一筆——對一個專門用來抓循環開票的圖樣而言，
    那是漏報。
    """
    hits: list[MotifHit] = []
    for cycle in nx.simple_cycles(g, length_bound=max_len):
        if len(cycle) < 2:  # 自環非交易環
            continue
        amounts = [
            float(g[cycle[i]][cycle[(i + 1) % len(cycle)]].get("amount", 0.0))
            for i in range(len(cycle))
        ]
        if min(amounts) < min_amount:
            continue
        center = min(cycle, key=str)
        start = cycle.index(center)
        ordered = cycle[start:] + cycle[:start]  # 旋轉至 center 起始，流向不變
        path_zh = " → ".join(str(n) for n in [*ordered, center])
        hits.append(
            MotifHit(
                motif="cycle_trade",
                center=center,
                nodes=ordered,
                description_zh=(
                    f"節點 {center} 位於長度 {len(cycle)} 的封閉資金環"
                    f"（{path_zh}，環上最小金額 {min(amounts):,.0f}），"
                    "符合循環交易／資金迴流圖樣。"
                ),
            )
        )
    return hits
