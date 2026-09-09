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


def test_counterparty_diversity_negative_edge_stays_in_unit_interval():
    """負數邊（折讓／退貨／沖銷）不得把多樣性推出 [0, 1] 區間。

    修復前：B1 5000、B2 5000、B3 -9000 會算出 -23.2193，違反本函式
    docstring 承諾的 0–1 值域。
    """
    g = nx.DiGraph()
    g.add_edge("B1", "T", amount=5000.0)
    g.add_edge("B2", "T", amount=5000.0)
    g.add_edge("B3", "T", amount=-9000.0)

    diversity = counterparty_diversity(g, "T")

    assert 0.0 <= diversity <= 1.0


def test_counterparty_diversity_zero_amount_edge_stays_in_unit_interval():
    """金額為 0 的邊不應造成除以零或超出值域。"""
    g = nx.DiGraph()
    g.add_edge("B1", "T", amount=0.0)
    g.add_edge("B2", "T", amount=1000.0)

    diversity = counterparty_diversity(g, "T")

    assert 0.0 <= diversity <= 1.0


def test_counterparty_diversity_missing_amount_stays_in_unit_interval():
    """缺 amount 屬性的邊（預設 0.0）不應造成超出值域。"""
    g = nx.DiGraph()
    g.add_edge("B1", "T")
    g.add_edge("B2", "T", amount=1000.0)

    diversity = counterparty_diversity(g, "T")

    assert 0.0 <= diversity <= 1.0


def test_network_credit_prefers_diversified_company():
    """對照組買方分散，網絡信用分應高於買方集中的申請人。"""
    g = load_supply_chain_scenario()
    sna_df, _, _, _ = run_sme_pipeline(g)

    assert network_credit(g, NORMAL_APPLICANT, sna_df) > network_credit(
        g, CREDIT_APPLICANT, sna_df
    )


def test_network_credit_is_none_for_zero_in_degree_node():
    """無收入紀錄（純買方，in-degree 為 0）的節點網絡信用分未評估，回傳 None。

    修復前：這類節點只取結構中心性，回傳 0.0——把「無法評估」當成「最差」，
    讓圖中最大、最健康的核心買方拿到全圖最低的網絡信用分。
    """
    g = load_supply_chain_scenario()
    sna_df, _, _, _ = run_sme_pipeline(g)

    for node in g.nodes():
        if g.in_degree(node) == 0:
            assert network_credit(g, node, sna_df) is None, node


def test_credit_opinion_does_not_penalise_unassessed_network_credit_as_worst():
    """網絡信用分未評估時，結構面以中性中點計入，不視為最重扣分。

    鴻寶電子是劇本圖中最大、最健康的核心買方（只被觀察到付款、從未收款），
    修復前 network_credit=0.0 讓它拿到與命中圖樣同等的結構懲罰
    （0.2×(1-0)=0.2，滿分懲罰）。修復後應改為中性中點 0.2×0.5=0.1。
    """
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        "鴻寶電子", g, sna_df, partition, risk_ratios, motif_hits
    )

    assert opinion["network_credit"] is None
    assert opinion["label"] == "normal"
    assert "未評估" in opinion["narrative_zh"]


def test_credit_opinion_applicant_and_control_unaffected_by_none_credit():
    """網絡信用分未評估的變更不得影響 in-degree 非 0 的申請人／對照組分數。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    applicant = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )
    control = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert applicant["network_credit"] is not None
    assert applicant["attention_score"] == 0.82
    assert control["network_credit"] is not None
    assert control["attention_score"] == 0.0584


def test_credit_opinion_narrative_covers_centrality_and_community_risk():
    """網絡信用分的中心性半數權重與社群風險比 10% 權重，敘事都必須點出來源。

    修復前這兩項只計入分數卻不出現在敘事裡，讀者看不到 10%~50% 權重的
    結構依據；且社群風險比措辭不得沿用防詐分支不可信的「已知非法佔比」
    （docs/TODO.md P1），必須陳述其真正定義：該社群中圖樣命中中心的比例。
    """
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert "百分位" in opinion["narrative_zh"]
    assert "已知非法佔比" not in opinion["narrative_zh"]
    assert "為企金風險圖樣命中中心" in opinion["narrative_zh"]


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
