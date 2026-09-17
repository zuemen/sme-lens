"""集團歸戶測試：公司關聯圖、遞移歸戶、曝險彙總與隱性關聯揭露。"""

from __future__ import annotations

from smelens.credit.group import (
    Affiliation,
    build_company_graph,
    detect_groups,
    group_exposure,
    hidden_links,
)

_AFFILIATIONS = [
    Affiliation("泰昇精密", "陳大明", "董事長"),
    Affiliation("泰昇投資", "陳大明", "董事"),
    Affiliation("昇泰貿易", "王秀英", "董事"),
    Affiliation("泰昇投資", "王秀英", "監察人"),
    Affiliation("禾昌五金", "林志豪", "董事長"),
]


def test_build_company_graph_links_companies_sharing_a_person():
    """共用同一自然人的兩家公司之間應連邊，未共用者不連。"""
    g = build_company_graph(_AFFILIATIONS)

    assert g.has_edge("泰昇精密", "泰昇投資")
    assert g["泰昇精密"]["泰昇投資"]["weight"] == 1
    assert g["泰昇精密"]["泰昇投資"]["shared"] == ["陳大明"]
    assert not g.has_edge("泰昇精密", "禾昌五金")
    assert "禾昌五金" in g  # 無共用者仍須入圖，否則歸戶會漏掉單獨公司


def test_build_company_graph_accumulates_multiple_shared_persons():
    """兩家公司共用多名自然人時，weight 要累加、shared 要收齊並排序。

    只共用一人的案例檢不出「以 shared = [person] 覆寫而非 append」或
    「weight 未累加」——這兩種錯在 weight==1 時看起來完全正常。
    """
    affiliations = [
        Affiliation("甲公司", "王五", "董事"),
        Affiliation("乙公司", "王五", "監察人"),
        Affiliation("甲公司", "李四", "監察人"),
        Affiliation("乙公司", "李四", "董事"),
        Affiliation("甲公司", "張三", "董事長"),
        Affiliation("乙公司", "張三", "董事"),
    ]

    g = build_company_graph(affiliations)

    assert g["甲公司"]["乙公司"]["weight"] == 3
    # 刻意讓插入順序（王五→李四→張三）與排序後順序（張三→李四→王五）相反，
    # 否則漏掉最後那圈 shared.sort() 也看不出來。
    assert g["甲公司"]["乙公司"]["shared"] == ["張三", "李四", "王五"]


def test_detect_groups_is_transitive():
    """A-B 共用、B-C 共用，則 A、B、C 同屬一個歸戶群組。"""
    g = build_company_graph(_AFFILIATIONS)

    groups = detect_groups(g)

    assert groups["泰昇精密"] == groups["泰昇投資"] == groups["昇泰貿易"]
    assert groups["禾昌五金"] != groups["泰昇精密"]


def test_detect_groups_ordering_is_deterministic():
    """歸戶結果的鍵順序必須穩定：前端照這個順序渲染表格，跳動會讓同一筆查詢
    看起來像不同的資料。連通元件是 set，不排序就會隨行程的 hash seed 改變。
    """
    affiliations = [
        Affiliation("戊公司", "趙一"),
        Affiliation("丁公司", "趙一"),
        Affiliation("丙公司", "趙一"),
        Affiliation("乙公司", "趙一"),
        Affiliation("甲公司", "趙一"),
    ]

    groups = detect_groups(build_company_graph(affiliations))

    # 依 Unicode code point 排序（sorted() 對中文字元的預設行為），不是數字順序
    # 「甲乙丙丁戊」——只要求穩定，不要求貼合人類讀法。已重跑多次確認同一順序。
    assert list(groups) == ["丁公司", "丙公司", "乙公司", "戊公司", "甲公司"]


def test_group_exposure_sums_by_group():
    """集團曝險為群組內各公司授信餘額之和。"""
    g = build_company_graph(_AFFILIATIONS)
    groups = detect_groups(g)
    exposures = {
        "泰昇精密": 30_000_000.0,
        "泰昇投資": 12_000_000.0,
        "昇泰貿易": 8_000_000.0,
        "禾昌五金": 5_000_000.0,
    }

    totals = group_exposure(groups, exposures)

    assert totals[groups["泰昇精密"]] == 50_000_000.0
    assert totals[groups["禾昌五金"]] == 5_000_000.0


def test_group_exposure_ignores_unknown_company():
    """不在關係圖中的公司不計入任何集團。"""
    groups = {"甲公司": 0}

    totals = group_exposure(groups, {"甲公司": 100.0, "查無此公司": 999.0})

    assert totals == {0: 100.0}


def test_hidden_links_reports_undeclared_relation():
    """客戶申報為不同集團、但關係圖上存在連結者，應列為隱性關聯。"""
    g = build_company_graph(_AFFILIATIONS)
    declared = {
        "泰昇精密": "泰昇集團",
        "泰昇投資": "泰昇集團",
        "昇泰貿易": "昇泰集團",  # 客戶申報為獨立集團，實際共用王秀英
    }

    found = hidden_links(g, declared)

    assert len(found) == 1
    assert found[0]["company_a"] == "昇泰貿易"
    assert found[0]["company_b"] == "泰昇投資"
    assert found[0]["shared_persons"] == ["王秀英"]
    assert found[0]["declared_group_a"] == "昇泰集團"
    assert found[0]["declared_group_b"] == "泰昇集團"


def test_build_company_graph_normalises_names():
    """尾隨空白與全形字元不得讓同一個人被當成兩個人。

    手動輸入的名冊常見這種寫法差異；對法遵工具而言，若不正規化，多打一個空格
    就是零成本的規避手法。
    """
    affiliations = [
        Affiliation("甲公司", "王小明"),
        Affiliation("乙公司", "王小明 "),
        Affiliation("丙公司", "王小明１"),
        Affiliation("丁公司", "王小明1"),
    ]

    g = build_company_graph(affiliations)
    groups = detect_groups(g)

    assert g.has_edge("甲公司", "乙公司")
    assert groups["丙公司"] == groups["丁公司"]


def test_same_name_different_identifiers_do_not_merge():
    """六個互不相干、恰好都叫「陳志明」的自然人，各自掛名一家公司——沒有
    person_id 時（純名稱比對）會全部併成一個集團，這是本測試要擋下的迴歸：
    identifier 不同時，即使名稱字串完全相同，公司也不得被併在一起。
    """
    affiliations = [
        Affiliation(f"公司{i}號", "陳志明", person_id=f"ID{i}") for i in range(1, 7)
    ]

    g = build_company_graph(affiliations)
    groups = detect_groups(g)

    group_ids = {groups[f"公司{i}號"] for i in range(1, 7)}
    assert len(group_ids) == 6  # 六家公司各自獨立成一個集團，一個都不能併
    assert len(hidden_links(g, {})) == 0  # 不同 identifier 之間不構成隱性關聯


def test_same_identifier_different_name_spellings_merge():
    """同一個 person_id、名稱寫法不同（尾隨空白、全形數字變體）仍須視為同一人，
    共用者的公司要合併——這正是本模組要抓的「換個寫法規避比對」。
    """
    affiliations = [
        Affiliation("甲公司", "王小明", person_id="P001"),
        Affiliation("乙公司", "王小明 ", person_id="P001"),  # 尾隨空白
        Affiliation("丙公司", "王小明１", person_id="P001"),  # 全形數字變體
    ]

    g = build_company_graph(affiliations)
    groups = detect_groups(g)

    assert groups["甲公司"] == groups["乙公司"] == groups["丙公司"]


def test_hidden_links_sentinel_cannot_be_spoofed():
    """客戶不得藉由申報一個撞到內部哨符的集團名，抹掉真實的隱性關聯。"""
    affiliations = [Affiliation("甲公司", "王小明"), Affiliation("乙公司", "王小明")]
    g = build_company_graph(affiliations)

    found = hidden_links(g, {"甲公司": "__undeclared__乙公司"})

    assert len(found) == 1
    assert found[0]["shared_persons"] == ["王小明"]


def test_same_name_different_company_ids_stay_separate():
    """兩家同名但不同統一編號的公司不得被併成一個節點。

    build_company_graph 內部以識別碼當節點鍵，最後才 relabel 回顯示名稱。
    relabel_nodes(copy=True) 在兩個鍵映到同一個名字時會靜默併成一個節點，
    一家公司的邊全部接到另一家身上、曝險就此消失，而 /group 的 unattributed
    偵測不到（它比對名稱，名稱明明在）。本模組嚴防「同名不同人」，同名不同
    公司是它的鏡像，而公司才是歸戶的主體。
    """
    affiliations = [
        Affiliation("台灣工業", "甲", role="董事", company_id="A1", person_id="P1"),
        Affiliation("台灣工業", "乙", role="董事", company_id="A2", person_id="P2"),
        Affiliation("丙公司", "甲", role="董事", company_id="B1", person_id="P1"),
    ]

    groups = detect_groups(build_company_graph(affiliations))

    assert len(groups) == 3
    assert sorted(groups) == ["丙公司", "台灣工業（A1）", "台灣工業（A2）"]
    # 只有 A1 與丙公司共用「甲」，A2 不得被拖進同一個集團。
    assert groups["台灣工業（A1）"] == groups["丙公司"]
    assert groups["台灣工業（A2）"] != groups["丙公司"]


def test_same_name_with_and_without_company_id_still_merges():
    """同一個名字只對到一個統編時不加後綴——帶統編與不帶統編的列是同一家公司。

    董監事資料集允許無統編列。若對這種情形也加後綴，會把同一家公司拆成兩個
    節點，比原本的問題更糟。撞名的定義是「兩個以上不同統編共用同一個名字」。
    """
    affiliations = [
        Affiliation("甲公司", "王小明", role="董事"),
        Affiliation("甲公司", "李大牛", role="監察人", company_id="C1", person_id="P9"),
    ]

    groups = detect_groups(build_company_graph(affiliations))

    assert sorted(groups) == ["甲公司"]


def test_hidden_links_returns_the_most_shared_pairs_first():
    """截斷前必須先依共用人數由高到低排序——否則回傳的是最不可疑的那些。

    /group 把 hidden_links 截到 200 筆並回 truncated=true。排序若反轉，
    回應的形狀完全正常（長度對、total 對、旗標對），內容卻正好相反。
    原先僅有的測試只驗長度與 total，改壞排序後 187 項測試全綠。
    """
    affiliations = [
        # 甲—乙 共用 3 人、丙—丁 共用 2 人、戊—己 共用 1 人
        *[Affiliation(c, f"三人{i}", role="董事") for i in range(3) for c in ("甲", "乙")],
        *[Affiliation(c, f"兩人{i}", role="董事") for i in range(2) for c in ("丙", "丁")],
        *[Affiliation(c, "一人", role="董事") for c in ("戊", "己")],
    ]
    g = build_company_graph(affiliations)

    top_two = hidden_links(g, {}, limit=2)

    assert [row["weight"] for row in top_two] == [3, 2]
    assert {top_two[0]["company_a"], top_two[0]["company_b"]} == {"甲", "乙"}
    assert {top_two[1]["company_a"], top_two[1]["company_b"]} == {"丙", "丁"}


def test_hidden_links_ties_break_on_company_names():
    """共用人數相同時以公司名排序決勝，確保結果穩定可重現。"""
    affiliations = [
        *[Affiliation(c, "共用甲", role="董事") for c in ("乙公司", "丙公司")],
        *[Affiliation(c, "共用乙", role="董事") for c in ("丁公司", "戊公司")],
    ]
    g = build_company_graph(affiliations)

    rows = hidden_links(g, {})

    pairs = [(r["company_a"], r["company_b"]) for r in rows]
    assert len(pairs) == 2
    assert pairs == sorted(pairs)


def test_a_tier_is_not_downgraded_by_a_later_b_tier_row():
    """同一個 person_id 先 A 後 B（或反序）時，信心一律以 A 為準。

    build_company_graph 明文寫著這條抗混報規則，但拆掉守衛後 187 項測試全綠。
    真實資料會發生：母公司自身列標 tier="A"、同名自然人列標 tier="B"。
    """
    for order in ("A 先", "B 先"):
        rows = [
            Affiliation("甲", "共用實體", company_id="C1", person_id="P1", tier="A"),
            Affiliation("乙", "共用實體", company_id="C2", person_id="P1", tier="B"),
        ]
        affiliations = rows if order == "A 先" else list(reversed(rows))

        found = hidden_links(build_company_graph(affiliations), {})

        assert [row["tier"] for row in found] == ["A"], order


def test_group_exposure_normalises_company_names():
    """曝險比對必須正規化公司名——行員從 Excel 貼上的名稱常帶尾隨空白。

    原先唯一相關的測試只斷言 /group 的 unattributed，而 unattributed 在
    API 層有自己獨立的 normalise_name 呼叫，故 group_exposure 這一行壞掉時
    它照樣綠：曝險被靜默歸零，unattributed 卻說一切正常。
    """
    assert group_exposure({"甲公司": 0}, {"甲公司 ": 100.0}) == {0: 100.0}
