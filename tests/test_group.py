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


def test_hidden_links_sentinel_cannot_be_spoofed():
    """客戶不得藉由申報一個撞到內部哨符的集團名，抹掉真實的隱性關聯。"""
    affiliations = [Affiliation("甲公司", "王小明"), Affiliation("乙公司", "王小明")]
    g = build_company_graph(affiliations)

    found = hidden_links(g, {"甲公司": "__undeclared__乙公司"})

    assert len(found) == 1
    assert found[0]["shared_persons"] == ["王小明"]
