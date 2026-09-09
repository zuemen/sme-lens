"""企鏡 SME Lens Streamlit Demo 工作台。

兩種模式：
1. 出金審查 Demo —— 提案書招牌情境「50 萬 USDT 出金攔阻」一鍵展演：
   決策卡 → 關聯路徑高亮圖譜 → 調查敘事 → STR 草稿下載。
2. 金流圖譜工作台 —— 輸入 TRON 地址抓取 2-hop USDT 金流圖自由探索。

啟動：streamlit run smelens/app/workbench.py（或 make app）
"""

from __future__ import annotations

import os
from typing import Any

import networkx as nx
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from pyvis.network import Network

from smelens.data import scenario, tron
from smelens.explain.evidence import generate_evidence, run_pipeline
from smelens.explain.screening import screen_withdrawal

load_dotenv()  # 讀取 .env（TRONGRID_API_KEY）

HIGH_RISK_THRESHOLD = 0.7
ROLE_COLOR = {
    "victim": "#f5b041",
    "support": "#e74c3c",
    "aggregator": "#c0392b",
    "mule": "#e67e22",
    "peel": "#d35400",
    "peel_side": "#7f8c8d",
    "otc": "#9b59b6",
    "normal": "#5dade2",
}


def load_graph(address: str, use_example: bool) -> tuple[nx.DiGraph, bool]:
    """回傳（圖, 是否為降級範例圖）。"""
    if use_example or not address:
        return tron.load_example_graph(), False
    try:
        return (
            tron.fetch_two_hop_graph(address, api_key=os.getenv("TRONGRID_API_KEY")),
            False,
        )
    except Exception:
        return tron.load_example_graph(), True


def build_pyvis_html(
    g: nx.DiGraph,
    evidences: dict[Any, dict],
    hit_nodes: set[Any],
    pagerank: dict[Any, float],
    highlight_path: list[Any] | None = None,
    focus: Any | None = None,
) -> str:
    """把分析結果渲染為 PyVis 互動網頁；highlight_path 上的邊以橘色加粗。"""
    path_edges = set(zip(highlight_path, highlight_path[1:])) if highlight_path else set()
    net = Network(
        height="650px", width="100%", directed=True, bgcolor="#111111", font_color="#eeeeee"
    )
    for node, data in g.nodes(data=True):
        score = evidences[node]["score"]
        risky = node in hit_nodes or score >= HIGH_RISK_THRESHOLD
        role = data.get("role")
        role_zh = scenario.ROLE_ZH.get(role, "")
        color = "#e74c3c" if risky else ROLE_COLOR.get(role, "#5dade2")
        if node == focus:
            color = "#f1c40f"  # 審查目標：金色聚焦
        title = f"{node}"
        if role_zh:
            title += f"｜{role_zh}"
        title += f"\nscore={score:.2f}（{evidences[node]['label']}）"
        net.add_node(
            str(node),
            label=str(node)[:14],
            title=title,
            color=color,
            size=float(10 + pagerank.get(node, 0.0) * 300),
            borderWidth=4 if node == focus else 1,
        )
    for u, v, d in g.edges(data=True):
        amount = float(d.get("amount", 0.0))
        on_path = (u, v) in path_edges
        net.add_edge(
            str(u),
            str(v),
            value=max(amount, 1.0),
            title=f"{amount:,.2f} USDT",
            color="#f39c12" if on_path else None,
            width=6 if on_path else None,
        )
    return net.generate_html()


def render_screening_demo() -> None:
    """出金審查 Demo：提案書第一章招牌情境之互動展演。"""
    g = scenario.load_withdrawal_scenario()
    st.info(f"**情境**：{g.graph['story_zh']}")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        target = st.selectbox(
            "出金目標地址",
            [g.graph["withdrawal_target"], g.graph["normal_target"]],
            format_func=lambda a: {
                g.graph["withdrawal_target"]: f"{a}（本案：未通報之 OTC 收款地址）",
                g.graph["normal_target"]: f"{a}（對照組：正常用戶地址）",
            }[a],
        )
    with col2:
        amount = st.number_input(
            "申請金額（USDT）",
            min_value=1.0,
            value=float(g.graph["withdrawal_amount_usdt"]),
            step=10_000.0,
        )
    with col3:
        st.write("")
        run = st.button("執行出金審查", type="primary", use_container_width=True)

    if not run:
        st.caption("按下「執行出金審查」，平台將於數秒內回傳風險分數、資金關聯與處置建議。")
        return

    result = screen_withdrawal(g, target, amount, request_id="DEMO-2026-001")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("綜合風險分數", f"{result['risk_score']:.2f}")
    m2.metric("自身結構分數", f"{result['self_score']:.2f}")
    m3.metric("關聯風險分數", f"{result['association_score']:.2f}")
    m4.metric("處置建議", result["decision_zh"])
    if result["decision"] == "block":
        st.error(f"🚫 {result['narrative_zh']}")
    elif result["decision"] == "review":
        st.warning(f"⚠️ {result['narrative_zh']}")
    else:
        st.success(f"✅ {result['narrative_zh']}")

    # 圖譜：高亮最近風險節點 → 目標之資金路徑
    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    hit_nodes = {n for hit in motif_hits for n in hit.nodes}
    evidences = {
        n: generate_evidence(n, g, sna_df, partition, risk_ratios, motif_hits)
        for n in g.nodes()
    }
    path = result["associations"][0]["path"] if result["associations"] else None
    st.subheader("金流圖譜（橘色路徑＝風險資金流向出金地址；金色＝審查目標）")
    components.html(
        build_pyvis_html(
            g, evidences, hit_nodes, sna_df["pagerank"].to_dict(), path, focus=target
        ),
        height=680,
    )

    if result["str_draft_zh"]:
        with st.expander("📄 可疑交易申報（STR）草稿", expanded=True):
            st.text(result["str_draft_zh"])
            st.download_button(
                "下載 STR 草稿（.txt）",
                result["str_draft_zh"],
                file_name=f"STR_draft_{target}.txt",
            )
    with st.expander("結構證據 JSON（稽核軌跡）"):
        st.json(result)


def render_workbench() -> None:
    """自由探索模式：TRON 地址 → 2-hop 金流圖 ＋ 風險證據面板。"""
    address = st.text_input("TRON 地址（TRC-20 USDT）", placeholder="T 開頭主網地址…")
    use_example = st.checkbox("使用內建範例圖（離線 Demo）", value=not address)

    address = address.strip()
    if address and not use_example and not tron.is_valid_tron_address(address):
        st.error("地址格式不正確：需為 T 開頭的 Base58 主網地址（34 字元）。")
        return

    g, degraded = load_graph(address, use_example)
    if degraded:
        st.warning("TronGrid 抓取失敗（無網路或限速），已改用內建範例圖。")

    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    hit_nodes = {n for hit in motif_hits for n in hit.nodes} | {h.center for h in motif_hits}
    evidences = {
        n: generate_evidence(n, g, sna_df, partition, risk_ratios, motif_hits)
        for n in g.nodes()
    }
    pagerank = sna_df["pagerank"].to_dict()

    with st.sidebar:
        st.header("風險證據面板")
        ranked = sorted(g.nodes(), key=lambda n: evidences[n]["score"], reverse=True)
        node = st.selectbox("選擇節點（依風險排序）", ranked)
        ev = evidences[node]
        st.metric("風險分數", f"{ev['score']:.2f}", ev["label"])
        st.write(ev["narrative_zh"])
        with st.expander("結構證據 JSON"):
            st.json(ev)

    st.subheader(f"金流圖譜（{g.number_of_nodes()} 節點 / {g.number_of_edges()} 邊）")
    components.html(build_pyvis_html(g, evidences, hit_nodes, pagerank), height=680)

    st.dataframe(
        sna_df.assign(score=[evidences[n]["score"] for n in sna_df.index])
        .sort_values("score", ascending=False)
        .head(15),
        use_container_width=True,
    )


def main() -> None:
    st.set_page_config(page_title="企鏡 SME Lens", layout="wide")
    st.title("企鏡 SME Lens — 詐騙金流偵測工作台")
    st.caption("SNA + 圖樣規則 + 可解釋證據｜研究用途，非投資或法律建議")

    mode = st.radio(
        "模式",
        ["出金審查 Demo（50 萬 USDT 攔阻情境）", "金流圖譜工作台"],
        horizontal=True,
    )
    if mode.startswith("出金審查"):
        render_screening_demo()
    else:
        render_workbench()


if __name__ == "__main__":
    main()
