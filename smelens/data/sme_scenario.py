"""3,000 萬營運週轉金授信劇本圖（企劃書第一章招牌情境）。

劇本：「泰昇精密」向臺企銀申請 3,000 萬營運週轉金。財報表面健康——營收
成長、毛利穩定、無退票紀錄，依現行徵信流程會通過。但關係圖揭露三件財報
看不到的事：

1. **買方集中**：逾八成收入來自單一買方「鴻寶電子」，該買方抽單即斷炊。
2. **空殼過水**：資金經「宏益企業」流出，該公司流入 ≈ 流出、對手方僅各一，
   自身幾無留存，是典型代收轉付空殼。
3. **循環交易**：泰昇精密 → 宏益企業 → 昇泰貿易 → 泰昇投資 → 泰昇精密
   構成封閉資金環，疑似循環開票虛增營收。

對照組「禾昌五金」買方分散、資金留存正常、不在任何環上，用以演示本系統
不會對正常企業誤報——**能區辨才有價值，全部標紅等於沒有訊號**。

邊屬性：amount（新台幣元）、timestamp（Unix 秒）。
邊方向 u → v 表示 u 付款給 v。
"""

from __future__ import annotations

import networkx as nx

# 劇本角色 → 中文名稱（工作台 tooltip 與敘事用）
ROLE_ZH = {
    "applicant": "授信申請人",
    "anchor_buyer": "核心買方",
    "buyer": "一般買方",
    "shell": "空殼中介",
    "related": "關係人公司",
    "supplier": "供應商",
    "normal": "對照組正常企業",
}

CREDIT_APPLICANT = "泰昇精密"
NORMAL_APPLICANT = "禾昌五金"
APPLICATION_AMOUNT_TWD = 30_000_000.0

_STORY_ZH = (
    "泰昇精密申請 3,000 萬營運週轉金，財報健康、無退票；關係圖卻顯示其逾八成"
    "收入來自單一買方、資金經空殼中介過水，並與關係人構成封閉資金環。"
)

_T0 = 1_760_000_000  # 劇本基準時間


def _add(g: nx.DiGraph, u: str, v: str, amount: float, offset_days: int) -> None:
    """加一筆付款：u 付款給 v。offset_days 為距劇本基準時間的天數。"""
    g.add_edge(u, v, amount=amount, timestamp=_T0 + offset_days * 86_400)


def load_supply_chain_scenario() -> nx.DiGraph:
    """建構中小企業供應鏈授信劇本圖。"""
    g = nx.DiGraph()

    roles = {
        CREDIT_APPLICANT: "applicant",
        "鴻寶電子": "anchor_buyer",
        "中部機電": "buyer",
        "宏益企業": "shell",
        "昇泰貿易": "related",
        "泰昇投資": "related",
        NORMAL_APPLICANT: "normal",
        "大安工業": "buyer",
        "永康鋼鐵": "buyer",
        "南方塑膠": "buyer",
        "華隆貿易": "buyer",
    }
    for name, role in roles.items():
        g.add_node(name, role=role)

    # --- 第一幕：申請人的收入結構（總收入 31,400,000，單一買方佔 84%）---
    _add(g, "鴻寶電子", CREDIT_APPLICANT, 26_400_000.0, 0)
    _add(g, "中部機電", CREDIT_APPLICANT, 1_200_000.0, 5)

    # --- 第二幕：資金經空殼中介流出，再繞經關係人回到申請人（封閉環）---
    _add(g, CREDIT_APPLICANT, "宏益企業", 6_000_000.0, 10)
    _add(g, "宏益企業", "昇泰貿易", 5_940_000.0, 12)  # 過水比 99%
    _add(g, "昇泰貿易", "泰昇投資", 4_500_000.0, 20)
    _add(g, "泰昇投資", CREDIT_APPLICANT, 3_800_000.0, 28)  # 資金迴流，環長 4

    # --- 第三幕：對照組——買方分散、資金留存正常、不在任何環上 ---
    _add(g, "大安工業", NORMAL_APPLICANT, 3_000_000.0, 2)
    _add(g, "永康鋼鐵", NORMAL_APPLICANT, 2_800_000.0, 7)
    _add(g, "南方塑膠", NORMAL_APPLICANT, 2_600_000.0, 14)
    _add(g, "華隆貿易", NORMAL_APPLICANT, 2_400_000.0, 21)
    _add(g, NORMAL_APPLICANT, "中部機電", 4_000_000.0, 25)  # 留存 63%，非空殼

    g.graph["credit_applicant"] = CREDIT_APPLICANT
    g.graph["normal_applicant"] = NORMAL_APPLICANT
    g.graph["application_amount_twd"] = APPLICATION_AMOUNT_TWD
    g.graph["story_zh"] = _STORY_ZH
    return g
