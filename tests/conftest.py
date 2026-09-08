"""共用 fixture：小型合成詐騙圖，含三種圖樣與一小群正常節點。"""

import networkx as nx
import pytest


@pytest.fixture
def scam_graph() -> nx.DiGraph:
    """合成詐騙金流圖。

    - fan-in：src0..src7 於 7 分鐘內匯入 collector（集資）
    - fan-out：hub 於 250 秒內拆分至 out0..out5（分散）
    - peeling chain：p0→p1→p2→p3→p4，每跳保留 90% 轉出＋10% 剝離至 peelN
    - 正常小圈：n0→n1→n2→n0
    """
    g = nx.DiGraph()
    t0 = 1_700_000_000
    for i in range(8):
        g.add_edge(f"src{i}", "collector", amount=100.0, timestamp=t0 + i * 60)
    g.add_edge("collector", "hub", amount=800.0, timestamp=t0 + 700)
    for i in range(6):
        g.add_edge("hub", f"out{i}", amount=130.0, timestamp=t0 + 800 + i * 50)

    g.add_edge("funder", "p0", amount=1000.0, timestamp=t0)
    amounts = [900.0, 810.0, 729.0, 656.1]
    for i, amt in enumerate(amounts):
        g.add_edge(f"p{i}", f"p{i + 1}", amount=amt, timestamp=t0 + (i + 1) * 120)
        g.add_edge(f"p{i}", f"peel{i}", amount=amt / 9, timestamp=t0 + (i + 1) * 120 + 10)

    g.add_edge("n0", "n1", amount=10.0, timestamp=t0)
    g.add_edge("n1", "n2", amount=5.0, timestamp=t0 + 100)
    g.add_edge("n2", "n0", amount=2.0, timestamp=t0 + 200)
    return g
