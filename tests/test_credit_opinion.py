"""授信意見書測試。"""

from __future__ import annotations

import networkx as nx

from smelens.credit.opinion import (
    counterparty_diversity,
    generate_credit_opinion,
    network_credit,
    run_sme_pipeline,
)
from smelens.data.sme_scenario import (
    CREDIT_APPLICANT,
    NORMAL_APPLICANT,
    load_supply_chain_scenario,
)


def test_counterparty_diversity_single_buyer_is_zero():
    """收入全部來自單一買方，多樣性為 0。"""
    g = nx.DiGraph()
    g.add_edge("唯一買方", "廠商", amount=5_000_000.0)

    assert counterparty_diversity(g, "廠商") == 0.0


def test_counterparty_diversity_even_split_is_one():
    """四個買方均分收入，多樣性為 1。"""
    g = nx.DiGraph()
    for i in range(4):
        g.add_edge(f"買方{i}", "廠商", amount=1_000_000.0)

    assert counterparty_diversity(g, "廠商") == 1.0


def test_counterparty_diversity_no_revenue_is_zero():
    """無收入者多樣性為 0，且不得除以零。"""
    g = nx.DiGraph()
    g.add_edge("廠商", "供應商", amount=1_000_000.0)

    assert counterparty_diversity(g, "廠商") == 0.0


def test_network_credit_prefers_diversified_company():
    """對照組買方分散，網絡信用分應高於買方集中的申請人。"""
    g = load_supply_chain_scenario()
    sna_df, _, _, _ = run_sme_pipeline(g)

    assert network_credit(g, NORMAL_APPLICANT, sna_df) > network_credit(
        g, CREDIT_APPLICANT, sna_df
    )


def test_credit_opinion_flags_applicant_with_motifs():
    """申請人命中圖樣，關注分數應達留意以上並附中文敘事與建議。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert opinion["target"] == CREDIT_APPLICANT
    assert opinion["label"] in {"watch", "caution"}
    assert opinion["attention_score"] >= 0.4
    assert opinion["motif_hits"], "申請人應命中至少一個企金圖樣"
    assert CREDIT_APPLICANT in opinion["narrative_zh"]
    assert opinion["recommendation_zh"]


def test_credit_opinion_includes_cycle_even_when_not_center():
    """循環交易的環上成員都應被引用，不能只算 center。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert any(hit["motif"] == "cycle_trade" for hit in opinion["motif_hits"])


def test_credit_opinion_normal_company_is_not_watch():
    """對照組未命中圖樣，不得被列為關注。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert opinion["label"] != "watch"
    assert opinion["motif_hits"] == []


def test_credit_opinion_label_thresholds_are_pinned():
    """三級分界與結構證據欄位都要釘死：把 0.7／0.4 對調也必須有測試會紅。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    watch = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )
    normal = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert watch["label"] == "watch"
    assert watch["label_zh"] == "關注"
    assert watch["attention_score"] >= 0.7
    assert normal["label"] == "normal"
    assert normal["label_zh"] == "正常"
    assert normal["attention_score"] < 0.4
    # 結構證據欄位是「可解釋」主張的實體，不得為空或殘缺
    assert set(watch["centrality_percentile"]) == {
        "in_degree",
        "out_degree",
        "pagerank",
        "kcore",
        "betweenness",
    }
    assert all(0.0 <= v <= 100.0 for v in watch["centrality_percentile"].values())
    assert isinstance(watch["community_risk_ratio"], float)
    assert {hit["motif"] for hit in watch["motif_hits"]} == {
        "cycle_trade",
        "buyer_concentration",
    }


def test_credit_opinion_narrative_speaks_about_the_applicant():
    """敘事必須以本次授信對象為主詞，且不得出現「。；」的串接瑕疵。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    narrative = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )["narrative_zh"]

    assert "。；" not in narrative
    # 環上證據要從本公司講起，不是從環上字典序最小的另一家公司講起
    assert "本公司位於長度 4 的封閉資金環（泰昇精密 →" in narrative


def test_credit_opinion_carries_group_context():
    """帶入集團資訊時應原樣附在意見書上，供行員覆核集團曝險。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT,
        g,
        sna_df,
        partition,
        risk_ratios,
        motif_hits,
        group_id=0,
        group_exposure_twd=50_000_000.0,
    )

    assert opinion["group_id"] == 0
    assert opinion["group_exposure_twd"] == 50_000_000.0
    assert "集團" in opinion["narrative_zh"]
