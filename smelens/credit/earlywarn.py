"""貸後早期預警：把已出事的授信戶當種子，沿關係圖擴散風險，產出關注名單。

為什麼需要這一層
----------------
貸前有集團歸戶、貸中有授信意見書，貸後管理卻仍倚賴季報與逾期通報——上下游
一家出事，銀行往往要等到自己的戶頭也逾期才知道。但「誰跟出事那家連得到」
這件事，關係圖現在就答得出來。

方法：帶夾制的標籤擴散（label spreading）
------------------------------------------
這是半監督式圖學習的經典解法（Zhu & Ghahramani 2002、Zhou et al. 2004）：
只需要少量已標註的節點（銀行手上本來就有的逾期戶／出事戶名單），就能把風險
推論到未標註的節點上。迭代式為

    f ← α · W · f + (1 − α) · y ，每輪把種子夾回 1.0

其中 W 是對稱正規化鄰接矩陣（D^-1/2 A D^-1/2）、y 是種子指示向量、α 是擴散
強度。夾制（clamping）讓種子始終為 1，避免擴散把已知事實稀釋掉。

**為什麼選這個方法，而不是訓練一個分類器**：企業關係圖這一側沒有真值標註
（銀行的逾期資料是少數且不對外），監督式模型沒有可信的訓練集；而標籤擴散
需要的正是「少量種子」，正好對得上銀行真實擁有的資料。更關鍵的是它**可解釋**
——每個被點名的公司都能回報「風險從哪一家、經過幾跳、沿哪條路徑傳過來」，
這與本系統「輸出可覆核的證據而非黑箱分數」的立場一致。分數高低只決定排序，
真正交給授信人員看的是那條路徑。

方向性的處理
------------
擴散用**無向**視圖：授信風險的傳染不分金流方向——買方倒帳會拖垮供應商，
供應商斷料也會害買方違約，兩個方向都要傳。金額方向仍保留在證據路徑裡供
授信人員判讀，只是不用來擋擴散。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx

#: 擴散強度。α 越大，風險傳得越遠。0.85 是 PageRank 慣用的阻尼值，實測在
#: 本劇本圖上讓一跳鄰居明顯高於二跳、三跳以外趨近於零——也就是「隔壁要看，
#: 隔三條街不用」，符合授信實務對關聯風險的直覺。呼叫端可調整。
DEFAULT_ALPHA = 0.85

#: 迭代次數上限。標籤擴散是收斂的，實務上二十輪內殘差已遠低於輸出精度；
#: 設上限而非只靠收斂判定，是為了讓最壞情況的執行時間有界。
DEFAULT_ITERATIONS = 50

#: 收斂判定：兩輪之間的最大變化小於此值即提早停止。
CONVERGENCE_TOL = 1e-9

#: 進入關注名單的分數門檻。一份什麼都列的名單等於沒有名單——這正是本系統
#: 對其他風控工具的批評，不能自己犯。實測劇本圖（11 節點）在門檻 0.05 時
#: 連對照組（禾昌五金，結構乾淨、三跳之外）與它的四個買方都會被列進來，
#: 名單等於整張圖；0.20 讓名單收斂到種子本身、兩家直接對手方與三家第二層
#: 對手方，對照組正確地不在名單上。呼叫端可依自身風控政策調整。
DEFAULT_THRESHOLD = 0.20

#: 最遠納入名單的跳數。授信實務上關聯風險的傳染有實質邊界——直接對手方
#: 要立刻查、第二層要覆審時追蹤，第三層以外的關聯性已弱到不足以改變授信
#: 決策，列進來只會淹沒真正該看的那幾家。與 DEFAULT_THRESHOLD 是兩道
#: 獨立的閘：分數管「傳得多強」，跳數管「傳得多遠」，兩者都要過。
DEFAULT_MAX_HOPS = 2


@dataclass(frozen=True)
class WarningItem:
    """關注名單的一筆：一家公司、它的預警分數，以及風險從哪裡來的證據。

    path 是從最近的種子到本公司的最短路徑（含兩端），這是這筆預警的**證據**
    ——授信人員要看的是「為什麼」，不是分數本身。
    """

    company: str
    score: float
    #: 距最近種子的跳數；種子本身為 0。
    hops: int
    #: 最近的種子（風險來源）。
    source: str
    #: 從 source 到 company 的最短路徑。
    path: tuple[str, ...]
    #: 本公司的授信餘額（呼叫端未提供時為 None）。
    exposure_twd: float | None
    action_zh: str
    reason_zh: str


def _normalised_adjacency(g: nx.Graph) -> tuple[list[Any], dict[Any, int], list[list[float]]]:
    """回傳 (節點順序, 節點→索引, 對稱正規化鄰接矩陣)。

    節點順序一律排序後固定：矩陣的列序會決定浮點加總的順序，不固定的話同一
    張圖在不同行程算出的分數末位可能不同，而前端是照分數排序算繪名單的。
    """
    nodes = sorted(g.nodes(), key=str)
    index = {node: i for i, node in enumerate(nodes)}
    degrees = [float(g.degree(node)) for node in nodes]
    size = len(nodes)
    matrix = [[0.0] * size for _ in range(size)]
    for u, v in g.edges():
        if u == v:
            continue  # 自環對擴散無意義，且會讓正規化分母失真
        iu, iv = index[u], index[v]
        denom = math.sqrt(degrees[iu] * degrees[iv])
        if denom <= 0:
            continue
        weight = 1.0 / denom
        matrix[iu][iv] = weight
        matrix[iv][iu] = weight
    return nodes, index, matrix


def propagate_risk(
    g: nx.Graph | nx.DiGraph,
    seeds: list[Any],
    *,
    alpha: float = DEFAULT_ALPHA,
    iterations: int = DEFAULT_ITERATIONS,
) -> dict[Any, float]:
    """帶夾制的標籤擴散，回傳 {公司: 預警分數}，分數夾在 [0, 1]。

    seeds 是已知出事的公司（逾期、退票、列為關注）。不在圖上的種子會被忽略
    ——呼叫端可能拿行內名單直接餵進來，其中有些公司不在這張圖裡，那不是錯誤。

    alpha 須落在 (0, 1)：等於 1 時風險會無衰減地傳遍整張連通圖，等於 0 時完全
    不傳，兩者都讓這個功能失去意義，故明確拒絕而不是默默給出無用的結果。
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha 須介於 0 與 1 之間（不含兩端）")
    if iterations < 1:
        raise ValueError("iterations 至少為 1")

    undirected = g.to_undirected(as_view=False) if g.is_directed() else g
    nodes, index, matrix = _normalised_adjacency(undirected)
    if not nodes:
        return {}

    seed_set = {s for s in seeds if s in index}
    y = [1.0 if node in seed_set else 0.0 for node in nodes]
    f = list(y)

    for _ in range(iterations):
        nxt = []
        for i in range(len(nodes)):
            row = matrix[i]
            total = sum(row[j] * f[j] for j in range(len(nodes)) if row[j])
            nxt.append(alpha * total + (1.0 - alpha) * y[i])
        # 夾制：種子是已知事實，不可被擴散稀釋。
        for node in seed_set:
            nxt[index[node]] = 1.0
        delta = max(abs(a - b) for a, b in zip(nxt, f)) if nodes else 0.0
        f = nxt
        if delta < CONVERGENCE_TOL:
            break

    return {node: round(min(max(f[index[node]], 0.0), 1.0), 4) for node in nodes}


_ACTION_BY_HOPS = {
    0: "已出事戶：依既有催收與轉呆程序辦理。",
    1: "直接往來對手方出事，建議立即查核應收帳款回收狀況與後續訂單。",
    2: "上下游第二層出事，建議於次月覆審時納入討論並追蹤主要買方集中度。",
}
_ACTION_FAR = "關聯層級較遠，建議列入觀察名單，暫不調整授信條件。"


def warning_list(
    g: nx.Graph | nx.DiGraph,
    seeds: list[Any],
    exposures: dict[Any, float] | None = None,
    *,
    alpha: float = DEFAULT_ALPHA,
    threshold: float = DEFAULT_THRESHOLD,
    max_hops: int = DEFAULT_MAX_HOPS,
    include_seeds: bool = True,
) -> list[WarningItem]:
    """產出關注名單：分數、跳數、風險來源與證據路徑，依分數由高到低排序。

    exposures 提供時，名單會帶上每家公司的授信餘額——授信人員真正要問的是
    「這件事會影響多少錢」，只給分數答不了這個問題。

    納入名單要同時過兩道閘：分數 >= threshold（傳得夠強）且跳數 <= max_hops
    （傳得不算遠）。種子本身不受兩道閘限制——它是已知事實，不是推論結果。

    排序在分數相同時以公司名決勝，確保同一筆查詢重跑的名單順序完全一致
    （前端照這個順序算繪，順序跳動看起來像資料變了）。
    """
    scores = propagate_risk(g, seeds, alpha=alpha)
    if not scores:
        return []

    undirected = g.to_undirected(as_view=False) if g.is_directed() else g
    present_seeds = [s for s in seeds if s in scores]
    exposures = exposures or {}

    items: list[WarningItem] = []
    for company, score in scores.items():
        is_seed = company in present_seeds
        if is_seed and not include_seeds:
            continue
        if not is_seed and score < threshold:
            continue

        best_hops: int | None = None
        best_path: tuple[str, ...] = (company,)
        best_source = company
        if is_seed:
            best_hops = 0
        else:
            # 逐一對種子取最短路徑，選最近的那一個當風險來源。種子數在實務上
            # 遠小於節點數（銀行的出事戶名單），逐一計算不構成效能問題。
            for seed in sorted(present_seeds, key=str):
                if not nx.has_path(undirected, seed, company):
                    continue
                path = nx.shortest_path(undirected, seed, company)
                hops = len(path) - 1
                if best_hops is None or hops < best_hops:
                    best_hops, best_path, best_source = hops, tuple(path), seed
        if best_hops is None:
            continue  # 與所有種子皆不連通：分數只可能來自浮點殘差，不列入
        if not is_seed and best_hops > max_hops:
            continue

        action = _ACTION_BY_HOPS.get(best_hops, _ACTION_FAR)
        if best_hops == 0:
            reason = f"{company} 為本次指定的已出事戶。"
        else:
            reason = (
                f"風險自 {best_source} 經 {best_hops} 跳傳至本公司"
                f"（{' → '.join(best_path)}）。"
            )
        items.append(
            WarningItem(
                company=company,
                score=score,
                hops=best_hops,
                source=best_source,
                path=best_path,
                exposure_twd=exposures.get(company),
                action_zh=action,
                reason_zh=reason,
            )
        )

    items.sort(key=lambda item: (-item.score, str(item.company)))
    return items


def exposure_at_risk(items: list[WarningItem], *, exclude_seeds: bool = True) -> float:
    """關注名單上的授信餘額合計——「這件事會影響多少錢」的答案。

    預設排除種子本身：種子是已經出事的戶，它的餘額已進催收程序，不屬於
    「因為這次擴散而新被點名」的曝險。把它算進來會虛增這份名單的價值。
    """
    return sum(
        item.exposure_twd or 0.0
        for item in items
        if not (exclude_seeds and item.hops == 0)
    )
