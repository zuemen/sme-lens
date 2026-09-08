"""50 萬 USDT 假投資詐騙出金攔阻劇本圖（提案書第一章招牌情境）。

劇本對應提案書「劇本—角色—金流圖樣」知識圖譜之假投資鏈路：
客服收款地址（fan-in 集資）→ 集資主錢包（gather-scatter）→ 車手分散（fan-out）
→ 剝洋蔥分層（peeling chain）→ OTC 出金地址（integration）。

關鍵設計：出金目標地址 TOtcOut01 **本身從未命中任何圖樣、也不在黑名單上**，
但與集資主錢包存在二階資金關聯——用以演示「由手法找地址」對比
黑名單比對之核心差異：黑名單看不到它，結構關聯追溯看得到。

時間軸註記：假投資詐團常以「限時加碼優惠」話術誘導被害人於短時間內集中
入金，故被害人入金壓縮於約 50 分鐘窗口內，符合 fan-in 圖樣之時間窗假設。
"""

from __future__ import annotations

import networkx as nx

# 劇本角色 → 中文名稱（工作台 tooltip 與敘事用）
ROLE_ZH = {
    "victim": "被害人",
    "support": "客服收款地址",
    "aggregator": "集資主錢包",
    "mule": "車手地址",
    "peel": "剝洋蔥中繼",
    "peel_side": "剝離小額地址",
    "otc": "OTC 出金地址",
    "normal": "正常交易地址",
}

WITHDRAWAL_TARGET = "TOtcOut01"  # 交易所用戶申請出金之目標地址（可疑）
NORMAL_TARGET = "TNormalUser01"  # 對照組：正常用戶出金地址
WITHDRAWAL_AMOUNT_USDT = 500_000.0  # 提案書情境：50 萬 USDT 提領


def _add(g: nx.DiGraph, u: str, v: str, amount: float, ts: int) -> None:
    g.add_edge(u, v, amount=amount, timestamp=ts)


def load_withdrawal_scenario() -> nx.DiGraph:
    """建構 50 萬 USDT 假投資詐騙劇本圖。

    節點屬性：role（英文角色鍵，見 ROLE_ZH）。
    圖屬性：center（集資主錢包）、withdrawal_target、normal_target、
    withdrawal_amount_usdt、story_zh（劇本一句話摘要）。
    """
    g = nx.DiGraph()
    t0 = 1_760_000_000  # 劇本基準時間

    # --- 第一幕：被害人於「限時加碼」話術下 50 分鐘內集中入金 ---
    # 12 名被害人 → 3 個客服收款地址（每個客服 ≥5 個不同來源 → fan-in）
    deposits: list[tuple[str, str, float, int]] = [
        # 客服一：V01–V05
        ("TVictim01", "TSupport01", 32_000, t0 + 0),
        ("TVictim02", "TSupport01", 18_500, t0 + 240),
        ("TVictim03", "TSupport01", 55_000, t0 + 480),
        ("TVictim04", "TSupport01", 27_000, t0 + 900),
        ("TVictim05", "TSupport01", 41_000, t0 + 1_200),
        # 客服二：V05–V09（V05 重複入金，跨客服）
        ("TVictim05", "TSupport02", 12_000, t0 + 300),
        ("TVictim06", "TSupport02", 63_000, t0 + 600),
        ("TVictim07", "TSupport02", 24_500, t0 + 1_000),
        ("TVictim08", "TSupport02", 38_000, t0 + 1_500),
        ("TVictim09", "TSupport02", 29_000, t0 + 1_800),
        # 客服三：V09–V12＋V01
        ("TVictim09", "TSupport03", 15_000, t0 + 700),
        ("TVictim10", "TSupport03", 47_000, t0 + 1_100),
        ("TVictim11", "TSupport03", 22_000, t0 + 1_600),
        ("TVictim12", "TSupport03", 35_000, t0 + 2_100),
        ("TVictim01", "TSupport03", 8_000, t0 + 2_400),
    ]
    for u, v, amount, ts in deposits:
        _add(g, u, v, float(amount), ts)

    # 部分被害人被誘導「直接匯入平台主帳戶」→ 主錢包 in-來源 ≥5（gather 條件）
    _add(g, "TVictim03", "TAggregator01", 20_000.0, t0 + 2_000)
    _add(g, "TVictim08", "TAggregator01", 16_000.0, t0 + 2_300)
    _add(g, "TVictim11", "TAggregator01", 9_000.0, t0 + 2_600)

    # --- 第二幕：客服層向集資主錢包歸集（placement → layering 交界） ---
    _add(g, "TSupport01", "TAggregator01", 173_500.0, t0 + 3_000)
    _add(g, "TSupport02", "TAggregator01", 166_500.0, t0 + 3_180)
    _add(g, "TSupport03", "TAggregator01", 127_000.0, t0 + 3_360)

    # --- 第三幕：主錢包 30 分鐘內拆分至 6 個車手（fan-out / gather-scatter） ---
    mule_amounts = [85_000.0, 84_000.0, 86_000.0, 83_000.0, 87_000.0, 85_000.0]
    for i, amount in enumerate(mule_amounts, start=1):
        _add(g, "TAggregator01", f"TMule{i:02d}", amount, t0 + 3_600 + i * 280)

    # --- 第四幕：分層——剝洋蔥鏈與直轉，最終整合至 OTC 出金地址 ---
    def peel_chain(start: str, base: float, ts: int, tag: str, sink: str) -> None:
        """自 start 起 3 跳剝洋蔥（每跳保留 90%），鏈尾整合至 sink。"""
        previous, amount = start, base
        for hop in range(3):
            nxt = f"TPeel{tag}{hop}"
            keep = amount * 0.9
            _add(g, previous, nxt, keep, ts + hop * 600)
            _add(g, previous, f"TSide{tag}{hop}", amount * 0.1, ts + hop * 600 + 60)
            previous, amount = nxt, keep
        _add(g, previous, sink, amount, ts + 3 * 600)

    peel_chain("TMule01", 85_000.0, t0 + 6_000, "A", WITHDRAWAL_TARGET)
    peel_chain("TMule02", 84_000.0, t0 + 6_300, "B", WITHDRAWAL_TARGET)
    # 車手三直轉 OTC → 形成主錢包至出金地址之「二階資金關聯」
    _add(g, "TMule03", WITHDRAWAL_TARGET, 86_000.0, t0 + 6_600)
    peel_chain("TMule04", 83_000.0, t0 + 6_900, "C", "TOtcOut02")
    _add(g, "TMule05", "TOtcOut02", 87_000.0, t0 + 7_200)
    peel_chain("TMule06", 85_000.0, t0 + 7_500, "D", "TOtcOut02")

    # --- 背景：正常交易（對照組，度數低於圖樣門檻，不應誤報） ---
    _add(g, "TShopA", "TShopB", 250.0, t0 + 500)
    _add(g, "TShopB", "TShopC", 120.0, t0 + 5_000)
    _add(g, "TShopC", "TShopA", 60.0, t0 + 9_000)
    _add(g, "THotWallet01", NORMAL_TARGET, 1_200.0, t0 + 4_000)
    _add(g, "THotWallet01", "TShopA", 800.0, t0 + 4_500)
    _add(g, NORMAL_TARGET, "TShopB", 300.0, t0 + 8_000)

    # --- 節點角色標註 ---
    roles: dict[str, str] = {}
    for node in g.nodes():
        name = str(node)
        if name.startswith("TVictim"):
            roles[node] = "victim"
        elif name.startswith("TSupport"):
            roles[node] = "support"
        elif name.startswith("TAggregator"):
            roles[node] = "aggregator"
        elif name.startswith("TMule"):
            roles[node] = "mule"
        elif name.startswith("TPeel"):
            roles[node] = "peel"
        elif name.startswith("TSide"):
            roles[node] = "peel_side"
        elif name.startswith("TOtcOut"):
            roles[node] = "otc"
        else:
            roles[node] = "normal"
    nx.set_node_attributes(g, roles, "role")

    g.graph.update(
        center="TAggregator01",
        withdrawal_target=WITHDRAWAL_TARGET,
        normal_target=NORMAL_TARGET,
        withdrawal_amount_usdt=WITHDRAWAL_AMOUNT_USDT,
        story_zh=(
            "交易所用戶申請將 50 萬 USDT 提領至外部地址 TOtcOut01。"
            "該地址從未被通報，但與假投資詐騙集資主錢包存在二階資金關聯。"
        ),
    )
    return g
