"""ChainLens FastAPI 服務。

POST /score：輸入 TRON 地址或 Elliptic tx_id，回傳風險分數與結構證據。

curl 範例：
    curl -X POST http://localhost:8000/score \
      -H "Content-Type: application/json" \
      -d '{"address": "TXYZ...", "mode": "example"}'

啟動：uvicorn smelens.api.main:app --port 8000（或 make api）
OpenAPI 文件：http://localhost:8000/docs
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Any, Literal

import httpx
import networkx as nx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field, model_validator

from smelens.api.serialize import graph_to_json, sna_table
from smelens.data import elliptic, scenario, tron
from smelens.explain.evidence import PipelineResult, generate_evidence, run_pipeline
from smelens.explain.screening import screen_withdrawal

load_dotenv()  # 讀取 .env（TRONGRID_API_KEY / SMELENS_API_KEY）

app = FastAPI(
    title="SME Lens API",
    description="中小企業關係網絡風控：授信意見書、集團歸戶與結構證據",
    version="0.1.0",
)


def _cors_origins() -> list[str]:
    """允許來源清單；未設定環境變數時全開。"""
    raw = os.getenv("SMELENS_CORS_ORIGINS", "*")
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


# allow_credentials 必須為 False：瀏覽器規範不允許它與 allow_origins=["*"] 併用，
# 且本 API 不使用 cookie，僅選配的 X-API-Key 標頭。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-API-Key"],
)

RAW_DIR = Path("data/raw")

# elliptic 模式全圖與管線結果快取（203k 節點載入＋SNA 需數分鐘，絕不可每請求重算）
_elliptic_cache: dict[str, tuple[nx.DiGraph, PipelineResult]] = {}


def _check_api_key(x_api_key: str | None) -> None:
    """設定 SMELENS_API_KEY 環境變數時，要求請求帶相同的 X-API-Key 標頭。"""
    expected = os.getenv("SMELENS_API_KEY")
    if expected and not (x_api_key and secrets.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="X-API-Key 缺少或不正確")


class ScoreRequest(BaseModel):
    """評分請求：TRON 模式吃 address、Elliptic 模式吃 tx_id。

    mode=auto 時依提供的欄位自動判斷；mode=example 使用內建離線範例圖。
    """

    address: str | None = Field(default=None, max_length=64)
    tx_id: str | None = Field(default=None, max_length=32)
    mode: Literal["auto", "tron", "elliptic", "example"] = "auto"

    @model_validator(mode="after")
    def _require_target(self) -> ScoreRequest:
        if not self.address and not self.tx_id:
            raise ValueError("address 與 tx_id 至少需提供一項")
        return self


class ScreenRequest(BaseModel):
    """出金審查請求：目標地址限定為劇本情境中的兩個地址。"""

    target: str = Field(max_length=64)
    amount_usdt: float = Field(gt=0)
    request_id: str | None = Field(default=None, max_length=64)


class GraphRequest(BaseModel):
    """工作台圖譜請求：內建範例圖，或 TronGrid 即時抓取的 2-hop 真實圖。"""

    mode: Literal["example", "tron"] = "example"
    address: str | None = Field(default=None, max_length=64)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """本服務為純 API，無前端頁面；根路徑導向互動式文件供瀏覽器訪客試打。"""
    return RedirectResponse("/docs")


@app.get("/favicon.ico", include_in_schema=False)
@app.get("/favicon.png", include_in_schema=False)
def favicon() -> Response:
    """瀏覽器會自動索取 favicon（.ico 與 .png 皆會試），回 204 避免 log 充斥無意義的 404。"""
    return Response(status_code=204)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def _evidences_for(
    g: nx.DiGraph,
    sna_df: Any,
    partition: dict[Any, int],
    risk_ratios: dict[int, float],
    motif_hits: list[Any],
) -> dict[Any, dict[str, Any]]:
    """全節點證據，供圖譜著色與節點面板使用。"""
    return {
        node: generate_evidence(node, g, sna_df, partition, risk_ratios, motif_hits)
        for node in g.nodes()
    }


@app.post("/screen")
def screen(req: ScreenRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """出金審查：回傳決策、關聯證據鏈、金流圖譜與 STR 草稿。"""
    _check_api_key(x_api_key)
    allowed = {scenario.WITHDRAWAL_TARGET, scenario.NORMAL_TARGET}
    if req.target not in allowed:
        raise HTTPException(status_code=400, detail="target 需為劇本情境中的出金地址")

    g = scenario.load_withdrawal_scenario()
    pipeline: PipelineResult = run_pipeline(g)
    sna_df, partition, risk_ratios, motif_hits = pipeline

    result = screen_withdrawal(
        g, req.target, req.amount_usdt, request_id=req.request_id, pipeline=pipeline
    )
    result["graph"] = graph_to_json(
        g,
        _evidences_for(g, sna_df, partition, risk_ratios, motif_hits),
        sna_df,
        motif_centers={hit.center for hit in motif_hits},
    )
    associations = result["associations"]
    result["highlight_path"] = (
        [str(node) for node in associations[0]["path"]] if associations else []
    )
    return result


@app.post("/graph")
def graph(req: GraphRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """工作台圖譜：回傳節點、邊、meta 與依風險排序的 SNA 指標表。"""
    _check_api_key(x_api_key)

    if req.mode == "example":
        g = tron.load_example_graph()
    else:
        if not req.address:
            raise HTTPException(status_code=400, detail="tron 模式需提供 address")
        if not tron.is_valid_tron_address(req.address):
            raise HTTPException(
                status_code=400,
                detail="address 需為合法 TRON 主網地址（T 開頭 Base58 34 字元）",
            )
        try:
            g = tron.fetch_two_hop_graph(req.address, api_key=os.getenv("TRONGRID_API_KEY"))
        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502, detail=f"TronGrid 抓取失敗：{exc.__class__.__name__}"
            ) from exc
        if g.number_of_nodes() == 0:
            raise HTTPException(status_code=404, detail=f"地址 {req.address} 查無 USDT 轉帳")

    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    evidences = _evidences_for(g, sna_df, partition, risk_ratios, motif_hits)
    payload = graph_to_json(
        g, evidences, sna_df, motif_centers={hit.center for hit in motif_hits}
    )
    payload["sna"] = sna_table(sna_df, evidences)
    return payload


def _build_graph(req: ScoreRequest) -> tuple[nx.DiGraph, Any]:
    """依請求模式建圖，回傳（圖, 目標節點）。"""
    mode = req.mode
    if mode == "auto":
        mode = "tron" if req.address else "elliptic"

    if mode == "example":
        g = tron.load_example_graph()
        target = req.address if req.address in g else g.graph["center"]
        return g, target

    if mode == "tron":
        if not req.address:
            raise HTTPException(status_code=400, detail="tron 模式需提供 address")
        if not tron.is_valid_tron_address(req.address):
            raise HTTPException(
                status_code=400, detail="address 需為合法 TRON 主網地址（T 開頭 Base58 34 字元）"
            )
        try:
            g = tron.fetch_two_hop_graph(req.address, api_key=os.getenv("TRONGRID_API_KEY"))
        except httpx.HTTPError as exc:
            # 明確回報上游失敗，絕不可靜默改用內建範例圖誤導呼叫端
            raise HTTPException(
                status_code=502, detail=f"TronGrid 抓取失敗：{exc.__class__.__name__}"
            ) from exc
        if req.address not in g:
            raise HTTPException(status_code=404, detail=f"地址 {req.address} 查無 USDT 轉帳")
        return g, req.address

    # elliptic 模式
    if not req.tx_id:
        raise HTTPException(status_code=400, detail="elliptic 模式需提供 tx_id")
    try:
        tx = int(req.tx_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="tx_id 需為整數") from exc
    if not elliptic.raw_files_exist(RAW_DIR):
        raise HTTPException(
            status_code=404,
            detail="data/raw 缺少 Elliptic 資料集，請先執行 make download-data",
        )
    g, _ = _elliptic_graph_and_pipeline()
    if tx not in g:
        raise HTTPException(status_code=404, detail=f"tx_id {tx} 不在資料集中")
    return g, tx


def _elliptic_graph_and_pipeline() -> tuple[nx.DiGraph, PipelineResult]:
    """載入 Elliptic 全圖並跑分析管線，結果依 RAW_DIR 快取於行程內。"""
    key = str(Path(RAW_DIR).resolve())
    if key not in _elliptic_cache:
        g = elliptic.load_elliptic_graph(RAW_DIR, include_features=False)
        _elliptic_cache[key] = (g, run_pipeline(g))
    return _elliptic_cache[key]


@app.post("/score")
def score(req: ScoreRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """對目標地址/交易評分，回傳 risk_score、label 與結構證據。"""
    _check_api_key(x_api_key)
    g, target = _build_graph(req)
    if req.mode == "elliptic" or (req.mode == "auto" and not req.address):
        _, pipeline = _elliptic_graph_and_pipeline()  # 命中快取，不重算
        sna_df, partition, risk_ratios, motif_hits = pipeline
    else:
        sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    evidence = generate_evidence(target, g, sna_df, partition, risk_ratios, motif_hits)
    return {
        "target": str(target),
        "risk_score": evidence["score"],
        "label": evidence["label"],
        "evidence": [evidence],
    }
