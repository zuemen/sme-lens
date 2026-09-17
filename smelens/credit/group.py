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
    """一筆公司—自然人關係（董監事、股東或負責人）。

    company_id（公司統一編號）與 person_id（自然人的識別碼，例如身分證字號的
    去識別化代碼）皆為選填。兩者一旦提供，就是本模組判斷「是不是同一個實體」
    的依據，名稱只用來顯示——這不是便利性欄位，是正確性欄位：全台叫「陳志明」
    的自然人不只一個，光憑名稱字串比對，六個互不相干的陳志明會被歸成同一個
    集團；反過來，真正想藏身的人只要換一種名稱寫法掛名，也能繞過名稱比對。
    有 identifier 就用 identifier，沒有才退回正規化後的名稱——與先前完全一致，
    既有只傳名稱的呼叫方行為不變。

    tier："A"＝法人董事關係（所代表法人→公司，無姓名歧義，見
    smelens.data.gcis）；"B"＝自然人董事／股東關係，靠姓名比對，須交由銀行
    自有身分證字號資料解析為候選才能確認，不可逕行歸戶。預設 "B"：既有只傳
    公司／姓名的呼叫方（如手動輸入的名冊、示範劇本）維持與先前完全一致的行為，
    不會被追溯貼上不該有的高信心標籤。

    shares（持有股份數）僅在來源資料有提供時才會非 None，為候選關聯排序用的
    真實權重，非比對依據。

    merge：這個共用實體是否可以拿來把兩家公司併成同一個歸戶集團。預設 True，
    既有呼叫方（demo 劇本、手動名冊）行為不變。False 用在銀行、政府基金這類
    「機構股東」：它們在數十家公司掛法人董事席次是機構投資，不是控股關係——
    全國實測發現若不分青紅皂白全部拿來做遞移合併，中國信託銀行、國發基金等
    十來個機構會把 7,187 家互不相干的公司透過遞移閉包併成一個假集團（見
    docs/GCIS_FINDINGS.md）。merge=False 的關係仍會入圖、仍會被列為證據
    （hidden_links 看得到、標成 bridge_only），只是不會被 detect_groups
    拿來當作合併兩家公司的依據——「兩家公司都有中國信託的席次」是行員該看到
    的資訊，不代表這兩家公司是同一個集團。
    """

    company: str
    person: str
    role: str = "董監事"
    company_id: str | None = None
    person_id: str | None = None
    tier: str = "B"
    shares: float | None = None
    merge: bool = True


def _identity_key(name: str, identifier: str | None, prefix: str) -> str:
    """實體鍵：identifier 提供時回傳識別碼衍生鍵，否則回傳正規化後的名稱。

    identifier 一律加上 prefix（"cid"／"pid"）區隔命名空間，避免識別碼衍生鍵
    與某個公司或自然人恰好正規化後長得一樣的名稱字串相撞。
    """
    if identifier:
        return f"{prefix}:{normalise_name(identifier)}"
    return normalise_name(name)


def build_company_graph(affiliations: Iterable[Affiliation]) -> nx.Graph:
    """由關係名冊建立公司關聯無向圖：共用同一自然人的兩家公司之間連邊。

    邊屬性 weight = 共用的自然人數；shared = 共用自然人名單（排序後）。
    無任何共用關係的公司仍會入圖成為孤立節點——歸戶時不能把它們漏掉。

    公司與自然人的「同一實體」判斷一律 identifier 優先、名稱退回（見
    Affiliation 與 _identity_key）：同一 person_id 底下不論名稱寫法（含尾隨
    空白、全形變體）都視為同一人；不同 person_id 即使名稱字串相同也視為不同
    人，不會因為同名而把互不相干的公司併成一個集團。

    邊屬性另有 tier："A"＝該邊至少有一個共用實體來自 Affiliation.tier=="A"
    （法人董事關係，無姓名歧義）；否則 "B"（自然人姓名比對，須銀行自有資料
    解析為候選）。同一對公司若同時因法人董事與同名自然人相連，以較高信心的
    "A" 為準——A 層的證據不會被 B 層的雜訊稀釋。

    邊屬性另有 bridge_only：True 代表這條邊目前的共用實體全部是
    Affiliation.merge==False（機構股東等橋接點），detect_groups 不會用它來
    合併兩家公司；只要其中一個共用實體 merge==True，這條邊就是可合併的
    真實邊（bridge_only=False），機構橋接不會蓋掉真正的控股關係證據。
    """
    raw = list(affiliations)

    # 節點鍵在有 company_id 時是識別碼衍生字串（"cid:..."），下游（API 回應、
    # 曝險比對、隱性關聯清單）全部把節點鍵當公司顯示名稱使用，故最後要 relabel
    # 回顯示名稱（同一識別碼底下第一次出現的正規化名稱）。沒有 company_id 時，
    # 這個對照是恆等映射，relabel 等於沒做，行為與先前完全相同。
    company_display: dict[str, str] = {}
    person_display: dict[str, str] = {}

    def company_key(item: Affiliation) -> str:
        key = _identity_key(item.company, item.company_id, "cid")
        company_display.setdefault(key, normalise_name(item.company))
        return key

    def person_key(item: Affiliation) -> str:
        key = _identity_key(item.person, item.person_id, "pid")
        person_display.setdefault(key, normalise_name(item.person))
        return key

    by_person: dict[str, set[str]] = {}
    person_tier: dict[str, str] = {}
    person_merge: dict[str, bool] = {}
    for item in raw:
        pk = person_key(item)
        by_person.setdefault(pk, set()).add(company_key(item))
        # "A" 一旦成立就不再降級：同一個 person_key 若同時被 tier="A" 與
        # tier="B" 的 Affiliation 指到（資料不一致或刻意混報），信心以較高者為準。
        if person_tier.get(pk) != "A":
            person_tier[pk] = item.tier
        # merge 同理：同一個實體只要有一筆 Affiliation 說「這是可合併的」
        # （merge=True），就不因為另一筆混報 merge=False 而被降級為機構橋接點。
        if not person_merge.get(pk, False):
            person_merge[pk] = item.merge

    g = nx.Graph()
    for item in raw:
        g.add_node(company_key(item))
    for person, companies in by_person.items():
        person_name = person_display[person]
        tier = person_tier.get(person, "B")
        can_merge = person_merge.get(person, True)
        for u, v in combinations(sorted(companies), 2):
            if g.has_edge(u, v):
                data = g[u][v]
                data["weight"] += 1
                data["shared"].append(person_name)
                if tier == "A":
                    data["tier"] = "A"
                if can_merge:
                    data["bridge_only"] = False
            else:
                g.add_edge(
                    u, v, weight=1, shared=[person_name], tier=tier, bridge_only=not can_merge
                )
    for _, _, data in g.edges(data=True):
        data["shared"].sort()

    return nx.relabel_nodes(g, company_display)


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

    連通元件只沿著 bridge_only!=True 的邊展開：邊屬性 bridge_only=True 代表
    這條邊唯一的共用實體是 merge=False 的機構股東（見 build_company_graph／
    Affiliation.merge 文件）——這種邊本身仍留在 company_graph 裡供 hidden_links
    等函式回報「兩家公司都有這個機構股東」的證據，但不能拿來把兩家公司併成
    同一個歸戶集團，否則全國實測發現中國信託銀行、國發基金這類同時出任數十家
    公司法人董事的機構，會把上千家互不相干的公司透過遞移閉包併成一個假集團。
    """
    merge_graph = nx.Graph()
    merge_graph.add_nodes_from(company_graph.nodes())
    merge_graph.add_edges_from(
        (u, v)
        for u, v, data in company_graph.edges(data=True)
        if not data.get("bridge_only", False)
    )
    groups: dict[str, int] = {}
    components = sorted(nx.connected_components(merge_graph), key=lambda c: sorted(c)[0])
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
                # tier："A"＝法人董事關係（無姓名歧義）；"B"＝自然人姓名比對候選，
                # 見 build_company_graph docstring。舊資料（未經 build_company_graph
                # 重建的圖）沒有這個邊屬性時退回 "B"，不假裝有法人層級的信心。
                "tier": data.get("tier", "B"),
                # bridge_only=True：這條關聯只來自機構股東（銀行、政府基金等），
                # detect_groups 不會拿它合併集團，但仍是行員該看到的證據——
                # 「兩家公司都有這個機構股東」不等於「這兩家公司是同一個集團」，
                # 兩者不能混為一談，故用旗標讓前端／行員自行判斷要不要採信。
                "bridge_only": data.get("bridge_only", False),
            }
        )
    found.sort(key=lambda row: (-row["weight"], row["company_a"], row["company_b"]))
    return found[:limit]
