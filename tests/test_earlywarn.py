"""貸後早期預警測試：標籤擴散的正確性、兩道閘的實際效果與證據路徑。"""

from __future__ import annotations

import networkx as nx
import pytest

from smelens.credit.earlywarn import (
    exposure_at_risk,
    propagate_risk,
    warning_list,
)
from smelens.data import sme_scenario

#: 劇本圖裡最可能先出事的那一家：空殼中介，過水比 99%、自身幾無留存。
SEED = "宏益企業"

_EXPOSURES = {
    "泰昇精密": 30_000_000.0,
    "昇泰貿易": 12_000_000.0,
    "宏益企業": 8_000_000.0,
    "鴻寶電子": 50_000_000.0,
    "中部機電": 4_000_000.0,
    "禾昌五金": 6_000_000.0,
}


def _scenario() -> nx.DiGraph:
    return sme_scenario.load_supply_chain_scenario()


def test_seed_stays_at_one():
    """種子是已知事實，夾制必須讓它始終為 1.0，不被擴散稀釋。"""
    scores = propagate_risk(_scenario(), [SEED])

    assert scores[SEED] == 1.0


def test_risk_decays_with_distance():
    """一跳鄰居的分數必須高於二跳，二跳高於三跳——否則「擴散」沒有意義。"""
    scores = propagate_risk(_scenario(), [SEED])

    one_hop = scores["昇泰貿易"]  # 宏益 → 昇泰
    two_hop = scores["泰昇投資"]  # 宏益 → 昇泰 → 泰昇投資
    three_hop = scores["禾昌五金"]  # 對照組，三跳之外

    assert one_hop > two_hop > three_hop > 0.0


def test_disconnected_company_gets_zero():
    """與種子完全不連通的公司分數為 0：風險不會憑空出現在無關的戶頭上。"""
    g = _scenario()
    g.add_node("孤立公司", role="normal")

    scores = propagate_risk(g, [SEED])

    assert scores["孤立公司"] == 0.0


def test_no_seeds_flags_nobody():
    """沒有種子時全圖為 0，名單為空——沒有已知事實就不該推論出風險。"""
    g = _scenario()

    assert set(propagate_risk(g, []).values()) == {0.0}
    assert warning_list(g, []) == []


def test_seed_not_in_graph_is_ignored():
    """行內名單裡有些公司不在這張圖上，那不是錯誤，不該炸掉。"""
    g = _scenario()

    scores = propagate_risk(g, [SEED, "不存在的公司"])

    assert scores[SEED] == 1.0


def test_alpha_out_of_range_is_rejected():
    """alpha 為 0 或 1 會讓功能失去意義（完全不傳／無衰減傳遍全圖），明確拒絕。"""
    for bad in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="alpha"):
            propagate_risk(_scenario(), [SEED], alpha=bad)


def test_propagation_is_deterministic():
    """同一張圖重跑兩次結果必須逐位相同——前端照分數排序算繪名單。"""
    g = _scenario()

    assert propagate_risk(g, [SEED]) == propagate_risk(g, [SEED])


def test_score_is_independent_of_node_insertion_order():
    """節點插入順序不得影響分數：浮點加總順序若隨字典順序浮動，末位會跳動。"""
    g = _scenario()
    shuffled = nx.DiGraph()
    for u, v, data in sorted(g.edges(data=True), key=lambda e: (e[1], e[0])):
        shuffled.add_edge(u, v, **data)

    assert propagate_risk(g, [SEED]) == propagate_risk(shuffled, [SEED])


def test_control_group_is_not_on_the_warning_list():
    """對照組（結構乾淨、距種子三跳）不得進入關注名單。

    這是整個功能的可信度所繫：一份把全圖都列進來的關注名單等於沒有名單，
    而那正是本系統對其他風控工具的批評。預設門檻 0.20 與最遠兩跳兩道閘，
    就是為了讓這件事成立。
    """
    items = warning_list(_scenario(), [SEED], _EXPOSURES)

    companies = [item.company for item in items]
    assert "禾昌五金" not in companies
    # 對照組的四個買方（四跳）更不該出現
    for buyer in ("大安工業", "永康鋼鐵", "南方塑膠", "華隆貿易"):
        assert buyer not in companies


def test_warning_list_contents_and_order():
    """名單內容與順序都要釘住：分數由高到低，種子在最前，直接對手方次之。"""
    items = warning_list(_scenario(), [SEED], _EXPOSURES)

    assert [item.company for item in items] == [
        "宏益企業",  # 種子 1.0
        "昇泰貿易",  # 一跳
        "泰昇精密",  # 一跳
        "泰昇投資",  # 二跳
        "鴻寶電子",  # 二跳
        "中部機電",  # 二跳
    ]
    assert [item.hops for item in items] == [0, 1, 1, 2, 2, 2]
    assert items[0].score == 1.0
    scores = [item.score for item in items]
    assert scores == sorted(scores, reverse=True)


def test_warning_item_carries_the_evidence_path():
    """每一筆都要說得出風險從哪來、經哪條路徑——那是授信人員要看的東西。"""
    items = warning_list(_scenario(), [SEED], _EXPOSURES)
    by_company = {item.company: item for item in items}

    applicant = by_company["泰昇精密"]
    assert applicant.source == SEED
    assert applicant.path == ("宏益企業", "泰昇精密")
    assert "宏益企業 → 泰昇精密" in applicant.reason_zh
    assert "應收帳款" in applicant.action_zh  # 一跳的處置建議

    second_layer = by_company["泰昇投資"]
    assert second_layer.path == ("宏益企業", "昇泰貿易", "泰昇投資")
    assert "覆審" in second_layer.action_zh  # 二跳的處置建議


def test_max_hops_gate_is_independent_of_threshold():
    """跳數閘要能單獨生效：把門檻放到 0 也不該讓三跳以外的公司進名單。"""
    items = warning_list(_scenario(), [SEED], _EXPOSURES, threshold=0.0, max_hops=1)

    assert {item.hops for item in items} <= {0, 1}
    assert "泰昇投資" not in [item.company for item in items]


def test_exposure_at_risk_excludes_the_seed():
    """種子的餘額已進催收程序，不屬於「這次新被點名」的曝險，預設要排除。

    算進去會虛增這份名單的價值——8,000,000 的差額就是那家已出事的公司。
    """
    items = warning_list(_scenario(), [SEED], _EXPOSURES)

    without_seed = exposure_at_risk(items)
    with_seed = exposure_at_risk(items, exclude_seeds=False)

    # 一跳 30,000,000 + 12,000,000、二跳 50,000,000 + 4,000,000（泰昇投資無餘額）
    assert without_seed == 96_000_000.0
    assert with_seed - without_seed == _EXPOSURES[SEED]


def test_multiple_seeds_report_the_nearest_source():
    """有多個出事戶時，每家公司的風險來源要指向最近的那一個。"""
    items = warning_list(_scenario(), [SEED, "鴻寶電子"], _EXPOSURES)
    by_company = {item.company: item for item in items}

    # 泰昇精密距兩個種子都是一跳；來源以字典序決勝，但必須是其中之一且跳數為 1
    assert by_company["泰昇精密"].hops == 1
    assert by_company["泰昇精密"].source in {SEED, "鴻寶電子"}
    # 中部機電距宏益二跳、距鴻寶二跳，仍應為二跳
    assert by_company["中部機電"].hops == 2
