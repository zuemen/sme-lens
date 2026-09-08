# ChainLens MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 從零建立「鏈鏡 ChainLens」——SNA + GNN 虛擬資產詐騙金流偵測平台 MVP，推上 GitHub `zuemen/ChainLens`。

**Architecture:** 資料層（Elliptic CSV 載入器 + TronGrid 2-hop 抓取器）→ 分析層（NetworkX SNA 指標、Louvain 社群、規則式詐騙圖樣）→ 模型層（PyG GCN/GraphSAGE 節點分類，時間切分）→ 解釋層（結構證據 JSON + 中文敘事）→ 服務層（FastAPI `/score` + Streamlit 工作台）。全記憶體運算，本地檔案快取，無資料庫。

**Tech Stack:** Python 3.11、uv、FastAPI、Streamlit、NetworkX、python-louvain、PyTorch + PyTorch Geometric、PyVis、pytest、ruff、GitHub Actions。

## Global Constraints

- Python `>=3.11`；套件管理一律 `uv`（pyproject.toml）
- 全部函式加 type hints；`ruff check` 通過；`pytest` 全綠才准 commit
- Conventional Commits；每完成一個里程碑 commit 一次
- 測試使用小型合成圖 fixture，不依賴大資料集
- `data/raw/*`、`data/cache/*`、`checkpoints/`、`.env` 一律 .gitignore
- Elliptic 官方時間切分：train `time_step<=34`、test `time_step>=35`，避免資料洩漏
- TronGrid API key 環境變數 `TRONGRID_API_KEY`；無 key 降級匿名限速模式
- LICENSE：MIT，著作權人 ChainLens Team
- README 中文為主，含 mermaid 架構圖、≤5 指令快速開始、指標表、免責聲明
- Windows 開發環境：Makefile 提供但本機驗證用直接指令（`uv run pytest` 等）

## File Structure

```
ChainLens/
├── README.md
├── LICENSE                      # MIT, ChainLens Team
├── pyproject.toml               # uv 管理；deps + dev deps + ruff 設定
├── Makefile                     # setup / download-data / train / api / app / test / lint
├── .gitignore / .env.example
├── .github/workflows/ci.yml    # ruff + pytest（CPU torch）
├── chainlens/
│   ├── __init__.py
│   ├── data/__init__.py
│   │   ├── elliptic.py          # Elliptic CSV → nx.DiGraph / PyG Data（含時間切分 mask）
│   │   └── tron.py              # TronGrid TRC-20 USDT 2-hop 圖 + 快取 + 離線範例圖
│   ├── sna/__init__.py
│   │   ├── metrics.py           # in/out degree, PageRank, k-core, 近似 betweenness
│   │   ├── community.py         # Louvain + 社群風險比率
│   │   └── motifs.py            # fan-in / fan-out / peeling chain 規則偵測
│   ├── models/__init__.py
│   │   ├── gcn.py               # 2 層 GCN baseline
│   │   ├── sage.py              # 2 層 GraphSAGE（主模型）
│   │   └── train.py             # 訓練/評估/消融 CLI；無資料時合成圖冒煙模式
│   ├── explain/__init__.py
│   │   └── evidence.py          # 結構證據 JSON + narrative_zh 模板
│   ├── api/__init__.py
│   │   └── main.py              # FastAPI POST /score
│   └── app/__init__.py
│       └── workbench.py         # Streamlit + PyVis 互動圖譜
├── tests/
│   ├── conftest.py              # 合成詐騙圖 fixture（fan-in/fan-out/peeling 各一段）
│   ├── test_elliptic.py / test_tron.py
│   ├── test_metrics.py / test_community.py / test_motifs.py
│   ├── test_models.py / test_evidence.py / test_api.py
└── data/raw/.gitkeep, data/cache/.gitkeep
```

## 關鍵介面（跨任務契約）

- `chainlens.data.elliptic.load_elliptic_graph(raw_dir: Path) -> nx.DiGraph`（node attrs: `time_step:int`, `label:int` 1=illicit/0=licit/-1=unknown, `feat:list[float]`）
- `chainlens.data.elliptic.load_elliptic_pyg(raw_dir: Path, extra_features: "np.ndarray | None" = None) -> torch_geometric.data.Data`（`data.y`、`data.train_mask`、`data.test_mask`、`data.time_step`）
- `chainlens.sna.metrics.compute_sna_features(g: nx.DiGraph, betweenness_samples: int = 64, seed: int = 42) -> pd.DataFrame`（index=node，columns=`in_degree,out_degree,pagerank,kcore,betweenness`）
- `chainlens.sna.community.detect_communities(g: nx.DiGraph, seed: int = 42) -> dict[Any, int]`
- `chainlens.sna.community.community_risk_ratio(partition: dict, labels: dict) -> dict[int, float]`
- `chainlens.sna.motifs.MotifHit`（dataclass：`motif:str, center:Any, nodes:list, description_zh:str`）
- `chainlens.sna.motifs.detect_fan_in/detect_fan_out(g, min_degree=5, window_seconds=None) -> list[MotifHit]`（邊可帶 `timestamp`/`amount`；無 timestamp 視為同一窗）
- `chainlens.sna.motifs.detect_peeling_chain(g, min_hops=3, keep_ratio=0.8) -> list[MotifHit]`
- `chainlens.sna.motifs.detect_all(g) -> list[MotifHit]`
- `chainlens.models.gcn.GCN(in_dim, hidden_dim=64, num_classes=2)` / `chainlens.models.sage.GraphSAGE(...)`（`forward(x, edge_index) -> logits`）
- `chainlens.models.train.train_and_evaluate(data, model_type="sage", epochs=200, ...) -> dict`（keys: `precision,recall,f1,pr_auc`，皆針對 illicit 類）
- `chainlens.explain.evidence.generate_evidence(node, g, sna_df, partition, risk_ratios, motif_hits, model_score=None) -> dict`（keys: `score,label,top_features,centrality_percentile,community_risk_ratio,motif_hits,narrative_zh`）
- `chainlens.data.tron.fetch_two_hop_graph(address: str, api_key: str | None = None, cache_dir: Path | None = None) -> nx.DiGraph`（edge attrs: `amount:float`(USDT), `timestamp:int`(秒)）
- `chainlens.data.tron.load_example_graph() -> nx.DiGraph`（離線內建範例，含三種圖樣）

---

### Task 1: Scaffold + CI

**Files:** Create `pyproject.toml`, `Makefile`, `.gitignore`, `.env.example`, `LICENSE`, `.github/workflows/ci.yml`, `chainlens/`（含各子套件 `__init__.py`）, `tests/__init__.py`, `data/raw/.gitkeep`, `data/cache/.gitkeep`, 極簡 `README.md` 佔位。

- [ ] pyproject：deps = networkx, python-louvain, pandas, numpy, scikit-learn, torch(CPU), torch-geometric, fastapi, uvicorn, httpx, streamlit, pyvis, python-dotenv, pydantic；dev = pytest, ruff。ruff 設定 line-length 100, target py311。
- [ ] `uv sync` 成功建立 venv
- [ ] `uv run ruff check .` 與 `uv run pytest`（無測試也不得報錯，`--collect-only` 可過）
- [ ] CI：push/PR 觸發，`astral-sh/setup-uv` + `uv sync` + ruff + pytest
- [ ] Commit: `chore: scaffold project with uv, ruff, pytest and CI`

### Task 2: Elliptic 載入器

**Files:** Create `chainlens/data/elliptic.py`, `tests/test_elliptic.py`

CSV 格式：`elliptic_txs_features.csv` 無 header、167 欄（txId, time_step, 165 features）；`elliptic_txs_classes.csv` 有 header `txId,class`（'1'=illicit, '2'=licit, 'unknown'）；`elliptic_txs_edgelist.csv` 有 header `txId1,txId2`。

- [ ] 測試：tmp_path 寫 6 節點迷你 CSV（3 期、含 unknown），驗證 `load_elliptic_graph` 節點數/邊數/label/time_step；`load_elliptic_pyg` 的 `train_mask`（t<=34 且 label>=0）與 `test_mask`（t>=35 且 label>=0）互斥且正確；`extra_features` 串接後 `data.x` 維度增加。
- [ ] 實作 + 測試綠 + `git commit -m "feat: elliptic dataset loader with temporal split"`

### Task 3: SNA metrics + community

**Files:** Create `chainlens/sna/metrics.py`, `chainlens/sna/community.py`, `tests/conftest.py`, `tests/test_metrics.py`, `tests/test_community.py`

conftest fixture `scam_graph`：合成 DiGraph——8 個來源 →`collector`（fan-in，600 秒內、各 100 USDT）；`collector`→`hub` 800 USDT；`hub`→6 個新地址（fan-out，300 秒內）；另一條 `p0→p1→p2→p3→p4` peeling chain（每跳轉出 90% 給下一跳＋10% 剝離到旁支）；加上一小群正常節點。邊皆有 `amount`、`timestamp`。

- [ ] 測試 metrics：回傳 DataFrame 包含全部節點、5 欄位；`collector` 的 in_degree==8；pagerank 總和≈1；betweenness 非負。
- [ ] 測試 community：partition 覆蓋全節點；同一 fan-in 星團多數落同社群；`community_risk_ratio({a:0,b:0,c:1}, {a:1,b:0,c:0})` → `{0:0.5, 1:0.0}`。
- [ ] 實作（betweenness 用 `nx.betweenness_centrality(k=min(samples,n), seed=seed)`；k-core 用無向去自環 copy）+ 測試綠 + `git commit -m "feat: SNA metrics and louvain community detection"`

### Task 4: 詐騙圖樣 motifs

**Files:** Create `chainlens/sna/motifs.py`, `tests/test_motifs.py`

- [ ] 測試：`detect_fan_in(scam_graph, min_degree=5, window_seconds=3600)` 命中 `collector`；`detect_fan_out` 命中 `hub`；`detect_peeling_chain(min_hops=3)` 命中鏈且 nodes 含 p0..p3；正常節點不命中；`description_zh` 非空中文；無 timestamp 的圖（純結構）fan-in 仍可命中。
- [ ] 實作：fan-in/out 以中心節點分組，若有 timestamp 用滑動窗計數 distinct 對手方；peeling chain 沿「單一大額轉出(≥keep_ratio×流入)＋至少一筆小額」遞迴延伸，長度≥min_hops 即命中。
- [ ] 測試綠 + `git commit -m "feat: rule-based fraud motif detection (fan-in, fan-out, peeling chain)"`

### Task 5: GNN 模型與訓練

**Files:** Create `chainlens/models/gcn.py`, `chainlens/models/sage.py`, `chainlens/models/train.py`, `tests/test_models.py`

- [ ] 測試：合成 PyG Data（60 節點、166 維隨機特徵、隨機邊、時間 1..49、兩類標籤），`train_and_evaluate(data, model_type="gcn", epochs=5)` 與 `"sage"` 皆回傳含 `precision/recall/f1/pr_auc` 的 dict 且值域 [0,1]；checkpoint 檔存在。
- [ ] 實作：兩層 conv + ReLU + dropout；`CrossEntropyLoss(weight=class_weights)`；Adam；只在 train_mask 上訓練、test_mask 上評估；`torch.save` 到 `checkpoints/{model_type}.pt`。CLI：`python -m chainlens.models.train --model sage --use-sna --raw-dir data/raw`；raw 缺檔時印警告並跑合成圖冒煙。消融：`--use-sna` 時把 `compute_sna_features` 結果 z-score 後接到 x。
- [ ] 測試綠 + `git commit -m "feat: GCN and GraphSAGE training with temporal split and SNA ablation"`

### Task 6: 可解釋證據

**Files:** Create `chainlens/explain/evidence.py`, `tests/test_evidence.py`

- [ ] 測試：對 `collector` 產生證據——`score`∈[0,1]、`motif_hits` 非空、`centrality_percentile.pagerank`≥50、`narrative_zh` 含節點名與「扇入」等關鍵詞、JSON 可序列化。正常節點 score 低於 `collector`。
- [ ] 實作：score = 0.5×motif 命中(有=1) + 0.3×centrality percentile 均值 + 0.2×community_risk_ratio，若給 model_score 則 0.5×model+0.5×rule；label = high/medium/low（≥0.7 / ≥0.4）；narrative_zh 模板拼接各證據句。
- [ ] 測試綠 + `git commit -m "feat: explainable risk evidence generator with Chinese narrative"`

### Task 7: FastAPI

**Files:** Create `chainlens/api/main.py`, `tests/test_api.py`

- [ ] 測試：TestClient POST `/score` `{"address":"TDemo…","mode":"example"}` → 200、body 含 `risk_score,label,evidence`；缺 address 與 tx_id → 422/400；GET `/health` → 200。
- [ ] 實作：`ScoreRequest(address|tx_id, mode:"auto"|"tron"|"elliptic"|"example")`；example/離線→`load_example_graph`；tron→`fetch_two_hop_graph`；elliptic→raw 存在才載入否則 404 說明。管線：SNA→community→motifs→evidence。附 curl 範例於 docstring 與 README。
- [ ] 測試綠 + `git commit -m "feat: FastAPI /score endpoint with evidence response"`

### Task 8: TRON 抓取器

**Files:** Create `chainlens/data/tron.py`, `tests/test_tron.py`

- [ ] 測試：以假 JSON（TronGrid trc20 回應格式）測 `_parse_transfers`；`build_graph_from_transfers` 邊帶 amount(6 位小數換算)/timestamp(ms→s)；`load_example_graph` 節點>10 且 `detect_all` 至少 2 種命中；快取寫入/讀回。
- [ ] 實作：httpx GET `https://api.trongrid.io/v1/accounts/{addr}/transactions/trc20?only_confirmed=true&limit=200&contract_address=TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t`；有 key 加 `TRON-PRO-API-KEY` header，無 key 匿名+`time.sleep(0.5)` 限速；2-hop：中心→取對手方（上限 8 個）再各抓一次；JSON 快取 `data/cache/{addr}.json`；網路失敗 raise 讓呼叫端 fallback example graph。
- [ ] 測試綠（mock httpx，不打真網路）+ `git commit -m "feat: TronGrid TRC-20 USDT 2-hop graph fetcher with cache"`

### Task 9: Streamlit 工作台

**Files:** Create `chainlens/app/workbench.py`

- [ ] 實作：地址輸入框＋「使用內建範例」按鈕；抓圖（失敗自動 fallback example）→ SNA/motifs/evidence → PyVis（node size=pagerank×比例、紅=motif 命中或 score≥0.7、灰=一般）`net.generate_html()` 嵌入 `components.html`；側欄：所選節點 narrative_zh + JSON。
- [ ] `uv run ruff check .` 通過、`uv run streamlit run chainlens/app/workbench.py` 冒煙啟動確認無 import error
- [ ] Commit: `feat: streamlit workbench with pyvis interactive graph`

### Task 10: README 完稿 + 發佈

**Files:** Modify `README.md`

- [ ] README：專案簡介（金融科技獎背景）、mermaid 架構圖、快速開始（≤5 指令）、Kaggle 下載步驟＋`make download-data`、模型指標表（無資料時標註「待 `make train` 產生」）、API curl 範例、免責聲明。
- [ ] 全量驗證：`uv run ruff check .` + `uv run pytest` 全綠
- [ ] `gh repo create zuemen/ChainLens --public --source=. --push`（或 remote add + push）
- [ ] 回報 repo 網址與 commit 清單

## Self-Review

- Spec 覆蓋：七大節需求逐一對應 Task 1–10 ✅（download-data 在 Task 1 Makefile + Task 10 README）
- 型別/命名一致性：以「關鍵介面」節為單一契約來源 ✅
- 無資料集時：Task 5 冒煙模式 + Task 10 README 標註 ✅
