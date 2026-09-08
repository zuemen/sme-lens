"""TronGrid TRC-20 USDT 轉帳抓取器：以指定地址為中心建 2-hop 金流圖。

- API key 讀環境變數 TRONGRID_API_KEY；無 key 時降級為匿名限速模式（每請求延遲）
- 回應 JSON 快取於 data/cache/，離線或重複查詢直接讀快取
- 無網路時可改用 load_example_graph() 內建範例圖
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx
import networkx as nx

USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"  # TRON 主網 USDT
BASE_URL = "https://api.trongrid.io/v1/accounts/{address}/transactions/trc20"
ANON_DELAY_SECONDS = 0.5  # 無 API key 時的匿名限速延遲
# 快取目錄可經 SMELENS_CACHE_DIR 覆寫（serverless 需指向可寫的 /tmp）
DEFAULT_CACHE_DIR = Path(os.getenv("SMELENS_CACHE_DIR", "data/cache"))
DEFAULT_CACHE_TTL_SECONDS = 24 * 3600  # 鏈上金流持續變動，快取一天後過期重抓
CACHE_FORMAT_VERSION = 2  # v2 起帶 tx_id 以去重；舊格式快取一律視為失效

# TRON 主網地址：T 開頭 Base58（34 字元）
TRON_ADDRESS_RE = re.compile(r"^T[1-9A-HJ-NP-Za-km-z]{33}$")
# 快取檔名/URL 安全字元：僅允許英數，杜絕路徑穿越與 URL 注入
_SAFE_ADDRESS_RE = re.compile(r"^[A-Za-z0-9]+$")


def is_valid_tron_address(address: str) -> bool:
    """是否為合法 TRON 主網地址格式。"""
    return bool(TRON_ADDRESS_RE.match(address))


def _parse_transfers(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """TronGrid trc20 回應 → 標準化轉帳列表（金額換算小數、時間戳 ms→s）。"""
    transfers: list[dict[str, Any]] = []
    for item in payload.get("data", []):
        token = item.get("token_info") or {}
        try:
            decimals = int(token.get("decimals", 6))
            transfers.append(
                {
                    "tx_id": item.get("transaction_id"),  # 供跨地址抓取去重
                    "from": item["from"],
                    "to": item["to"],
                    "amount": int(item["value"]) / 10**decimals,
                    "timestamp": int(item["block_timestamp"]) // 1000,
                }
            )
        except (KeyError, TypeError, ValueError):
            continue  # 略過缺欄位或格式錯誤的紀錄
    return transfers


def _dedupe_transfers(transfers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去除跨地址抓取的重複轉帳（center↔neighbor 的同一筆會出現在兩邊的回應）。

    有 tx_id 用 tx_id；缺 tx_id 時退回 (from, to, amount, timestamp) 四元組。
    """
    seen: set[Any] = set()
    unique: list[dict[str, Any]] = []
    for t in transfers:
        key = t.get("tx_id") or (t["from"], t["to"], t["amount"], t["timestamp"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(t)
    return unique


def _fetch_transfers(
    address: str, api_key: str | None, client: httpx.Client
) -> list[dict[str, Any]]:
    """抓取單一地址的 TRC-20 USDT 轉帳（單頁，最多 200 筆）。"""
    headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}
    if not api_key:
        time.sleep(ANON_DELAY_SECONDS)
    response = client.get(
        BASE_URL.format(address=address),
        params={"only_confirmed": "true", "limit": 200, "contract_address": USDT_CONTRACT},
        headers=headers,
        timeout=15.0,
    )
    response.raise_for_status()
    return _parse_transfers(response.json())


def build_graph_from_transfers(transfers: list[dict[str, Any]]) -> nx.DiGraph:
    """轉帳列表 → 有向圖；平行轉帳聚合為單邊（金額加總、取最早時間戳）。"""
    g = nx.DiGraph()
    for t in transfers:
        u, v = t["from"], t["to"]
        if g.has_edge(u, v):
            data = g[u][v]
            data["amount"] += t["amount"]
            data["timestamp"] = min(data["timestamp"], t["timestamp"])
        else:
            g.add_edge(u, v, amount=t["amount"], timestamp=t["timestamp"])
    return g


def _read_cache(cache_file: Path, ttl_seconds: float) -> list[dict[str, Any]] | None:
    """讀取快取；過期、舊格式（無版本標記）或損毀時回 None 觸發重抓。"""
    if not cache_file.exists():
        return None
    if time.time() - cache_file.stat().st_mtime > ttl_seconds:
        return None
    try:
        payload = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("version") != CACHE_FORMAT_VERSION:
        return None  # v1 舊快取帶有重複轉帳（金額灌水），一律失效
    return payload.get("transfers", [])


def fetch_two_hop_graph(
    address: str,
    api_key: str | None = None,
    cache_dir: Path | None = DEFAULT_CACHE_DIR,
    max_neighbors: int = 8,
    cache_ttl_seconds: float = DEFAULT_CACHE_TTL_SECONDS,
) -> nx.DiGraph:
    """以 address 為中心抓取 2-hop USDT 金流圖（對手方最多 max_neighbors 個）。

    address 僅允許英數字元（快取檔名與 URL 皆直接使用，防路徑穿越/注入）；
    API/前端入口應另以 is_valid_tron_address 做完整格式驗證。
    """
    if not _SAFE_ADDRESS_RE.match(address):
        raise ValueError(f"地址含非法字元：{address!r}")
    cache_file = cache_dir / f"{address}_2hop.json" if cache_dir else None
    transfers = _read_cache(cache_file, cache_ttl_seconds) if cache_file else None
    if transfers is None:
        with httpx.Client() as client:
            transfers = _fetch_transfers(address, api_key, client)
            neighbors: list[str] = []
            for t in transfers:
                peer = t["to"] if t["from"] == address else t["from"]
                if peer != address and peer not in neighbors:
                    neighbors.append(peer)
            for peer in neighbors[:max_neighbors]:
                transfers.extend(_fetch_transfers(peer, api_key, client))
        transfers = _dedupe_transfers(transfers)
        if cache_file:
            # 快取為選配加速；唯讀檔案系統（如 Vercel serverless，除 /tmp 外唯讀）
            # 寫入失敗不應中斷評分，靜默略過即可
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(
                    json.dumps(
                        {"version": CACHE_FORMAT_VERSION, "transfers": transfers},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            except OSError:
                pass
    g = build_graph_from_transfers(transfers)
    g.graph["center"] = address
    return g


def load_example_graph() -> nx.DiGraph:
    """內建離線範例圖：含集資扇入、快速分散與剝洋蔥鏈三種圖樣＋正常交易背景。"""
    g = nx.DiGraph()
    t0 = 1_750_000_000
    center = "TScamCollector001"
    for i in range(8):
        g.add_edge(f"TVictim{i:02d}", center, amount=500.0 + i * 40, timestamp=t0 + i * 90)
    hub = "TLaunderHub001"
    g.add_edge(center, hub, amount=3800.0, timestamp=t0 + 900)
    for i in range(6):
        g.add_edge(hub, f"TMule{i:02d}", amount=600.0, timestamp=t0 + 1000 + i * 40)
    # 剝洋蔥鏈：自 TMule00 起，每跳保留 90% 轉出＋10% 剝離
    previous = "TMule00"
    for i, amount in enumerate([540.0, 486.0, 437.4]):
        nxt = f"TPeel{i:02d}"
        g.add_edge(previous, nxt, amount=amount, timestamp=t0 + 1400 + i * 120)
        g.add_edge(previous, f"TSide{i:02d}", amount=amount / 9, timestamp=t0 + 1410 + i * 120)
        previous = nxt
    # 正常交易背景
    g.add_edge("TShopA", "TShopB", amount=25.0, timestamp=t0 + 50)
    g.add_edge("TShopB", "TShopC", amount=12.5, timestamp=t0 + 500)
    g.graph["center"] = center
    return g
