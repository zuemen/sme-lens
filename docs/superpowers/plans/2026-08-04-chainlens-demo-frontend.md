# ChainLens Demo 網站 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建一個公開的四頁 Demo 網站，讓人打開網址就能完整跑完 50 萬 USDT 出金攔阻演示，不需要終端機或本機 Streamlit。

**Architecture:** `web/` 放 Vite + React + TypeScript 靜態站，部署為獨立 Vercel 專案（Root Directory = `web`），從 CDN 秒開；資料來自既有 FastAPI 專案新增的兩個端點 `POST /screen` 與 `POST /graph`，跨網域以 CORS 連接。既有 API 的部署設定完全不動。

**Tech Stack:** Python 3.11 / FastAPI / NetworkX / pandas（後端），Vite 7 / React 18 / TypeScript / Tailwind CSS v4 / Cytoscape.js + dagre / Vitest / Playwright（前端）。

**設計來源：** `docs/superpowers/specs/2026-08-04-chainlens-demo-frontend-design.md`。契約細節以該 spec 為準。

## Global Constraints

- Python 3.11；ruff 設定為 `line-length = 100`、`target-version = "py311"`、`select = ["E", "F", "I", "W", "UP"]`。每個後端任務結束前 `ruff check` 必須全過。
- **後端不得新增任何 Python 依賴。** `requirements.txt` 是 Vercel serverless 的輕量清單，刻意排除 `torch`、`streamlit`、`pyvis`、`scikit-learn`。新端點所需的 `networkx`、`python-louvain`、`pandas`、`scipy` 皆已在列。
- **不得修改 `vercel.json`、`pyproject.toml` 的 `[tool.vercel]`、`.vercelignore`。** 這三個檔案控制既有 API 部署，本日已因它們失敗兩次。
- **不得修改 `chainlens/app/workbench.py`。** Streamlit 保留，與網站並存。
- 既有測試基線為 **61 個全綠**。每個任務結束時 `pytest -q` 的總數只能增加，不能有任何失敗。
- 前端套件管理器用 **npm**（本機 npm 11.11、Node 25；CI 固定 Node 20）。
- 前端所有使用者可見文字一律繁體中文。
- 地址與數值一律等寬字體呈現（`IBM Plex Mono` + `tabular-nums`）。
- **色票是實算過的，不得自行更動。** 依據見 spec 第九節。特別是 `--color-risk-high` 必須是
  `#F87171`——`#EF4444` 在面板底色上只有 4.16:1，未達 WCAG AA 的 4.5:1。
- **不得只用顏色傳達狀態。** 風險等級、服務狀態、導覽目前位置都必須同時有文字或字重差異。
- 所有互動元素需有可見的鍵盤焦點樣式；`prefers-reduced-motion` 必須生效。
- 不得使用 emoji 當圖示。
- 提交訊息用英文，主旨行祈使句。

---

## File Structure

**後端（修改 2 檔、新增 3 檔）**

| 檔案 | 責任 |
|---|---|
| `chainlens/api/serialize.py`（新） | 圖 + 證據 → 前端 JSON 的純資料轉換。不 import FastAPI，可獨立測試。 |
| `chainlens/api/main.py`（改） | 加 CORS middleware、`POST /screen`、`POST /graph` |
| `chainlens/explain/screening.py`（改） | `screen_withdrawal` 加一個選配的 `pipeline` 參數，讓呼叫端能重用已算好的管線結果 |
| `tests/test_serialize.py`（新） | 序列化模組單元測試 |
| `tests/test_api_web.py`（新） | 兩個新端點的契約與錯誤路徑測試 |

`tests/test_api.py` 既有 61 個測試不動。

**前端（全新 `web/`）**

| 檔案 | 責任 |
|---|---|
| `web/package.json`、`vite.config.ts`、`tsconfig.json`、`index.html` | 建置設定 |
| `web/src/index.css` | Tailwind v4 匯入 + 主題 token |
| `web/src/main.tsx` | React 進入點 + Router |
| `web/src/App.tsx` | 版面外殼、導覽、API 暖機 |
| `web/src/api/types.ts` | 後端契約的 TypeScript 型別 |
| `web/src/api/errors.ts` | HTTP 狀態碼 → 中文訊息（純函式） |
| `web/src/api/client.ts` | fetch 包裝，回傳型別化結果 |
| `web/src/api/snapshot.ts` | 離線快照資料（API 全掛時的 Demo 保險） |
| `web/src/graph/elements.ts` | 圖 JSON → Cytoscape elements + 樣式（純函式） |
| `web/src/graph/GraphView.tsx` | Cytoscape 渲染元件 |
| `web/src/components/RiskBadge.tsx` | 風險分數與標籤徽章 |
| `web/src/components/DecisionCard.tsx` | 出金審查決策卡 |
| `web/src/components/ErrorNotice.tsx` | 錯誤訊息與重試／切換動作 |
| `web/src/components/Panel.tsx` | 深色面板容器 |
| `web/src/pages/Landing.tsx` | 首頁 |
| `web/src/pages/Screening.tsx` | 出金審查 Demo |
| `web/src/pages/Workbench.tsx` | 金流圖譜工作台 |
| `web/src/pages/Research.tsx` | 研究成果 |
| `web/e2e/screening.spec.ts` | Playwright Demo 全流程冒煙 |
| `.github/workflows/ci.yml`（改） | 加一個與 Python job 並行的 `web` job |

---

## Task 1: 圖序列化模組

把圖轉 JSON 的邏輯獨立成不依賴 FastAPI 的純函式，先於任何端點完成並測到位。後續兩個端點都只是薄薄一層。

**Files:**
- Create: `chainlens/api/serialize.py`
- Test: `tests/test_serialize.py`

**Interfaces:**
- Consumes: 既有 `chainlens.explain.evidence.run_pipeline` / `generate_evidence`、`chainlens.data.scenario.ROLE_ZH`、`chainlens.sna.motifs.MotifHit`
- Produces:
  - `graph_to_json(g: nx.DiGraph, evidences: dict[Any, dict[str, Any]], sna_df: pd.DataFrame, *, motif_centers: set[Any], degraded: bool = False, limit: int = MAX_GRAPH_NODES) -> dict[str, Any]`
  - `sna_table(sna_df: pd.DataFrame, evidences: dict[Any, dict[str, Any]], limit: int = 15) -> list[dict[str, Any]]`
  - 常數 `DEFAULT_ROLE = "normal"`、`SNA_TABLE_LIMIT = 15`、`MAX_GRAPH_NODES = 300`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_serialize.py`：

```python
"""圖 → 前端 JSON 序列化測試（純資料轉換，不經 HTTP）。"""

from __future__ import annotations

import networkx as nx

from chainlens.api.serialize import graph_to_json, sna_table
from chainlens.data import scenario, tron
from chainlens.explain.evidence import generate_evidence, run_pipeline


def _payload_for(g: nx.DiGraph):
    """算一次管線與全節點證據，回傳序列化函式需要的四樣東西。"""
    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
    evidences = {
        n: generate_evidence(n, g, sna_df, partition, risk_ratios, motif_hits) for n in g.nodes()
    }
    return sna_df, evidences, {h.center for h in motif_hits}


def test_scenario_graph_counts_match() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["node_count"] == 53
    assert payload["meta"]["edge_count"] == 63
    assert len(payload["nodes"]) == 53
    assert len(payload["edges"]) == 63


def test_scenario_nodes_carry_roles_and_scores() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    by_id = {n["id"]: n for n in payload["nodes"]}

    aggregator = by_id["TAggregator01"]
    assert aggregator["role"] == "aggregator"
    assert aggregator["role_zh"] == "集資主錢包"
    assert aggregator["is_motif_center"] is True
    assert 0.0 <= aggregator["score"] <= 1.0
    assert aggregator["narrative_zh"]

    otc = by_id["TOtcOut01"]
    assert otc["role"] == "otc"
    assert otc["is_motif_center"] is False  # 本案主角自身不命中任何圖樣


def test_example_graph_has_no_roles_so_falls_back_to_normal() -> None:
    """範例圖與 TRON 圖沒有 role 屬性，必須落到 normal 而非 None。"""
    g = tron.load_example_graph()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert {n["role"] for n in payload["nodes"]} == {"normal"}
    assert {n["role_zh"] for n in payload["nodes"]} == {"正常交易地址"}


def test_edges_carry_amount_and_timestamp() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    edge = payload["edges"][0]
    assert isinstance(edge["source"], str)
    assert isinstance(edge["target"], str)
    assert isinstance(edge["amount"], float)
    assert isinstance(edge["timestamp"], int)


def test_edges_without_attributes_degrade_cleanly() -> None:
    """缺 amount / timestamp 的邊不得讓序列化爆炸。"""
    g = nx.DiGraph()
    g.add_edge("A", "B")
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["edges"] == [
        {"source": "A", "target": "B", "amount": 0.0, "timestamp": None}
    ]


def test_large_graph_truncated_to_highest_risk_nodes() -> None:
    """超過上限時保留風險最高的節點，並誠實標示已截斷。"""
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=10)
    assert payload["meta"]["truncated"] is True
    assert payload["meta"]["node_count"] == 10
    assert payload["meta"]["total_node_count"] == 53
    assert len(payload["nodes"]) == 10
    scores = [n["score"] for n in payload["nodes"]]
    assert scores == sorted(scores, reverse=True)


def test_truncated_graph_drops_edges_to_removed_nodes() -> None:
    """截斷後不得留下指向已移除節點的邊，否則前端渲染會出現孤兒引用。"""
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, limit=10)
    ids = {n["id"] for n in payload["nodes"]}
    for edge in payload["edges"]:
        assert edge["source"] in ids
        assert edge["target"] in ids
    assert payload["meta"]["edge_count"] == len(payload["edges"])


def test_graph_under_limit_is_not_marked_truncated() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["truncated"] is False
    assert payload["meta"]["total_node_count"] == 53


def test_meta_carries_story_and_degraded_flag() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers, degraded=True)
    assert payload["meta"]["degraded"] is True
    assert "TOtcOut01" in payload["meta"]["story_zh"]


def test_meta_story_is_none_for_graphs_without_one() -> None:
    g = tron.load_example_graph()
    sna_df, evidences, centers = _payload_for(g)
    payload = graph_to_json(g, evidences, sna_df, motif_centers=centers)
    assert payload["meta"]["story_zh"] is None
    assert payload["meta"]["degraded"] is False


def test_sna_table_sorted_by_score_and_limited() -> None:
    g = scenario.load_withdrawal_scenario()
    sna_df, evidences, _ = _payload_for(g)
    rows = sna_table(sna_df, evidences, limit=5)
    assert len(rows) == 5
    scores = [r["score"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    assert set(rows[0]) == {
        "node",
        "in_degree",
        "out_degree",
        "pagerank",
        "kcore",
        "betweenness",
        "score",
    }


def test_sna_table_empty_graph_returns_empty_list() -> None:
    g = nx.DiGraph()
    sna_df, evidences, _ = _payload_for(g)
    assert sna_table(sna_df, evidences) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/test_serialize.py -q`
Expected: FAIL，`ModuleNotFoundError: No module named 'chainlens.api.serialize'`

- [ ] **Step 3: 寫實作**

建立 `chainlens/api/serialize.py`：

```python
"""圖與風險證據 → 前端可直接渲染的 JSON。

刻意不 import FastAPI：這裡只做資料轉換，可獨立於 HTTP 層測試。
"""

from __future__ import annotations

from typing import Any

import networkx as nx
import pandas as pd

from chainlens.data.scenario import ROLE_ZH

DEFAULT_ROLE = "normal"
SNA_TABLE_LIMIT = 15

# 每個節點的 JSON 實測約 500 bytes（narrative_zh 是多句中文敘事）。
# TronGrid 的真實 2-hop 圖可達 795 節點 → 約 390KB 回應，經冷啟動的 serverless
# 傳輸過慢，且力導向排版在該量級會糊成無法閱讀的毛球。300 落在圖形函式庫
# 舒適的 101–500 canvas 區間。
MAX_GRAPH_NODES = 300


def _retained_nodes(
    g: nx.DiGraph, evidences: dict[Any, dict[str, Any]], limit: int
) -> list[Any]:
    """超過上限時只保留風險分數最高的 limit 個節點。"""
    if g.number_of_nodes() <= limit:
        return list(g.nodes())
    ranked = sorted(
        g.nodes(),
        key=lambda node: (evidences.get(node, {}).get("score", 0.0), str(node)),
        reverse=True,
    )
    return ranked[:limit]


def graph_to_json(
    g: nx.DiGraph,
    evidences: dict[Any, dict[str, Any]],
    sna_df: pd.DataFrame,
    *,
    motif_centers: set[Any],
    degraded: bool = False,
    limit: int = MAX_GRAPH_NODES,
) -> dict[str, Any]:
    """圖 + 全節點證據 → 前端圖譜 JSON。

    只有 scenario 劇本圖的節點有 role 屬性；範例圖與 TronGrid 抓回的真實圖
    一律沒有，會落到 DEFAULT_ROLE。前端因此不能只靠角色著色。

    節點數超過 limit 時依風險分數截斷，並在 meta 標示 truncated 與原始節點數，
    讓前端能誠實告知使用者看到的不是全圖。
    """
    pagerank = sna_df["pagerank"].to_dict() if not sna_df.empty else {}
    retained = _retained_nodes(g, evidences, limit)
    retained_set = set(retained)

    nodes = []
    for node in retained:
        attrs = g.nodes[node]
        evidence = evidences.get(node, {})
        role = attrs.get("role") or DEFAULT_ROLE
        nodes.append(
            {
                "id": str(node),
                "role": role,
                "role_zh": ROLE_ZH.get(role, role),
                "score": evidence.get("score", 0.0),
                "label": evidence.get("label", "low"),
                "is_motif_center": node in motif_centers,
                "pagerank": float(pagerank.get(node, 0.0)),
                "narrative_zh": evidence.get("narrative_zh", ""),
            }
        )

    edges = []
    for source, target, attrs in g.edges(data=True):
        if source not in retained_set or target not in retained_set:
            continue
        timestamp = attrs.get("timestamp")
        edges.append(
            {
                "source": str(source),
                "target": str(target),
                "amount": float(attrs.get("amount", 0.0)),
                "timestamp": int(timestamp) if timestamp is not None else None,
            }
        )

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "node_count": len(nodes),
            "total_node_count": g.number_of_nodes(),
            "edge_count": len(edges),
            "truncated": len(nodes) < g.number_of_nodes(),
            "story_zh": g.graph.get("story_zh"),
            "degraded": degraded,
        },
    }


def sna_table(
    sna_df: pd.DataFrame,
    evidences: dict[Any, dict[str, Any]],
    limit: int = SNA_TABLE_LIMIT,
) -> list[dict[str, Any]]:
    """依風險分數由高到低排序的 SNA 指標表，供工作台表格使用。"""
    if sna_df.empty:
        return []
    rows = [
        {
            "node": str(node),
            "in_degree": float(row["in_degree"]),
            "out_degree": float(row["out_degree"]),
            "pagerank": float(row["pagerank"]),
            "kcore": float(row["kcore"]),
            "betweenness": float(row["betweenness"]),
            "score": evidences.get(node, {}).get("score", 0.0),
        }
        for node, row in sna_df.iterrows()
    ]
    rows.sort(key=lambda row: row["score"], reverse=True)
    return rows[:limit]
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/test_serialize.py -q && .venv/Scripts/python.exe -m ruff check chainlens tests`
Expected: 12 passed；ruff `All checks passed!`

- [ ] **Step 5: 確認沒有回歸並提交**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: 73 passed（61 既有 + 12 新增）

```bash
git add chainlens/api/serialize.py tests/test_serialize.py
git commit -m "feat(api): add graph-to-JSON serialization module"
```

---

## Task 2: CORS 與 `POST /screen`

出金審查端點。順帶為 `screen_withdrawal` 加一個選配參數，讓端點能重用已算好的管線結果，不必重跑。

**Files:**
- Modify: `chainlens/explain/screening.py`（`screen_withdrawal` 簽章與第 202 行附近）
- Modify: `chainlens/api/main.py`
- Test: `tests/test_api_web.py`

**Interfaces:**
- Consumes: Task 1 的 `graph_to_json`
- Produces:
  - `screen_withdrawal(..., pipeline: PipelineResult | None = None)` — 新增最後一個關鍵字參數，預設 `None` 時行為與現在完全相同
  - `POST /screen` 端點
  - `_evidences_for(g, sna_df, partition, risk_ratios, motif_hits) -> dict[Any, dict[str, Any]]`（`main.py` 內部輔助，Task 3 會重用）

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_api_web.py`：

```python
"""網站專用端點測試：POST /screen 與 POST /graph。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from chainlens.api.main import app

client = TestClient(app)


def test_screen_blocks_the_scenario_target() -> None:
    """本案主角：自身乾淨、上游髒，必須被關聯分數攔下。"""
    response = client.post("/screen", json={"target": "TOtcOut01", "amount_usdt": 500000.0})
    assert response.status_code == 200
    body = response.json()
    assert body["target"] == "TOtcOut01"
    assert body["risk_score"] == pytest.approx(0.7307, abs=1e-4)
    assert body["self_score"] == pytest.approx(0.3268, abs=1e-4)
    assert body["association_score"] == pytest.approx(0.6, abs=1e-4)
    assert body["decision"] == "block"
    assert body["decision_zh"] == "暫緩出金並啟動人工審查"
    assert len(body["associations"]) == 6
    assert body["str_draft_zh"]
    assert body["evidence"]["motif_hits"] == []  # 自身不命中任何圖樣，這是整個 Demo 的論點


def test_screen_passes_the_control_target() -> None:
    """對照組：同一套引擎不得誤殺正常用戶。"""
    response = client.post("/screen", json={"target": "TNormalUser01", "amount_usdt": 500000.0})
    assert response.status_code == 200
    body = response.json()
    assert body["risk_score"] == pytest.approx(0.0962, abs=1e-4)
    assert body["decision"] == "pass"
    assert body["associations"] == []
    assert body["str_draft_zh"] is None


def test_screen_returns_graph_and_highlight_path() -> None:
    response = client.post("/screen", json={"target": "TOtcOut01", "amount_usdt": 500000.0})
    body = response.json()
    assert body["graph"]["meta"]["node_count"] == 53
    assert body["graph"]["meta"]["edge_count"] == 63
    assert body["highlight_path"] == ["TAggregator01", "TMule03", "TOtcOut01"]


def test_screen_highlight_path_empty_when_no_associations() -> None:
    response = client.post("/screen", json={"target": "TNormalUser01", "amount_usdt": 500000.0})
    assert response.json()["highlight_path"] == []


def test_screen_rejects_targets_outside_the_scenario() -> None:
    """白名單：避免端點淪為任意圖計算的公開資源。"""
    response = client.post("/screen", json={"target": "TAggregator01", "amount_usdt": 1000.0})
    assert response.status_code == 400
    assert response.json()["detail"] == "target 需為劇本情境中的出金地址"


def test_screen_rejects_non_positive_amount() -> None:
    response = client.post("/screen", json={"target": "TOtcOut01", "amount_usdt": 0})
    assert response.status_code == 422


def test_cors_headers_present() -> None:
    response = client.options(
        "/screen",
        headers={
            "Origin": "https://example.vercel.app",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"
```

再於 `tests/test_serialize.py` 之外，另建 `tests/test_screening_pipeline_reuse.py`：

```python
"""screen_withdrawal 的選配 pipeline 參數：重用不得改變結果。"""

from __future__ import annotations

import pytest

from chainlens.data import scenario
from chainlens.explain.evidence import run_pipeline
from chainlens.explain.screening import screen_withdrawal


def test_passing_precomputed_pipeline_gives_identical_result() -> None:
    g = scenario.load_withdrawal_scenario()
    fresh = screen_withdrawal(g, "TOtcOut01", 500000.0)
    reused = screen_withdrawal(g, "TOtcOut01", 500000.0, pipeline=run_pipeline(g))
    assert fresh == reused


def test_default_pipeline_argument_keeps_existing_behaviour() -> None:
    g = scenario.load_withdrawal_scenario()
    result = screen_withdrawal(g, "TOtcOut01", 500000.0)
    assert result["risk_score"] == pytest.approx(0.7307, abs=1e-4)
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_web.py tests/test_screening_pipeline_reuse.py -q`
Expected: FAIL — `/screen` 回 404、`screen_withdrawal() got an unexpected keyword argument 'pipeline'`

- [ ] **Step 3: 為 `screen_withdrawal` 加選配 pipeline 參數**

在 `chainlens/explain/screening.py`，把簽章的最後加上參數：

```python
def screen_withdrawal(
    g: nx.DiGraph,
    target: Any,
    amount_usdt: float,
    request_id: str | None = None,
    max_hops: int = DEFAULT_MAX_HOPS,
    decay: float = DEFAULT_DECAY,
    pipeline: PipelineResult | None = None,
) -> dict[str, Any]:
```

把原本第 202 行的：

```python
    sna_df, partition, risk_ratios, motif_hits = run_pipeline(g)
```

改為：

```python
    sna_df, partition, risk_ratios, motif_hits = pipeline if pipeline is not None else run_pipeline(g)
```

並確認檔案頂端的 import 含 `PipelineResult`：

```python
from chainlens.explain.evidence import PipelineResult, generate_evidence, run_pipeline
```

在 docstring 的參數說明補一句：

```
    pipeline 傳入已算好的 run_pipeline 結果時直接重用，供同一張圖上還要
    產生圖譜 JSON 的呼叫端（API /screen）避免重算。
```

- [ ] **Step 4: 在 `main.py` 加 CORS 與 `/screen`**

`chainlens/api/main.py` 頂端 import 區加入：

```python
from fastapi.middleware.cors import CORSMiddleware

from chainlens.api.serialize import graph_to_json
from chainlens.data import elliptic, scenario, tron
from chainlens.explain.evidence import (
    PipelineResult,
    generate_evidence,
    run_pipeline,
)
from chainlens.explain.screening import screen_withdrawal
```

（`chainlens.data` 原本只 import `elliptic, tron`，加上 `scenario`；`chainlens.explain.evidence` 原本 import `PipelineResult, generate_evidence, run_pipeline` 之外還有其他名稱，請保留既有項目再補齊。）

在 `app = FastAPI(...)` 建立之後、`RAW_DIR` 之前插入：

```python
def _cors_origins() -> list[str]:
    """允許來源清單；未設定環境變數時全開。"""
    raw = os.getenv("CHAINLENS_CORS_ORIGINS", "*")
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
```

在 `ScoreRequest` 類別之後加入請求模型：

```python
class ScreenRequest(BaseModel):
    """出金審查請求：目標地址限定為劇本情境中的兩個地址。"""

    target: str = Field(max_length=64)
    amount_usdt: float = Field(gt=0)
    request_id: str | None = Field(default=None, max_length=64)
```

在 `/health` 端點之後、`_build_graph` 之前加入輔助函式與端點：

```python
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
```

- [ ] **Step 5: 跑測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_web.py tests/test_screening_pipeline_reuse.py -q`
Expected: 9 passed

- [ ] **Step 6: 確認沒有回歸並提交**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check chainlens tests`
Expected: 82 passed；ruff `All checks passed!`

```bash
git add chainlens/api/main.py chainlens/explain/screening.py tests/test_api_web.py tests/test_screening_pipeline_reuse.py
git commit -m "feat(api): add POST /screen endpoint and CORS support"
```

---

## Task 3: `POST /graph`

工作台的資料來源。與 `/score` 共用既有的 TRON 抓取與驗證邏輯，但**不做**靜默降級——Streamlit 版本抓取失敗會偷偷改用範例圖，那會讓使用者誤以為看到的是真實資料。

**Files:**
- Modify: `chainlens/api/main.py`
- Test: `tests/test_api_web.py`（延伸）

**Interfaces:**
- Consumes: Task 1 的 `graph_to_json` 與 `sna_table`；Task 2 的 `_evidences_for`
- Produces: `POST /graph` 端點

- [ ] **Step 1: 寫失敗的測試**

在 `tests/test_api_web.py` 末端追加：

```python
def test_graph_example_mode_contract() -> None:
    response = client.post("/graph", json={"mode": "example"})
    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["node_count"] == 25
    assert body["meta"]["total_node_count"] == 25
    assert body["meta"]["edge_count"] == 23
    assert body["meta"]["truncated"] is False  # 25 遠低於 300 上限
    assert body["meta"]["story_zh"] is None
    assert len(body["nodes"]) == 25
    assert {n["role"] for n in body["nodes"]} == {"normal"}


def test_graph_example_mode_returns_sna_table() -> None:
    body = client.post("/graph", json={"mode": "example"}).json()
    assert len(body["sna"]) == 15
    scores = [row["score"] for row in body["sna"]]
    assert scores == sorted(scores, reverse=True)


def test_graph_tron_mode_requires_address() -> None:
    response = client.post("/graph", json={"mode": "tron"})
    assert response.status_code == 400
    assert response.json()["detail"] == "tron 模式需提供 address"


def test_graph_tron_mode_rejects_malformed_address() -> None:
    response = client.post("/graph", json={"mode": "tron", "address": "not-an-address"})
    assert response.status_code == 400
    assert "合法 TRON 主網地址" in response.json()["detail"]


def test_graph_tron_failure_returns_502_not_a_silent_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """抓取失敗必須誠實回錯，不得偷偷改用範例圖冒充真實資料。"""
    import httpx

    from chainlens.api import main as api_main

    def boom(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("network down")

    monkeypatch.setattr(api_main.tron, "fetch_two_hop_graph", boom)
    response = client.post(
        "/graph",
        json={"mode": "tron", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"},
    )
    assert response.status_code == 502
    assert "TScamCollector001" not in response.text


def test_graph_tron_empty_result_returns_404(monkeypatch: pytest.MonkeyPatch) -> None:
    import networkx as nx

    from chainlens.api import main as api_main

    monkeypatch.setattr(
        api_main.tron, "fetch_two_hop_graph", lambda *a, **k: nx.DiGraph()
    )
    response = client.post(
        "/graph",
        json={"mode": "tron", "address": "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"},
    )
    assert response.status_code == 404
    assert "查無 USDT 轉帳" in response.json()["detail"]


def test_graph_rejects_unknown_mode() -> None:
    response = client.post("/graph", json={"mode": "elliptic"})
    assert response.status_code == 422
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_web.py -q`
Expected: 新增的 7 個 FAIL（`/graph` 回 404），既有 7 個仍 pass

- [ ] **Step 3: 寫實作**

`chainlens/api/main.py` 的 import 補上 `sna_table`：

```python
from chainlens.api.serialize import graph_to_json, sna_table
```

在 `ScreenRequest` 之後加請求模型：

```python
class GraphRequest(BaseModel):
    """工作台圖譜請求：內建範例圖，或 TronGrid 即時抓取的 2-hop 真實圖。"""

    mode: Literal["example", "tron"] = "example"
    address: str | None = Field(default=None, max_length=64)
```

在 `/screen` 端點之後加入：

```python
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
```

- [ ] **Step 4: 跑測試確認通過**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api_web.py -q`
Expected: 14 passed

- [ ] **Step 5: 確認沒有回歸並提交**

Run: `.venv/Scripts/python.exe -m pytest -q && .venv/Scripts/python.exe -m ruff check chainlens tests`
Expected: 89 passed；ruff `All checks passed!`

```bash
git add chainlens/api/main.py tests/test_api_web.py
git commit -m "feat(api): add POST /graph endpoint for the workbench"
```

---

## Task 4: 前端骨架與 CI

建立 `web/` 專案並讓 CI 一起把關。這一步結束時網站還沒有內容，但 `npm run build` 與 `npm test` 必須能跑。

**Files:**
- Create: `web/package.json`、`web/vite.config.ts`、`web/tsconfig.json`、`web/tsconfig.node.json`、`web/index.html`、`web/.gitignore`、`web/src/main.tsx`、`web/src/App.tsx`、`web/src/index.css`、`web/src/smoke.test.ts`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: 可建置的 Vite 專案；`VITE_API_BASE` 環境變數約定；主題 CSS token

- [ ] **Step 1: 建立專案骨架**

```bash
mkdir -p web/src
cd web
npm init -y
npm install react react-dom react-router-dom cytoscape cytoscape-dagre
npm install -D vite @vitejs/plugin-react typescript @types/react @types/react-dom @types/cytoscape tailwindcss @tailwindcss/vite vitest jsdom @testing-library/react @testing-library/jest-dom
```

- [ ] **Step 2: 寫設定檔**

`web/package.json` 的 `scripts` 與 `type` 欄位改為：

```json
{
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  }
}
```

`web/vite.config.ts`：

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
  },
})
```

`web/tsconfig.json`：

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "types": ["vitest/globals"]
  },
  "include": ["src", "e2e"]
}
```

`web/index.html`：

```html
<!doctype html>
<html lang="zh-Hant">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <!-- 字體來自 Google Fonts；先建立連線可省下一次 DNS + TLS 往返。
         Noto Sans TC 是中日韓字體，體積大，Google 以 unicode-range 分片供應，
         這個 preconnect 對首次繪製的影響特別明顯。 -->
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <!-- 字體必須從這裡載入，不能寫在 index.css 的 @import：
         Tailwind v4 展開後會把它擠到合法位置之後而被丟棄。
         display=swap 避免字體載入期間文字不可見。 -->
    <link
      rel="stylesheet"
      href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+TC:wght@400;500;700&display=swap"
    />
    <title>鏈鏡 ChainLens — 虛擬資產詐騙金流偵測平台</title>
    <meta
      name="description"
      content="以社會網路分析與圖神經網路偵測虛擬資產詐騙金流，每個風險判定都附帶可稽核的結構證據。"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/.gitignore`：

```
node_modules
dist
.vite
test-results
playwright-report
```

- [ ] **Step 3: 寫主題 token**

`web/src/index.css`：

所有色值的對比皆為實算，依據見 spec 第九節。**不要自行更動這些值**——多數是為了通過
WCAG 門檻才選定的，尤其 `--color-risk-high`。

字體**不要**用 CSS `@import` 載入。Tailwind v4 的 `@import "tailwindcss"` 會就地展開，把字體的
`@import` 擠到 CSS 允許 `@import` 的位置之後，結果整條規則在正式建置中被靜默丟棄——實測建置
產物裡 `@import` 與 `fonts.googleapis` 出現次數皆為 0，字體永遠不會載入。字體改由
`web/index.html` 的 `<link rel="stylesheet">` 載入（見該檔）。

```css
@import "tailwindcss";

@theme {
  /* 表面：slate 階系，可從同一階系推導整套 UI 色 */
  --color-base: #0F172A;         /* slate-900 */
  --color-panel: #1B2336;
  --color-panel-raised: #222B40;

  /* 邊框分兩階：裝飾線不受 3:1 規範，控制項邊界必須達標 */
  --color-line: #334155;         /* 1.72:1 — 僅供分隔線與面板外框 */
  --color-line-strong: #64748B;  /* 3.75:1 — 表單輸入框與控制項邊界 */

  --color-ink: #F8FAFC;          /* 17.06:1 於 base */
  --color-muted: #94A3B8;        /* 6.96:1 於 base、6.11:1 於 panel */

  /* 風險語意色：文字用，兩種底色皆 ≥4.5:1 */
  --color-risk-high: #F87171;    /* 6.45 / 5.66 — 不可改回 #EF4444，它在面板上只有 4.16 */
  --color-risk-med: #F59E0B;     /* 8.31 / 7.30 */
  --color-risk-low: #22C55E;     /* 7.83 / 6.88 */

  /* 圖譜專用（非文字，門檻 3:1，繪製於 canvas） */
  --color-graph-bg: #0d1219;
  --color-focus: #f1c40f;        /* 11.31:1 於畫布 */
  --color-path: #f39c12;         /* 8.57:1 於畫布 */

  --color-ring: #38BDF8;         /* 8.33:1 — 鍵盤焦點環 */

  --font-sans: "IBM Plex Sans", "Noto Sans TC", system-ui, sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, "SFMono-Regular", Menlo, monospace;
}

html {
  background-color: var(--color-base);
  color: var(--color-ink);
  color-scheme: dark;
}

body {
  margin: 0;
  font-family: var(--font-sans);
}

/* 地址與數值一律等寬且等距數字，這是法遵工具的閱讀慣例，也避免數字跳動 */
.tabular {
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* 表單控制項的邊界是識別它的唯一依據，必須用達標的那一階 */
input,
select {
  border-color: var(--color-line-strong);
}

:focus-visible {
  outline: 2px solid var(--color-ring);
  outline-offset: 2px;
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

- [ ] **Step 4: 寫最小的 App 與進入點**

`web/src/main.tsx`：

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import './index.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
)
```

`web/src/App.tsx`（Task 6 會擴充成完整版面）：

```tsx
export default function App() {
  return <div className="min-h-screen bg-base text-ink">ChainLens</div>
}
```

- [ ] **Step 5: 寫一個確認測試設施可用的測試**

`web/src/smoke.test.ts`：

```ts
import { describe, expect, it } from 'vitest'

describe('測試設施', () => {
  it('可以跑', () => {
    expect(1 + 1).toBe(2)
  })
})
```

- [ ] **Step 6: 跑建置與測試確認通過**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: typecheck 無錯；1 test passed；`dist/` 產生

- [ ] **Step 7: 加 CI job**

把 `.github/workflows/ci.yml` 整份改為：

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

jobs:
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: uv sync
      - name: Lint
        run: uv run ruff check .
      - name: Test
        run: uv run pytest -q

  web:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: web/package-lock.json
      - name: Install dependencies
        run: npm ci
      - name: Typecheck
        run: npm run typecheck
      - name: Test
        run: npm test
      - name: Build
        run: npm run build
```

- [ ] **Step 8: 提交**

```bash
git add web .github/workflows/ci.yml
git commit -m "build(web): scaffold Vite React frontend with CI job"
```

---

## Task 5: API 客戶端、錯誤映射與離線快照

前端與後端之間的整層。錯誤映射與快照都是純資料，先於任何畫面完成並測到位。

**Files:**
- Create: `web/src/api/types.ts`、`web/src/api/errors.ts`、`web/src/api/client.ts`、`web/src/api/snapshot.ts`、`web/src/api/errors.test.ts`
- Delete: `web/src/smoke.test.ts`

**Interfaces:**
- Consumes: Task 2、Task 3 的端點契約
- Produces:
  - 型別 `GraphNode`、`GraphEdge`、`GraphMeta`、`GraphPayload`、`Evidence`、`Association`、`ScreenResult`、`WorkbenchPayload`、`SnaRow`
  - `describeError(status: number, detail?: string): string`
  - `postScreen(target: string, amountUsdt: number): Promise<ScreenResult>`
  - `postGraph(body: { mode: 'example' | 'tron'; address?: string }): Promise<WorkbenchPayload>`
  - `warmUp(): void`
  - `checkHealth(): Promise<boolean>`
  - `ApiError`（含 `status: number`、`detail: string`）
  - `SCREENING_SNAPSHOT: ScreenResult`

- [ ] **Step 1: 寫型別**

`web/src/api/types.ts`：

```ts
export type RiskLabel = 'high' | 'medium' | 'low'
export type Decision = 'block' | 'review' | 'pass'

export interface GraphNode {
  id: string
  role: string
  role_zh: string
  score: number
  label: RiskLabel
  is_motif_center: boolean
  pagerank: number
  narrative_zh: string
}

export interface GraphEdge {
  source: string
  target: string
  amount: number
  timestamp: number | null
}

export interface GraphMeta {
  /** 實際回傳（可能已截斷）的節點數 */
  node_count: number
  /** 截斷前的原始節點數 */
  total_node_count: number
  edge_count: number
  /** 超過 300 節點上限而截斷；前端必須告知使用者 */
  truncated: boolean
  story_zh: string | null
  degraded: boolean
}

export interface GraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meta: GraphMeta
}

export interface MotifHit {
  motif: string
  center: string
  nodes: string[]
  description_zh: string
}

export interface Evidence {
  score: number
  label: RiskLabel
  top_features: string[]
  centrality_percentile: Record<string, number>
  community_risk_ratio: number
  motif_hits: MotifHit[]
  narrative_zh: string
}

export interface Association {
  risky_node: string
  distance: number
  path: string[]
  motifs: string[]
}

export interface ScreenResult {
  target: string
  amount_usdt: number
  risk_score: number
  self_score: number
  association_score: number
  decision: Decision
  decision_zh: string
  narrative_zh: string
  associations: Association[]
  evidence: Evidence | null
  str_draft_zh: string | null
  /** 目標不在圖中時後端才會帶這個鍵，正常路徑完全沒有此欄位 */
  insufficient_data?: true
  graph: GraphPayload
  highlight_path: string[]
}

export interface SnaRow {
  node: string
  in_degree: number
  out_degree: number
  pagerank: number
  kcore: number
  betweenness: number
  score: number
}

export interface WorkbenchPayload extends GraphPayload {
  sna: SnaRow[]
}
```

- [ ] **Step 2: 寫錯誤映射的失敗測試**

`web/src/api/errors.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { describeError } from './errors'

describe('describeError', () => {
  it('把逾時與閘道錯誤說成鏈上查詢問題', () => {
    expect(describeError(502)).toContain('鏈上查詢')
  })

  it('查無資料時給明確訊息', () => {
    expect(describeError(404, '地址 TXxx 查無 USDT 轉帳')).toBe('地址 TXxx 查無 USDT 轉帳')
  })

  it('沒有 detail 的 404 也要有可讀訊息', () => {
    expect(describeError(404)).toContain('查無')
  })

  it('優先採用後端提供的 detail', () => {
    expect(describeError(400, 'tron 模式需提供 address')).toBe('tron 模式需提供 address')
  })

  it('401 提示金鑰問題', () => {
    expect(describeError(401)).toContain('金鑰')
  })

  it('0 代表連線失敗', () => {
    expect(describeError(0)).toContain('無法連線')
  })

  it('未知狀態碼仍回傳非空字串', () => {
    expect(describeError(418).length).toBeGreaterThan(0)
  })
})
```

- [ ] **Step 3: 跑測試確認失敗**

Run: `cd web && npm test`
Expected: FAIL — 找不到 `./errors` 模組

- [ ] **Step 4: 寫錯誤映射**

`web/src/api/errors.ts`：

```ts
/** HTTP 狀態碼 → 使用者看得懂的中文訊息。後端有給 detail 時一律優先採用。 */
export function describeError(status: number, detail?: string): string {
  if (detail) return detail
  switch (status) {
    case 0:
      return '無法連線到分析服務，請確認網路後重試。'
    case 400:
      return '請求參數不正確。'
    case 401:
      return '缺少或不正確的 API 金鑰。'
    case 404:
      return '查無資料。'
    case 422:
      return '輸入格式不正確。'
    case 502:
      return '鏈上查詢逾時或失敗，可改用內建範例圖繼續。'
    default:
      return `分析服務回應異常（HTTP ${status}）。`
  }
}
```

- [ ] **Step 5: 寫客戶端**

`web/src/api/client.ts`：

```ts
import { describeError } from './errors'
import type { ScreenResult, WorkbenchPayload } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, describeError(0))
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((payload: { detail?: unknown }) =>
        typeof payload.detail === 'string' ? payload.detail : undefined,
      )
      .catch(() => undefined)
    throw new ApiError(response.status, describeError(response.status, detail))
  }
  return (await response.json()) as T
}

export function postScreen(target: string, amountUsdt: number): Promise<ScreenResult> {
  return post<ScreenResult>('/screen', {
    target,
    amount_usdt: amountUsdt,
    request_id: 'DEMO-2026-001',
  })
}

export function postGraph(body: {
  mode: 'example' | 'tron'
  address?: string
}): Promise<WorkbenchPayload> {
  return post<WorkbenchPayload>('/graph', body)
}

/** 背景喚醒 serverless 函式。冷啟動實測約 5 秒，趁使用者閱讀時吃掉。 */
export function warmUp(): void {
  void fetch(`${API_BASE}/health`).catch(() => undefined)
}

/** 分析服務是否可用，供首頁的即時狀態指示使用。 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/health`)
    return response.ok
  } catch {
    return false
  }
}
```

- [ ] **Step 6: 產生離線快照**

先從線上 API 取得真實回應存成快照：

```bash
curl -s -X POST https://chain-lens-beta.vercel.app/screen \
  -H "Content-Type: application/json" \
  -d '{"target":"TOtcOut01","amount_usdt":500000,"request_id":"DEMO-2026-001"}' \
  -o web/src/api/screening-snapshot.json
```

> 此步驟必須在 Task 2 部署上線後執行。若 `/screen` 尚未上線，改用本機：
> `.venv/Scripts/python.exe -c "import json;from fastapi.testclient import TestClient;from chainlens.api.main import app;print(json.dumps(TestClient(app).post('/screen',json={'target':'TOtcOut01','amount_usdt':500000,'request_id':'DEMO-2026-001'}).json(),ensure_ascii=False))" > web/src/api/screening-snapshot.json`

`web/src/api/snapshot.ts`：

```ts
import type { ScreenResult } from './types'
import raw from './screening-snapshot.json'

/**
 * 現場保險：API 完全無法連線時，出金審查頁改用這份快照把 Demo 演完。
 * 使用時畫面必須顯示「離線快照」標記，不得偽裝成即時查詢結果。
 */
export const SCREENING_SNAPSHOT = raw as unknown as ScreenResult
```

- [ ] **Step 7: 跑測試確認通過**

```bash
cd web && rm src/smoke.test.ts && npm run typecheck && npm test
```
Expected: 7 passed；typecheck 無錯

- [ ] **Step 8: 提交**

```bash
# -A 一併把 Step 7 刪掉的 smoke.test.ts 記錄為刪除
git add -A web/src web/package.json web/package-lock.json
git commit -m "feat(web): add typed API client, error mapping and offline snapshot"
```

---

## Task 6: 版面外殼、主題與導覽

四頁共用的深色外殼。這一步結束時四個路由都能走到，內容是佔位標題，但主題與導覽已定型。

**Files:**
- Create: `web/src/components/Panel.tsx`、`web/src/components/RiskBadge.tsx`、`web/src/components/ErrorNotice.tsx`、`web/src/components/RiskBadge.test.tsx`
- Modify: `web/src/App.tsx`
- Create: `web/src/pages/Landing.tsx`、`web/src/pages/Screening.tsx`、`web/src/pages/Workbench.tsx`、`web/src/pages/Research.tsx`

**Interfaces:**
- Produces:
  - `<Panel title?: string, children: ReactNode>` — 深色面板容器
  - `<RiskBadge score: number, label: RiskLabel>` — 分數徽章
  - `<ErrorNotice message: string, action?: { label: string; onClick: () => void }>`
  - `riskColor(label: RiskLabel): string` — 由 `RiskBadge.tsx` 具名匯出，回傳 CSS 變數字串，僅供 DOM 樣式使用

- [ ] **Step 1: 寫 RiskBadge 的失敗測試**

`web/src/components/RiskBadge.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskBadge, riskColor } from './RiskBadge'

describe('riskColor', () => {
  it('三個風險等級各有不同顏色', () => {
    const colors = new Set([riskColor('high'), riskColor('medium'), riskColor('low')])
    expect(colors.size).toBe(3)
  })
})

describe('RiskBadge', () => {
  it('顯示兩位小數的分數與中文等級', () => {
    render(<RiskBadge score={0.7307} label="high" />)
    expect(screen.getByText('0.73')).toBeDefined()
    expect(screen.getByText('高風險')).toBeDefined()
  })

  it('低風險顯示對應中文', () => {
    render(<RiskBadge score={0.0962} label="low" />)
    expect(screen.getByText('0.10')).toBeDefined()
    expect(screen.getByText('低風險')).toBeDefined()
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd web && npm test`
Expected: FAIL — 找不到 `./RiskBadge`

- [ ] **Step 3: 寫元件**

`web/src/components/RiskBadge.tsx`：

```tsx
import type { RiskLabel } from '../api/types'

const LABEL_ZH: Record<RiskLabel, string> = {
  high: '高風險',
  medium: '中風險',
  low: '低風險',
}

const LABEL_COLOR: Record<RiskLabel, string> = {
  high: 'var(--color-risk-high)',
  medium: 'var(--color-risk-med)',
  low: 'var(--color-risk-low)',
}

export function riskColor(label: RiskLabel): string {
  return LABEL_COLOR[label]
}

export function RiskBadge({ score, label }: { score: number; label: RiskLabel }) {
  return (
    <span className="inline-flex items-baseline gap-2">
      <span className="tabular text-3xl font-semibold" style={{ color: riskColor(label) }}>
        {score.toFixed(2)}
      </span>
      <span className="text-sm" style={{ color: riskColor(label) }}>
        {LABEL_ZH[label]}
      </span>
    </span>
  )
}
```

`web/src/components/Panel.tsx`：

```tsx
import type { ReactNode } from 'react'

export function Panel({
  title,
  actions,
  children,
}: {
  title?: string
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="rounded-lg border border-line bg-panel p-5">
      {(title || actions) && (
        <header className="mb-4 flex items-center justify-between gap-4">
          {title && <h2 className="text-base font-semibold text-ink">{title}</h2>}
          {actions}
        </header>
      )}
      {children}
    </section>
  )
}
```

`web/src/components/ErrorNotice.tsx`：

```tsx
export function ErrorNotice({
  message,
  action,
}: {
  message: string
  action?: { label: string; onClick: () => void }
}) {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-4 rounded-lg border p-4"
      style={{ borderColor: 'var(--color-risk-med)', color: 'var(--color-risk-med)' }}
    >
      <span className="flex-1">{message}</span>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="rounded border border-current px-3 py-1 text-sm"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}
```

- [ ] **Step 4: 寫版面外殼**

`web/src/App.tsx`：

```tsx
import { useEffect } from 'react'
import { NavLink, Route, Routes } from 'react-router-dom'
import { warmUp } from './api/client'
import Landing from './pages/Landing'
import Research from './pages/Research'
import Screening from './pages/Screening'
import Workbench from './pages/Workbench'

const NAV = [
  { to: '/', label: '首頁' },
  { to: '/screening', label: '出金審查' },
  { to: '/workbench', label: '金流圖譜' },
  { to: '/research', label: '研究成果' },
]

export default function App() {
  // 冷啟動實測約 5 秒；趁使用者讀首頁時背景喚醒，按鈕按下去時函式已是熱的。
  useEffect(warmUp, [])

  return (
    <div className="min-h-screen bg-base text-ink">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded focus:bg-ink focus:px-4 focus:py-2 focus:text-base"
      >
        跳至主要內容
      </a>

      <header className="border-b border-line">
        <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-6 px-6 py-4">
          <span className="font-semibold">
            鏈鏡 <span className="text-muted">ChainLens</span>
          </span>
          <div className="flex gap-5 text-sm">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                // 目前位置不只靠顏色標示，同時加粗並提供 aria-current
                className={({ isActive }) =>
                  isActive ? 'font-semibold text-ink' : 'text-muted'
                }
              >
                {item.label}
              </NavLink>
            ))}
          </div>
          <NavLink
            to="/screening"
            className="ml-auto rounded bg-ink px-4 py-1.5 text-sm font-semibold text-base"
          >
            看 Demo
          </NavLink>
        </nav>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-6 py-8">
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/screening" element={<Screening />} />
          <Route path="/workbench" element={<Workbench />} />
          <Route path="/research" element={<Research />} />
        </Routes>
      </main>

      <footer className="border-t border-line px-6 py-6 text-center text-sm text-muted">
        研究用途，非投資或法律建議
      </footer>
    </div>
  )
}
```

四個頁面先寫成佔位，Task 8–10 會逐一填滿。四份檔案內容分別為：

`web/src/pages/Landing.tsx`：
```tsx
export default function Landing() {
  return <h1 className="text-2xl font-semibold">首頁</h1>
}
```

`web/src/pages/Screening.tsx`：
```tsx
export default function Screening() {
  return <h1 className="text-2xl font-semibold">出金審查</h1>
}
```

`web/src/pages/Workbench.tsx`：
```tsx
export default function Workbench() {
  return <h1 className="text-2xl font-semibold">金流圖譜工作台</h1>
}
```

`web/src/pages/Research.tsx`：
```tsx
export default function Research() {
  return <h1 className="text-2xl font-semibold">研究成果</h1>
}
```

- [ ] **Step 5: 跑測試確認通過**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: 10 passed；建置成功

- [ ] **Step 6: 提交**

```bash
git add web/src
git commit -m "feat(web): add dark theme shell, navigation and shared components"
```

---

## Task 7: 圖譜元件

把後端圖 JSON 轉成 Cytoscape 元素並渲染。轉換是純函式先測，渲染元件隨後。

**Files:**
- Create: `web/src/graph/elements.ts`、`web/src/graph/elements.test.ts`、`web/src/graph/GraphView.tsx`

**Interfaces:**
- Consumes: Task 5 的 `GraphPayload`、`GraphNode`
- Produces:
  - `type ColorScheme = 'role' | 'risk'`
  - `toElements(payload: GraphPayload, options: { scheme: ColorScheme; highlightPath?: string[]; focus?: string }): ElementDefinition[]`
  - `nodeColor(node: GraphNode, options: { scheme: ColorScheme; focus?: string }): string`
  - `<GraphView payload, highlightPath?, focus?, layout: 'dagre' | 'cose', scheme: ColorScheme, onSelect?>`

> **本檔的顏色與主題 token 是兩套，不要「修正」成一致——這是刻意的。**
>
> - Task 6 的 `riskColor` 回傳 `var(--color-risk-*)`，是**畫在 DOM 上的文字色**，
>   門檻 4.5:1，所以用較亮的 `#F87171` 系列。
> - 本檔的 hex 是**畫在 canvas 上的圖形填色**，門檻 3:1，沿用 `chainlens/app/workbench.py`
>   既有的 `ROLE_COLOR`（實測全部通過，最低 `#c0392b` 為 3.45:1），以維持與
>   `docs/images/` 既有截圖的一致性。
>
> 另外 Cytoscape 在 canvas 上繪製，**解析不了 CSS 變數**，這裡技術上也只能用原始 hex。

- [ ] **Step 1: 寫失敗的測試**

`web/src/graph/elements.test.ts`：

```ts
import { describe, expect, it } from 'vitest'
import type { GraphPayload } from '../api/types'
import { nodeColor, toElements } from './elements'

const payload: GraphPayload = {
  nodes: [
    {
      id: 'TAggregator01',
      role: 'aggregator',
      role_zh: '集資主錢包',
      score: 0.91,
      label: 'high',
      is_motif_center: true,
      pagerank: 0.04,
      narrative_zh: '敘事',
    },
    {
      id: 'TMule03',
      role: 'mule',
      role_zh: '車手地址',
      score: 0.42,
      label: 'medium',
      is_motif_center: false,
      pagerank: 0.02,
      narrative_zh: '敘事',
    },
    {
      id: 'TOtcOut01',
      role: 'otc',
      role_zh: 'OTC 出金地址',
      score: 0.33,
      label: 'low',
      is_motif_center: false,
      pagerank: 0.03,
      narrative_zh: '敘事',
    },
  ],
  edges: [
    { source: 'TAggregator01', target: 'TMule03', amount: 86000, timestamp: 1760000600 },
    { source: 'TMule03', target: 'TOtcOut01', amount: 86000, timestamp: 1760001200 },
  ],
  meta: {
    node_count: 3,
    total_node_count: 3,
    edge_count: 2,
    truncated: false,
    story_zh: null,
    degraded: false,
  },
}

describe('toElements', () => {
  it('每個節點與每條邊各產生一個元素', () => {
    expect(toElements(payload, { scheme: 'role' })).toHaveLength(5)
  })

  it('節點帶入標籤與角色供樣式使用', () => {
    const node = toElements(payload, { scheme: 'role' }).find((el) => el.data.id === 'TMule03')
    expect(node?.data.roleZh).toBe('車手地址')
    expect(node?.data.score).toBe(0.42)
  })

  it('命中圖樣的節點被標記，供工作台加外框', () => {
    const node = toElements(payload, { scheme: 'risk' }).find(
      (el) => el.data.id === 'TAggregator01',
    )
    expect(node?.data.motifCenter).toBe(true)
  })

  it('高亮路徑上的邊被標記', () => {
    const elements = toElements(payload, {
      scheme: 'role',
      highlightPath: ['TAggregator01', 'TMule03', 'TOtcOut01'],
    })
    expect(elements.filter((el) => el.data.highlighted === true)).toHaveLength(2)
  })

  it('不在路徑上的邊不被標記', () => {
    const elements = toElements(payload, {
      scheme: 'role',
      highlightPath: ['TMule03', 'TOtcOut01'],
    })
    expect(elements.filter((el) => el.data.highlighted === true)).toHaveLength(1)
  })

  it('沒有高亮路徑時所有邊都不標記', () => {
    const elements = toElements(payload, { scheme: 'role' })
    expect(elements.some((el) => el.data.highlighted === true)).toBe(false)
  })
})

describe('nodeColor（role 配色：劇本圖）', () => {
  it('focus 節點用金色，優先於其他規則', () => {
    expect(nodeColor(payload.nodes[0], { scheme: 'role', focus: 'TAggregator01' })).toBe('#f1c40f')
  })

  it('命中圖樣的節點用紅色', () => {
    expect(nodeColor(payload.nodes[0], { scheme: 'role' })).toBe('#e74c3c')
  })

  it('高分節點即使沒命中圖樣也用紅色', () => {
    expect(nodeColor({ ...payload.nodes[1], score: 0.8 }, { scheme: 'role' })).toBe('#e74c3c')
  })

  it('其餘節點依角色著色', () => {
    expect(nodeColor(payload.nodes[1], { scheme: 'role' })).toBe('#e67e22')
    expect(nodeColor(payload.nodes[2], { scheme: 'role' })).toBe('#9b59b6')
  })
})

describe('nodeColor（risk 配色：工作台）', () => {
  // 範例圖與真實 TRON 圖沒有 role，全部是 normal；只靠角色著色會整片單色。
  const normal = (score: number): GraphPayload['nodes'][number] => ({
    ...payload.nodes[1],
    role: 'normal',
    role_zh: '正常交易地址',
    is_motif_center: false,
    score,
  })

  it('高分紅、中分琥珀、低分藍——三段都不同', () => {
    expect(nodeColor(normal(0.85), { scheme: 'risk' })).toBe('#e74c3c')
    expect(nodeColor(normal(0.55), { scheme: 'risk' })).toBe('#f5b041')
    expect(nodeColor(normal(0.12), { scheme: 'risk' })).toBe('#5dade2')
  })

  it('風險配色忽略角色，同分數不因角色而異色', () => {
    const asMule = { ...normal(0.12), role: 'mule' }
    expect(nodeColor(asMule, { scheme: 'risk' })).toBe(nodeColor(normal(0.12), { scheme: 'risk' }))
  })

  it('focus 仍然優先', () => {
    expect(nodeColor(normal(0.12), { scheme: 'risk', focus: 'TMule03' })).toBe('#f1c40f')
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd web && npm test`
Expected: FAIL — 找不到 `./elements`

- [ ] **Step 3: 寫轉換函式**

`web/src/graph/elements.ts`：

```ts
import type { ElementDefinition } from 'cytoscape'
import type { GraphNode, GraphPayload } from '../api/types'

/** 角色色碼沿用 chainlens/app/workbench.py 的 ROLE_COLOR，與既有截圖保持一致。 */
const ROLE_COLOR: Record<string, string> = {
  victim: '#f5b041',
  support: '#e74c3c',
  aggregator: '#c0392b',
  mule: '#e67e22',
  peel: '#d35400',
  peel_side: '#7f8c8d',
  otc: '#9b59b6',
  normal: '#5dade2',
}

const FOCUS_COLOR = '#f1c40f'
const HIT_COLOR = '#e74c3c'
const MED_COLOR = '#f5b041'
const LOW_COLOR = '#5dade2'
const HIGH_SCORE = 0.7
const MED_SCORE = 0.4

/**
 * role＝劇本圖，沿用 Streamlit 的角色語意配色。
 * risk＝工作台，範例圖與真實 TRON 圖沒有 role 屬性（全是 normal），
 *       只靠角色著色會渲染成整片單色，故改用分數色階。
 */
export type ColorScheme = 'role' | 'risk'

export function nodeColor(
  node: GraphNode,
  options: { scheme: ColorScheme; focus?: string },
): string {
  if (options.focus && node.id === options.focus) return FOCUS_COLOR
  if (options.scheme === 'risk') {
    if (node.score >= HIGH_SCORE) return HIT_COLOR
    if (node.score >= MED_SCORE) return MED_COLOR
    return LOW_COLOR
  }
  if (node.is_motif_center || node.score >= HIGH_SCORE) return HIT_COLOR
  return ROLE_COLOR[node.role] ?? ROLE_COLOR.normal
}

export function toElements(
  payload: GraphPayload,
  options: { scheme: ColorScheme; highlightPath?: string[]; focus?: string },
): ElementDefinition[] {
  const { scheme, highlightPath = [], focus } = options
  const pathEdges = new Set(
    highlightPath.slice(0, -1).map((from, index) => `${from}->${highlightPath[index + 1]}`),
  )

  const nodes: ElementDefinition[] = payload.nodes.map((node) => ({
    data: {
      id: node.id,
      label: node.id.length > 14 ? `${node.id.slice(0, 14)}…` : node.id,
      roleZh: node.role_zh,
      score: node.score,
      narrative: node.narrative_zh,
      color: nodeColor(node, { scheme, focus }),
      size: 16 + node.pagerank * 300,
      focused: focus === node.id,
      motifCenter: node.is_motif_center,
    },
  }))

  const edges: ElementDefinition[] = payload.edges.map((edge, index) => ({
    data: {
      id: `e${index}`,
      source: edge.source,
      target: edge.target,
      amount: edge.amount,
      highlighted: pathEdges.has(`${edge.source}->${edge.target}`),
    },
  }))

  return [...nodes, ...edges]
}
```

- [ ] **Step 4: 跑測試確認通過**

Run: `cd web && npm test`
Expected: 23 passed

- [ ] **Step 5: 寫渲染元件**

`web/src/graph/GraphView.tsx`：

```tsx
import cytoscape from 'cytoscape'
import dagre from 'cytoscape-dagre'
import { useEffect, useRef } from 'react'
import type { GraphPayload } from '../api/types'
import { type ColorScheme, toElements } from './elements'

cytoscape.use(dagre)

const STYLE: cytoscape.StylesheetJson = [
  {
    selector: 'node',
    style: {
      'background-color': 'data(color)',
      width: 'data(size)',
      height: 'data(size)',
      label: 'data(label)',
      color: '#e6edf3',
      'font-size': 9,
      'font-family': 'ui-monospace, Menlo, monospace',
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'border-width': 0,
    },
  },
  {
    // 工作台用分數色階時，命中圖樣的節點靠外框而非填色來標示
    selector: 'node[?motifCenter]',
    style: { 'border-width': 2, 'border-color': '#e74c3c' },
  },
  {
    selector: 'node[?focused]',
    style: { 'border-width': 4, 'border-color': '#f1c40f' },
  },
  {
    selector: 'edge',
    style: {
      width: 1,
      'line-color': '#2b3947',
      'target-arrow-color': '#2b3947',
      'target-arrow-shape': 'triangle',
      'arrow-scale': 0.7,
      'curve-style': 'bezier',
    },
  },
  {
    selector: 'edge[?highlighted]',
    style: { width: 5, 'line-color': '#f39c12', 'target-arrow-color': '#f39c12' },
  },
]

export function GraphView({
  payload,
  highlightPath,
  focus,
  layout,
  scheme,
  onSelect,
}: {
  payload: GraphPayload
  highlightPath?: string[]
  focus?: string
  /** dagre＝劇本圖由左至右說故事；cose＝真實 2-hop 圖沒有敘事順序 */
  layout: 'dagre' | 'cose'
  scheme: ColorScheme
  onSelect?: (nodeId: string) => void
}) {
  const container = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!container.current) return
    const cy = cytoscape({
      container: container.current,
      elements: toElements(payload, { scheme, highlightPath, focus }),
      style: STYLE,
      layout:
        layout === 'dagre'
          ? { name: 'dagre', rankDir: 'LR', nodeSep: 18, rankSep: 90 }
          : { name: 'cose', randomize: false, animate: false },
      minZoom: 0.2,
      maxZoom: 2.5,
    })
    if (onSelect) {
      cy.on('tap', 'node', (event) => onSelect(event.target.id() as string))
    }
    return () => cy.destroy()
  }, [payload, highlightPath, focus, layout, scheme, onSelect])

  return (
    <div
      ref={container}
      data-testid="graph-view"
      className="h-[520px] w-full rounded border border-line"
      style={{ backgroundColor: 'var(--color-graph-bg)' }}
    />
  )
}
```

- [ ] **Step 6: 確認建置通過並提交**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: 23 passed；建置成功

```bash
git add web/src/graph
git commit -m "feat(web): add Cytoscape graph view with role-aware colouring"
```

---

## Task 8: 出金審查頁

網站的核心。對應 `docs/DEMO_SCRIPT.md` 的五步演示動線。

**Files:**
- Create: `web/src/components/DecisionCard.tsx`、`web/src/components/DecisionCard.test.tsx`
- Modify: `web/src/pages/Screening.tsx`

**Interfaces:**
- Consumes: `postScreen`、`ApiError`、`SCREENING_SNAPSHOT`、`GraphView`、`Panel`、`RiskBadge`、`ErrorNotice`
- Produces: `<DecisionCard result: ScreenResult>`

- [ ] **Step 1: 寫 DecisionCard 的失敗測試**

`web/src/components/DecisionCard.test.tsx`：

```tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { ScreenResult } from '../api/types'
import { DecisionCard } from './DecisionCard'

const blocked: ScreenResult = {
  target: 'TOtcOut01',
  amount_usdt: 500000,
  risk_score: 0.7307,
  self_score: 0.3268,
  association_score: 0.6,
  decision: 'block',
  decision_zh: '暫緩出金並啟動人工審查',
  narrative_zh: '敘事',
  associations: [
    {
      risky_node: 'TAggregator01',
      distance: 2,
      path: ['TAggregator01', 'TMule03', 'TOtcOut01'],
      motifs: ['fan_in', 'fan_out', 'gather_scatter'],
    },
  ],
  evidence: null,
  str_draft_zh: '草稿',
  graph: {
    nodes: [],
    edges: [],
    meta: {
      node_count: 0,
      total_node_count: 0,
      edge_count: 0,
      truncated: false,
      story_zh: null,
      degraded: false,
    },
  },
  highlight_path: ['TAggregator01', 'TMule03', 'TOtcOut01'],
}

describe('DecisionCard', () => {
  it('顯示綜合風險與處置建議', () => {
    render(<DecisionCard result={blocked} />)
    expect(screen.getByText('0.73')).toBeDefined()
    expect(screen.getByText('暫緩出金並啟動人工審查')).toBeDefined()
  })

  it('拆解自身分數與關聯分數——這是 Demo 的論點', () => {
    render(<DecisionCard result={blocked} />)
    expect(screen.getByText('0.33')).toBeDefined()
    expect(screen.getByText('0.60')).toBeDefined()
  })

  it('放行時顯示放行文案', () => {
    render(
      <DecisionCard
        result={{ ...blocked, decision: 'pass', decision_zh: '予以放行', risk_score: 0.0962 }}
      />,
    )
    expect(screen.getByText('予以放行')).toBeDefined()
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

Run: `cd web && npm test`
Expected: FAIL — 找不到 `./DecisionCard`

- [ ] **Step 3: 寫 DecisionCard**

`web/src/components/DecisionCard.tsx`：

```tsx
import type { Decision, ScreenResult } from '../api/types'
import { Panel } from './Panel'
import { RiskBadge } from './RiskBadge'

const DECISION_COLOR: Record<Decision, string> = {
  block: 'var(--color-risk-high)',
  review: 'var(--color-risk-med)',
  pass: 'var(--color-risk-low)',
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-muted">{label}</div>
      <div className="tabular mt-1 text-2xl">{value}</div>
    </div>
  )
}

export function DecisionCard({ result }: { result: ScreenResult }) {
  return (
    <Panel title="審查決策">
      <div className="grid grid-cols-2 gap-6 md:grid-cols-4">
        <div>
          <div className="text-xs text-muted">綜合風險分數</div>
          <div className="mt-1">
            <RiskBadge
              score={result.risk_score}
              label={result.risk_score >= 0.7 ? 'high' : result.risk_score >= 0.4 ? 'medium' : 'low'}
            />
          </div>
        </div>
        <Metric label="自身結構分數" value={result.self_score.toFixed(2)} />
        <Metric label="關聯風險分數" value={result.association_score.toFixed(2)} />
        <div>
          <div className="text-xs text-muted">處置建議</div>
          <div
            className="mt-1 text-lg font-semibold"
            style={{ color: DECISION_COLOR[result.decision] }}
          >
            {result.decision_zh}
          </div>
        </div>
      </div>

      <p
        className="mt-5 rounded border-l-2 pl-4 text-sm leading-relaxed text-ink"
        style={{ borderColor: DECISION_COLOR[result.decision] }}
      >
        {result.narrative_zh}
      </p>
    </Panel>
  )
}
```

- [ ] **Step 4: 寫出金審查頁**

`web/src/pages/Screening.tsx`：

```tsx
import { useState } from 'react'
import { ApiError, postScreen } from '../api/client'
import { SCREENING_SNAPSHOT } from '../api/snapshot'
import type { ScreenResult } from '../api/types'
import { DecisionCard } from '../components/DecisionCard'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { GraphView } from '../graph/GraphView'

const TARGETS = [
  { value: 'TOtcOut01', label: 'TOtcOut01（本案：未通報之 OTC 收款地址）' },
  { value: 'TNormalUser01', label: 'TNormalUser01（對照組：正常用戶地址）' },
]

const MOTIF_ZH: Record<string, string> = {
  fan_in: '集資扇入',
  fan_out: '快速分散',
  gather_scatter: '集散（smurfing）',
  peeling_chain: '剝洋蔥鏈',
}

export default function Screening() {
  const [target, setTarget] = useState(TARGETS[0].value)
  const [amount, setAmount] = useState(500000)
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(await postScreen(target, amount))
      setOffline(false)
    } catch (err) {
      // 連線完全失敗時退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      if (err instanceof ApiError && err.status === 0 && target === 'TOtcOut01') {
        setResult(SCREENING_SNAPSHOT)
        setOffline(true)
      } else {
        setError(err instanceof ApiError ? err.detail : '審查失敗，請稍後再試。')
      }
    } finally {
      setLoading(false)
    }
  }

  function downloadStr() {
    if (!result?.str_draft_zh) return
    const url = URL.createObjectURL(new Blob([result.str_draft_zh], { type: 'text/plain' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `STR_draft_${result.target}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">出金審查</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          交易所用戶申請將 50 萬 USDT 提領至外部地址。該地址從未被通報、不在任何黑名單上——
          傳統名單比對會直接放行。以下展示結構化關聯追溯如何攔下它。
        </p>
      </div>

      <Panel>
        <div className="grid gap-4 md:grid-cols-[2fr_1fr_auto] md:items-end">
          <label className="block">
            <span className="text-xs text-muted">出金目標地址</span>
            <select
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            >
              {TARGETS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs text-muted">申請金額（USDT）</span>
            <input
              type="number"
              min={1}
              step={10000}
              value={amount}
              onChange={(event) => setAmount(Number(event.target.value))}
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            />
          </label>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '審查中…' : '執行出金審查'}
          </button>
        </div>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {offline && (
        <ErrorNotice message="目前顯示的是內建離線快照，非即時查詢結果。" />
      )}

      {result && (
        <>
          <DecisionCard result={result} />

          {result.associations.length > 0 && (
            <Panel title="資金關聯證據鏈">
              <ul className="space-y-3 text-sm">
                {result.associations.map((association) => (
                  <li key={association.risky_node} className="border-l-2 border-line pl-4">
                    <div className="tabular">
                      {association.risky_node}
                      <span className="ml-2 text-muted">{association.distance} 階關聯</span>
                    </div>
                    <div className="mt-1 text-muted">
                      命中圖樣：
                      {association.motifs.map((m) => MOTIF_ZH[m] ?? m).join('、')}
                    </div>
                    <div className="tabular mt-1 text-xs text-muted">
                      {association.path.join(' → ')}
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="金流圖譜（橘色路徑＝風險資金流向出金地址；金色＝審查目標）">
            <GraphView
              payload={result.graph}
              highlightPath={result.highlight_path}
              focus={result.target}
              layout="dagre"
              scheme="role"
            />
          </Panel>

          {result.str_draft_zh && (
            <Panel
              title="可疑交易申報（STR）草稿"
              actions={
                <button
                  type="button"
                  onClick={downloadStr}
                  className="rounded border border-line px-3 py-1 text-sm"
                >
                  下載草稿（.txt）
                </button>
              }
            >
              <pre className="tabular max-h-96 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-muted">
                {result.str_draft_zh}
              </pre>
            </Panel>
          )}

          <Panel title="結構證據 JSON（稽核軌跡）">
            <pre className="tabular max-h-96 overflow-auto text-xs text-muted">
              {JSON.stringify(result.evidence, null, 2)}
            </pre>
          </Panel>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 5: 跑測試與建置確認通過**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: 26 passed；建置成功

- [ ] **Step 6: 提交**

```bash
git add web/src
git commit -m "feat(web): build the withdrawal screening demo page"
```

---

## Task 9: 金流圖譜工作台頁

自由探索模式。真實 TRON 查詢誠實回錯並提供一鍵切換範例圖。

**Files:**
- Modify: `web/src/pages/Workbench.tsx`

**Interfaces:**
- Consumes: `postGraph`、`ApiError`、`GraphView`、`Panel`、`ErrorNotice`、`WorkbenchPayload`

- [ ] **Step 1: 寫實作**

`web/src/pages/Workbench.tsx`：

```tsx
import { useCallback, useEffect, useState } from 'react'
import { ApiError, postGraph } from '../api/client'
import type { GraphNode, WorkbenchPayload } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { GraphView } from '../graph/GraphView'

const TRON_ADDRESS = /^T[1-9A-HJ-NP-Za-km-z]{33}$/

export default function Workbench() {
  const [address, setAddress] = useState('')
  const [payload, setPayload] = useState<WorkbenchPayload | null>(null)
  const [selected, setSelected] = useState<GraphNode | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function load(mode: 'example' | 'tron') {
    setLoading(true)
    setError(null)
    try {
      const next = await postGraph(mode === 'tron' ? { mode, address } : { mode })
      setPayload(next)
      setSelected(null)
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : '載入失敗，請稍後再試。')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void load('example')
    // 只在首次掛載時載入內建範例圖
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 必須用 useCallback 穩定身分：GraphView 的 effect 依賴 onSelect 且清理時會 cy.destroy()，
  // 若每次 render 都給新的行內函式，點一次節點就會重建整張圖並重跑 cose 排版。
  const handleSelect = useCallback(
    (id: string) => setSelected(payload?.nodes.find((node) => node.id === id) ?? null),
    [payload],
  )

  const addressValid = TRON_ADDRESS.test(address)

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">金流圖譜工作台</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          內建範例圖含集資扇入、快速分散、剝洋蔥鏈三種圖樣。也可輸入 TRON 主網地址，
          即時抓取 2-hop USDT 金流圖——真實查詢約需 10–30 秒。
        </p>
      </div>

      <Panel>
        <div className="grid gap-4 md:grid-cols-[3fr_auto_auto] md:items-end">
          <label className="block">
            <span className="text-xs text-muted">TRON 地址（TRC-20 USDT）</span>
            <input
              value={address}
              onChange={(event) => setAddress(event.target.value.trim())}
              placeholder="T 開頭主網地址，34 字元"
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            />
            {address && !addressValid && (
              <span className="mt-1 block text-xs" style={{ color: 'var(--color-risk-med)' }}>
                地址格式不正確：需為 T 開頭的 Base58 主網地址（34 字元）。
              </span>
            )}
          </label>

          <button
            type="button"
            onClick={() => load('tron')}
            disabled={!addressValid || loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-40"
          >
            {loading ? '查詢中…' : '抓取真實金流'}
          </button>

          <button
            type="button"
            onClick={() => load('example')}
            disabled={loading}
            className="rounded border border-line px-5 py-2"
          >
            用內建範例圖
          </button>
        </div>
      </Panel>

      {error && (
        <ErrorNotice
          message={error}
          action={{ label: '改用內建範例圖', onClick: () => load('example') }}
        />
      )}

      {payload && (
        <>
          <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
            <Panel
              title={`金流圖譜（${payload.meta.node_count} 節點 / ${payload.meta.edge_count} 邊）`}
            >
              <GraphView
                payload={payload}
                layout="cose"
                scheme="risk"
                onSelect={handleSelect}
              />
              {payload.meta.truncated && (
                <p className="mt-3 text-xs" style={{ color: 'var(--color-risk-med)' }}>
                  圖譜顯示風險最高的 {payload.meta.node_count} 個節點（原始共{' '}
                  {payload.meta.total_node_count} 個）。完整連線見下方鄰接表。
                </p>
              )}
              <p className="mt-3 text-xs text-muted">點選節點查看該地址的風險證據。</p>
            </Panel>

            <Panel title="風險證據">
              {selected ? (
                <div className="space-y-3">
                  <div className="tabular text-sm">{selected.id}</div>
                  <div className="tabular text-3xl">{selected.score.toFixed(2)}</div>
                  <p className="text-sm leading-relaxed text-muted">{selected.narrative_zh}</p>
                </div>
              ) : (
                <p className="text-sm text-muted">尚未選取節點。</p>
              )}
            </Panel>
          </div>

          <Panel title="資金流向明細（鄰接表）">
            <p className="mb-3 text-xs text-muted">
              圖譜對螢幕閱讀器不可讀，此表為等效的文字替代，列出圖中每一條資金流向。
            </p>
            <div className="max-h-80 overflow-auto">
              <table className="tabular w-full text-left text-xs">
                <caption className="sr-only">
                  金流圖譜的鄰接表，欄位為來源地址、目標地址與轉帳金額
                </caption>
                <thead className="sticky top-0 bg-panel text-muted">
                  <tr>
                    <th scope="col" className="py-2 pr-4 font-normal">來源</th>
                    <th scope="col" className="py-2 pr-4 font-normal">目標</th>
                    <th scope="col" className="py-2 pr-4 font-normal">金額（USDT）</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.edges.map((edge) => (
                    <tr key={`${edge.source}->${edge.target}`} className="border-t border-line">
                      <td className="py-2 pr-4">{edge.source}</td>
                      <td className="py-2 pr-4">{edge.target}</td>
                      <td className="py-2 pr-4">{edge.amount.toLocaleString('zh-TW')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="SNA 指標（依風險分數排序前 15 名）">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-xs">
                <thead className="text-muted">
                  <tr>
                    {['地址', 'in', 'out', 'PageRank', 'k-core', 'betweenness', '分數'].map(
                      (head) => (
                        <th key={head} className="py-2 pr-4 font-normal">
                          {head}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {payload.sna.map((row) => (
                    <tr key={row.node} className="border-t border-line">
                      <td className="py-2 pr-4">{row.node}</td>
                      <td className="py-2 pr-4">{row.in_degree.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.out_degree.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.pagerank.toFixed(4)}</td>
                      <td className="py-2 pr-4">{row.kcore.toFixed(0)}</td>
                      <td className="py-2 pr-4">{row.betweenness.toFixed(4)}</td>
                      <td className="py-2 pr-4">{row.score.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 跑測試與建置確認通過**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: 26 passed；建置成功

- [ ] **Step 3: 提交**

```bash
git add web/src/pages/Workbench.tsx
git commit -m "feat(web): build the money-flow graph workbench page"
```

---

## Task 10: 首頁與研究成果頁

兩頁都是靜態內容，資料來自 `README.md`。

**Files:**
- Modify: `web/src/pages/Landing.tsx`、`web/src/pages/Research.tsx`

- [ ] **Step 1: 寫首頁**

`web/src/pages/Landing.tsx`：

依「即時／維運型」落地頁結構：Hero（含服務即時狀態）→ 關鍵指標 → 運作方式 → CTA。

```tsx
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkHealth } from '../api/client'
import { Panel } from '../components/Panel'

const METRICS = [
  { value: '0.806', label: '最佳模型 F1', note: 'Random Forest，illicit 類別' },
  { value: '0.795', label: 'PR-AUC', note: '遵守官方時間切分，無資料洩漏' },
  { value: '203k', label: 'Elliptic 節點數', note: '公開比特幣交易圖基準' },
  { value: '4', label: '洗錢圖樣規則', note: '扇入／分散／集散／剝洋蔥' },
]

const FLOW = [
  { stage: '資料層', detail: 'Elliptic 203k 節點 BTC 交易圖／TronGrid TRC-20 USDT 2-hop 圖' },
  { stage: '分析層', detail: 'SNA 指標、Louvain 社群偵測、詐騙圖樣規則' },
  { stage: '模型層', detail: 'GCN／GraphSAGE（PyTorch Geometric）、Random Forest 基線' },
  { stage: '解釋層', detail: '風險證據產生器、出金審查引擎、STR 草稿' },
]

const PILLARS = [
  {
    title: '結構證據，不是黑箱分數',
    body: '每個風險判定都附中心性百分位、社群風險佔比與命中的資金圖樣，法遵人員看得懂、稽核追得到。',
  },
  {
    title: '不依賴黑名單',
    body: '從未被通報的地址，仍可經由上游關聯追溯攔下——集資扇入、快速分散、剝洋蔥鏈由圖樣庫主動掃出。',
  },
  {
    title: '人在迴路中',
    body: '高風險的處置是「暫緩並啟動人工審查」而非直接拒絕，並自動產出 STR 草稿作為人工審查的起點。',
  },
]

function ServiceStatus() {
  const [online, setOnline] = useState<boolean | null>(null)
  useEffect(() => {
    void checkHealth().then(setOnline)
  }, [])

  const color =
    online === null
      ? 'var(--color-muted)'
      : online
        ? 'var(--color-risk-low)'
        : 'var(--color-risk-med)'
  const text = online === null ? '檢查分析服務…' : online ? '分析服務運作中' : '分析服務未回應'

  return (
    <span className="inline-flex items-center gap-2 text-sm" style={{ color }}>
      {/* 狀態不只靠顏色傳達，同時有文字說明 */}
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {text}
    </span>
  )
}

export default function Landing() {
  return (
    <div className="space-y-12">
      <section className="py-8">
        <ServiceStatus />
        <h1 className="mt-4 text-4xl font-semibold leading-tight">
          鏈鏡 <span className="text-muted">ChainLens</span>
        </h1>
        <p className="mt-3 text-xl text-muted">基於社會網路分析之虛擬資產詐騙金流偵測平台</p>
        <p className="mt-5 max-w-2xl leading-relaxed text-muted">
          以社會網路分析（SNA）與圖神經網路（GNN）偵測虛擬資產詐騙金流，
          服務對象為 VASP 業者的法遵篩查。核心賣點是可解釋性。
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/screening" className="rounded bg-ink px-5 py-2 font-semibold text-base">
            看 50 萬 USDT 攔阻 Demo
          </Link>
          <Link to="/workbench" className="rounded border border-line px-5 py-2">
            自己試查一個地址
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-sm text-muted">關鍵指標</h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {METRICS.map((metric) => (
            <Panel key={metric.label}>
              <div className="tabular text-3xl font-semibold">{metric.value}</div>
              <div className="mt-1 text-sm">{metric.label}</div>
              <div className="mt-1 text-xs text-muted">{metric.note}</div>
            </Panel>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-sm text-muted">運作方式</h2>
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="四層架構">
            <ol className="space-y-3">
              {FLOW.map((step, index) => (
                <li key={step.stage} className="flex gap-4">
                  <span className="tabular w-6 shrink-0 text-muted">{index + 1}</span>
                  <div>
                    <div className="font-semibold">{step.stage}</div>
                    <div className="text-sm text-muted">{step.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          <div className="space-y-5">
            {PILLARS.map((pillar) => (
              <Panel key={pillar.title} title={pillar.title}>
                <p className="text-sm leading-relaxed text-muted">{pillar.body}</p>
              </Panel>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-8 text-center">
        <h2 className="text-xl font-semibold">看它攔下一筆黑名單攔不住的出金</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted">
          目標地址從未被通報、自身結構分數只有 0.33。真正攔下它的是上游二階的資金關聯。
        </p>
        <Link
          to="/screening"
          className="mt-6 inline-block rounded bg-ink px-6 py-2.5 font-semibold text-base"
        >
          執行出金審查 Demo
        </Link>
      </section>
    </div>
  )
}
```

- [ ] **Step 2: 寫研究成果頁**

`web/src/pages/Research.tsx`：

```tsx
import { Panel } from '../components/Panel'

const METRICS = [
  { model: 'GCN', features: '原始 165 維', p: 0.48, r: 0.535, f1: 0.506, auc: 0.524 },
  { model: 'GraphSAGE', features: '原始 165 維', p: 0.581, r: 0.666, f1: 0.62, auc: 0.671 },
  { model: 'GraphSAGE', features: '原始 + SNA（消融）', p: 0.552, r: 0.66, f1: 0.601, auc: 0.648 },
  { model: 'GraphSAGE + RMP', features: '原始 165 維', p: 0.707, r: 0.621, f1: 0.661, auc: 0.692 },
  { model: 'Random Forest', features: '原始 165 維', p: 0.907, r: 0.725, f1: 0.806, auc: 0.795 },
]

const FINDINGS = [
  {
    title: 'Random Forest 仍是最強基線',
    body: 'F1 0.806、PR-AUC 0.795，重現 Weber et al. 2019 的 RF≈0.79–0.83。GNN 未必優於樹模型。',
  },
  {
    title: 'Reverse message passing 讓 GraphSAGE F1 +4.1pp',
    body: '0.620 → 0.661。有向交易圖的入邊與出邊訊號確實互補（AAAI 2024 Multi-GNN）。',
  },
  {
    title: '串接 SNA 特徵未提升 F1',
    body: '0.601 vs 0.620。GNN 的訊息傳遞已隱含學到局部結構——SNA 在本系統的價值在可解釋層，不在特徵層。',
  },
]

export default function Research() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">研究成果</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          遵守 Elliptic 官方時間切分（train ≤ 34 期 / test ≥ 35 期）避免資料洩漏。
          以下為 illicit 類別指標，五列為同一次完整資料集實測。
        </p>
      </div>

      <Panel title="模型指標（illicit 類別）">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-muted">
              <tr>
                {['模型', '特徵', 'Precision', 'Recall', 'F1', 'PR-AUC'].map((head) => (
                  <th key={head} className="py-2 pr-4 font-normal">
                    {head}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {METRICS.map((row) => (
                <tr key={`${row.model}-${row.features}`} className="border-t border-line">
                  <td className="py-2 pr-4">{row.model}</td>
                  <td className="py-2 pr-4 text-muted">{row.features}</td>
                  <td className="tabular py-2 pr-4">{row.p.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.r.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.f1.toFixed(3)}</td>
                  <td className="tabular py-2 pr-4">{row.auc.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          訓練設定：CPU、200 epochs、hidden 64、lr 0.01、加權 CrossEntropy（逆類別頻率）、
          weight decay 5e-4、seed 42；SNA 特徵為 in/out degree、PageRank、k-core、
          近似 betweenness（64 源點）之 z-score。
        </p>
      </Panel>

      <section className="grid gap-5 md:grid-cols-3">
        {FINDINGS.map((finding) => (
          <Panel key={finding.title} title={finding.title}>
            <p className="text-sm leading-relaxed text-muted">{finding.body}</p>
          </Panel>
        ))}
      </section>

      <Panel title="研究基礎">
        <p className="text-sm leading-relaxed text-muted">
          設計選擇與改進方向根據對 14 個主流研究方向的深度調查：Elliptic／Elliptic2 基準、
          IBM Multi-GNN、時序 GNN、洗錢 typology、異質性 GNN、GNN 可解釋性、LLM + 圖、
          TRON／USDT 實證、商用系統、聯邦與隱私 AML 等。完整定位、五大領域痛點對應表與
          Roadmap 見 repo 的 <span className="tabular">docs/RESEARCH.md</span>。
        </p>
      </Panel>
    </div>
  )
}
```

- [ ] **Step 3: 跑測試與建置確認通過**

Run: `cd web && npm run typecheck && npm test && npm run build`
Expected: 26 passed；建置成功

- [ ] **Step 4: 提交**

```bash
git add web/src/pages
git commit -m "feat(web): build the landing and research pages"
```

---

## Task 11: 端對端冒煙測試與部署文件

確認 Demo 動線真的跑得完，並寫下部署步驟。

**Files:**
- Create: `web/playwright.config.ts`、`web/e2e/screening.spec.ts`、`web/.env.example`
- Modify: `web/package.json`、`README.md`

- [ ] **Step 1: 安裝 Playwright**

```bash
cd web && npm install -D @playwright/test && npx playwright install chromium
```

- [ ] **Step 2: 寫設定**

`web/playwright.config.ts`：

```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  use: { baseURL: 'http://localhost:4173' },
  webServer: {
    command: 'npm run build && npm run preview -- --port 4173',
    port: 4173,
    reuseExistingServer: true,
    timeout: 120_000,
  },
})
```

`web/package.json` 的 `scripts` 加入：

```json
"e2e": "playwright test"
```

`web/.env.example`：

```
# 後端 API 位址。本機開發指向 http://localhost:8000（先跑 make api）
VITE_API_BASE=https://chain-lens-beta.vercel.app
```

- [ ] **Step 3: 寫冒煙測試**

`web/e2e/screening.spec.ts`：

```ts
import { expect, test } from '@playwright/test'

test('出金審查 Demo 全流程', async ({ page }) => {
  await page.goto('/screening')

  await expect(page.getByRole('heading', { name: '出金審查' })).toBeVisible()

  await page.getByRole('button', { name: '執行出金審查' }).click()

  // 決策卡：綜合風險 0.73 → 暫緩出金
  await expect(page.getByText('0.73')).toBeVisible({ timeout: 30_000 })
  await expect(page.getByText('暫緩出金並啟動人工審查')).toBeVisible()

  // 論點：自身只有 0.33，風險來自關聯的 0.60
  await expect(page.getByText('0.33')).toBeVisible()
  await expect(page.getByText('0.60')).toBeVisible()

  // 圖譜有渲染出來
  await expect(page.getByTestId('graph-view')).toBeVisible()

  // STR 草稿可下載
  await expect(page.getByRole('button', { name: '下載草稿（.txt）' })).toBeVisible()
})

test('對照組不被誤殺', async ({ page }) => {
  await page.goto('/screening')
  await page.getByRole('combobox').selectOption('TNormalUser01')
  await page.getByRole('button', { name: '執行出金審查' }).click()
  await expect(page.getByText('予以放行')).toBeVisible({ timeout: 30_000 })
})

test('四個頁面都走得到', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: /鏈鏡/ })).toBeVisible()
  for (const name of ['出金審查', '金流圖譜', '研究成果']) {
    await page.getByRole('link', { name }).click()
    await expect(page.locator('h1')).toBeVisible()
  }
})
```

- [ ] **Step 4: 跑冒煙測試**

先確認後端可用（`VITE_API_BASE` 指向已部署的 API 或本機 `make api`），然後：

Run: `cd web && npm run e2e`
Expected: 3 passed

- [ ] **Step 5: 寫部署文件**

在 `README.md` 的「## 部署」章節，於 Vercel 段落之後插入：

````markdown
### Demo 網站（web/）

`web/` 是對外的 Demo 網站（Vite + React），部署為**獨立的 Vercel 專案**，
與 API 專案分開，避免動到 API 的框架偵測設定。

Vercel 專案設定：

| 欄位 | 值 |
|---|---|
| Root Directory | `web` |
| Framework Preset | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| 環境變數 | `VITE_API_BASE` = API 專案網址（例：`https://chain-lens-beta.vercel.app`） |

API 專案需設定 `CHAINLENS_CORS_ORIGINS` 為網站網址（逗號分隔可多個）；
未設定時預設全開。

本機開發：

```bash
make api                      # 終端機 A：FastAPI 於 :8000
cd web && cp .env.example .env  # 把 VITE_API_BASE 改成 http://localhost:8000
npm install && npm run dev    # 終端機 B：Vite 於 :5173
```
````

- [ ] **Step 6: 提交**

```bash
git add web README.md
git commit -m "test(web): add Playwright smoke tests and deployment docs"
```

---

## 驗收

全部任務完成後，下列每一項都必須實際跑過並看到預期輸出，才能宣稱完成：

- [ ] `.venv/Scripts/python.exe -m pytest -q` → 89 passed
- [ ] `.venv/Scripts/python.exe -m ruff check chainlens tests` → All checks passed!
- [ ] `cd web && npm run typecheck && npm test && npm run build` → 全過
- [ ] `cd web && npm run e2e` → 3 passed
- [ ] 網站部署後，實際點過四個頁面：首頁、出金審查（跑完五步）、工作台（範例圖與真實地址各一次）、研究成果
- [ ] 把瀏覽器開發者工具的網路面板關掉重整一次，確認首頁在 API 冷啟動期間仍立即顯示內容

**UI／UX 交付前檢查**

- [ ] 用鍵盤（只用 Tab 與 Enter）走完出金審查全流程，每一步的焦點都看得見
- [ ] 375px 寬檢視四個頁面，沒有水平捲動；表格在自己的容器內橫向捲動
- [ ] 開啟系統的「減少動態效果」後重整，動畫確實停止
- [ ] 沒有任何狀態只靠顏色傳達（風險等級、服務狀態、導覽位置皆有文字或字重）
- [ ] 圖譜的文字替代存在且正確：`/screening` 有關聯證據鏈、`/workbench` 有鄰接表
- [ ] 沒有 emoji 被當成圖示使用
- [ ] 用 795 節點等級的真實地址查一次，確認截斷提示出現且數字正確
