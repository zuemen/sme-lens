"""集團歸戶：以公司—自然人關係投影出公司關聯圖，揭露隱性集團。

現行實務中，集團授信歸戶主要倚賴客戶自行申報的關係企業表，行員再以人工
比對。共用董監事、交叉持股、共用登記地址等隱性關聯查不出來，導致集團曝
險在帳面上被拆散、實際上超限。本模組把這件事變成一個圖問題。
"""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import networkx as nx


def normalise_name(name: str) -> str:
    """統一名稱寫法：NFKC 正規化、去除前後空白、把內部連續空白摺成單一空格。

    手動輸入的董監事名冊常帶尾隨空白或全形字元。若不正規化，「王小明」與
    「王小明 」會被當成兩個不同的人，共用董事的關聯就此查不出來——而那正是
    本模組唯一要抓的東西。對一個法遵工具而言，這也意味著刻意多打一個空格
    就是零成本的規避手法，故正規化是正確性要求，不是便利性。
    """
    return " ".join(unicodedata.normalize("NFKC", name).split())


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
    records = [
        Affiliation(
            company=normalise_name(item.company),
            person=normalise_name(item.person),
            role=item.role,
        )
        for item in affiliations
    ]
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

    元件內部也要排序後再指派：nx.connected_components 回傳的是 set，其迭代順序
    受行程的 hash 隨機化影響。歸戶結果的「值」不受影響，但回應中鍵的順序會在不同
    請求之間跳動，而前端是照這個順序渲染歸戶結果表的——同一筆查詢重跑一次表格就
    換個排列，現場看起來像資料變了。
    """
    groups: dict[str, int] = {}
    components = sorted(nx.connected_components(company_graph), key=lambda c: sorted(c)[0])
    for index, component in enumerate(components):
        for company in sorted(component):
            groups[company] = index
    return groups


def group_exposure(groups: dict[str, int], exposures: Mapping[str, float]) -> dict[int, float]:
    """彙總各集團的授信曝險總額。不在 groups 內的公司一律忽略。"""
    totals: dict[int, float] = {}
    for company, amount in exposures.items():
        group_id = groups.get(normalise_name(company))
        if group_id is None:
            continue
        totals[group_id] = totals.get(group_id, 0.0) + float(amount)
    return totals


DEFAULT_HIDDEN_LINKS_LIMIT = 200


def hidden_links(
    company_graph: nx.Graph,
    declared: Mapping[str, str],
    *,
    limit: int = DEFAULT_HIDDEN_LINKS_LIMIT,
) -> list[dict[str, Any]]:
    """列出關係圖上存在、但客戶申報表歸屬不同集團的公司對（隱性關聯）。

    declared 為客戶自行申報的集團代號 {公司: 申報集團}；未申報者視為各自
    獨立的集團。回傳每筆含兩家公司、共用自然人與雙方申報集團，供行員覆核
    ——本模組只負責把證據攤開，是否併入歸戶由授信人員判斷。

    affiliations 雖以 500 筆為上限，但 hidden_links 是 build_company_graph
    的**輸出**而非輸入：500 家公司共用同一人可組出 124,750 個候選公司對，
    全數回傳會產生超過 13MB 的單一回應。故依 weight（共用自然人數）由高到
    低只回傳前 limit 筆——那正是授信人員本來就該優先看的：共用董監事愈多，
    隱性關聯愈可疑，截斷掉的是產品邏輯上本來就次要的那些，不是妥協。
    金額相同時以 (company_a, company_b) 排序決勝，確保結果穩定可重現。
    """
    declared_norm = {normalise_name(k): v for k, v in declared.items()}
    found: list[dict[str, Any]] = []
    for u, v, data in company_graph.edges(data=True):
        company_a, company_b = sorted([u, v])
        # 哨符改用 tuple：申報值一律是字串，型別不同就永遠不會比較相等。原本以
        # f"__undeclared__{company}" 當哨符，等於讓內部標記與「客戶自行申報的集團名」
        # 共用同一個命名空間——客戶只要把申報值寫成剛好等於對方的哨符字串，兩邊就會
        # 相等而抹掉一筆真實的隱性關聯。申報內容是不可信輸入，不能與內部標記同域。
        group_a = declared_norm.get(company_a, ("__undeclared__", company_a))
        group_b = declared_norm.get(company_b, ("__undeclared__", company_b))
        if group_a == group_b:
            continue
        found.append(
            {
                "company_a": company_a,
                "company_b": company_b,
                "shared_persons": list(data["shared"]),
                "declared_group_a": declared_norm.get(company_a),
                "declared_group_b": declared_norm.get(company_b),
                "weight": data["weight"],
            }
        )
    found.sort(key=lambda row: (-row["weight"], row["company_a"], row["company_b"]))
    return found[:limit]
