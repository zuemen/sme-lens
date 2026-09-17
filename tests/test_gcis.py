"""商業司董監事資料集載入器測試：以 tests/fixtures/gcis_directors_sample.csv
（從全國實測檔案 tests/fixtures/gcis_directors_sample.csv 抽樣 213 列）驗證
佔位字串剔除、A/B 兩層信心標籤、鄰域展開的邊界。
"""

from __future__ import annotations

from pathlib import Path

from smelens.credit.group import build_company_graph, detect_groups, hidden_links
from smelens.data.gcis import (
    VACANCY_PLACEHOLDERS,
    CorporateDirectorEdge,
    classify_hub_entities,
    corporate_edges_to_affiliations,
    extract_neighborhood,
    load_affiliations,
    load_corporate_director_edges,
)

FIXTURE = Path(__file__).parent / "fixtures" / "gcis_directors_sample.csv"


def _edge(company_id: str, represented_name: str, represented_id: str | None = None):
    """組一筆最小 CorporateDirectorEdge，供 classify_hub_entities／merge 旗標測試用。

    company_name／representative_person／shares 對這兩組測試無關，填佔位值即可。
    """
    return CorporateDirectorEdge(
        company_id=company_id,
        company_name=f"{company_id}公司",
        represented_name=represented_name,
        represented_id=represented_id,
        representative_person="某代表人",
        shares=None,
    )


def test_load_affiliations_drops_vacancy_placeholders():
    """「缺額」「暫缺」「(缺額)」不是自然人，載入後不得出現在姓名裡。

    抽樣檔案刻意混入這三種佔位字串各至少一筆——只驗證「沒有留下佔位字串」還
    不夠，因為若剔除邏輯漏掉某一種，該種字串完全不出現在結果裡看起來仍正常；
    故另外斷言結果列數確實少於原始檔案列數，證明真的剔除了東西。
    """
    with open(FIXTURE, encoding="utf-8-sig", newline="") as f:
        raw_row_count = sum(1 for _ in f) - 1  # 扣掉表頭

    affiliations = list(load_affiliations(FIXTURE))

    assert not any(a.person in VACANCY_PLACEHOLDERS for a in affiliations)
    assert len(affiliations) < raw_row_count


def test_load_affiliations_carries_company_id_and_tier_b():
    """B 層 Affiliation 一律 tier="B"，company_id 帶統一編號、person_id 為 None。"""
    affiliations = list(load_affiliations(FIXTURE))

    assert affiliations, "抽樣檔案應至少能載入一筆自然人董監事關係"
    for a in affiliations:
        assert a.tier == "B"
        assert a.person_id is None
        assert a.company_id  # 統一編號一律非空


def test_load_affiliations_keeps_company_without_unified_number_suffix():
    """公司名稱含「（無統編）」樣態的列仍須正常載入，不能被當成髒資料跳過。"""
    affiliations = list(load_affiliations(FIXTURE))

    assert any("（無統編）" in a.company for a in affiliations)


def test_load_affiliations_respects_limit():
    """limit 只在測試／抽樣情境使用，須精確截斷筆數（不含被剔除的佔位列）。"""
    affiliations = list(load_affiliations(FIXTURE, limit=5))

    assert len(affiliations) == 5


def test_corporate_director_edges_are_deduplicated_and_high_confidence():
    """所代表法人非空的列去重為 (公司, 法人) 唯一邊，轉成 Affiliation 後 tier="A"。"""
    edges = load_corporate_director_edges(FIXTURE)

    assert edges  # 抽樣檔案刻意含 20 筆法人董事列
    # 去重：同一 (company_id, 正規化後的所代表法人名稱) 只能出現一次。
    seen = {(e.company_id, e.represented_name) for e in edges}
    assert len(seen) == len(edges)

    affiliations = list(corporate_edges_to_affiliations(edges))
    assert all(a.tier == "A" for a in affiliations)
    assert all(a.role == "法人董事" for a in affiliations)


def test_classify_hub_entities_marks_entities_at_or_above_threshold():
    """代表席次數達門檻的法人才算機構橋接實體，未達門檻的一般控股公司不算。

    銀行（統編 B1）代表出任 5 家公司董事，一般控股公司（統編 H1）只代表
    出任 3 家——用預設門檻 5 分類，前者應入選、後者不應入選。
    """
    edges = [_edge(f"C{i}", "某銀行", represented_id="B1") for i in range(5)]
    edges += [_edge(f"D{i}", "某控股公司", represented_id="H1") for i in range(3)]

    hubs = classify_hub_entities(edges, seat_threshold=5)

    assert "pid:B1" in hubs
    assert "pid:H1" not in hubs


def test_classify_hub_entities_counts_by_identifier_not_name_string():
    """同一統編、不同名稱寫法（全半形、簡繁等）的代表法人要合併計數。

    _represented_identity_key 優先用 represented_id 衍生鍵，避免因為名稱字串
    寫法不同而低估某個法人的實際代表席次數，導致該入選門檻的機構漏網。
    """
    edges = [_edge("C1", "某銀行股份有限公司", represented_id="B1")]
    edges += [_edge(f"C{i}", "某銀行（股）公司", represented_id="B1") for i in range(2, 6)]

    hubs = classify_hub_entities(edges, seat_threshold=5)

    assert "pid:B1" in hubs


def test_corporate_edges_to_affiliations_marks_hub_entities_as_non_merging():
    """機構橋接實體轉出的 Affiliation 一律 merge=False，其餘維持預設 merge=True。"""
    edges = [_edge(f"C{i}", "某銀行", represented_id="B1") for i in range(5)]
    edges += [_edge("D1", "某控股公司", represented_id="H1")]

    affiliations = list(corporate_edges_to_affiliations(edges, hub_seat_threshold=5))

    hub_affs = [a for a in affiliations if a.person_id == "B1"]
    other_affs = [a for a in affiliations if a.person_id == "H1"]
    assert hub_affs and all(a.merge is False for a in hub_affs)
    assert other_affs and all(a.merge is True for a in other_affs)


def test_hub_entities_bridge_without_merging_groups():
    """機構橋接實體的邊仍畫進圖裡（bridge_only 標記），但 detect_groups 不會
    拿它合併兩家公司——這正是全國實測 7,187 家假集團問題的修復核心行為。
    """
    edges = [_edge(f"C{i}", "某銀行", represented_id="B1") for i in range(5)]
    affiliations = list(corporate_edges_to_affiliations(edges, hub_seat_threshold=5))

    graph = build_company_graph(affiliations)
    for u, v, data in graph.edges(data=True):
        assert data["bridge_only"] is True

    groups = detect_groups(graph)
    # 5 家公司唯一的共同點是機構橋接實體，理應各自獨立，不歸同一集團。
    assert len(set(groups.values())) == 5


def test_a_tier_edge_outranks_b_tier_in_hidden_links():
    """兩家公司若同時因法人董事（A）與同名自然人（B）相連，回報時信心以 A 為準。

    只用真實 A 層資料很難在小樣本裡剛好湊出「同一對公司兩層都連」的案例，
    這裡用最小手動關係直接檢驗 build_company_graph／hidden_links 的信心合併規則
    ——這條規則是 smelens.credit.group 的行為，不是 gcis 載入器本身的行為，
    但正是餵入真實資料後才會實際發生的情境，故放在這裡一起驗證。
    """
    from smelens.credit.group import Affiliation

    affiliations = [
        Affiliation("甲公司", "同名王小明", role="董事", tier="B"),
        Affiliation("乙公司", "同名王小明", role="監察人", tier="B"),
        Affiliation(
            "甲公司", "共同法人", company_id="C1", person_id="C9", role="法人董事", tier="A"
        ),
        Affiliation(
            "乙公司", "共同法人", company_id="C2", person_id="C9", role="法人董事", tier="A"
        ),
    ]

    g = build_company_graph(affiliations)
    found = hidden_links(g, {})

    assert len(found) == 1
    assert found[0]["tier"] == "A"


def test_hidden_links_defaults_to_tier_b_when_no_a_tier_evidence():
    """完全沒有 A 層證據時，隱性關聯一律標 "B"，不會無中生有出高信心標籤。"""
    from smelens.credit.group import Affiliation

    g = build_company_graph(
        [Affiliation("甲公司", "王小明"), Affiliation("乙公司", "王小明")]
    )

    found = hidden_links(g, {})

    assert found[0]["tier"] == "B"


def test_extract_neighborhood_finds_companies_sharing_a_person():
    """從單一統編出發，depth=1 應找到所有與其共用董監事姓名的公司。

    抽樣檔案裡「李賢維」掛名 4 家公司（北凰貿易、鍵腦實業、鍵輝實業、和樺
    企業）；以其中一家的統編為起點展開，鄰域應含全部 4 家。
    """
    affiliations = [a for a in load_affiliations(FIXTURE) if a.person == "李賢維"]
    assert len(affiliations) == 4  # 抽樣資料本身的前提，先確認没被上游改動
    root = affiliations[0].company_id

    neighborhood = extract_neighborhood(FIXTURE, root, depth=1, max_companies=50)

    companies = {a.company_id for a in neighborhood}
    assert companies == {a.company_id for a in affiliations}


def test_extract_neighborhood_is_bounded_by_max_companies():
    """max_companies 必須真的擋住展開——不能因為某層還沒走完就超過上限。"""
    affiliations = [a for a in load_affiliations(FIXTURE) if a.person == "李賢維"]
    root = affiliations[0].company_id

    neighborhood = extract_neighborhood(FIXTURE, root, depth=3, max_companies=2)

    companies = {a.company_id for a in neighborhood}
    assert len(companies) <= 2


_A_TIER_NEIGHBORHOOD_CSV = """統一編號,公司名稱,職稱,姓名,所代表法人,持有股份數
00000001,甲光電股份有限公司,董事,張三,乙投資股份有限公司,1000
00000002,丙精工股份有限公司,董事,李四,乙投資股份有限公司,2000
00000003,丁生技股份有限公司,董事,王五,獨立業主股份有限公司,3000
"""


def test_extract_neighborhood_includes_a_tier_corporate_director_edges(tmp_path: Path):
    """鄰域展開現在會一併納入 A 層（所代表法人）關係，不再只展開 B 層。

    甲光電、丙精工都由「乙投資」派員代表出任董事（A 層、代表席次 2 家，
    遠低於機構橋接門檻），從甲光電出發 depth=1 應找到丙精工，且該筆
    Affiliation 須標 tier="A"、merge=True（未達門檻，不是機構橋接）；
    丁生技與「獨立業主」無其他公司共用，不該被納入鄰域。
    """
    csv_path = tmp_path / "a_tier_sample.csv"
    csv_path.write_text(_A_TIER_NEIGHBORHOOD_CSV, encoding="utf-8-sig")

    neighborhood = extract_neighborhood(csv_path, "00000001", depth=1, max_companies=50)

    companies = {a.company_id for a in neighborhood}
    assert companies == {"00000001", "00000002"}

    a_tier = [a for a in neighborhood if a.tier == "A"]
    assert a_tier, "應收集到甲光電、丙精工之間的 A 層關係"
    assert all(a.merge is True for a in a_tier)


def test_extract_neighborhood_rejects_invalid_depth():
    """depth 必須至少為 1，否則連起點公司自己的關係都展開不出來。"""
    import pytest

    with pytest.raises(ValueError):
        extract_neighborhood(FIXTURE, "00000005", depth=0)
