"""出金審查引擎：資金關聯追溯 ＋ 風險融合決策 ＋ 可疑交易申報（STR）草稿。

對應提案書第一章招牌情境：用戶申請提領 USDT 至外部地址，平台於數秒內
回傳該地址與已知詐騙集資節點之 k 階資金關聯與風險分數，供交易所
即時暫緩出金並產出調查報告。

核心差異：目標地址即使**本身未命中任何圖樣、亦不在黑名單**，只要上游
k 階內存在圖樣命中節點（集資、集散、剝洋蔥），風險即沿資金路徑衰減傳導
（decay^(距離-1)），再與節點自身結構分數以 noisy-or 融合——
「由手法找地址」的主動防禦，補足黑名單之被動比對。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

import networkx as nx

from smelens.explain.evidence import PipelineResult, generate_evidence, run_pipeline
from smelens.sna.motifs import MotifHit

DEFAULT_MAX_HOPS = 4  # 關聯追溯之最大階數
DEFAULT_DECAY = 0.6  # 每增加一階，風險傳導衰減係數
BLOCK_THRESHOLD = 0.7  # ≥ 此分數 → 暫緩出金並人工審查
REVIEW_THRESHOLD = 0.4  # ≥ 此分數 → 加強審查（EDD）

_DECISION_ZH = {"block": "暫緩出金並啟動人工審查", "review": "加強審查（EDD）", "pass": "予以放行"}

_MOTIF_ZH = {
    "fan_in": "集資扇入",
    "fan_out": "快速分散",
    "gather_scatter": "集散（smurfing）",
    "peeling_chain": "剝洋蔥鏈",
}


@dataclass
class Association:
    """目標地址與單一風險節點之資金關聯。"""

    risky_node: Any
    distance: int  # 資金路徑階數（邊數）
    path: list[Any] = field(default_factory=list)  # 風險節點 → 目標之資金流路徑
    motifs: list[str] = field(default_factory=list)  # 該風險節點命中之圖樣


def find_risky_associations(
    g: nx.DiGraph,
    target: Any,
    motif_hits: list[MotifHit],
    max_hops: int = DEFAULT_MAX_HOPS,
) -> list[Association]:
    """沿資金流向（有向路徑）追溯：哪些圖樣命中節點的資金於 max_hops 階內流抵 target。

    以 target 於反向圖上做單源 BFS（O(V+E)），一次取得所有上游節點距離，
    再對每個命中節點回溯最短路徑。回傳依距離排序。
    """
    center_motifs: dict[Any, list[str]] = {}
    for hit in motif_hits:
        center_motifs.setdefault(hit.center, []).append(hit.motif)
    if not center_motifs or target not in g:
        return []

    reverse = g.reverse(copy=False)
    lengths = nx.single_source_shortest_path_length(reverse, target, cutoff=max_hops)
    associations = [
        Association(
            risky_node=node,
            distance=dist,
            path=list(reversed(nx.shortest_path(reverse, target, node))),
            motifs=sorted(set(center_motifs[node])),
        )
        for node, dist in lengths.items()
        if node in center_motifs and dist > 0
    ]
    return sorted(associations, key=lambda a: (a.distance, str(a.risky_node)))


def association_score(associations: list[Association], decay: float = DEFAULT_DECAY) -> float:
    """關聯風險分數 = max(decay^(距離-1))；一階關聯 = 1.0，隨距離幾何衰減。"""
    if not associations:
        return 0.0
    return max(decay ** (a.distance - 1) for a in associations)


def _format_ts(ts: float | None) -> str:
    if ts is None:
        return "—"
    return datetime.fromtimestamp(int(ts), tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _path_zh(g: nx.DiGraph, path: list[Any]) -> str:
    """把資金路徑轉為「A →(金額/時間) B」中文敘述。"""
    parts: list[str] = [str(path[0])]
    for u, v in zip(path, path[1:]):
        d = g[u][v]
        amount = d.get("amount")
        amount_str = f"{amount:,.0f} USDT" if amount is not None else "金額不明"
        parts.append(f" →（{amount_str}，{_format_ts(d.get('timestamp'))}）{v}")
    return "".join(parts)


def generate_str_draft(
    target: Any,
    amount_usdt: float,
    decision: str,
    combined_score: float,
    evidence: dict[str, Any],
    associations: list[Association],
    g: nx.DiGraph,
    request_id: str | None = None,
) -> str:
    """產生可疑交易申報（STR）草稿——提案書三大模組之「可疑交易報告輔助」。

    輸出依「交易概要／可疑事由／資金關聯證據鏈／建議處置」結構化，
    每項判定均對應可稽核之結構證據，非黑箱分數。
    """
    lines: list[str] = [
        "【可疑交易申報草稿】（由企鏡 SME Lens 自動產生，供法遵人員審閱修訂）",
        "",
        "一、交易概要",
        f"　　案件編號：{request_id or '（待填）'}",
        "　　交易類型：虛擬資產出金（TRC-20 USDT）",
        f"　　出金目標地址：{target}",
        f"　　申請金額：{amount_usdt:,.0f} USDT",
        f"　　系統判定：綜合風險分數 {combined_score:.2f}，建議{_DECISION_ZH[decision]}。",
        "",
        "二、可疑事由",
    ]
    if associations:
        nearest = associations[0]
        motifs_zh = "、".join(_MOTIF_ZH.get(m, m) for m in nearest.motifs)
        lines.append(
            f"　　目標地址與命中「{motifs_zh}」圖樣之節點 {nearest.risky_node} "
            f"存在 {nearest.distance} 階資金關聯；該地址本身未見於黑名單，"
            "惟其上游資金結構符合假投資詐騙「集資—分層—整合」洗錢路徑特徵。"
        )
    else:
        lines.append("　　目標地址自身結構指標異常（詳見結構證據）。")
    lines += [
        "",
        "三、資金關聯證據鏈",
    ]
    if associations:
        for i, assoc in enumerate(associations[:5], start=1):
            motifs_zh = "、".join(_MOTIF_ZH.get(m, m) for m in assoc.motifs)
            lines.append(
                f"　　({i}) 風險節點 {assoc.risky_node}（{motifs_zh}，{assoc.distance} 階）"
            )
            lines.append(f"　　　　路徑：{_path_zh(g, assoc.path)}")
    else:
        lines.append("　　（無圖樣命中節點之上游關聯）")
    lines += [
        "",
        "四、目標地址結構證據",
        f"　　{evidence['narrative_zh']}",
        "",
        "五、建議處置",
        f"　　{_DECISION_ZH[decision]}；如經人工審查確認，依洗錢防制法及虛擬資產服務法",
        "　　相關規定辦理可疑交易申報，並保留本報告與圖譜快照為稽核軌跡。",
    ]
    return "\n".join(lines)


def screen_withdrawal(
    g: nx.DiGraph,
    target: Any,
    amount_usdt: float,
    request_id: str | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    pipeline: PipelineResult | None = None,
) -> dict[str, Any]:
    """出金審查主流程：SNA 管線 → 目標證據 → 關聯追溯 → noisy-or 融合 → 決策＋STR。

    combined = 1 − (1 − 自身結構分數) × (1 − 關聯分數)：
    兩訊號互補——自身乾淨但上游髒（本劇本主角）或自身即為樞紐，皆可攔截。

    target 不在圖中（全新地址、鏈上無交易紀錄——最常見的正常出金）時，
    回傳 insufficient_data 的放行結果而非拋錯。

    pipeline 傳入已算好的 run_pipeline 結果時直接重用，供同一張圖上還要
    產生圖譜 JSON 的呼叫端（API /screen）避免重算。
    """
    if target not in g:
        return {
            "target": str(target),
            "amount_usdt": amount_usdt,
            "risk_score": 0.0,
            "self_score": 0.0,
            "association_score": 0.0,
            "decision": "pass",
            "decision_zh": _DECISION_ZH["pass"],
            "insufficient_data": True,
            "narrative_zh": (
                f"出金目標地址 {target}（申請金額 {amount_usdt:,.0f} USDT）"
                "鏈上查無交易紀錄（全新地址或無 USDT 歷史），無結構證據可供評估，"
                f"建議{_DECISION_ZH['pass']}；如有其他風險情資請併同人工判斷。"
            ),
            "associations": [],
            "evidence": None,
            "str_draft_zh": None,
        }
    sna_df, partition, risk_ratios, motif_hits = (
        pipeline if pipeline is not None else run_pipeline(g)
    )
    evidence = generate_evidence(target, g, sna_df, partition, risk_ratios, motif_hits)
    associations = find_risky_associations(g, target, motif_hits, max_hops=max_hops)

    assoc = association_score(associations, decay=decay)
    combined = 1.0 - (1.0 - evidence["score"]) * (1.0 - assoc)
    decision = "block" if combined >= BLOCK_THRESHOLD else (
        "review" if combined >= REVIEW_THRESHOLD else "pass"
    )

    narrative: list[str] = [
        f"出金目標地址 {target}（申請金額 {amount_usdt:,.0f} USDT）"
        f"綜合風險分數 {combined:.2f}，建議{_DECISION_ZH[decision]}。"
    ]
    if associations:
        nearest = associations[0]
        motifs_zh = "、".join(_MOTIF_ZH.get(m, m) for m in nearest.motifs)
        narrative.append(
            f"該地址與命中「{motifs_zh}」圖樣之節點 {nearest.risky_node} "
            f"存在 {nearest.distance} 階資金關聯（關聯分數 {assoc:.2f}）。"
        )
        if evidence["score"] < REVIEW_THRESHOLD:
            narrative.append("注意：該地址自身結構未見異常且不在黑名單，僅憑名單比對將漏放此筆出金。")

    str_draft = (
        generate_str_draft(
            target, amount_usdt, decision, combined, evidence, associations, g, request_id
        )
        if decision != "pass"
        else None
    )

    return {
        "target": str(target),
        "amount_usdt": amount_usdt,
        "risk_score": round(combined, 4),
        "self_score": evidence["score"],
        "association_score": round(assoc, 4),
        "decision": decision,
        "decision_zh": _DECISION_ZH[decision],
        "narrative_zh": "".join(narrative),
        "associations": [asdict(a) for a in associations],
        "evidence": evidence,
        "str_draft_zh": str_draft,
    }
