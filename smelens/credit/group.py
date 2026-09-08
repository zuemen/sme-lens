"""集團歸戶：以公司—自然人關係投影出公司關聯圖，揭露隱性集團。

現行實務中，集團授信歸戶主要倚賴客戶自行申報的關係企業表，行員再以人工
比對。共用董監事、交叉持股、共用登記地址等隱性關聯查不出來，導致集團曝
險在帳面上被拆散、實際上超限。本模組把這件事變成一個圖問題。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class Affiliation:
    """一筆公司—自然人關係（董監事、股東或負責人）。"""

    company: str
    person: str
    role: str = "董監事"


def build_company_graph(affiliations: Iterable[Affiliation]) -> nx.Graph:
    """由關係名冊建立公司關聯無向圖：共用同一自然人的兩家公司之間連邊。

    邊屬性 weight = 共用的自然人數；shared = 共用自然人名單（排序後）。
    無任何共用關係的公司仍會入圖成為孤立節點——歸戶時不能把它們漏掉。
    """
    records = list(affiliations)
    by_person: dict[str, set[str]] = {}
    for item in records:
        by_person.setdefault(item.person, set()).add(item.company)

    g = nx.Graph()
    for item in records:
        g.add_node(item.company)
    for person, companies in by_person.items():
        for u, v in combinations(sorted(companies), 2):
            if g.has_edge(u, v):
                g[u][v]["weight"] += 1
                g[u][v]["shared"].append(person)
            else:
                g.add_edge(u, v, weight=1, shared=[person])
    for _, _, data in g.edges(data=True):
        data["shared"].sort()
    return g


def detect_groups(company_graph: nx.Graph) -> dict[str, int]:
    """以連通元件切分集團，回傳 {公司: 集團編號}。

    刻意**不用** Louvain：集團歸戶在授信實務上是**遞移關係**——A 與 B 共用
    董事、B 與 C 共用董事，則 A、B、C 同屬一個歸戶群組，不因群內連結稀疏
    而被模組度切開。Louvain 會把弱連結的邊緣公司切出去，那正是集團歸戶最
    怕的漏網。社群偵測適合找「結構相似的群」，歸戶要的是「連得到就算」。

    集團編號依元件內字典序最小的公司名排序後給定，確保結果穩定可重現。
    """
    groups: dict[str, int] = {}
    components = sorted(nx.connected_components(company_graph), key=lambda c: sorted(c)[0])
    for index, component in enumerate(components):
        for company in component:
            groups[company] = index
    return groups


def group_exposure(groups: dict[str, int], exposures: Mapping[str, float]) -> dict[int, float]:
    """彙總各集團的授信曝險總額。不在 groups 內的公司一律忽略。"""
    totals: dict[int, float] = {}
    for company, amount in exposures.items():
        group_id = groups.get(company)
        if group_id is None:
            continue
        totals[group_id] = totals.get(group_id, 0.0) + float(amount)
    return totals


def hidden_links(
    company_graph: nx.Graph, declared: Mapping[str, str]
) -> list[dict[str, Any]]:
    """列出關係圖上存在、但客戶申報表歸屬不同集團的公司對（隱性關聯）。

    declared 為客戶自行申報的集團代號 {公司: 申報集團}；未申報者視為各自
    獨立的集團。回傳每筆含兩家公司、共用自然人與雙方申報集團，供行員覆核
    ——本模組只負責把證據攤開，是否併入歸戶由授信人員判斷。
    """
    found: list[dict[str, Any]] = []
    for u, v, data in company_graph.edges(data=True):
        company_a, company_b = sorted([u, v])
        group_a = declared.get(company_a, f"__undeclared__{company_a}")
        group_b = declared.get(company_b, f"__undeclared__{company_b}")
        if group_a == group_b:
            continue
        found.append(
            {
                "company_a": company_a,
                "company_b": company_b,
                "shared_persons": list(data["shared"]),
                "declared_group_a": declared.get(company_a),
                "declared_group_b": declared.get(company_b),
            }
        )
    return sorted(found, key=lambda row: (row["company_a"], row["company_b"]))
