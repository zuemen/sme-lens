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


def test_credit_opinion_caution_band_is_reachable_and_pinned():
    """留意級（0.4 ≤ 分數 < 0.7）必須被真的走到，否則門檻對調不會被抓到。

    兩家劇本公司的規則分數是 0.83 與 0.09，都落在模糊帶之外——把 0.7 與 0.4
    對調，它們的 label 一個字都不會變，測試等於沒牙。改以 model_score 把分數
    推進中間帶：此時門檻一對調，caution 就會變成 watch，測試才真的擋得住。
    這同時也是 model_score 混合路徑（0.5×模型 + 0.5×規則）唯一的測試。
    """
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits, model_score=0.8
    )

    assert opinion["label"] == "caution"
    assert opinion["label_zh"] == "留意"
    assert 0.4 <= opinion["attention_score"] < 0.7
    assert "GNN 模型判定違約機率 0.80" in opinion["narrative_zh"]


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


def test_credit_opinion_recommendation_matches_label():
    """行員真正據以行動的是建議字串——把 watch 與 normal 的建議對調也必須有測試會紅。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    watch = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )
    normal = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert watch["recommendation_zh"].startswith("建議暫緩核貸")
    assert normal["recommendation_zh"].startswith("結構面未見異常")


def test_credit_opinion_does_not_flag_clean_bystanders():
    """未命中任何圖樣的旁觀公司不得被列為留意以上——否則等於全圖標紅，訊號歸零。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    for company in ("鴻寶電子", "中部機電", "大安工業", "永康鋼鐵", "南方塑膠", "華隆貿易"):
        opinion = generate_credit_opinion(
            company, g, sna_df, partition, risk_ratios, motif_hits
        )
        assert opinion["motif_hits"] == [], f"{company} 不應命中任何圖樣"
        assert opinion["label"] == "normal", (
            f"{company} 未命中圖樣卻被評為 {opinion['label']}（{opinion['attention_score']}）"
        )
