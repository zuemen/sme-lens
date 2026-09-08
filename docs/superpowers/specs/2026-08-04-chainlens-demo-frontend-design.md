# ChainLens Demo 網站前端設計

> 目標讀者：實作本設計的工程師。假設熟悉 Web 開發，但對 ChainLens 領域與程式庫一無所知。

**日期**：2026-08-04
**狀態**：已核准，待轉為實作計畫

## 一、目的與成功標準

ChainLens 目前只有兩個對外介面：FastAPI 的 `POST /score`（單點評分）與本機 Streamlit 工作台。線上沒有任何可以直接展示給評審或他人看的網站。

本設計要建一個**完整產品站**，讓人打開網址就能：

1. 理解 ChainLens 在做什麼（首頁）
2. 完整跑一次 50 萬 USDT 出金攔阻 Demo（對應 `docs/DEMO_SCRIPT.md` 的五步演示）
3. 自由探索金流圖譜，包含真實 TRON 地址查詢
4. 查閱模型指標與研究依據

**成功標準**：現場對評審演示 `docs/DEMO_SCRIPT.md` 的 2.5–3 分鐘動線，全程在瀏覽器完成，不需要開終端機或本機 Streamlit。

## 二、現況盤點

實作前必須知道的既有事實（已逐一驗證）：

| 事實 | 影響 |
|---|---|
| `screen_withdrawal()` 位於 `chainlens/explain/screening.py`，**API 完全沒有暴露**，只有 Streamlit 叫得到 | 前端無法只靠既有 API 完成，必須新增後端端點 |
| `POST /score` 只回單點評分，`evidence` 是**只含一個元素的 list** | 新端點不要沿用這個容易誤用的形狀 |
| 圖譜渲染 `build_pyvis_html()` 是 Python 端產生 HTML 字串，pyvis 只在 `workbench.py` 用到 | Web 前端需改用 JS 圖形庫，並需要回傳圖 JSON 的端點 |
| 線上 API 冷啟動實測 ~5.0 秒，暖機後 ~0.31 秒 | 排除「FastAPI 出 HTML」方案；前端須主動暖機 |
| `requirements.txt` 已含 `networkx`、`python-louvain`、`pandas`、`scipy`，但**刻意排除** `torch`、`streamlit`、`pyvis`、`scikit-learn` | 新端點所需的 `run_pipeline` / `screen_withdrawal` 不必加任何依賴 |
| 既有 Vercel 部署對框架偵測敏感（本日已因 entrypoint 與 `.vercelignore` 各壞一次） | 不動現有 API 專案的部署設定 |
| 既有測試 61 個全綠，CI 為 `.github/workflows/ci.yml` 單一 Python job | 新增測試接在後面；CI 加一個並行的 Node job |

## 三、架構

```
web/  (Vite + React 18 + TypeScript)     ← 獨立 Vercel 專案，Root Directory = web
  └ 靜態產物由 CDN 供應，首頁載入不經過 Python
        │
        │  fetch(import.meta.env.VITE_API_BASE) + CORS
        ▼
chainlens/api/main.py  (既有 Vercel 專案，部署設定不動)
  + CORSMiddleware
  + POST /screen      ← 新增
  + POST /graph       ← 新增
    GET  /score       ← 既有，不修改
    GET  /health      ← 既有，前端用來暖機
```

**為何拆成兩個 Vercel 專案**：把「新加的、會壞的東西」與「已經能跑的 API」隔開。單一專案用 rewrites 併存雖然網址較漂亮，但需要在 repo root 加 `package.json`，會改變 Vercel 的框架偵測結果——本日該偵測已造成兩次部署失敗，不值得為網址美觀冒這個險。

**暖機策略**：前端在 App 掛載時背景 `fetch(API_BASE + '/health')`，不阻塞畫面。使用者讀首頁的時間足以吃掉 5 秒冷啟動，按下審查鈕時函式已是熱的。

**一次算完**：`POST /screen` 同時回傳決策資料、圖譜與 STR 草稿。Streamlit 版本為了畫圖重複呼叫了一次 `run_pipeline()`（53 節點上重跑 SNA + Louvain + motif 偵測），新端點只算一次。

## 四、後端新增端點

### 4.1 CORS

在 `chainlens/api/main.py` 加入 `CORSMiddleware`。允許來源由環境變數 `CHAINLENS_CORS_ORIGINS` 指定（逗號分隔）；未設定時預設 `["*"]`。

必須設 `allow_credentials=False`。瀏覽器規範不允許 `allow_origins=["*"]` 與 `allow_credentials=True` 併用，且本 API 不使用 cookie 驗證——僅選配的 `X-API-Key` 標頭，該標頭需列入 `allow_headers`。

### 4.2 共用的圖 JSON 形狀

兩個新端點都回傳這個結構，前端只需要一套轉換程式碼：

```jsonc
{
  "nodes": [
    {
      "id": "TAggregator01",        // str
      "role": "aggregator",          // str，來自節點屬性 role；無此屬性時為 "normal"
      "role_zh": "集資主錢包",       // str，查 scenario.ROLE_ZH，查無則回傳 role 原字串
      "score": 0.8123,               // float，evidence["score"]
      "label": "high",               // "high" | "medium" | "low"
      "is_motif_center": true,       // bool，是否為任一 MotifHit 的 center
      "pagerank": 0.0412,            // float，取自 sna_df
      "narrative_zh": "..."          // str，evidence["narrative_zh"]
    }
  ],
  "edges": [
    {
      "source": "TVictim01",  // str
      "target": "TSupport01", // str
      "amount": 32000.0,      // float，邊屬性 amount，缺少時為 0.0
      "timestamp": 1760000600 // int | null，邊屬性 timestamp，缺少時為 null
    }
  ],
  "meta": {
    "node_count": 53,        // int，實際回傳的節點數
    "total_node_count": 53,  // int，截斷前的原始節點數
    "edge_count": 63,        // int
    "truncated": false,      // bool，是否因超過上限而截斷
    "story_zh": "...",       // str | null，圖屬性 story_zh，僅劇本圖有
    "degraded": false        // bool，是否因抓取失敗而退回範例圖
  }
}
```

**節點上限 300。** 實測每個節點的 JSON 約 500 bytes（`narrative_zh` 是多句中文敘事），
TronGrid 抓回的真實 2-hop 圖可達 795 節點 → **約 390 KB** 的回應，經冷啟動的 serverless
傳輸過慢，且 795 節點的力導向排版會糊成無法閱讀的毛球。

超過上限時，依 `score` 由高到低保留前 300 個節點與其之間的邊，並設 `truncated: true`、
`total_node_count` 為原始節點數。300 落在圖形函式庫舒適的 101–500 canvas 區間。

**截斷必須對使用者可見**，前端要顯示「圖譜顯示風險最高的 300 個節點（共 795）」，
不得靜默截斷讓人以為看到的是全圖。

**只有劇本圖有角色**：`chainlens/data/scenario.py` 的劇本圖為每個節點設了 `role` 屬性（八種），但 `tron.load_example_graph()`（25 節點 / 23 邊）與 TronGrid 抓回的真實圖**完全沒有 `role` 屬性**（實測全為 `None`）。這兩種圖的所有節點都會是 `role: "normal"` / `role_zh: "正常交易地址"`。

前端不得只依角色著色，否則工作台會渲染成整片單色而看起來像壞掉。工作台圖譜的著色主軸是 **`score` 風險色階與 `is_motif_center`**，角色色僅在劇本圖有意義。詳見 5.3。

### 4.3 `POST /screen`

**用途**：出金審查 Demo 的唯一資料來源。

**Request**：
```jsonc
{
  "target": "TOtcOut01",       // str，必填。白名單見下
  "amount_usdt": 500000.0,     // float，> 0
  "request_id": "DEMO-2026-001" // str | null，選填
}
```

**白名單**：`target` 只接受 `chainlens/data/scenario.py` 的 `WITHDRAWAL_TARGET`（`TOtcOut01`）與 `NORMAL_TARGET`（`TNormalUser01`）。其他值回 400，`detail` 為 `"target 需為劇本情境中的出金地址"`。這道限制避免端點變成任意圖計算的公開資源。

**Response 200**：`screen_withdrawal()` 的既有欄位，外加 `graph` 與 `highlight_path`。

```jsonc
{
  "target": "TOtcOut01",
  "amount_usdt": 500000.0,
  "risk_score": 0.7307,
  "self_score": 0.3268,
  "association_score": 0.6,
  "decision": "block",                      // "block" | "review" | "pass"
  "decision_zh": "暫緩出金並啟動人工審查",
  "narrative_zh": "...",
  "associations": [
    {
      "risky_node": "TAggregator01",
      "distance": 2,
      "path": ["TAggregator01", "TMule03", "TOtcOut01"],
      "motifs": ["fan_in", "fan_out", "gather_scatter"]
    }
  ],
  "evidence": { /* generate_evidence 字典，見 4.5 */ },
  "str_draft_zh": "一、交易概要\n...",       // str | null，decision == "pass" 時為 null
  "graph": { /* 4.2 的形狀 */ },
  "highlight_path": ["TAggregator01", "TMule03", "TOtcOut01"]  // list[str]，無關聯時為 []
}
```

`highlight_path` 取 `associations[0]["path"]`；`associations` 為空時回傳 `[]`。

**注意 `insufficient_data`**：`screen_withdrawal()` 在目標不在圖中時會多回一個 `"insufficient_data": true`，**正常路徑則完全沒有這個鍵**（不是 `false`）。前端必須用可選存取。因為有白名單，此路徑在正式流程中不會發生，但契約仍須保留。

**已驗證的實際輸出值**（實作時可直接寫進測試斷言）：

| target | risk_score | self_score | association_score | decision | associations 筆數 | str_draft_zh |
|---|---|---|---|---|---|---|
| `TOtcOut01` @ 500000 | 0.7307 | 0.3268 | 0.6 | `block` | 6 | 有 |
| `TNormalUser01` @ 500000 | 0.0962 | 0.0962 | 0.0 | `pass` | 0 | `null` |

`TOtcOut01` 的六筆關聯依序為：`TAggregator01`（距離 2）、`TSupport01/02/03`（距離 3）、`TMule01`、`TMule02`（距離 4）。

**這就是整個 Demo 的論點**：`TOtcOut01` 自身命中零個圖樣、自身分數只有 0.33（label 為 `low`），名單比對與單點特徵都攔不住它；風險完全來自上游二階關聯的 0.60。

### 4.4 `POST /graph`

**用途**：金流圖譜工作台的資料來源。

**Request**：
```jsonc
{
  "mode": "example",   // "example" | "tron"
  "address": null      // str | null；mode == "tron" 時必填
}
```

**Response 200**：4.2 的圖結構，外加 `sna` 欄位——依 `score` 由高到低排序的前 15 個節點：

```jsonc
{
  "nodes": [ /* ... */ ],
  "edges": [ /* ... */ ],
  "meta": { /* ... */ },
  "sna": [
    {
      "node": "TScamCollector001",
      "in_degree": 8.0,
      "out_degree": 2.0,
      "pagerank": 0.0412,
      "kcore": 1.0,
      "betweenness": 0.0231,
      "score": 0.8944
    }
  ]
}
```

**錯誤碼**（沿用 `/score` 既有的處理方式與訊息）：

| 狀態碼 | 條件 | `detail` |
|---|---|---|
| 400 | `mode == "tron"` 但缺 `address` | `"tron 模式需提供 address"` |
| 400 | 地址不符 `^T[1-9A-HJ-NP-Za-km-z]{33}$` | `"address 需為合法 TRON 主網地址（T 開頭 Base58 34 字元）"` |
| 404 | 抓到的圖沒有 USDT 轉帳 | `f"地址 {address} 查無 USDT 轉帳"` |
| 502 | TronGrid `httpx.HTTPError` | `f"TronGrid 抓取失敗：{exc.__class__.__name__}"` |

TRON 模式**不做**自動退回範例圖。Streamlit 版本會靜默降級，但那會讓使用者以為看到的是真實資料。API 誠實回錯，由前端顯示明確訊息並提供一鍵切換。

### 4.5 `evidence` 字典形狀（既有，供前端參考）

`generate_evidence()` 回傳的字典，`/screen` 與 `/graph` 都會用到：

```jsonc
{
  "score": 0.3268,                  // float
  "label": "low",                   // "high" | "medium" | "low"
  "top_features": ["in_degree", "pagerank", "kcore"],  // list[str]，3 個
  "centrality_percentile": {        // dict[str, float]，0–100
    "in_degree": 88.68, "out_degree": 0.0, "pagerank": 88.68,
    "kcore": 33.96, "betweenness": 0.0
  },
  "community_risk_ratio": 1.0,      // float 0–1
  "motif_hits": [                   // list[dict]，只含 center == 該節點的命中
    {
      "motif": "fan_in",            // "fan_in"|"fan_out"|"gather_scatter"|"peeling_chain"
      "center": "TScamCollector001",
      "nodes": ["..."],
      "description_zh": "..."
    }
  ],
  "narrative_zh": "..."             // str
}
```

## 五、前端

### 5.1 技術選型

| 項目 | 選擇 | 理由 |
|---|---|---|
| 建置 | Vite + React 18 + TypeScript | 靜態產物、Vercel 一等支援 |
| 路由 | React Router | 四頁多頁站 |
| 圖譜 | Cytoscape.js + `cytoscape-dagre` | 見 5.3 |
| 樣式 | Tailwind CSS | 深色主題與設計 token 好管理 |
| 單元測試 | Vitest | 與 Vite 同源 |
| 端對端 | Playwright | 跑 Demo 全流程冒煙 |

### 5.2 頁面

| 路由 | 內容 |
|---|---|
| `/` | 依「即時／維運型」落地頁結構：① Hero（定位 + 服務即時狀態）② 關鍵指標 ③ 運作方式（四層架構）④ CTA。主要 CTA 同時出現在導覽列與指標區之後 |
| `/screening` | 五步 Demo：目標與金額輸入 → 決策卡 → 金流圖譜 → STR 草稿（可下載 `.txt`） → 證據 JSON 展開 |
| `/workbench` | 範例圖 / 真實 TRON 查詢、互動圖譜、SNA 前 15 名表格、節點風險證據面板 |
| `/research` | 模型指標表、消融結論、14 項研究方向摘要 |

`/research` 的內容全部是靜態文字，來源為 `README.md` 與 `docs/RESEARCH.md`，寫死在前端，不打 API。

### 5.3 圖譜排版：改用分層排版而非物理擾動

Streamlit 版本用 pyvis 的力導向物理排版，節點會聚成一團，且每次結果不同。

新版改用 **dagre 由左至右分層排版**，理由是 `docs/DEMO_SCRIPT.md` 第 3 步的演示動線就是「由左至右講一次完整劇本」：被害人 ×12 → 客服收款 ×3 → 集資主錢包 → 車手 ×6 → 剝洋蔥鏈 → OTC 出金。分層排版讓洗錢的集資—分層—整合三階段在版面上自然浮現，且排版具確定性，每次演示長得一樣。

**著色沿用既有色碼**（來自 `chainlens/app/workbench.py` 的 `ROLE_COLOR`），維持與 `docs/images/` 既有截圖的一致性：

```
victim #f5b041 / support #e74c3c / aggregator #c0392b / mule #e67e22
peel #d35400 / peel_side #7f8c8d / otc #9b59b6 / normal #5dade2
```

優先序與 Streamlit 版一致：focus 節點金色 `#f1c40f` → 命中圖樣或 `score >= 0.7` 紅色 `#e74c3c` → 否則角色色。高亮路徑邊為橘色 `#f39c12`、加粗。節點大小 `10 + pagerank * 300`。

**工作台圖譜的著色不同**：如 4.2 所述，範例圖與真實 TRON 圖沒有 `role` 屬性，全部節點都會落到 `normal` 的藍色。因此 `/workbench` 的圖譜改以 `score` 連續風險色階（低=藍 `#5dade2` → 中=琥珀 `#f5b041` → 高=紅 `#e74c3c`）著色，並為 `is_motif_center` 的節點加上紅色外框。角色色階只在 `/screening` 的劇本圖使用。

工作台的排版也不用 dagre：真實 2-hop 圖（可達 795 節點）不是敘事性的線性流程，分層排版沒有意義，改用 Cytoscape 的 `cose` 力導向排版並固定亂數種子以維持可重現性。

### 5.3.1 圖譜必須附文字替代表

網路圖的無障礙評級是最低的 D 級——螢幕閱讀器完全讀不到節點與連線，因此它**永遠不能是資訊的唯一載體**。

- `/screening` 的替代表是**資金關聯證據鏈清單**（每筆含風險節點、階數、命中圖樣、完整路徑）。
  它本來就在畫面上，同時滿足演示敘事與無障礙需求。
- `/workbench` 必須另外提供**鄰接表**（來源 → 目標 → 金額），列出圖中所有邊。
  SNA 指標表是節點層級的統計，描述不了連線結構，不能代替鄰接表。

### 5.4 視覺主題

深色「法遵戰情室」風格：深色底、高對比風險色階、地址與數值一律等寬字體。目的是讓金流圖譜在暗底上發光，並讓金融法遵背景的評審一眼認出這是專業鏈上分析工具。具體色票與字體見第九節。

## 六、錯誤處理與降級

| 情況 | 前端行為 |
|---|---|
| 冷啟動未完成 | 骨架畫面 + 「喚醒分析服務中…」，不顯示空白 |
| TRON 逾時或 502 | 「鏈上查詢逾時，已為你切換內建範例圖」+ 一鍵切換鈕 |
| 地址格式錯誤 | 送出前即時驗證 `^T[1-9A-HJ-NP-Za-km-z]{33}$`，不發請求 |
| 查無轉帳（404） | 「該地址查無 USDT 轉帳紀錄」 |
| API 完全無法連線 | `/screening` 改用內建靜態快照 JSON，Demo 照常跑完 |

最後一條是現場保險：把 4.3 表中的實測值（0.7307 / 0.3268 / 0.6 / `block` / 6 筆關聯）連同劇本圖 JSON 烘進前端 bundle。網路或 API 在演示當下炸掉，畫面仍完整。快照載入時畫面須顯示明確的「離線快照」標記，不得偽裝成即時查詢結果。

## 七、測試

**後端**（接在既有 61 個測試之後）：
- `/screen` 兩個白名單目標的完整契約欄位，斷言用 4.3 表的實測值
- `/screen` 非白名單目標回 400
- `/screen` 回傳的 `graph.nodes` 數為 53、`graph.edges` 數為 63
- `/graph` example 模式契約
- `/graph` 各錯誤碼路徑（400 缺 address、400 格式錯、502 TronGrid 失敗，比照既有 `test_api.py` 用 monkeypatch）
- CORS 標頭存在

**前端**：
- Vitest 測純函式：風險分數→色階映射、HTTP 錯誤碼→中文訊息、圖 JSON→Cytoscape elements 轉換
- Playwright 冒煙：進 `/screening` → 按執行審查 → 決策卡出現 0.73 與「暫緩出金」→ 圖譜節點渲染 → STR 草稿可展開

**CI**：`.github/workflows/ci.yml` 新增與既有 Python job 並行的 `web` job（Node 20，執行 `tsc --noEmit`、`vitest run`、`vite build`）。

## 八、明確不做

- **不動 Streamlit**。`chainlens/app/workbench.py` 保留，它是本機的重度探索工具，且已被 README 與提案書引用。網站是對外的公開面，兩者並存。
- **不做使用者帳號、登入或任何持久化**。
- **不在網站上暴露 Elliptic 模式**。該模式需要 203k 節點資料集與數分鐘計算，不適合 serverless；`/score` 的 elliptic 模式維持原狀但前端不使用。
- **不清理 `api/index.py`**。它現在是冗餘的薄轉出層（Vercel 已由 `pyproject.toml` 的 `[tool.vercel] entrypoint` 定位 app），但部署正常運作中，不在本次範圍內動它。

## 九、設計系統

由 ui-ux-pro-max 產生（產品類型：fintech 法遵／詐騙偵測儀表板，variance 4、motion 4、density 8），
再依本產品的語意限制裁決。所有對比數值皆為實算，非估計。

### 9.1 採納的建議

- **落地頁型態**：即時／維運型（Hero + 關鍵指標 + 運作方式 + CTA），CTA 置於導覽列與指標區後
- **風格**：Modern Dark，深色為主要模式
- **基礎色**：背景 `#0F172A`、卡片 `#1B2336`、前景 `#F8FAFC`、次要文字 `#94A3B8`
- **反模式**：不做嬉鬧風格、不用 AI 感的紫／粉漸層、不用 emoji 當圖示、避免純黑 `#000000`
- **動效層級**：微互動 150–300ms，複雜轉場 ≤400ms

背景由原訂的 `#0b0f14` 改為 `#0F172A`。後者是成熟色階（slate-900）的一員，
整套 UI 色可從同一階系推導，而 `#0b0f14` 是孤立的自訂值。兩者對比皆遠超門檻
（17.06:1 對 18.37:1），改用色階換取系統一致性。

### 9.2 否決的建議與理由

工具的建議需依產品語意裁決，以下四項直接牴觸本產品的設計限制：

| 建議 | 否決理由 |
|---|---|
| 標題字體 Orbitron | 該字體自身的適用情境標註為「gaming、cyberpunk narrative games」。本產品的評審是金融法遵背景，賽博龐克字體會讀成幣圈風格而**傷害可信度**，也牴觸工具自己列出的「不做嬉鬧風格」反模式 |
| 主色琥珀 `#F59E0B` | 琥珀在本系統已是**中風險的語意色**。主色若也是琥珀，CTA 按鈕與中風險節點同色，違反「語意色不得挪作裝飾」的原則 |
| 輔色紫 `#8B5CF6` | 工具自身的反模式清單就寫著避免 AI 紫；且紫色已被圖譜的 `otc`（OTC 出金地址）角色佔用，會造成語意衝突 |
| 毛玻璃、環境光暈、BlurView | 皆為行動端 API（Reanimated／BlurView），本專案是 web；且模糊與光暈疊在資料密集的圖譜上會直接損害可讀性。模糊的正當用途是表示背景可關閉，不是裝飾 |
| 400–600ms 全螢幕轉場遮罩 | 評審會快速點過四個頁面，每次切換都等 0.4–0.6 秒會累積成遲鈍感。路由切換維持即時，動效預算留給資料揭露 |

### 9.3 字體

改用 **IBM Plex** 家族，其適用情境標註為「Banks, finance, insurance, investment, fintech」，
說明為「conveys trust and professionalism. Excellent for data」——正是本產品要的訊號。
同家族有 Sans 與 Mono 兩種，介面與資料共用一套設計語言。

| 用途 | 字體 |
|---|---|
| 介面與標題 | `IBM Plex Sans` |
| 中文 | `Noto Sans TC`（IBM Plex 無中日韓字符，必須指定後備） |
| 地址、金額、指標 | `IBM Plex Mono`，搭配 `font-variant-numeric: tabular-nums` |

### 9.4 色票與實算對比

顏色只花在有意義的地方。介面外殼（導覽、面板、按鈕）維持無彩度的 slate 階系，
色彩保留給風險與圖譜語意。主要 CTA 因此是**淺色高對比按鈕**而非彩色按鈕——
這同時避開了所有語意衝突。

**文字用色**（門檻 4.5:1，兩種底色皆須通過）

| Token | 值 | 對背景 | 對卡片 |
|---|---|---|---|
| `--color-ink` | `#F8FAFC` | 17.06:1 | 14.98:1 |
| `--color-muted` | `#94A3B8` | 6.96:1 | 6.11:1 |
| `--color-risk-high` | `#F87171` | 6.45:1 | 5.66:1 |
| `--color-risk-med` | `#F59E0B` | 8.31:1 | 7.30:1 |
| `--color-risk-low` | `#22C55E` | 7.83:1 | 6.88:1 |

**高風險文字必須用 `#F87171`，不能用 `#EF4444`。** 紅色 `#EF4444` 在頁背景上是 4.74:1 勉強通過，
但在卡片底 `#1B2336` 上只有 **4.16:1，未達 4.5:1**。決策卡的處置建議正是紅字渲染在卡片上，
若沿用 `#EF4444` 會直接違反 AA。`#EF4444` 僅保留給圖譜節點填色等非文字用途（4.74:1 > 3:1 門檻）。

**非文字用色**（門檻 3:1）

| Token | 值 | 對比 | 用途 |
|---|---|---|---|
| `--color-line` | `#334155` | 1.72:1 | 純裝飾性分隔線與面板外框，不受 3:1 規範 |
| `--color-line-strong` | `#64748B` | 3.75:1 | **表單輸入框與控制項邊界**，此處邊框是識別控制項的唯一依據，必須達標 |
| `--color-ring` | `#38BDF8` | 8.33:1 | 鍵盤焦點環 |

邊框分兩階是必要的：`#334155` 與 `#475569` 都達不到 3:1，直接拿來當輸入框邊界會讓控制項邊界在
弱視條件下消失。但若全部提升到 `#64748B`，密集的面板分隔線又會過於搶眼。

**圖譜角色色**沿用 `chainlens/app/workbench.py` 的既有色碼，實算全部通過資料對比門檻 3:1
（對畫布 `#0d1219`）：最低的 `aggregator #c0392b` 為 3.45:1、`otc #9b59b6` 為 4.02:1，
其餘介於 4.5:1 至 11.31:1。既有配色可直接沿用，不需為無障礙重新調色。

### 9.5 動效

`prefers-reduced-motion` 必須生效。動畫只用 `transform` 與 `opacity`。
進場緩動用 ease-out，離場用 ease-in 且時長約為進場的 60–70%。
清單／表格列的進場錯開 30–50ms。持續性動畫僅用於載入指示，不得用於裝飾。

## 十、後續事項（實作後триаж結果）

實作完成後的全分支審查留下 11 項次要發現，經триаж後多數可以真的等。以下三項有明確時限或條件，不應遺忘：

| 事項 | 何時處理 | 說明 |
|---|---|---|
| react-router 的 npm audit 警告 | **對外公開前必須覆查** | 兩項 high 等級的 RSC-mode CSRF 公告。本站是純用戶端 SPA，不走 RSC，故目前不適用；修復需破壞性降版。公開前需重新確認該公告範圍是否擴大。 |
| `/graph` 與 `_build_graph` 的 tron 分支重複 | 下次動到任一端點時 | 兩者的驗證順序、抓取呼叫、502/404 處理幾乎逐行相同，含三段使用者可見字串。任一處改動未同步就會產生不一致的錯誤訊息。 |
| SPA rewrite 的部署後驗證 | **首次部署後立即** | `web/vercel.json` 的 catch-all rewrite 無法在本機證實——`vite preview` 自帶 history fallback 會遮住它。部署後以 `curl -I https://<網站>/screening` 確認回 200 而非 404。 |

其餘次要項目（`toElements` 的邊防禦、三個未使用的契約欄位、StrictMode 下的重複請求、快照無執行期型別驗證以外的加固等）不影響正確性，可隨後續改動順手處理。
