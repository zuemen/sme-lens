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

### 既有端點（防詐分支）

`POST /score`、`POST /screen`、`POST /graph` 沿用 ChainLens 的詐騙金流分析
能力，服務科技防詐情境。

## 淵源與授權

核心圖引擎（SNA 指標、Louvain 社群偵測、GNN 模型、圖譜序列化）衍生自同作者的
[ChainLens](https://github.com/zuemen/ChainLens)（MIT 授權），該專案已在虛擬資產
詐騙金流場域驗證。企鏡在其上新增企金語意層：企業風險圖樣、集團歸戶與授信意見書。

MIT License. See [LICENSE](LICENSE).
