"""授信與集團歸戶 API 測試。"""

from __future__ import annotations

from fastapi.testclient import TestClient

import smelens.api.main as main_module
from smelens.api import serialize
from smelens.api.main import app
from smelens.data.sme_scenario import CREDIT_APPLICANT, NORMAL_APPLICANT

client = TestClient(app)


def test_credit_endpoint_returns_opinion_with_graph():
    """授信意見書須含分數、敘事、建議與可繪製的圖譜。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == CREDIT_APPLICANT
    assert body["label"] in {"watch", "caution", "normal"}
    assert body["recommendation_zh"]
    assert body["narrative_zh"]
    assert body["graph"]["nodes"]
    assert body["graph"]["edges"]


def test_credit_graph_nodes_carry_real_scores():
    """圖譜節點的 score 必須是真實關注分數，不得整張圖靜默染成 0。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    nodes = response.json()["graph"]["nodes"]
    scores = [node["score"] for node in nodes]

    assert max(scores) > 0.0
    assert len(set(scores)) > 1, "所有節點同分代表著色欄位沒接上"


def test_credit_graph_nodes_carry_chinese_roles():
    """企金角色必須中文化，不得回退成英文鍵。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    nodes = {node["id"]: node for node in response.json()["graph"]["nodes"]}

    assert nodes[CREDIT_APPLICANT]["role"] == "applicant"
    assert nodes[CREDIT_APPLICANT]["role_zh"] == "授信申請人"


def test_credit_endpoint_rejects_unknown_company():
    """查無此公司應回 404，不得靜默回傳空意見書。"""
    response = client.post("/credit", json={"target": "查無此公司"})

    assert response.status_code == 404


def test_credit_endpoint_normal_company_is_not_watch():
    """對照組不得被列為關注。"""
    response = client.post("/credit", json={"target": NORMAL_APPLICANT})

    assert response.json()["label"] != "watch"


def test_group_endpoint_returns_groups_and_hidden_links():
    """集團歸戶須回傳歸戶結果、集團曝險與隱性關聯。"""
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
                {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
                {"company": "昇泰貿易", "person": "王秀英", "role": "董事"},
                {"company": "泰昇投資", "person": "王秀英", "role": "監察人"},
                {"company": "禾昌五金", "person": "林志豪", "role": "董事長"},
            ],
            "declared_groups": {
                "泰昇精密": "泰昇集團",
                "泰昇投資": "泰昇集團",
                "昇泰貿易": "昇泰集團",
            },
            "exposures": {"泰昇精密": 30_000_000, "泰昇投資": 12_000_000},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["groups"]["泰昇精密"] == body["groups"]["昇泰貿易"]
    assert body["groups"]["禾昌五金"] != body["groups"]["泰昇精密"]
    assert sum(body["exposures"].values()) == 42_000_000
    assert len(body["hidden_links"]) == 1
    assert body["hidden_links"][0]["shared_persons"] == ["王秀英"]


def test_group_endpoint_reports_unattributed_exposure():
    """名冊上沒有的公司，其曝險不得靜默消失——必須列名回報。"""
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
                {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
            ],
            "exposures": {"泰昇精密": 30_000_000, "查無此公司": 8_000_000},
        },
    )

    body = response.json()
    assert body["unattributed"] == ["查無此公司"]
    assert sum(body["exposures"].values()) == 30_000_000


def test_group_endpoint_bounds_hidden_links_payload():
    """500 家公司共用一名董事是合法名冊，但完整隱性關聯有 124,750 筆。

    回應必須被截斷在合理大小內，同時誠實回報 hidden_links_total 與
    truncated，不得讓回應看起來只找到這麼多筆。
    """
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": f"C{i}", "person": "共用董事"} for i in range(500)
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["hidden_links"]) == 200
    assert body["hidden_links_total"] == 124_750
    assert body["truncated"] is True
    # 回應本體應遠低於未截斷時的 16MB+。
    assert len(response.content) < 1_000_000


def test_group_endpoint_reports_untruncated_when_small():
    """未超過截斷上限時，truncated 應誠實回報 False，total 與清單長度一致。"""
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
                {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
                {"company": "昇泰貿易", "person": "王秀英", "role": "董事"},
                {"company": "泰昇投資", "person": "王秀英", "role": "監察人"},
            ],
        },
    )

    body = response.json()
    assert body["truncated"] is False
    assert body["hidden_links_total"] == len(body["hidden_links"])


def test_group_endpoint_rejects_empty_affiliations():
    """空名冊無從歸戶，應回 400。"""
    response = client.post("/group", json={"affiliations": []})

    assert response.status_code == 400


def test_credit_endpoint_keeps_target_when_graph_truncated(monkeypatch):
    """授信對象即使分數不夠高，也不得被截斷邏輯排除在附圖之外。

    劇本圖本身節點數低於 MAX_GRAPH_NODES，故以極小的 limit 強制觸發截斷，
    驗證 /credit 傳入的 keep={req.target} 生效。
    """
    monkeypatch.setattr(
        main_module,
        "graph_to_json",
        lambda *args, **kwargs: serialize.graph_to_json(*args, **{**kwargs, "limit": 2}),
    )

    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    assert response.status_code == 200
    body = response.json()
    assert body["graph"]["meta"]["truncated"] is True
    ids = {n["id"] for n in body["graph"]["nodes"]}
    assert CREDIT_APPLICANT in ids


def test_credit_graph_labels_use_frontend_vocabulary():
    """圖譜節點的 label 必須是前端 RiskLabel 認得的 high/medium/low，頂層仍為 watch。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    body = response.json()
    assert body["label"] == "watch"
    assert {node["label"] for node in body["graph"]["nodes"]} <= {"high", "medium", "low"}


def test_credit_graph_target_narrative_matches_top_level():
    """同一家公司在同一個回應裡不得出現兩份不同的敘事。"""
    response = client.post(
        "/credit",
        json={"target": CREDIT_APPLICANT, "group_id": 0, "group_exposure_twd": 50000000},
    )

    body = response.json()
    target_node = next(n for n in body["graph"]["nodes"] if n["id"] == CREDIT_APPLICANT)
    assert target_node["narrative_zh"] == body["narrative_zh"]
    assert "歸戶集團編號 #0" in target_node["narrative_zh"]


def test_credit_rejects_non_finite_exposure():
    """NaN／Infinity 的曝險金額必須當場擋下，不能寫進授信意見書。"""
    for bad in ("NaN", "Infinity", "-Infinity"):
        response = client.post(
            "/credit",
            content=f'{{"target": "泰昇精密", "group_id": 1, "group_exposure_twd": {bad}}}',
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422, bad


def test_credit_rejects_negative_exposure_and_group_id():
    """負數曝險與負數集團編號在金融語意上不成立。"""
    assert client.post(
        "/credit", json={"target": "泰昇精密", "group_exposure_twd": -1}
    ).status_code == 422
    assert client.post("/credit", json={"target": "泰昇精密", "group_id": -1}).status_code == 422


def test_group_unattributed_respects_name_normalisation():
    """曝險名稱多打一個空白，不得被誤報為「不在名冊中」。"""
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": "甲公司", "person": "王小明"},
                {"company": "乙公司", "person": "王小明"},
            ],
            "exposures": {"甲公司 ": 1_000_000, "查無此公司": 500_000},
        },
    )

    body = response.json()
    assert body["unattributed"] == ["查無此公司"]


def test_group_rejects_oversized_roster():
    """名冊筆數需設上限：build_company_graph 對共用同一人的公司是 O(n²)。"""
    response = client.post(
        "/group",
        json={"affiliations": [{"company": f"C{i}", "person": "P"} for i in range(501)]},
    )

    assert response.status_code == 422
