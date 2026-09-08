"""FastAPI /score 端點測試（example 模式，不依賴網路與資料集）。"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smelens.api.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_score_example_mode() -> None:
    response = client.post("/score", json={"address": "TDemoAddress", "mode": "example"})
    assert response.status_code == 200
    body = response.json()
    assert 0.0 <= body["risk_score"] <= 1.0
    assert body["label"] in {"high", "medium", "low"}
    assert body["evidence"]
    assert body["evidence"][0]["narrative_zh"]
    assert body["evidence"][0]["motif_hits"]  # 範例圖中心必命中圖樣


def test_score_known_node_in_example_graph() -> None:
    response = client.post("/score", json={"address": "TShopA", "mode": "example"})
    assert response.status_code == 200
    assert response.json()["target"] == "TShopA"


def test_score_requires_target() -> None:
    response = client.post("/score", json={"mode": "example"})
    assert response.status_code in (400, 422)


def test_elliptic_mode_without_dataset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from smelens.api import main as api_main

    monkeypatch.setattr(api_main, "RAW_DIR", tmp_path / "empty")
    response = client.post("/score", json={"tx_id": "123", "mode": "elliptic"})
    assert response.status_code == 404  # 無資料集時應回 404 與說明


def test_tron_mode_rejects_invalid_address() -> None:
    response = client.post("/score", json={"address": "../../etc", "mode": "tron"})
    assert response.status_code == 400
    response = client.post("/score", json={"address": "TTooShort", "mode": "tron"})
    assert response.status_code == 400


def test_tron_fetch_failure_returns_502_not_example_graph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TronGrid 失敗必須回 502，不得靜默回傳內建範例圖的假高風險分數。"""
    import httpx

    from smelens.api import main as api_main

    def boom(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(api_main.tron, "fetch_two_hop_graph", boom)
    response = client.post(
        "/score",
        json={"address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", "mode": "tron"},
    )
    assert response.status_code == 502
    assert "TScamCollector001" not in response.text


def test_api_key_enforced_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SMELENS_API_KEY", "secret-key")
    body = {"address": "TDemoAddress", "mode": "example"}
    assert client.post("/score", json=body).status_code == 401
    ok = client.post("/score", json=body, headers={"X-API-Key": "secret-key"})
    assert ok.status_code == 200


def test_root_redirects_to_docs() -> None:
    """根路徑不應回 404：導向互動式 API 文件，讓瀏覽器訪客有落點。"""
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (307, 308)
    assert response.headers["location"] == "/docs"


def test_root_follows_through_to_docs() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


def test_favicon_no_content() -> None:
    """瀏覽器自動索取 favicon，回 204 避免無謂的 404 噪音。"""
    assert client.get("/favicon.ico").status_code == 204


def test_favicon_png_no_content() -> None:
    """瀏覽器亦會索取 /favicon.png，一併回 204。"""
    assert client.get("/favicon.png").status_code == 204
