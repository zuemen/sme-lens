"""TRON 抓取器測試：mock 網路層，不打真實 API。"""

from pathlib import Path

import pytest

from smelens.data import tron
from smelens.sna.motifs import detect_all


def test_parse_transfers() -> None:
    payload = {
        "data": [
            {
                "transaction_id": "abc123",
                "from": "TAlice",
                "to": "TBob",
                "value": "12500000",
                "block_timestamp": 1750000000000,
                "token_info": {"symbol": "USDT", "decimals": 6},
            },
            # 格式錯誤的紀錄應被略過
            {"from": "TBob", "to": "TCarol", "value": "bad", "block_timestamp": 1},
        ]
    }
    assert tron._parse_transfers(payload) == [
        {
            "tx_id": "abc123",
            "from": "TAlice",
            "to": "TBob",
            "amount": 12.5,
            "timestamp": 1750000000,
        }
    ]


def test_two_hop_dedupes_overlapping_transfers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """center 與 neighbor 的回應含同一筆轉帳：金額不得重複累計（灌水 2 倍 bug）。"""
    shared = {"tx_id": "t1", "from": "TCenter", "to": "TPeer", "amount": 10.0, "timestamp": 100}

    def fake_fetch(address: str, api_key: str | None, client: object) -> list[dict]:
        return [dict(shared)]  # 兩個地址的回應都包含同一筆 tx

    monkeypatch.setattr(tron, "_fetch_transfers", fake_fetch)
    g = tron.fetch_two_hop_graph("TCenter", cache_dir=tmp_path)
    assert g["TCenter"]["TPeer"]["amount"] == 10.0  # 而非 20.0


def test_fetch_rejects_unsafe_address(tmp_path: Path) -> None:
    """address 直接進快取檔名與 URL：非英數字元（路徑穿越/注入）必須拒絕。"""
    for bad in ["../../evil", "T123/..", "a?b=c", ""]:
        with pytest.raises(ValueError):
            tron.fetch_two_hop_graph(bad, cache_dir=tmp_path)


def test_is_valid_tron_address() -> None:
    assert tron.is_valid_tron_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t")
    assert not tron.is_valid_tron_address("TShort")
    assert not tron.is_valid_tron_address("0x52908400098527886E0F7030069857D2E4169EE7")
    assert not tron.is_valid_tron_address("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLjOO")  # 含 O 非 Base58


def test_build_graph_aggregates_parallel_edges() -> None:
    transfers = [
        {"from": "a", "to": "b", "amount": 1.0, "timestamp": 100},
        {"from": "a", "to": "b", "amount": 2.0, "timestamp": 50},
    ]
    g = tron.build_graph_from_transfers(transfers)
    assert g["a"]["b"]["amount"] == 3.0
    assert g["a"]["b"]["timestamp"] == 50


def test_example_graph_contains_motifs() -> None:
    g = tron.load_example_graph()
    assert g.number_of_nodes() > 10
    assert g.graph["center"] in g
    kinds = {h.motif for h in detect_all(g)}
    assert {"fan_in", "fan_out", "peeling_chain"} <= kinds


def test_cache_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(address: str, api_key: str | None, client: object) -> list[dict]:
        calls.append(address)
        return [{"from": address, "to": "TPeer", "amount": 1.0, "timestamp": 100}]

    monkeypatch.setattr(tron, "_fetch_transfers", fake_fetch)
    g1 = tron.fetch_two_hop_graph("TCenter", cache_dir=tmp_path)
    assert calls == ["TCenter", "TPeer"]  # 中心 + 1 個對手方

    g2 = tron.fetch_two_hop_graph("TCenter", cache_dir=tmp_path)
    assert calls == ["TCenter", "TPeer"]  # 第二次走快取，不再打網路
    assert set(g1.edges()) == set(g2.edges())
    assert g2.graph["center"] == "TCenter"
