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
    classify_coinvestee_companies,
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


def test_load_affiliations_marks_tier_b_as_non_merging():
    """B 層沒有身分證字號佐證，一律 merge=False——只能是候選，不可逕行歸戶。

    這是兩層證據結構性分離的根本依據：若 B 層預設 merge=True，一詮精密工業
    走查案例裡「李家緯」單一姓名比對就會把 11 家公司強行併進歸戶群組，讓
    A 層（4 家子公司＋母公司）真正確認的關聯被淹沒在同一份「15 家集團」裡。
    """
    affiliations = list(load_affiliations(FIXTURE))

    assert affiliations
    assert all(a.merge is False for a in affiliations)


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

    「某銀行」本身現在也會因為 represented_id 查得到而多一筆「母公司自己」
    的 Affiliation（見 corporate_edges_to_affiliations 的根因修復），故圖裡
    多了「某銀行」這個節點——但它一樣是機構橋接實體（席次數達門檻），與它
    相連的邊一律 bridge_only=True，故「某銀行」自己也維持孤立，不與任何一家
    子公司合併：6 個節點（5 家子公司＋銀行自己）各自獨立成一個集團。
    """
    edges = [_edge(f"C{i}", "某銀行", represented_id="B1") for i in range(5)]
    affiliations = list(corporate_edges_to_affiliations(edges, hub_seat_threshold=5))

    graph = build_company_graph(affiliations)
    assert "某銀行" in graph
    for u, v, data in graph.edges(data=True):
        assert data["bridge_only"] is True

    groups = detect_groups(graph)
    # 5 家子公司＋銀行自己，唯一的共同點是機構橋接實體，理應各自獨立，不歸同一集團。
    assert len(set(groups.values())) == 6
    assert groups["某銀行"] not in {groups[f"C{i}公司"] for i in range(5)}


def test_classify_coinvestee_companies_marks_companies_at_or_above_threshold():
    """相異法人董事數達門檻的公司才算合資橋接實體，未達門檻的一般子公司不算。

    合資公司「X」被 4 個互不相干的法人（A1～D1）共同代表出任董事；一般
    子公司「Y」只被 2 個法人共同代表——用門檻 4 分類，前者應入選、後者不該。
    """
    edges = [_edge("X", f"法人{i}", represented_id=f"P{i}") for i in range(4)]
    edges += [_edge("Y", "法人0", represented_id="P0")]
    edges += [_edge("Y", "法人1", represented_id="P1")]

    coinvestees = classify_coinvestee_companies(edges, director_threshold=4)

    assert "X" in coinvestees
    assert "Y" not in coinvestees


def test_classify_coinvestee_companies_counts_by_identifier_not_name_string():
    """同一統編、不同名稱寫法的法人董事要合併計數，不因寫法不同而虛增相異數。

    公司「X」被 4 筆列代表，但其中 2 筆其實是同一個法人（P0）的不同名稱
    寫法——相異法人董事數應是 3，不是 4，門檻 4 不該命中。
    """
    edges = [
        _edge("X", "某法人股份有限公司", represented_id="P0"),
        _edge("X", "某法人（股）公司", represented_id="P0"),
        _edge("X", "法人1", represented_id="P1"),
        _edge("X", "法人2", represented_id="P2"),
    ]

    coinvestees = classify_coinvestee_companies(edges, director_threshold=4)

    assert "X" not in coinvestees
    assert "X" in classify_coinvestee_companies(edges, director_threshold=3)


def test_classify_hub_entities_and_coinvestee_companies_are_mirror_images():
    """機構橋接（一個法人代表太多家）與合資橋接（一家公司被太多法人代表）是
    同一套「分組後計數相異值」邏輯，只是分組方向對調——用同一組資料的
    「轉置」驗證兩個分類函式確實共用同一種計數方式，不是兩套各自維護的邏輯。

    原始資料：「某銀行」代表出任 5 家公司董事（機構橋接案例）。
    轉置資料：「某公司」被 5 個相異法人共同代表出任董事（合資橋接案例）
    ——把 company_id 與 represented_id 對調角色即可，計數應完全對應。
    """
    hub_edges = [_edge(f"C{i}", "某銀行", represented_id="B1") for i in range(5)]
    coinvestee_edges = [_edge("某公司", f"法人{i}", represented_id=f"C{i}") for i in range(5)]

    hubs = classify_hub_entities(hub_edges, seat_threshold=5)
    coinvestees = classify_coinvestee_companies(coinvestee_edges, director_threshold=5)

    assert "pid:B1" in hubs
    assert "某公司" in coinvestees


def test_corporate_edges_to_affiliations_marks_coinvestee_companies_as_non_merging():
    """合資橋接公司轉出的「作為子公司被代表」Affiliation 一律 merge=False；
    各法人自身（母公司）的 Affiliation 不受影響，仍照機構橋接門檻單獨判斷。
    """
    edges = [_edge("X", f"法人{i}", represented_id=f"P{i}") for i in range(4)]
    edges += [_edge("Y", "法人0", represented_id="P0")]  # Y 只有一個法人董事，非橋接

    affiliations = list(
        corporate_edges_to_affiliations(
            edges, hub_seat_threshold=5, coinvestee_director_threshold=4
        )
    )

    x_affs = [a for a in affiliations if a.company_id == "X"]
    y_affs = [a for a in affiliations if a.company_id == "Y"]
    self_affs = [a for a in affiliations if a.role == "法人董事（母公司自身）"]
    assert x_affs and all(a.merge is False for a in x_affs)
    assert y_affs and all(a.merge is True for a in y_affs)
    assert self_affs and all(a.merge is True for a in self_affs), (
        "各法人自身只代表 X 一次、遠低於機構橋接門檻，不該被合資橋接誤標"
    )


def test_coinvestee_companies_bridge_without_merging_groups():
    """合資公司的邊仍畫進圖裡（bridge_only 標記），但 detect_groups 不會拿它
    合併兩個原本不相干的法人家族——這正是機構橋接修復的鏡像：機構橋接防
    「一個法人代表太多家」，這裡防「一家公司被太多不同法人代表」。

    「X公司」被法人 A、B、C、D 共同代表出任董事；A～D 各自另外還控股一家
    真正的子公司（ASUB～DSUB）。合資橋接修復後：A～D 各自與自己的子公司
    仍正確歸戶為一個集團，但不會因為都在「X公司」掛席次就被併成同一個
    超大集團，「X公司」自己也維持孤立。
    """
    parents = ["A", "B", "C", "D"]
    edges = [_edge("X", f"{p}公司", represented_id=f"{p}1") for p in parents]
    edges += [_edge(f"{p}SUB", f"{p}公司", represented_id=f"{p}1") for p in parents]

    affiliations = list(
        corporate_edges_to_affiliations(
            edges, hub_seat_threshold=5, coinvestee_director_threshold=4
        )
    )
    graph = build_company_graph(affiliations)

    for u, v, data in graph.edges(data=True):
        if "X公司" in (u, v):
            assert data["bridge_only"] is True

    groups = detect_groups(graph)
    for p in parents:
        assert groups[f"{p}公司"] == groups[f"{p}SUB公司"]
    for p, q in zip(parents, parents[1:]):
        assert groups[f"{p}公司"] != groups[f"{q}公司"]
    assert groups["X公司"] not in {groups[f"{p}公司"] for p in parents}


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


_A_TIER_WITH_RESOLVABLE_PARENT_CSV = """統一編號,公司名稱,職稱,姓名,所代表法人,持有股份數
00000001,甲光電股份有限公司,董事,張三,乙投資股份有限公司,1000
00000002,丙精工股份有限公司,董事,李四,乙投資股份有限公司,2000
00000009,乙投資股份有限公司,董事長,陳大文,,5000
"""


def test_corporate_parent_lands_in_the_same_group_as_its_subsidiaries(tmp_path: Path):
    """根因修復——母公司（所代表法人查得到統一編號）必須進自己的歸戶群組。

    「乙投資」在本資料集裡自己也是一家公司（統編 00000009），且是甲光電、
    丙精工的所代表法人。修復前：只有甲光電、丙精工彼此連邊，乙投資本身
    從未被畫進圖裡——母公司在自己的集團裡完全找不到，這正是走查一詮精密
    工業時發現的核心defect。修復後：乙投資節點應直接與兩家子公司連邊，
    detect_groups 三者同屬一個歸戶群組。
    """
    csv_path = tmp_path / "a_tier_with_parent.csv"
    csv_path.write_text(_A_TIER_WITH_RESOLVABLE_PARENT_CSV, encoding="utf-8-sig")

    neighborhood = extract_neighborhood(csv_path, "00000001", depth=1, max_companies=50)

    graph = build_company_graph(neighborhood)
    assert "乙投資股份有限公司" in graph
    assert graph.has_edge("乙投資股份有限公司", "甲光電股份有限公司")
    assert graph.has_edge("乙投資股份有限公司", "丙精工股份有限公司")

    groups = detect_groups(graph)
    parent_group = groups["乙投資股份有限公司"]
    assert parent_group == groups["甲光電股份有限公司"] == groups["丙精工股份有限公司"]


def test_corporate_parent_self_affiliation_not_fabricated_when_unresolvable(tmp_path: Path):
    """所代表法人查不到統一編號（約 19% 的政府機關／境外法人／基金會等）時，
    不得無中生有出一個母公司節點——維持既有的名稱比對退回，子公司之間仍
    因共用「所代表法人」名稱字串而連邊，但沒有可靠的母公司公司節點可連。
    """
    csv_path = tmp_path / "a_tier_unresolved.csv"
    csv_path.write_text(_A_TIER_NEIGHBORHOOD_CSV, encoding="utf-8-sig")

    neighborhood = extract_neighborhood(csv_path, "00000001", depth=1, max_companies=50)

    graph = build_company_graph(neighborhood)
    assert "乙投資股份有限公司" not in graph
    assert graph.has_edge("甲光電股份有限公司", "丙精工股份有限公司")


_MIXED_TIER_CSV = """統一編號,公司名稱,職稱,姓名,所代表法人,持有股份數
00000001,甲光電股份有限公司,董事,張三,乙投資股份有限公司,1000
00000001,甲光電股份有限公司,監察人,王小明,,999
00000002,丙精工股份有限公司,董事,李四,乙投資股份有限公司,2000
00000003,戊顧問有限公司,董事,王小明,,3000
00000009,乙投資股份有限公司,董事長,陳大文,,5000
"""


def test_tier_a_and_tier_b_stay_structurally_separable(tmp_path: Path):
    """A 層（母子公司）與 B 層（單一姓名比對）在同一鄰域裡出現時，結果必須
    可分開看，不能被一次 detect_groups 混成一個「集團」：

    甲光電、丙精工都由乙投資派員代表出任董事（A 層，無姓名歧義）；甲光電、
    戊顧問則只是恰好都有一位「王小明」董監事（B 層，僅一筆姓名比對）。
    修復後，detect_groups 只把乙投資、甲光電、丙精工歸為一個集團——戊顧問
    因為唯一的連結是 tier=B、merge=False，不會被拉進來，只會出現在
    hidden_links 裡標成 bridge_only=True 的候選，並點名共用的自然人。
    """
    csv_path = tmp_path / "mixed_tier.csv"
    csv_path.write_text(_MIXED_TIER_CSV, encoding="utf-8-sig")

    neighborhood = extract_neighborhood(csv_path, "00000001", depth=1, max_companies=50)
    graph = build_company_graph(neighborhood)
    groups = detect_groups(graph)

    parent_group = groups["乙投資股份有限公司"]
    assert parent_group == groups["甲光電股份有限公司"] == groups["丙精工股份有限公司"]
    assert groups["戊顧問有限公司"] != groups["甲光電股份有限公司"]

    candidates = [
        link
        for link in hidden_links(graph, {})
        if link["tier"] == "B" and link["bridge_only"]
    ]
    assert any(
        {link["company_a"], link["company_b"]} == {"甲光電股份有限公司", "戊顧問有限公司"}
        and link["shared_persons"] == ["王小明"]
        for link in candidates
    )


_COINVESTEE_NEIGHBORHOOD_CSV = """統一編號,公司名稱,職稱,姓名,所代表法人,持有股份數
00000001,甲投資股份有限公司,董事長,王一,,1000
00000002,乙投資股份有限公司,董事長,王二,,1000
00000003,丙投資股份有限公司,董事長,王三,,1000
00000004,丁投資股份有限公司,董事長,王四,,1000
00000010,Z合資股份有限公司,董事,甲代表,甲投資股份有限公司,1000
00000010,Z合資股份有限公司,董事,乙代表,乙投資股份有限公司,1000
00000010,Z合資股份有限公司,董事,丙代表,丙投資股份有限公司,1000
00000010,Z合資股份有限公司,董事,丁代表,丁投資股份有限公司,1000
00000011,甲子公司,董事,某代表,甲投資股份有限公司,500
00000012,乙子公司,董事,某代表,乙投資股份有限公司,500
"""


def test_extract_neighborhood_coinvestee_bridges_without_merging_groups(tmp_path: Path):
    """BFS 鄰域展開這一側也要有合資橋接防護，不只全國批次的
    corporate_edges_to_affiliations——這是同一個修復，兩個入口都要生效。

    「Z合資」被甲、乙、丙、丁四家互不相干的投資公司共同代表出任董事（相異
    法人董事數 4，達門檻）；甲投資另外控股甲子公司，乙投資另外控股乙子
    公司。合資橋接修復後：甲投資與甲子公司仍正確歸戶同一集團，乙投資與
    乙子公司也是，但這兩個集團不會因為都在「Z合資」掛席次而被併成一個，
    「Z合資」自己也維持孤立。
    """
    csv_path = tmp_path / "coinvestee_neighborhood.csv"
    csv_path.write_text(_COINVESTEE_NEIGHBORHOOD_CSV, encoding="utf-8-sig")

    neighborhood = extract_neighborhood(
        csv_path,
        "00000011",
        depth=2,
        max_companies=50,
        coinvestee_director_threshold=4,
    )
    graph = build_company_graph(neighborhood)
    groups = detect_groups(graph)

    assert groups["甲子公司"] == groups["甲投資股份有限公司"]
    assert groups["乙子公司"] == groups["乙投資股份有限公司"]
    assert groups["甲投資股份有限公司"] != groups["乙投資股份有限公司"]
    assert groups["Z合資股份有限公司"] not in {
        groups["甲投資股份有限公司"],
        groups["乙投資股份有限公司"],
    }

    for u, v, data in graph.edges(data=True):
        if "Z合資股份有限公司" in (u, v):
            assert data["bridge_only"] is True


def test_extract_neighborhood_rejects_invalid_depth():
    """depth 必須至少為 1，否則連起點公司自己的關係都展開不出來。"""
    import pytest

    with pytest.raises(ValueError):
        extract_neighborhood(FIXTURE, "00000005", depth=0)
