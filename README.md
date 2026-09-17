# 企鏡 SME Lens

**中小企業關係網絡風控引擎**

把銀行既有的轉帳流水、票據與企業登記關係變成一張「企業關係圖」，讓沒有漂亮財報的
中小企業也能用**交易網絡**當信用證據；並讓每一個 AI 判斷都附帶**可稽核的結構證據**，
而不是黑箱分數。

> 銀行不缺分數，缺的是看得見的理由。

2026 年臺灣中小企業銀行校園金融科技創意挑戰賽參賽作品
（情境：企業金融服務創新 ⊕ 科技防詐）。

## 三個核心應用

| 時點 | 痛點 | SME Lens 解法 |
| :-- | :-- | :-- |
| **貸前** 集團歸戶 | 關係人歸戶靠客戶申報，隱性關聯查不出來，集團曝險超限 | 公司—自然人二部圖投影 + 連通元件歸戶，揭露未申報的實質關聯 |
| **貸中** 無財報授信 | 中小企業財報粗糙、擔保品不足，好公司借不到錢 | 以交易網絡結構產生**網絡信用分**，補財報之不足 |
| **貸後** 早期預警 | 貸後管理倚賴季報，上下游出事才知道 | 企金風險圖樣（循環交易、空殼中介、買方集中）產生關注名單 |

## 快速開始

本專案不依賴 `uv` 或 `make`，直接用虛擬環境的直譯器即可：

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m pytest -q          # 測試
.venv/Scripts/python.exe -m uvicorn smelens.api.main:app --port 8000
```

OpenAPI 文件：<http://localhost:8000/docs>

## API

### `POST /credit` — 授信意見書

```bash
curl -X POST http://localhost:8000/credit \
  -H "Content-Type: application/json" \
  -d '{"target": "泰昇精密"}'
```

回傳網絡信用分、授信關注分數、命中的企金風險圖樣、中文授信敘事、建議事項
與可直接繪製的關係圖譜。

### `POST /group` — 集團歸戶

```bash
curl -X POST http://localhost:8000/group \
  -H "Content-Type: application/json" \
  -d '{
    "affiliations": [
      {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
      {"company": "泰昇投資", "person": "陳大明", "role": "董事"}
    ],
    "declared_groups": {"泰昇精密": "泰昇集團"},
    "exposures": {"泰昇精密": 30000000}
  }'
```

回傳歸戶結果、各集團授信曝險合計，以及「關係圖上存在、但客戶未申報」的
隱性關聯清單。

### `GET /gcis/group` — 用真實統一編號查集團歸戶

公開 Demo 專用：名冊不由呼叫端自備，而是從隨 repo 發佈的精簡登記索引現場
展開（`data/demo/gcis_a_tier.sqlite.gz`，見 `scripts/build_demo_extract.py`）。

```bash
curl "http://localhost:8000/gcis/group?company_id=35866232"
```

回應含歸戶成員、A 層證據、B 層候選、耗時與鄰域是否被上限截斷。歸戶僅採
A 層（法人董事）證據；B 層只列候選不合併，用於授信決策需接行內 KYC 身分資料。

### 既有端點（防詐分支）

`POST /score`、`POST /screen`、`POST /graph` 沿用 ChainLens 的詐騙金流分析
能力，服務科技防詐情境。

## 部署

正式網址：

| 專案 | 網址 | Root Directory | 設定檔 |
|---|---|---|---|
| 前端 | <https://sme-lens.vercel.app> | `web/` | `web/vercel.json`（SPA rewrite） |
| 後端 API | <https://sme-lens-api.vercel.app> | repo 根目錄 | `vercel.json` |

兩個都是指向同一個 repo 的獨立 Vercel 專案，且都綁在 `main`——**推上 `main`
就會自動重新部署**，不需要手動 deploy。也因此每次改完都要重新實打驗證（見下方
驗證指令），不能假設「本機綠燈＝線上正確」。

**後端**：進入點必須是 `api/index.py`——Vercel 只把 `api/` 底下的檔案當
serverless function。`vercel.json` 的 `functions` 鍵若寫成模組真正的位置
（`smelens/api/main.py`）會匹配不到任何 function，build 直接失敗；另外那條
`rewrites`（`/(.*)` → `/api/index`）也不能少，少了的話 build 會過但每一個
API 路徑都落到靜態檔案查找而回 404。兩者都實際發生過。

部署後**必須實打驗證**，只看 `/health` 驗不出來（舊部署與靜態站台都會回 200）：

```bash
curl -sf "$API/ready" | grep '"ready":true'      # 服務身分＋企金端點齊備
curl -sf "$API/gcis/group?company_id=35866232"   # 真實統編查詢
curl -sf -X POST "$API/credit" -H 'content-type: application/json' -d '{"target":"泰昇精密"}'
```

**前端**：`VITE_API_BASE` 是 **build-time** 變數——改了環境變數必須重新
build 才會生效，改完再 deploy 一次。設定位置：Vercel 專案的 Environment
Variables，以及本機的 `web/.env`（範本見 `web/.env.example`）。

拿到正式網址後要回填三處：`web/.env.example`、`docs/DEMO_SCRIPT.md` 的網址欄、
一頁式企劃書頁尾的 QR（`docs/proposal/proposal.html`，改完重跑
`node scripts/render-proposal.mjs`）。

## 淵源與授權

核心圖引擎（SNA 指標、Louvain 社群偵測、GNN 模型、圖譜序列化）衍生自同作者的
[ChainLens](https://github.com/zuemen/ChainLens)（MIT 授權），該專案已在虛擬資產
詐騙金流場域驗證。企鏡在其上新增企金語意層：企業風險圖樣、集團歸戶與授信意見書。
GNN 模型（`smelens/models/`）目前僅供離線訓練與評估，線上 API 一律以規則分數服務；
意見書中的「0.5×模型 + 0.5×規則」融合路徑已實作並有測試涵蓋，但尚未接上線上端點。

MIT License. See [LICENSE](LICENSE).
