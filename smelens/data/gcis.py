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
  成確認的關聯，本模組不假裝能做到這一步。因此本模組所有 B 層 Affiliation
  一律 merge=False：這種共用關係仍會入圖、仍會被 hidden_links 回報成候選
  （帶共用姓名、tier="B"、bridge_only=True），但 detect_groups 不會拿它把
  兩家公司併成同一個歸戶集團——集團歸戶（`groups`）只由 A 層無姓名歧義的
  證據撐起，B 層只能是交給銀行拿身分證字號解析的候選清單，兩者在輸出上
  必須是可分開看的兩個東西，不能被一次歸戶結果混著呈現成十五家「同一個
  集團」。

董監事資料集裡的「缺額」類佔位字串必須先剔除，否則會把好幾千個空缺席次
誤判成同一個「人」，把互不相干的公司全部併成一個假集團。
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import os
import shutil
import sqlite3
import uuid
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

    merge 固定為 False：B 層沒有身分證字號佐證，純姓名字串比對必然把同名
    不同人的公司誤併（全台「陳建宏」一個名字掛名 411 家公司，見
    docs/GCIS_FINDINGS.md）。這條關係仍會入圖、仍會被 hidden_links 回報成
    候選（帶共用姓名與 tier="B"），但 detect_groups 不會拿它把兩家公司併成
    同一個歸戶集團——集團歸戶只能由 A 層（無姓名歧義）證據撐起，B 層永遠是
    交給銀行拿自己 KYC 身分證字號資料解析的候選清單，不可逕行歸戶。
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
            merge=False,
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


#: 法人董事席次數達到此門檻即視為「機構／橋接實體」，其共用關係只作證據
#: 不作歸戶合併依據（Affiliation.merge=False）。
#:
#: 門檻由全國實測資料的席次分布實際掃出來，不是憑感覺訂的（見
#: docs/GCIS_FINDINGS.md「機構橋接門檻」一節，可用
#: scripts/gcis_findings.py 重新驗證）：對 67,838 條法人董事邊依代表實體
#: 分組計數席次數後，以不同門檻重跑 build_company_graph+detect_groups 觀察
#: 最大歸戶群組規模——
#:   門檻 2：多公司群組全數消失（多數真實的小型控股集團也被當成機構濾掉，
#:           門檻太嚴不可用）
#:   門檻 3～4：最大群組仍有 9～46 家，殘留跨集團誤併
#:   門檻 5：最大群組驟降到 89 家（原始未過濾時為 7,187 家）——這是本欄位
#:           實測到最大群組規模開始明顯收斂、且排除實體僅佔全體代表實體
#:           3.7%（1,610／43,376）的轉折點，故取 5 為預設值
#:   門檻 6 以上：最大群組回升到 224、423、987……橋接效應重新主導
#: 5 家以上法人代表席次，落在「可能是專業經理人／會計師事務所常態掛名」與
#: 「真正控股家族集團」的模糊地帶，純席次計數無法完美區分兩者（若要精準
#: 區分，需要「持有股份數」這類實質控制力訊號，屬後續工作）；用 5 作預設
#: 是保守選擇——寧可漏掉幾個中型集團的合併資格，也不要讓機構股東把整個
#: 資本市場透過遞移閉包併成一個假集團。銀行可依自身風控政策調整。
DEFAULT_HUB_SEAT_THRESHOLD = 5


def _represented_identity_key(edge: CorporateDirectorEdge) -> str:
    """A 層代表實體的識別鍵，與 build_company_graph._identity_key 邏輯一致：
    有 represented_id 就用 identifier 衍生鍵，沒有才退回正規化後的名稱。
    """
    if edge.represented_id:
        return f"pid:{normalise_name(edge.represented_id)}"
    return normalise_name(edge.represented_name)


def _distinct_group_counts(
    edges: list[CorporateDirectorEdge],
    group_key,
    item_key,
) -> Counter[str]:
    """依 group_key 分組，計數每組內「相異」item_key 值的個數。

    機構橋接（一個法人代表太多家公司）與合資橋接（一家公司被太多不同法人
    代表）是同一個問題的兩個方向——差別只在於哪一端當分組鍵、哪一端當計數
    對象。本函式把「分組→計數相異值」這個共同邏輯抽出來，
    classify_hub_entities／classify_coinvestee_companies 各自只需要決定
    group_key 與 item_key 怎麼指定，不必各寫一份幾乎相同的迴圈。
    """
    groups: dict[str, set[str]] = {}
    for e in edges:
        groups.setdefault(group_key(e), set()).add(item_key(e))
    return Counter({key: len(items) for key, items in groups.items()})


def classify_hub_entities(
    edges: list[CorporateDirectorEdge], *, seat_threshold: int = DEFAULT_HUB_SEAT_THRESHOLD
) -> set[str]:
    """回傳法人董事席次數達門檻的「機構／橋接實體」識別鍵集合。

    計數以 _represented_identity_key 分組（identifier 優先、名稱退回），
    與 build_company_graph 判斷「同一實體」的邏輯一致，確保這裡標記的
    hub 與圖上實際會被合併的邊是同一組實體。以相異公司數計數（而非邊數），
    避免同一家公司因所代表法人名稱寫法不一致而重覆列在同一組底下時，把
    分母灌水。
    """
    counts = _distinct_group_counts(edges, _represented_identity_key, lambda e: e.company_id)
    return {key for key, count in counts.items() if count >= seat_threshold}


#: 一家公司被幾個「相異」法人董事共同代表即視為「合資／被投資橋接實體」，
#: 其 A 層 Affiliation 只作證據不作歸戶合併依據——與 DEFAULT_HUB_SEAT_THRESHOLD
#: 是同一個問題的鏡像版本（機構橋接防「一個法人代表太多家」；合資橋接防
#: 「一家公司被太多不同法人代表」），見 classify_coinvestee_companies docstring
#: 與 docs/GCIS_FINDINGS.md「合資橋接門檻」一節的實測依據。
#:
#: 門檻由兩份全國實測資料交叉決定，不是憑感覺訂的：
#:
#: 1. 分布（scripts/_coinvestee_scan.py 產出 data/cache/coinvestee_scan.json
#:    可重跑驗證）：對 53,114 家有法人董事的公司計數相異法人董事數，高度
#:    右偏——1 個：43,995 家（82.8%）、2 個：6,024 家（11.3%）、3 個：
#:    1,798 家（3.4%）、4 個以上僅 1,297 家（2.4%）。4 是分布尾巴實際開始
#:    變細的轉折點：1～3 個仍是「一家控股公司＋至多一兩位共同投資人」的
#:    合理結構，4 個以上才明顯是多方共同出資的合資／創投被投資公司型態。
#: 2. 全國最大群組規模（scripts/_coinvestee_sweep.py，機構橋接門檻固定在
#:    DEFAULT_HUB_SEAT_THRESHOLD=5，只變動本門檻）——
#:      門檻 2：最大群組 14 家，多公司群組 17,282 個
#:      門檻 3：最大群組 34 家，多公司群組 19,082 個
#:      門檻 4：最大群組 60 家，多公司群組 19,129 個（本欄位取此值）
#:      門檻 5：最大群組 99 家，多公司群組 18,991 個
#:      門檻 6：最大群組 108 家，多公司群組 18,889 個
#:      門檻 7：最大群組 118 家，多公司群組 18,826 個
#:      門檻 10：最大群組 349 家，多公司群組 18,696 個
#:      不設此防護：最大群組 1,448 家（母公司歸戶修復的副作用，見
#:      docs/GCIS_FINDINGS.md）
#:    門檻 4 同時是「最大群組規模仍低（60 家）」與「多公司群組數最高
#:    （19,129，比門檻 2、3 都多）」兩者兼顧的最佳點——門檻 2、3 雖然最大
#:    群組更小，但濾掉了更多真實的小型多公司群組（過嚴誤殺）；門檻 5 以上
#:    最大群組回升，橋接效應重新主導。取 4 為預設值：與機構橋接門檻 5 相近
#:    但略嚴一格——公司端的合資訊號比法人端的機構訊號更直接（一家公司同時
#:    被 4 個不相干法人派任董事，幾乎必然代表多方共同投資）。銀行可依自身
#:    風控政策調整。
DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD = 4


def classify_coinvestee_companies(
    edges: list[CorporateDirectorEdge],
    *,
    director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
) -> set[str]:
    """回傳相異法人董事數達門檻的「合資／被投資橋接」公司統一編號集合。

    這是 classify_hub_entities 的鏡像：機構橋接防「一個法人代表太多家
    公司」，合資橋接防「一家公司被太多不同法人代表」——兩者都是遞移閉包
    過度擴散的同一類問題，只是換了分組的方向，故重用 _distinct_group_counts
    同一份邏輯，只是把 group_key／item_key 對調。

    全國實測發現：母公司歸戶根因修復（母公司自身也入圖）之後，任何一家
    「被多個不相干法人共同派任董事」的公司（合資公司、創投被投資公司）
    會把這些法人各自的家族全部橋接起來，即使每個法人各自的代表席次都遠
    低於機構橋接門檻——這正是本函式要抓的對稱防護，見
    docs/GCIS_FINDINGS.md「合資橋接門檻」一節。

    計數以公司統一編號分組（load_corporate_director_edges 保證非空），
    相異法人董事以 _represented_identity_key 判斷（identifier 優先、名稱
    退回），與 classify_hub_entities 完全一致。
    """
    counts = _distinct_group_counts(edges, lambda e: e.company_id, _represented_identity_key)
    return {key for key, count in counts.items() if count >= director_threshold}


def corporate_edges_to_affiliations(
    edges: list[CorporateDirectorEdge],
    *,
    hub_seat_threshold: int = DEFAULT_HUB_SEAT_THRESHOLD,
    coinvestee_director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
) -> Iterator[Affiliation]:
    """把 A 層邊轉成 Affiliation，餵進 build_company_graph 沿用既有歸戶機制。

    把「所代表法人」當成 Affiliation 的 person 端：兩家公司若由同一個法人
    出任董事，build_company_graph 的共用實體機制就會自動把它們連邊——這正是
    A 層要抓的「同一法人坐兩家公司董事席」，且因為 person_id 用統一編號
    （查得到時）或正規化名稱（查不到時）比對，不會被姓名撞名污染。tier="A"
    讓這條邊在 build_company_graph 裡標記為高信心，不會被同一對公司之間
    可能存在的 B 層雜訊邊蓋掉。

    hub_seat_threshold 用來標記機構／橋接實體（見 DEFAULT_HUB_SEAT_THRESHOLD
    docstring 的實測依據）：席次數達門檻者，該法人的每一筆 Affiliation 都
    設 merge=False——build_company_graph／detect_groups 仍會把它畫成邊（供
    hidden_links 回報「這兩家公司都有此機構股東」的證據），但不會拿來把
    兩家公司併成同一個歸戶集團，避免銀行、政府基金等把大半資本市場透過
    遞移閉包併成一個假集團（全國實測：不過濾時最大群組 7,187 家公司，
    見 docs/GCIS_FINDINGS.md）。

    根因修復——母公司要進自己的歸戶群組：改版前只把「所代表法人」當成連結
    兩家*子公司*的橋（子公司 A、子公司 B 因共用同一法人代表而連邊），母公司
    本身從未被畫進圖裡，於是「一詮精密工業」帶出 4 家子公司的歸戶群組裡完全
    找不到一詮精密工業自己——這正好把銀行法「關係企業」最在意的母公司排除
    在曝險歸戶外，倒果為因。修法：所代表法人名稱一旦能對照回統一編號
    （represented_id 非 None），就額外多送一筆「母公司自己」的 Affiliation
    （company=person=該法人本身、company_id=person_id=represented_id）。
    這筆 Affiliation 與每一筆子公司的 A 層 Affiliation 共用同一個
    person_key（都是同一個 represented_id），build_company_graph 的共用實體
    機制就會把母公司節點與每一家子公司節點直接連邊，不必再繞經自然人姓名
    重疊才勉強接上。查不到統一編號的所代表法人（約 19%，多為政府機關、
    境外法人、基金會，見 docs/GCIS_FINDINGS.md）本就不是這份資料集裡的
    公司節點，沒有母公司節點可連，維持現狀退回名稱比對，信心不變、也不會
    被靜默丟棄——子公司之間仍照舊靠名稱字串共用同一個「所代表法人」而連邊。
    同一個母公司在多筆邊裡重覆出現時，這筆自身 Affiliation 只送一次
    （seen_parents 去重），避免無意義地重覆同一份資料。

    合資橋接對稱防護——一家公司被太多不同法人代表：母公司根因修復讓母公司
    節點本身也入圖後，任何「被多個不相干法人共同派任董事」的公司（合資
    公司、創投被投資公司）會把這些法人各自的家族全部橋接起來，即使每個
    法人各自的代表席次都遠低於機構橋接門檻——這是機構橋接問題的鏡像，見
    classify_coinvestee_companies docstring。修法：coinvestee_director_threshold
    達標的公司統一編號（見 classify_coinvestee_companies），其「作為子公司
    被代表」的那筆 Affiliation（company=該公司）額外標記 merge=False；母
    公司自身的 Affiliation 不受影響，仍照機構橋接門檻單獨判斷。這與機構
    橋接的合併判斷同理必須落到 build_company_graph 的逐邊（而非逐實體）
    層級——見該函式 docstring「按 (company, person) 逐邊判斷」一節。
    """
    hub_ids = classify_hub_entities(edges, seat_threshold=hub_seat_threshold)
    coinvestee_ids = classify_coinvestee_companies(
        edges, director_threshold=coinvestee_director_threshold
    )
    seen_parents: set[str] = set()
    for edge in edges:
        key = _represented_identity_key(edge)
        can_merge = key not in hub_ids and edge.company_id not in coinvestee_ids
        yield Affiliation(
            company=edge.company_name,
            person=edge.represented_name,
            role="法人董事",
            company_id=edge.company_id,
            person_id=edge.represented_id,
            tier="A",
            shares=edge.shares,
            merge=can_merge,
        )
        if edge.represented_id and key not in seen_parents:
            seen_parents.add(key)
            parent_can_merge = key not in hub_ids and edge.represented_id not in coinvestee_ids
            yield Affiliation(
                company=edge.represented_name,
                person=edge.represented_name,
                role="法人董事（母公司自身）",
                company_id=edge.represented_id,
                person_id=edge.represented_id,
                tier="A",
                shares=None,
                merge=parent_can_merge,
            )


#: 一次性索引的存放目錄。已在 .gitignore 中整批排除（見 data/cache/.gitkeep），
#: 索引檔不會被提交，且可安全刪除重建。
INDEX_CACHE_DIR = Path("data/cache")

_INDEX_SCHEMA = """
CREATE TABLE rows (
    company_id TEXT NOT NULL,
    company_name TEXT NOT NULL,
    role TEXT NOT NULL,
    person_name TEXT NOT NULL,
    person_norm TEXT NOT NULL,
    represented_name TEXT NOT NULL DEFAULT '',
    represented_norm TEXT NOT NULL DEFAULT '',
    represented_id TEXT,
    shares REAL
)
"""


def _default_index_path(csv_path: str | Path) -> Path:
    """依來源 CSV 的路徑＋檔案大小＋修改時間算出索引檔名。

    索引檔名不能是固定的一個名字：若兩個不同的 CSV（例如測試用的小型抽樣檔
    與正式的全國檔）共用同一個索引檔路徑，先建立的那個會被誤認成「已經有
    索引了」而被後面完全不同來源的查詢直接沿用——查出來的鄰域會是另一份
    資料的結果，且不會有任何錯誤訊息。指紋含檔案大小與修改時間，來源檔案
    被商業司月更後也會自動失效重建，不會悄悄回傳過期資料。
    """
    path = Path(csv_path).resolve()
    try:
        stat = path.stat()
        fingerprint = f"{path}:{stat.st_size}:{int(stat.st_mtime)}"
    except OSError:
        fingerprint = str(path)
    digest = hashlib.sha1(fingerprint.encode("utf-8")).hexdigest()[:16]
    return INDEX_CACHE_DIR / f"gcis_index_{digest}.sqlite"


def build_index(
    csv_path: str | Path, db_path: str | Path | None = None, *, force: bool = False
) -> Path:
    """把 CSV 建成一次性 SQLite 索引：company_id／person_norm／represented_norm
    各建一個索引，之後查詢是 O(log n) 的索引查找，不必每次請求都重掃 119MB。

    db_path 省略時依來源 CSV 算出專屬路徑（見 _default_index_path）；索引檔
    已存在且 force=False 時直接略過重建——extract_neighborhood 每次呼叫都會
    先呼叫本函式，若每次都重建索引就失去意義，故「已存在就沿用」是正確的
    預設行為，不是偷懶。

    建置本身仍是一次全檔線性掃描（兩次：一次建公司名稱→統編索引供 A 層
    represented_id 查找、一次插入所有列），對 119MB 檔案實測約需一到兩分鐘
    （見 docs/GCIS_FINDINGS.md 效能量測），但只需要做一次；之後不論查詢
    多少個統編、depth 多深，都不必再碰 CSV。

    寫入採 PRAGMA journal_mode=OFF、synchronous=OFF：索引檔是可重建的衍生
    產物（來源永遠是 CSV），不需要交易安全性換取寫入速度；建置中斷只會留下
    半成品檔案，重跑本函式即可（見下方 tmp 檔＋rename 的原子性處理）。
    """
    db_path = Path(db_path) if db_path is not None else _default_index_path(csv_path)
    if db_path.exists() and not force:
        return db_path

    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_suffix(db_path.suffix + ".building")
    tmp_path.unlink(missing_ok=True)

    name_index = _build_company_name_index(csv_path)

    conn = sqlite3.connect(tmp_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(_INDEX_SCHEMA)

        def _gen_rows() -> Iterator[tuple]:
            for row in iter_rows(csv_path):
                person = row[COL_PERSON_NAME].strip()
                if not person or person in VACANCY_PLACEHOLDERS:
                    continue
                cid = row[COL_COMPANY_ID].strip()
                if not cid:
                    continue
                represented = row[COL_REPRESENTED_ENTITY].strip()
                if represented and represented not in VACANCY_PLACEHOLDERS:
                    represented_norm = normalise_name(represented)
                    represented_id = name_index.get(represented_norm)
                else:
                    represented, represented_norm, represented_id = "", "", None
                yield (
                    cid,
                    row[COL_COMPANY_NAME],
                    row[COL_ROLE] or "董監事",
                    person,
                    normalise_name(person),
                    represented,
                    represented_norm,
                    represented_id,
                    _parse_shares(row[COL_SHARES]),
                )

        conn.executemany("INSERT INTO rows VALUES (?,?,?,?,?,?,?,?,?)", _gen_rows())
        conn.execute("CREATE INDEX idx_rows_company ON rows(company_id)")
        conn.execute("CREATE INDEX idx_rows_person ON rows(person_norm)")
        conn.execute("CREATE INDEX idx_rows_represented ON rows(represented_norm)")
        conn.commit()
    finally:
        conn.close()

    tmp_path.replace(db_path)
    return db_path


#: 精簡索引（scripts/build_demo_extract.py）額外攜帶的自然人席次表名稱。
#: 全國索引沒有這張表，_seat_counts 會退回就地聚合——兩者結果相同。
PERSON_SEAT_TABLE = "person_seats"


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    """索引檔裡是否存在指定資料表。"""
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,))
    return cur.fetchone() is not None


def _seat_counts(conn: sqlite3.Connection, column: str, values: set[str]) -> dict[str, int]:
    """查詢 column 欄位在 values 集合內各值的相異公司數（席次數）。

    column 只會是內部固定的 "person_norm" 或 "represented_norm"，不是使用者
    輸入，字串組 SQL 不構成注入風險。

    自然人席次（person_norm）另有一條路徑：精簡索引只保留「A 層宇宙」內公司
    的列（見 scripts/build_demo_extract.py），就地聚合會低估自然人席次，樞紐
    姓名因此濾不掉、BFS 會沿著菜市場名過度展開。故精簡索引另帶一張由全國
    資料算好的 person_seats 表，存在時優先採用；全國索引沒有這張表，走原本
    的就地聚合，兩者結果一致。represented_norm（法人席次）不需要這道處理：
    精簡索引保留了全部 A 層列，法人席次本來就是精確的。
    """
    if not values:
        return {}
    if column == "person_norm" and _has_table(conn, PERSON_SEAT_TABLE):
        placeholders = ",".join("?" * len(values))
        cur = conn.execute(
            f"SELECT person_norm, seats FROM {PERSON_SEAT_TABLE} "
            f"WHERE person_norm IN ({placeholders})",
            tuple(values),
        )
        return dict(cur.fetchall())
    placeholders = ",".join("?" * len(values))
    cur = conn.execute(
        f"SELECT {column}, COUNT(DISTINCT company_id) FROM rows "
        f"WHERE {column} IN ({placeholders}) GROUP BY {column}",
        tuple(values),
    )
    return dict(cur.fetchall())


def _coinvestee_director_counts(conn: sqlite3.Connection, company_ids: set[str]) -> dict[str, int]:
    """查詢 company_ids 這批公司統一編號各自的相異法人董事數。

    與 _seat_counts 是同一種聚合的鏡像方向：_seat_counts 數「一個法人代表
    幾家公司」，本函式數「一家公司被幾個相異法人代表」——COALESCE 讓
    represented_id 查得到時優先用它去重，查不到才退回 represented_norm，
    與 classify_coinvestee_companies／_represented_identity_key 同一套識別
    鍵邏輯，確保 BFS 展開這一側判斷的合資橋接公司與全國批次腳本判斷的是
    同一組公司。用一次 SQL 聚合完成，不必先把候選公司的全部列搬進 Python。
    """
    if not company_ids:
        return {}
    placeholders = ",".join("?" * len(company_ids))
    cur = conn.execute(
        "SELECT company_id, COUNT(DISTINCT COALESCE(represented_id, represented_norm)) "
        f"FROM rows WHERE company_id IN ({placeholders}) AND represented_norm != '' "
        "GROUP BY company_id",
        tuple(company_ids),
    )
    return dict(cur.fetchall())


#: 隨 repo 一起發佈的精簡索引（gzip）。全國 CSV 與完整索引都太大，無法進
#: 版控也無法上雲端函式；這份由 scripts/build_demo_extract.py 產生，內容與
#: 取捨見該腳本說明。
DEMO_INDEX_GZ = Path(__file__).resolve().parents[2] / "data" / "demo" / "gcis_a_tier.sqlite.gz"


def demo_index_path(cache_dir: Path | None = None) -> Path:
    """把隨 repo 發佈的精簡索引解壓到快取目錄，回傳可直接連線的 SQLite 路徑。

    解壓一次就好，之後沿用；先解到暫存檔再 rename，避免同時有多個請求進來時
    讀到寫到一半的檔案（serverless 冷啟動常見）。快取目錄預設 data/cache，可
    用 SMELENS_CACHE_DIR 覆寫成雲端函式唯一可寫的 /tmp。

    找不到隨附索引時丟 FileNotFoundError，由呼叫端決定要回什麼錯誤——不要
    退回去讀 119MB 的原始 CSV，那在雲端環境根本不存在。
    """
    if not DEMO_INDEX_GZ.exists():
        raise FileNotFoundError(f"找不到隨附的精簡索引：{DEMO_INDEX_GZ}")
    base = Path(cache_dir) if cache_dir else Path(os.getenv("SMELENS_CACHE_DIR", "data/cache"))
    target = base / "gcis_a_tier.sqlite"
    if target.exists():
        return target
    base.mkdir(parents=True, exist_ok=True)
    # 檔名要夠獨特：同一個 serverless 實例可能同時處理多個請求，只用 PID 的話
    # 多個執行緒會寫進同一個暫存檔，先完成的 rename 走掉，其他還在寫——於是那個
    # 實例之後永久沿用一個被截斷的 SQLite。加上隨機字串讓每次解壓各寫各的。
    tmp = target.with_suffix(target.suffix + f".unpacking{os.getpid()}-{uuid.uuid4().hex[:8]}")
    with gzip.open(DEMO_INDEX_GZ, "rb") as src, open(tmp, "wb") as dst:
        shutil.copyfileobj(src, dst)
    tmp.replace(target)
    return target


def extract_neighborhood(
    csv_path: str | Path,
    root_company_id: str,
    *,
    depth: int = 2,
    max_companies: int = 300,
    hub_name_threshold: int = 20,
    hub_seat_threshold: int = DEFAULT_HUB_SEAT_THRESHOLD,
    coinvestee_director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
    db_path: str | Path | None = None,
) -> list[Affiliation]:
    """從指定統一編號出發，沿 A 層（法人董事）與 B 層（自然人姓名）關係
    展開至多 depth 層的鄰域，一併回傳兩層的 Affiliation（tier 各自標好）。

    國家級全圖有 102 萬家公司、67,838 條 A 層邊，任何端點都不該對整張圖跑
    動機偵測——一份先前的效能量測顯示 detect_cycle_trade 在 3,000 節點就要
    24 秒，是信用管線裡唯一的非線性步驟。此函式把分析範圍先收斂到有限鄰域，
    讓後續分析（含動機偵測）有界。

    實作：底層是 build_index 建的一次性 SQLite 索引（company_id／
    person_norm／represented_norm 各有索引），BFS 每一層對邊界公司發兩條
    索引查詢（正向：這些公司自己的列；反向：哪些公司也掛了同一批姓名／
    代表法人），不再逐請求重掃 119MB CSV——這是相對先前純檔案掃描版本
    最大的差異：先前對台積電 depth=2 要 68 秒，改用索引後同一查詢實測見
    docs/GCIS_FINDINGS.md（索引一旦建好即可重覆使用，建置本身的一次性
    成本另計，見 build_index）。

    兩層一起展開、且 A 層優先──公司董事會若以法人代表出任居多（例如台積電），
    只展開 B 層會嚴重低估鄰域；A 層是無姓名歧義的高信心關係，理當納入展開，
    不是只展開低信心的 B 層再假裝涵蓋全貌。回傳的每筆 Affiliation 帶
    tier（"A"／"B"）與 merge（A 層機構橋接實體 merge=False，見
    DEFAULT_HUB_SEAT_THRESHOLD），呼叫端可直接餵給 build_company_graph，
    也能單獨依 tier 過濾只看高信心關係。

    hub_name_threshold／hub_seat_threshold 是兩層各自的樞紐防護閥：某姓名
    或某法人若已知關聯公司數達門檻，就不再用它往外展開 BFS（但仍收進鄰域
    本身收集到的 Affiliation 清單，只是不當作橋樑）——不論是撞名的自然人
    姓名還是機構股東，真實世界裡度數異常高的節點放行展開，兩三層內鄰域
    就會吃下全國圖，這正是全國實測發現的機構橋接問題在鄰域展開這一側的
    對應防護。

    coinvestee_director_threshold 是機構橋接的鏡像防護閥（見
    smelens.data.gcis.DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD）：某公司若被
    達門檻的相異法人董事共同代表（合資公司、創投被投資公司），該公司「作為
    子公司被代表」這一側的 Affiliation 標記 merge=False，不會被拿去把兩個
    原本不相干的法人家族併成一個歸戶集團——關係仍收進鄰域清單、仍可在
    hidden_links 看到，只是不當作合併依據。

    max_companies 是鄰域公司數上限，達到後停止展開（即使 depth 還沒走完）。
    """
    if depth < 1:
        raise ValueError("depth 至少為 1")

    affiliations, _ = extract_neighborhood_with_meta(
        csv_path,
        root_company_id,
        depth=depth,
        max_companies=max_companies,
        hub_name_threshold=hub_name_threshold,
        hub_seat_threshold=hub_seat_threshold,
        coinvestee_director_threshold=coinvestee_director_threshold,
        db_path=db_path,
    )
    return affiliations


def extract_neighborhood_with_meta(
    csv_path: str | Path,
    root_company_id: str,
    *,
    depth: int = 2,
    max_companies: int = 300,
    hub_name_threshold: int = 20,
    hub_seat_threshold: int = DEFAULT_HUB_SEAT_THRESHOLD,
    coinvestee_director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
    db_path: str | Path | None = None,
) -> tuple[list[Affiliation], dict[str, Any]]:
    """同 extract_neighborhood，但一併回傳展開過程的 meta。

    為什麼需要：BFS 達到 max_companies 時直接停止展開，而留下哪些公司只取決
    於 SQL 回列順序，與相關性無關。回一個普通的 list 等於讓呼叫端把一份被任
    意砍過的鄰域當成完整答案——本專案在 /group 對同一個問題處理得很好（回
    hidden_links_total 與 truncated，註解寫明「截斷本身不算隱瞞，但若不同時
    回報原本有多少筆，回應會讓人誤以為只找到這麼多」），這條路徑必須遵守
    同一個標準。

    meta 欄位：visited_companies（實際展開到的公司數）、max_companies（當次
    上限）、truncated（是否達上限）、frontier_remaining（停止時還有多少家在
    邊界上沒展開）。

    extract_neighborhood 仍保留原簽章供既有呼叫端使用；需要誠實呈現截斷狀態
    的呼叫端（API 回應）用這一個。
    """
    if depth < 1:
        raise ValueError("depth 至少為 1")

    resolved_db_path = build_index(csv_path, db_path)
    conn = sqlite3.connect(resolved_db_path)
    try:
        return _bfs_neighborhood(
            conn,
            root_company_id,
            depth,
            max_companies,
            hub_name_threshold,
            hub_seat_threshold,
            coinvestee_director_threshold,
        )
    finally:
        conn.close()


def _collect_hop(
    conn: sqlite3.Connection,
    company_ids: set[str],
    hub_name_threshold: int,
    hub_seat_threshold: int,
    collected: list[Affiliation],
    collected_keys: set[tuple[str, str, str]],
    coinvestee_director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
) -> tuple[set[str], set[str]]:
    """抓 company_ids 這批公司自己的全部董監事列，收進 collected，並回傳
    「值得繼續往外展開」的 (自然人姓名正規化鍵集合, 所代表法人正規化鍵集合)
    ——樞紐姓名／樞紐法人（見 hub_name_threshold／hub_seat_threshold）已排除。

    這批公司本身一定要被收進 collected：不管接下來還展不展得開，「這批公司
    自己的董監事關係」都是鄰域資料的一部分，不能因為 depth 用完了就漏掉——
    這正是先前版本在 depth=1 時只回傳根節點自己、漏掉第一層鄰居實際關係列
    的迴歸（BFS 展開找到下一層公司，卻要等到下一次迴圈才去抓它們的列；
    depth 用完時迴圈提前結束，下一層公司因此完全沒有資料被收集）。
    """
    if not company_ids:
        return set(), set()

    placeholders = ",".join("?" * len(company_ids))
    hop_rows = conn.execute(
        "SELECT company_id, company_name, role, person_name, person_norm, "
        "represented_name, represented_norm, represented_id, shares "
        f"FROM rows WHERE company_id IN ({placeholders})",
        tuple(company_ids),
    ).fetchall()

    person_norms = {r[4] for r in hop_rows if not r[6]}  # 只有非法人代表列才算 B 層姓名
    represented_norms = {r[6] for r in hop_rows if r[6]}

    person_seat_counts = _seat_counts(conn, "person_norm", person_norms)
    represented_seat_counts = _seat_counts(conn, "represented_norm", represented_norms)

    expand_person_norms = {
        n for n in person_norms if person_seat_counts.get(n, 0) < hub_name_threshold
    }
    hub_represented_norms = {
        n for n in represented_norms if represented_seat_counts.get(n, 0) >= hub_seat_threshold
    }
    expand_represented_norms = represented_norms - hub_represented_norms

    # 合資橋接對稱防護（見 DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD）：查詢這批
    # 公司自己，以及本輪出現的所代表法人（可能本身也是一家公司、可能還沒
    # 進 company_ids）各自的相異法人董事數——與 person_seat_counts／
    # represented_seat_counts 一樣是全域聚合查詢，不受這一個 BFS 批次的視野
    # 限制，故母公司即使不在本批 company_ids 裡，其自身的合資橋接狀態一樣
    # 判斷得到。
    represented_ids_seen = {r[7] for r in hop_rows if r[7]}
    coinvestee_counts = _coinvestee_director_counts(
        conn, company_ids | represented_ids_seen
    )
    coinvestee_cids = {
        cid for cid, count in coinvestee_counts.items() if count >= coinvestee_director_threshold
    }

    for r in hop_rows:
        cid, company_name, role, person_name, person_norm = r[0], r[1], r[2], r[3], r[4]
        represented_name, represented_norm, represented_id, shares = r[5], r[6], r[7], r[8]
        if represented_norm:
            not_hub = represented_norm not in hub_represented_norms
            can_merge = not_hub and cid not in coinvestee_cids
            # 根因修復：所代表法人（母公司）查得到統一編號時，額外收一筆「母公司
            # 自己」的 Affiliation，讓母公司節點透過同一個 person_key（represented_id）
            # 直接與每一家子公司連邊，不再只靠子公司之間共用母公司這個「人」而漏掉
            # 母公司自身——見 corporate_edges_to_affiliations 的同一段修復說明。
            # 用獨立的鍵命名空間（前綴 "SELF"）去重，同一個母公司在多筆列裡重覆
            # 出現時只送一次，不受下方子公司列去重鍵（cid, "A", ...）影響。
            if represented_id:
                self_key = ("SELF", "A", represented_norm)
                if self_key not in collected_keys:
                    collected_keys.add(self_key)
                    # 母公司自身這筆 Affiliation 的合資橋接判斷要看母公司自己
                    # （represented_id）的相異法人董事數，不是子公司 cid 的——
                    # 兩者是不同的公司節點，不能共用 can_merge。
                    parent_can_merge = not_hub and represented_id not in coinvestee_cids
                    collected.append(
                        Affiliation(
                            company=represented_name,
                            person=represented_name,
                            role="法人董事（母公司自身）",
                            company_id=represented_id,
                            person_id=represented_id,
                            tier="A",
                            shares=None,
                            merge=parent_can_merge,
                        )
                    )
            key = (cid, "A", represented_norm)
            if key in collected_keys:
                continue
            collected_keys.add(key)
            collected.append(
                Affiliation(
                    company=company_name,
                    person=represented_name,
                    role=role or "法人董事",
                    company_id=cid,
                    person_id=represented_id,
                    tier="A",
                    shares=shares,
                    merge=can_merge,
                )
            )
        else:
            key = (cid, "B", person_norm)
            if key in collected_keys:
                continue
            collected_keys.add(key)
            collected.append(
                Affiliation(
                    company=company_name,
                    person=person_name,
                    role=role or "董監事",
                    company_id=cid,
                    person_id=None,
                    tier="B",
                    shares=shares,
                    merge=False,
                )
            )

    return expand_person_norms, expand_represented_norms


def _bfs_neighborhood(
    conn: sqlite3.Connection,
    root_company_id: str,
    depth: int,
    max_companies: int,
    hub_name_threshold: int,
    hub_seat_threshold: int,
    coinvestee_director_threshold: int = DEFAULT_COINVESTEE_DIRECTOR_THRESHOLD,
) -> tuple[list[Affiliation], dict[str, Any]]:
    visited: set[str] = {root_company_id}
    frontier: set[str] = {root_company_id}
    collected: list[Affiliation] = []
    collected_keys: set[tuple[str, str, str]] = set()  # (company_id, tier, 實體正規化鍵)

    for _ in range(depth):
        if not frontier or len(visited) >= max_companies:
            break

        expand_person_norms, expand_represented_norms = _collect_hop(
            conn,
            frontier,
            hub_name_threshold,
            hub_seat_threshold,
            collected,
            collected_keys,
            coinvestee_director_threshold,
        )

        next_frontier: set[str] = set()

        def _absorb(rows: list[tuple]) -> None:
            for (cid,) in rows:
                if cid in visited:
                    continue
                if len(visited) >= max_companies:
                    return
                visited.add(cid)
                next_frontier.add(cid)

        if expand_person_norms:
            ph = ",".join("?" * len(expand_person_norms))
            _absorb(
                conn.execute(
                    f"SELECT DISTINCT company_id FROM rows WHERE person_norm IN ({ph})",
                    tuple(expand_person_norms),
                ).fetchall()
            )
        if expand_represented_norms:
            ph = ",".join("?" * len(expand_represented_norms))
            _absorb(
                conn.execute(
                    "SELECT DISTINCT company_id FROM rows "
                    f"WHERE represented_norm IN ({ph})",
                    tuple(expand_represented_norms),
                ).fetchall()
            )

        frontier = next_frontier

    # depth 用完（或 max_companies 額滿）時，最後一輪展開找到的公司還沒被
    # _collect_hop 收錄過自己的列——它們是「depth 層以內」貨真價實的鄰居，
    # 不能因為迴圈次數用完就漏掉，故額外收一次（不再繼續往外展開）。
    if frontier:
        _collect_hop(
            conn,
            frontier,
            hub_name_threshold,
            hub_seat_threshold,
            collected,
            collected_keys,
            coinvestee_director_threshold,
        )

    return collected, {
        "visited_companies": len(visited),
        "max_companies": max_companies,
        # 「還有邊界沒展開」與「已達公司數上限」兩件事都要看：前者代表 depth
        # 用完，後者代表被上限砍斷。任一成立，這份鄰域就不是完整的。
        "truncated": len(visited) >= max_companies,
        "frontier_remaining": len(frontier),
    }
