"""經濟部商業發展署「董監事資料集」載入器：把全國公司登記資料餵進集團歸戶引擎。

來源：https://data.gcis.nat.gov.tw/od/file?oid=7E5201D9-CAD2-494E-8920-5319D66F66A1
資料集頁：https://data.gov.tw/dataset/96731
提供機關：經濟部商業發展署　授權：政府資料開放授權條款－第1版　更新頻率：每月
欄位：統一編號, 公司名稱, 職稱, 姓名, 所代表法人, 持有股份數

這份資料集**沒有身分證字號**，姓名比對必然會把同名不同人的公司誤併（全台
「陳建宏」一個名字就掛名 411 家公司）。因此本模組把資料切成兩層信心，對應
到 smelens.credit.group.Affiliation.tier：

- A 層（法人董事關係，tier="A"）：「所代表法人」欄位直接指名另一個登記在案
  的法人，是不是同一個實體不必猜——法人名稱在商業登記上要求不重複，不像
  自然人姓名那樣浮濫撞名。這層的群組歸戶站得住腳，不需要銀行另外核對身分。
- B 層（自然人董事關係，tier="B"）：純靠姓名字串相同判斷「可能是同一人」，
  是候選清單，不是定論——銀行要拿自己 KYC 留存的身分證字號才能把候選收斂
  成確認的關聯，本模組不假裝能做到這一步。

董監事資料集裡的「缺額」類佔位字串必須先剔除，否則會把好幾千個空缺席次
誤判成同一個「人」，把互不相干的公司全部併成一個假集團。
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from smelens.credit.group import Affiliation, normalise_name

#: 董監事欄位裡出現的席次佔位字串，不是自然人姓名。剔除範圍刻意只取這三種
#: 精確字串（依實測次數由高到低：缺額 3,512、暫缺 603、(缺額) 277），
#: 不做模糊比對——模糊比對會連「辭任缺額」「從缺」這類措辭不一但仍是佔位的
#: 罕見寫法一起吃下，範圍會隨資料抽樣而變、不可重現；本模組只保證這三種
#: 精確字串一定被剔除，其餘留給下游人工覆核判斷。
VACANCY_PLACEHOLDERS = frozenset({"缺額", "暫缺", "(缺額)"})

#: 董監事資料集欄位名稱，供 csv.DictReader 對照。
COL_COMPANY_ID = "統一編號"
COL_COMPANY_NAME = "公司名稱"
COL_ROLE = "職稱"
COL_PERSON_NAME = "姓名"
COL_REPRESENTED_ENTITY = "所代表法人"
COL_SHARES = "持有股份數"


def _parse_shares(raw: str) -> float | None:
    """持有股份數欄位轉浮點數；空字串或無法解析一律回傳 None（非 0）。

    0 股與「沒有這個欄位」在授信意義上不同：前者是登記在案的股東持股歸零，
    後者是資料集根本沒填。回傳 None 才能讓下游區分「真的是 0」與「不知道」。
    """
    raw = raw.strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def iter_rows(csv_path: str | Path) -> Iterator[dict[str, str]]:
    """逐列串流讀取董監事資料集原始 CSV，不一次載入 119MB 進記憶體。

    檔案為 UTF-8 with BOM；用 utf-8-sig 開檔讓 csv 模組自動吃掉 BOM，
    否則第一欄欄位名稱會變成 "\\ufeff統一編號"，後續所有欄位查找都會失敗。
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        yield from csv.DictReader(f)


def load_affiliations(csv_path: str | Path, *, limit: int | None = None) -> Iterator[Affiliation]:
    """串流載入 B 層（自然人董事）Affiliation：剔除席次佔位列，姓名比對候選。

    company_id 一律填入統一編號（無歧義）；person_id 留 None——資料集本身
    沒有身分證字號可填，硬編一個假的 identifier 只會製造「看起來已核實」
    的錯覺。tier 固定為 "B"，因為這一層天生就只能靠姓名比對。
    limit 只在測試或抽樣時使用；正式流程不應該傳。
    """
    count = 0
    for row in iter_rows(csv_path):
        if limit is not None and count >= limit:
            return
        person = row[COL_PERSON_NAME].strip()
        if not person or person in VACANCY_PLACEHOLDERS:
            continue
        count += 1
        yield Affiliation(
            company=row[COL_COMPANY_NAME],
            person=person,
            role=row[COL_ROLE] or "董監事",
            company_id=row[COL_COMPANY_ID].strip() or None,
            person_id=None,
            tier="B",
            shares=_parse_shares(row[COL_SHARES]),
        )


@dataclass(frozen=True)
class CorporateDirectorEdge:
    """一筆 A 層（法人董事）關係：某公司的董監事席次由另一個法人代表出任。

    represented_id 是把 represented_name 對照全檔「公司名稱→統一編號」索引
    後查到的統一編號；查不到（例如所代表法人是未登記或名稱寫法不一致的實體）
    時為 None，此時這條邊仍可用名稱字串當退回鍵，但信心跟著名稱比對的限制走。
    """

    company_id: str
    company_name: str
    represented_name: str
    represented_id: str | None
    representative_person: str
    shares: float | None


def _build_company_name_index(csv_path: str | Path) -> dict[str, str]:
    """建立「正規化公司名稱→統一編號」索引，供所代表法人的名稱查回統編用。

    同一公司名稱理論上對應同一統編；重複出現時保留第一次看到的統編
    （同一家公司在檔案裡會因多個董監事席次重複出現很多列，取哪一列的統編
    都一樣，不影響結果）。
    """
    index: dict[str, str] = {}
    for row in iter_rows(csv_path):
        name = normalise_name(row[COL_COMPANY_NAME])
        cid = row[COL_COMPANY_ID].strip()
        if name and cid:
            index.setdefault(name, cid)
    return index


def load_corporate_director_edges(csv_path: str | Path) -> list[CorporateDirectorEdge]:
    """載入 A 層邊：所代表法人非空的列，去重為 (公司, 所代表法人) 唯一邊。

    同一家公司對同一個法人董事可能因股東會改選、多個席次而在資料集裡出現
    多列，這些都代表同一條「A 公司—B 法人」關聯，去重後才是實際的邊數
    （全檔實測：112,687 列去重後 67,736 條邊，見 docs/GCIS_FINDINGS.md）。

    需要先掃一次全檔建公司名稱索引，再掃一次收集所代表法人非空的列——固定
    兩次線性掃描，不是 O(n²)；索引本身留在記憶體（約百萬筆字串鍵，可接受），
    但每一列的原始內容不會全部留著。
    """
    name_index = _build_company_name_index(csv_path)
    seen: set[tuple[str, str]] = set()
    edges: list[CorporateDirectorEdge] = []
    for row in iter_rows(csv_path):
        represented = row[COL_REPRESENTED_ENTITY].strip()
        if not represented or represented in VACANCY_PLACEHOLDERS:
            continue
        company_id = row[COL_COMPANY_ID].strip()
        if not company_id:
            continue
        key = (company_id, normalise_name(represented))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            CorporateDirectorEdge(
                company_id=company_id,
                company_name=row[COL_COMPANY_NAME],
                represented_name=represented,
                represented_id=name_index.get(normalise_name(represented)),
                representative_person=row[COL_PERSON_NAME].strip(),
                shares=_parse_shares(row[COL_SHARES]),
            )
        )
    return edges


def corporate_edges_to_affiliations(edges: list[CorporateDirectorEdge]) -> Iterator[Affiliation]:
    """把 A 層邊轉成 Affiliation，餵進 build_company_graph 沿用既有歸戶機制。

    把「所代表法人」當成 Affiliation 的 person 端：兩家公司若由同一個法人
    出任董事，build_company_graph 的共用實體機制就會自動把它們連邊——這正是
    A 層要抓的「同一法人坐兩家公司董事席」，且因為 person_id 用統一編號
    （查得到時）或正規化名稱（查不到時）比對，不會被姓名撞名污染。tier="A"
    讓這條邊在 build_company_graph 裡標記為高信心，不會被同一對公司之間
    可能存在的 B 層雜訊邊蓋掉。
    """
    for edge in edges:
        yield Affiliation(
            company=edge.company_name,
            person=edge.represented_name,
            role="法人董事",
            company_id=edge.company_id,
            person_id=edge.represented_id,
            tier="A",
            shares=edge.shares,
        )


def extract_neighborhood(
    csv_path: str | Path,
    root_company_id: str,
    *,
    depth: int = 2,
    max_companies: int = 300,
    hub_name_threshold: int = 20,
) -> list[Affiliation]:
    """從指定統一編號出發，沿共用自然人董監事姓名（B 層）關係展開至多 depth
    層的鄰域。

    目前只展開 B 層：實測發現以法人代表出任董事的公司（如台積電）董監事名冊
    多半是「法人代表 A 代表 B 法人出任」的登記型態，A 層關係（所代表法人）
    未被這個函式用來擴展邊界——要把兩層一起展開，需要另外對 所代表法人 建立
    第二種索引查找，屬已知限制，留待下一階段擴充；目前對外只承諾 B 層鄰域，
    不誇稱涵蓋 A 層。

    國家級全圖有 102 萬家公司、67,736 條 A 層邊，任何端點都不該對整張圖跑
    動機偵測——一份先前的效能量測顯示 detect_cycle_trade 在 3,000 節點就要
    24 秒，是信用管線裡唯一的非線性步驟。此函式把分析範圍先收斂到有限鄰域，
    讓後續分析（含動機偵測）有界。

    展開方式：以公司統編為單位做 BFS，每一層線性掃描兩次全檔（一次收集邊界
    公司自身的董監事列，一次找這些姓名還掛名了哪些公司）——O(depth) 次檔案
    掃描、O(邊界公司數) 記憶體，不會把全國圖建進記憶體，但也代表延遲隨
    depth 線性成長：實測對台積電（22099131）depth=2、max_companies=300 要
    約 35 秒（見 docs/GCIS_FINDINGS.md 效能量測）——對單次分析可接受，但不
    適合逐次請求都重新掃檔；正式上線應在檔案之上建一次性索引（例如
    company_id→董監事姓名、姓名→company_id 的反向表存進資料庫或記憶體結構），
    而不是每個請求都重掃 CSV。本函式目前的設計目標是「正確且有界」，不是
    「毫秒級回應」。

    hub_name_threshold 是姓名同名爆炸的防護閥：一個姓名若已知掛名公司數
    達到門檻（例如「陳建宏」411 家），就不再用它往外展開——真實世界裡這種
    姓名幾乎必然是撞名而非同一人，放行的話兩三層以內鄰域就會吃下全國圖。
    這個防護閥本身就是 B 層「姓名比對不可靠」的直接體現，不是效能取巧。

    max_companies 是鄰域公司數上限，達到後停止展開（即使 depth 還沒走完）。
    回傳值是這個鄰域內收集到的 Affiliation 清單（B 層 + 可判別的 A 層皆含），
    可直接餵給 build_company_graph。
    """
    if depth < 1:
        raise ValueError("depth 至少為 1")

    visited_companies: set[str] = {root_company_id}
    frontier: set[str] = {root_company_id}
    collected: list[Affiliation] = []
    collected_keys: set[tuple[str, str, str]] = set()  # (company_id, person, role) 去重

    for _ in range(depth):
        if not frontier or len(visited_companies) >= max_companies:
            break

        # 第一次掃描：收集邊界公司自己的董監事列，順便統計每個姓名在這一批
        # 裡掛了幾家公司——用來套用 hub_name_threshold。
        hop_rows: list[dict[str, str]] = []
        name_hit_count: dict[str, int] = {}
        for row in iter_rows(csv_path):
            cid = row[COL_COMPANY_ID].strip()
            if cid not in frontier:
                continue
            person = row[COL_PERSON_NAME].strip()
            if not person or person in VACANCY_PLACEHOLDERS:
                continue
            hop_rows.append(row)
            key = normalise_name(person)
            name_hit_count[key] = name_hit_count.get(key, 0) + 1

        expand_names = {
            normalise_name(row[COL_PERSON_NAME])
            for row in hop_rows
            if name_hit_count[normalise_name(row[COL_PERSON_NAME])] < hub_name_threshold
        }

        for row in hop_rows:
            key = (row[COL_COMPANY_ID].strip(), row[COL_PERSON_NAME].strip(), row[COL_ROLE])
            if key in collected_keys:
                continue
            collected_keys.add(key)
            collected.append(
                Affiliation(
                    company=row[COL_COMPANY_NAME],
                    person=row[COL_PERSON_NAME].strip(),
                    role=row[COL_ROLE] or "董監事",
                    company_id=row[COL_COMPANY_ID].strip() or None,
                    person_id=None,
                    tier="B",
                    shares=_parse_shares(row[COL_SHARES]),
                )
            )

        if not expand_names:
            break

        # 第二次掃描：找出誰還掛名了哪些其他公司（排除 hub 姓名），組成下一層邊界。
        # max_companies 在這裡就要即時生效——visited_companies 每發現一家新公司
        # 就立刻計入，額滿後續行只收既有邊界公司的列，不再讓新公司進來，
        # 否則同一層裡先掃到的列會把上限撐爆才被發現。
        next_frontier: set[str] = set()
        for row in iter_rows(csv_path):
            person = row[COL_PERSON_NAME].strip()
            if not person or person in VACANCY_PLACEHOLDERS:
                continue
            if normalise_name(person) not in expand_names:
                continue
            cid = row[COL_COMPANY_ID].strip()
            if not cid:
                continue
            is_new_company = cid not in visited_companies
            if is_new_company:
                if len(visited_companies) >= max_companies:
                    continue
                visited_companies.add(cid)
                next_frontier.add(cid)
            key = (cid, person, row[COL_ROLE])
            if key not in collected_keys:
                collected_keys.add(key)
                collected.append(
                    Affiliation(
                        company=row[COL_COMPANY_NAME],
                        person=person,
                        role=row[COL_ROLE] or "董監事",
                        company_id=cid,
                        person_id=None,
                        tier="B",
                        shares=_parse_shares(row[COL_SHARES]),
                    )
                )

        frontier = next_frontier

    return collected
