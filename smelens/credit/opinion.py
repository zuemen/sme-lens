"""授信意見書產生器：把圖結構證據轉成行員可覆核的授信意見。

設計原則：**不輸出黑箱分數**。每一個判定都附帶結構證據（命中圖樣、中心性
百分位、對手多樣性、集團曝險）與中文敘事，讓授信人員能覆核、能寫進徵信
報告、能對監理交代。分數只是敘事的索引，不是結論本身。
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import networkx as nx
import pandas as pd

from smelens.explain.evidence import PipelineResult
from smelens.sna.community import community_risk_ratio, detect_communities
from smelens.sna.metrics import compute_sna_features
from smelens.sna.sme_motifs import detect_all_sme

_LABEL_ZH = {"watch": "關注", "caution": "留意", "normal": "正常"}


def _motif_sentence(node: Any, hit: Any) -> str:
    """把圖樣命中改寫成以「本次授信對象」為主詞的句子（結尾不帶句號）。

    圖樣的 `center` 是全圖層級的代表節點——以循環交易為例，取的是環上字典序
    最小者。但授信意見書是寫給「這一家公司」看的：一份談 A 公司的文件，證據
    段卻以 B 公司開頭，讀的人第一秒就會卡住，而可讀性正是本模組存在的理由。

    故當本公司只是環上成員而非 center 時，改以本公司為起點重述整條路徑。
    其餘圖樣的 center 本來就是被指認的那家公司，沿用原敘事即可。
    """
    text = hit.description_zh.rstrip("。")
    if hit.motif == "cycle_trade" and hit.center != node and node in hit.nodes:
        start = hit.nodes.index(node)
        ordered = hit.nodes[start:] + hit.nodes[:start]
        path_zh = " → ".join(str(n) for n in [*ordered, node])
        return (
            f"本公司位於長度 {len(hit.nodes)} 的封閉資金環（{path_zh}），"
            "符合循環交易／資金迴流圖樣"
        )
    # 其餘情形 center 就是本公司，把「節點 X」改寫為「本公司」——「節點」是圖論
    # 術語，出現在寫給授信人員的文件裡會讓讀者出戲。
    return text.replace(f"節點 {node} ", "本公司", 1)


_RECOMMENDATION_ZH = {
    "watch": "建議暫緩核貸，先行實地查核關係人交易與主要買方合約之真實性。",
    "caution": "建議核貸但調降額度並縮短覆審週期，要求補提主要買方合約與出貨憑證。",
    "normal": "結構面未見異常，得依既有授信條件辦理。",
}


def run_sme_pipeline(g: nx.DiGraph) -> PipelineResult:
    """企金版分析管線：SNA → 社群 → 企金圖樣，回傳四元組。

    與 `smelens.explain.evidence.run_pipeline` 的唯一差異是圖樣集合——企金
    三圖樣取代詐騙圖樣。社群風險比以圖樣命中中心作為代理標註（企業關係圖
    無 licit/illicit 真值標註，與 ChainLens 處理 TRON 即時圖的慣例一致）。
    """
    sna_df = compute_sna_features(g)
    partition = detect_communities(g)
    motif_hits = detect_all_sme(g)
    # 全節點都標記（命中中心為 1、其餘為 0），社群風險比才會是「該社群有多少比例
    # 的成員是風險中心」這個真正有鑑別力的比例。只標記命中者會讓分母等於分子，
    # 任何含命中的社群都固定得到 1.0，等於對整個社群加一個無資訊的常數。
    labels = dict.fromkeys(g.nodes(), 0)
    for hit in motif_hits:
        labels[hit.center] = 1
    risk_ratios = community_risk_ratio(partition, labels)
    return sna_df, partition, risk_ratios, motif_hits


def counterparty_diversity(g: nx.DiGraph, node: Any) -> float:
    """交易對手多樣性（0–1）：買方金額分布的正規化熵。

    單一買方 → 0；n 個買方平均分攤 → 1。無收入者回傳 0。
    企金意義：這是「客戶集中度」的連續版本，比二元的圖樣命中更適合放進
    信用分計算——集中度是程度問題，不是有無問題。

    金額先以 max(amount, 0.0) 夾到 0 才累加：折讓、退貨與沖銷在真實流水中
    必然出現，負數邊代表沖銷而非負收入。夾住之後熵的定義域自然落在
    [0, 1]，但保險起見回傳前仍明確 clamp 一次——這是本函式簽章已對外
    承諾的區間，不該因為未預期的浮點誤差或未來的計算路徑改動而破功。
    """
    amounts: dict[Any, float] = {}
    for u, _, data in g.in_edges(node, data=True):
        amounts[u] = amounts.get(u, 0.0) + max(float(data.get("amount", 0.0)), 0.0)
    total = sum(amounts.values())
    if total <= 0:
        return 0.0
    shares = [amount / total for amount in amounts.values() if amount > 0]
    if len(shares) < 2:
        return 0.0
    entropy = -sum(share * math.log(share) for share in shares)
    diversity = entropy / math.log(len(shares))
    return round(min(max(diversity, 0.0), 1.0), 4)


def network_credit(g: nx.DiGraph, node: Any, sna_df: pd.DataFrame) -> float | None:
    """網絡信用分（0–1，愈高信用愈佳）；無收入者回傳 None（未評估）。

    = 0.5 × 結構中心性百分位均值 + 0.5 × 交易對手多樣性

    企金意義：在供應鏈網絡中位置愈核心、交易對手愈分散的企業，現金流韌性
    愈高——這是財報看不到、但關係圖看得到的信用證據，正是「沒有漂亮財報
    的好公司」得以被看見的依據。

    百分位採**嚴格小於**：真實圖上多數節點的 betweenness 為 0、degree 為 1，
    若用小於等於，這批節點會被算進第 85+ 百分位而虛胖成「結構核心」。

    無收入者（in-degree 為 0，純買方／資金源頭）沒有「買方結構」可言，網絡
    信用分**不可評估**，故回傳 None 而非只取結構中心性、更不是 0。這與
    `counterparty_diversity` 已經採用的立場一致——未定義不是零。早期實作曾
    只取結構中心性當替代值，但小圖上的中心性本身就是雜訊：核心買方（圖中
    最大、最健康的節點，只被觀察到付款、從未收款）會因此得到全圖最低的
    網絡信用分，排在空殼中介與問題申請人之後——這正是本分數存在的理由要
    反過來咬自己。呼叫端（`generate_credit_opinion`）在 None 時須改用中性
    中點，而非把「無法評估」當「最差」處理。
    """
    if g.in_degree(node) == 0:
        return None
    percentiles = {
        column: float((sna_df[column] < sna_df.at[node, column]).mean())
        for column in sna_df.columns
    }
    centrality = sum(percentiles.values()) / len(percentiles)
    return round(0.5 * centrality + 0.5 * counterparty_diversity(g, node), 4)


def generate_credit_opinion(
    node: Any,
    g: nx.DiGraph,
    sna_df: pd.DataFrame,
    partition: dict[Any, int],
    risk_ratios: dict[int, float],
    motif_hits: list[Any],
    *,
    group_id: int | None = None,
    group_exposure_twd: float | None = None,
    model_score: float | None = None,
) -> dict[str, Any]:
    """對單一企業產生授信意見書。

    attention_score = 0.7×圖樣強度 + 0.2×(1−網絡信用) + 0.1×社群風險比；圖樣強度為
    0 紅旗 0、1 紅旗 0.55、2 種以上 1.0；提供 GNN model_score 時改為 0.5 × 模型
    + 0.5 × 規則分數（與 ChainLens 的模型／規則融合慣例一致）。

    **圖樣歸屬規則**：一般圖樣只計 center，避免周邊成員連坐；但 cycle_trade
    例外——封閉資金環上的**每一個**成員都是循環交易的參與者，不是被動的
    對手方，故環上成員全部引用。
    """
    if node not in sna_df.index:
        raise KeyError(f"企業 {node} 不在關係圖中")

    relevant = [
        hit
        for hit in motif_hits
        if hit.center == node or (hit.motif == "cycle_trade" and node in hit.nodes)
    ]
    credit = network_credit(g, node, sna_df)
    diversity = counterparty_diversity(g, node)
    community = partition.get(node, -1)
    risk_ratio = float(risk_ratios.get(community, 0.0))
    percentiles = {
        column: round(float((sna_df[column] < sna_df.at[node, column]).mean() * 100), 2)
        for column in sna_df.columns
    }

    # 相異圖樣種類數：兩個以上彼此獨立的結構紅旗同時成立，比單一紅旗特別嚴重
    # 更難用巧合解釋，故直接給滿分。這條規則對授信人員是可以講清楚的。
    flag_kinds = len({hit.motif for hit in relevant})
    motif_strength = 0.0 if flag_kinds == 0 else (0.55 if flag_kinds == 1 else 1.0)
    # 網絡信用分未評估（無收入紀錄）時，結構面以中性中點 0.5 計入——不可評估
    # 不等於最差，把 credit=None 當成 credit=0（0.2×(1-0)=0.2，滿分懲罰）
    # 會讓核心買方這種只被觀察到付款、從未收款的健康節點得到最重的結構扣分。
    structure_term = 0.5 if credit is None else (1.0 - credit)
    rule_score = 0.7 * motif_strength + 0.2 * structure_term + 0.1 * risk_ratio
    score = 0.5 * model_score + 0.5 * rule_score if model_score is not None else rule_score
    score = min(max(score, 0.0), 1.0)
    label = "watch" if score >= 0.7 else "caution" if score >= 0.4 else "normal"

    credit_zh = "未評估" if credit is None else f"{credit:.2f}"
    narrative: list[str] = [
        f"企業 {node} 網絡信用分 {credit_zh}、授信關注分數 {score:.2f}"
        f"（{_LABEL_ZH[label]}）。"
    ]
    if credit is None:
        narrative.append(
            "本公司於本圖中僅觀察到付款、無收入紀錄，網絡信用分未評估"
            "（結構面以中性值計入關注分數，不視為最差）。"
        )
    else:
        # 網絡信用分半數權重來自結構中心性，narrative 需點出取用的是哪個指標、
        # 落在第幾百分位——否則這一半權重對授信人員而言就是黑箱數字。
        top_feature = max(percentiles, key=lambda c: percentiles[c])
        narrative.append(
            f"結構中心性以 {top_feature} 指標最高，位居全圖第 "
            f"{percentiles[top_feature]:.0f} 百分位（此為網絡信用分半數權重來源）。"
        )
    if relevant:
        # 逐句去掉自帶的句號再以分號串接，最後統一補一個句號——直接串會產生「。；」。
        sentences = "；".join(_motif_sentence(node, hit) for hit in relevant)
        narrative.append(f"命中企金風險圖樣：{sentences}。")
    else:
        narrative.append("未命中任何企金風險圖樣。")
    if diversity == 0.0:
        narrative.append("本公司於本圖中無足以評估買方結構的收入紀錄。")
    else:
        narrative.append(
            f"交易對手多樣性 {diversity:.2f}"
            f"（{'買方高度集中' if diversity < 0.5 else '買方結構分散'}）。"
        )
    # 社群風險比是關注分數 10% 權重的來源，但標籤是圖樣命中中心的代理標註
    # （非真值），故措辭只能陳述這個比例實際上是什麼——該社群裡有多少比例
    # 的成員是圖樣命中中心，不得寫成「已知非法佔比」這種暗示真值標註存在
    # 的說法（docs/TODO.md P1 已記錄防詐分支的同一措辭不可信，此處不重蹈）。
    narrative.append(f"所屬社群 #{community} 中有 {risk_ratio:.0%} 的成員為企金風險圖樣命中中心。")
    if group_id is not None:
        exposure_text = (
            f"，該集團授信曝險合計 {group_exposure_twd:,.0f} 元"
            if group_exposure_twd is not None
            else ""
        )
        # 標明出處：歸戶脈絡是呼叫端傳入的，本模組並未自行核驗。不寫清楚的話，
        # 一段由呼叫端填入的數字會被讀成系統推導出來的結論。
        narrative.append(f"歸戶集團編號 #{group_id}（依呼叫端提供之歸戶結果）{exposure_text}。")
    if model_score is not None:
        narrative.append(f"GNN 模型判定違約機率 {model_score:.2f}。")

    return {
        "target": str(node),
        "attention_score": round(score, 4),
        "network_credit": credit,
        "label": label,
        "label_zh": _LABEL_ZH[label],
        "counterparty_diversity": diversity,
        "centrality_percentile": percentiles,
        "community_risk_ratio": round(risk_ratio, 4),
        "group_id": group_id,
        "group_exposure_twd": group_exposure_twd,
        "motif_hits": [asdict(hit) for hit in relevant],
        "narrative_zh": "".join(narrative),
        "recommendation_zh": _RECOMMENDATION_ZH[label],
    }
