"""中小企業供應鏈授信劇本圖測試。"""

from __future__ import annotations

from smelens.data.sme_scenario import (
    APPLICATION_AMOUNT_TWD,
    CREDIT_APPLICANT,
    NORMAL_APPLICANT,
    load_supply_chain_scenario,
)
from smelens.sna.sme_motifs import (
    detect_all_sme,
    detect_buyer_concentration,
    detect_cycle_trade,
    detect_shell_intermediary,
)


def test_scenario_graph_metadata():
    """圖屬性須完整，供 API 與工作台直接引用。"""
    g = load_supply_chain_scenario()

    assert g.graph["credit_applicant"] == CREDIT_APPLICANT
    assert g.graph["normal_applicant"] == NORMAL_APPLICANT
    assert g.graph["application_amount_twd"] == APPLICATION_AMOUNT_TWD
    assert g.graph["story_zh"]
    assert all("role" in d for _, d in g.nodes(data=True))


def test_applicant_sits_on_a_closed_money_cycle():
    """申請人與關係人構成封閉資金環。"""
    g = load_supply_chain_scenario()

    cycles = detect_cycle_trade(g)

    assert any(CREDIT_APPLICANT in hit.nodes for hit in cycles)


def test_shell_intermediary_is_the_only_passthrough():
    """劇本中僅宏益企業為空殼過水節點。"""
    g = load_supply_chain_scenario()

    centers = {hit.center for hit in detect_shell_intermediary(g)}

    assert centers == {"宏益企業"}


def test_applicant_is_buyer_concentrated():
    """申請人逾七成收入來自單一買方。"""
    g = load_supply_chain_scenario()

    centers = {hit.center for hit in detect_buyer_concentration(g, min_ratio=0.7)}

    assert CREDIT_APPLICANT in centers


def test_normal_applicant_triggers_no_motif():
    """對照組結構乾淨，不得命中任何企金圖樣。"""
    g = load_supply_chain_scenario()

    hits = [hit for hit in detect_all_sme(g) if hit.center == NORMAL_APPLICANT]

    assert hits == []
