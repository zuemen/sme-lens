"""SME Lens FastAPI 服務。

企金授信分支：
    POST /credit：輸入企業名稱，回傳授信意見書（網絡信用分、關注分數、
                  結構證據、中文敘事、建議與關係圖譜）。
    POST /group ：輸入公司—自然人名冊，回傳集團歸戶、各集團曝險，
                  以及客戶未申報的隱性關聯。

科技防詐分支（沿用自 ChainLens）：
    POST /score 、/screen、/graph：虛擬資產詐騙金流風險評分與出金審查。

curl 範例：
    curl -X POST http://localhost:8000/credit \
      -H "Content-Type: application/json" \
      -d '{"target": "泰昇精密"}'

啟動：./.venv/Scripts/python.exe -m uvicorn smelens.api.main:app --port 8000
OpenAPI 文件：http://localhost:8000/docs
"""

from __future__ import annotations

import math
import os
import secrets
from pathlib import Path
from typing import Any, Literal

import httpx
import networkx as nx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from smelens.api.serialize import graph_to_json, sna_table
from smelens.credit.group import (
    DEFAULT_HIDDEN_LINKS_LIMIT,
    Affiliation,
    build_company_graph,
    detect_groups,
    group_exposure,
    hidden_links,
    normalise_name,
)
from smelens.credit.opinion import generate_credit_opinion, run_sme_pipeline
from smelens.data import elliptic, scenario, sme_scenario, tron
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

@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422 回應需先消毒非有限浮點數，理由見 `_sanitize_for_json`。"""
    return JSONResponse(
        status_code=422,
        content={"detail": _sanitize_for_json(jsonable_encoder(exc.errors()))},
    )


RAW_DIR = Path("data/raw")

# elliptic 模式全圖與管線結果快取（203k 節點載入＋SNA 需數分鐘，絕不可每請求重算）
_elliptic_cache: dict[str, tuple[nx.DiGraph, PipelineResult]] = {}

# graph_to_json 與前端 RiskLabel 用的是 high/medium/low；授信意見書用 watch/caution/
# normal。兩邊都有 .get 預設值，漏接不會拋錯、只會靜默吐出前端不認得的標籤。
_GRAPH_LABEL_ZH = {"watch": "high", "caution": "medium", "normal": "low"}


def _sanitize_for_json(value: Any) -> Any:
    """遞迴把非有限浮點數（NaN／±Infinity）換成字串。

    這類值正是本 API 要擋下的輸入（例如 group_exposure_twd=NaN），但 pydantic
    的驗證錯誤內容會原封不動帶回這個輸入值；Starlette 的 JSONResponse 預設
    `allow_nan=False`，序列化時會直接丟出 ValueError，讓本該回 422 的請求
    變成 500——比完全不擋還糟。故渲染錯誤內容前先行消毒。
    """
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    return value


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
    associations = result["associations"]
    highlight_path = associations[0]["path"] if associations else []
    result["highlight_path"] = [str(node) for node in highlight_path]
    # keep：出金目標與其 highlight_path 上的節點無論分數高低都不得被截斷邏輯
    # 丟掉——否則回應會帶著一條引用不存在節點的高亮路徑，前端渲染不出來，
    # 而 highlight_path 正是這支端點的招牌展演。
    result["graph"] = graph_to_json(
        g,
        _evidences_for(g, sna_df, partition, risk_ratios, motif_hits),
        sna_df,
        motif_centers={hit.center for hit in motif_hits},
        keep={req.target, *highlight_path},
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
        if req.address is not None:
            # 呼叫端明確指定了地址：不在範例圖中就必須誠實回 404，絕不可靜默改答
            # 另一個地址的分數——tron 分支在同樣情境下已是這樣做，example 模式
            # 沒有理由是唯一說謊的分支。
            if req.address not in g:
                raise HTTPException(
                    status_code=404, detail=f"地址 {req.address} 不在範例圖中"
                )
            return g, req.address
        # 未提供地址時才回退到範例圖中心，這是「請給我一個範例」的請求，不是
        # 「請回答關於這個地址的問題」。
        return g, g.graph["center"]

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


class CreditRequest(BaseModel):
    """授信意見書請求：target 為劇本圖中的企業名稱。"""

    target: str = Field(description="授信對象企業名稱", max_length=128)
    group_id: int | None = Field(default=None, ge=0, description="歸戶集團編號（選配）")
    group_exposure_twd: float | None = Field(
        default=None, ge=0, description="該集團授信曝險合計（新台幣元，選配）"
    )

    @field_validator("group_exposure_twd")
    @classmethod
    def _finite_exposure(cls, v: float | None) -> float | None:
        # ge=0 擋得掉負數與 NaN（NaN 的比較一律為 False），但擋不掉 +Infinity。
        # 放行的話，授信意見書會出現「合計 inf 元」而同一個回應的 JSON 欄位卻是 null。
        if v is not None and not math.isfinite(v):
            raise ValueError("group_exposure_twd 需為有限數值")
        return v


class AffiliationInput(BaseModel):
    """一筆公司—自然人關係。

    company_id（公司統一編號）與 person_id（自然人識別碼）皆為選填，一旦提供
    即為歸戶依據，優先於名稱字串——見 smelens.credit.group.Affiliation 的
    docstring：名稱比對抓不出「同名不同人」也擋不住「同人換名」，identifier 才行。
    """

    company: str
    person: str
    role: str = "董監事"
    company_id: str | None = None
    person_id: str | None = None


class GroupRequest(BaseModel):
    """集團歸戶請求。"""

    # 測得單一共用同一人的名冊：500 筆 0.63 秒、1500 筆 9.0 秒、3000 筆 50 秒——
    # build_company_graph 對共用同一人的公司數是 O(n²)（combinations 逐對建邊）。
    # 沒有上限的話，一份異常大的名冊就能讓 worker 卡住將近一分鐘。
    affiliations: list[AffiliationInput] = Field(
        description="公司—自然人關係名冊", max_length=500
    )
    declared_groups: dict[str, str] = Field(
        default_factory=dict, description="客戶自行申報的集團代號"
    )
    exposures: dict[str, float] = Field(
        default_factory=dict, description="各公司授信餘額（新台幣元）"
    )

    @field_validator("exposures")
    @classmethod
    def _finite_exposures(cls, v: dict[str, float]) -> dict[str, float]:
        # 單一非有限值會讓整個集團加總變成 NaN，序列化後靜默成 null——
        # 對銀行而言那是「曝險不明」而不是「輸入有誤」，必須當場擋下。
        for company, amount in v.items():
            if not math.isfinite(amount) or amount < 0:
                raise ValueError(f"{company} 的曝險金額需為非負的有限數值")
        return v


@app.post("/credit")
def credit(req: CreditRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """授信意見書：回傳網絡信用分、關注分數、結構證據、中文敘事與圖譜。"""
    _check_api_key(x_api_key)
    g = sme_scenario.load_supply_chain_scenario()
    if req.target not in g:
        raise HTTPException(status_code=404, detail=f"企業 {req.target} 不在關係圖中")

    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)
    opinion = generate_credit_opinion(
        req.target,
        g,
        sna_df,
        partition,
        risk_ratios,
        motif_hits,
        group_id=req.group_id,
        group_exposure_twd=req.group_exposure_twd,
    )
    evidences: dict[Any, dict[str, Any]] = {}
    for node in g.nodes():
        item = dict(
            opinion
            if node == req.target
            else generate_credit_opinion(node, g, sna_df, partition, risk_ratios, motif_hits)
        )
        # 目標公司直接沿用上面那份意見書（含歸戶集團脈絡），避免同一家公司在同一個
        # 回應裡出現兩份敘事不一致的文件；同時補上 graph_to_json 著色所需的相容鍵。
        item["score"] = item["attention_score"]
        item["label"] = _GRAPH_LABEL_ZH[item["label"]]
        evidences[node] = item

    opinion["graph"] = graph_to_json(
        g,
        evidences,
        sna_df,
        motif_centers={hit.center for hit in motif_hits},
        role_zh=sme_scenario.ROLE_ZH,
        # keep：授信對象無論分數高低都不得被截斷邏輯丟掉——否則會出現一份談
        # A 公司的授信意見書，附圖裡卻連 A 都找不到。
        keep={req.target},
    )
    return opinion


@app.post("/group")
def group(req: GroupRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """集團歸戶：回傳歸戶結果、各集團曝險與未申報的隱性關聯。"""
    _check_api_key(x_api_key)
    if not req.affiliations:
        raise HTTPException(status_code=400, detail="affiliations 不得為空")

    company_graph = build_company_graph(
        Affiliation(
            company=a.company,
            person=a.person,
            role=a.role,
            company_id=a.company_id,
            person_id=a.person_id,
        )
        for a in req.affiliations
    )
    groups = detect_groups(company_graph)
    totals = group_exposure(groups, req.exposures)
    # group_exposure 會靜默略過不在名冊中的公司。對銀行而言那是「曝險憑空消失」，
    # 是本系統最不該有的行為——改為明確列名回報，讓授信人員自己判斷該補名冊還是視為單獨歸戶。
    unattributed = sorted(
        c for c in req.exposures if normalise_name(c) not in groups
    )
    # hidden_links 依 weight 截斷至 DEFAULT_HIDDEN_LINKS_LIMIT 筆（見該函式 docstring：
    # 500 家公司共用同一人可組出 12.4 萬筆候選、13MB+ 的單一回應）。截斷本身不算
    # 隱瞞，但若不同時回報「原本有多少筆」，回應會讓人誤以為只找到這麼多——
    # 那才是真正的低估，故一律附上 total 與 truncated 旗標。
    all_hidden_links = hidden_links(company_graph, req.declared_groups, limit=10**9)
    hidden_links_total = len(all_hidden_links)
    return {
        "groups": groups,
        "exposures": {str(gid): amount for gid, amount in totals.items()},
        "hidden_links": all_hidden_links[:DEFAULT_HIDDEN_LINKS_LIMIT],
        "hidden_links_total": hidden_links_total,
        "truncated": hidden_links_total > DEFAULT_HIDDEN_LINKS_LIMIT,
        "unattributed": unattributed,
    }
