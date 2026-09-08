# 企鏡 SME Lens 核心引擎 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 ChainLens 的圖風控引擎轉為企鏡 SME Lens——新增三個企金風險圖樣、集團歸戶模組與授信意見書產生器，並以 `/credit`、`/group` 兩個 API 端點對外提供。

**Architecture:** 沿用 ChainLens 已驗證的 SNA（degree／PageRank／k-core／betweenness）與 Louvain 社群偵測作為圖引擎，一行不改；在其上新增企金語意層——`sna/sme_motifs.py` 提供循環交易／空殼中介／買方集中三個圖樣，`credit/opinion.py` 把結構證據轉為含網絡信用分與關注分數的授信意見書，`credit/group.py` 以公司—自然人二部關係投影出公司關聯圖並用連通元件做集團歸戶。所有輸出都附帶可稽核的結構證據與中文敘事，不輸出黑箱分數。

**Tech Stack:** Python 3.11.2、networkx 3.6.1、pandas、FastAPI、pytest、ruff

**Spec:** `docs/superpowers/specs/2026-09-08-sme-lens-spec.md`

## Global Constraints

- **Python 直呼叫**：本機**沒有** `uv`，也**沒有** `make`。所有指令一律用 `.venv\Scripts\python.exe -m <module>`。Makefile 內容仍要更新（供 CI 與他人使用），但執行時不要依賴它。
- **Python 直譯器絕對路徑**：`C:\Users\sanketsu\sme-lens\.venv\Scripts\python.exe`（Python 3.11.2，torch 2.12.1+cpu、PyG 2.8.0、networkx 3.6.1 皆已安裝）
- **工作目錄**：`C:\Users\sanketsu\sme-lens`
- **Remote**：`https://github.com/zuemen/sme-lens`，預設分支 `main`
- **套件名**：`smelens`（由 `chainlens` 改名而來）
- **語言慣例**：所有 docstring、註解、使用者可見字串一律**繁體中文**，與既有程式碼一致
- **Ruff**：line-length 100、target-version py311、select `["E", "F", "I", "W", "UP"]`
- **測試**：完整套件約需 95 秒。TDD 過程中只跑目標測試檔；每個 Task 的最後一步才跑完整套件。
- **grep／sed 一律排除 `.venv`**（內含 1 GB site-packages，未排除會掃到無關檔案並可能損毀套件）
- **金額慣例**：圖的邊屬性 `amount`（新台幣元）、`timestamp`（Unix 秒）。邊方向 `u → v` 表示 **u 付款給 v**，故 v 的收入為其 in-edges 金額總和。
- **Commit 訊息結尾**必須附上兩行（每個 commit 步驟都已寫出完整指令）：
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
  ```
- **不得回歸**：既有 89 項 ChainLens 測試在每個 Task 結束時都必須維持全綠。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `smelens/sna/sme_motifs.py` | **新增** 企金三大風險圖樣偵測（循環交易、空殼中介、買方集中）＋ `detect_all_sme` |
| `smelens/data/sme_scenario.py` | **新增** 中小企業供應鏈授信劇本圖（demo 與測試的共同基準） |
| `smelens/credit/__init__.py` | **新增** 企金子套件 |
| `smelens/credit/group.py` | **新增** 集團歸戶：公司關聯圖建構、連通元件歸戶、集團曝險彙總、隱性關聯揭露 |
| `smelens/credit/opinion.py` | **新增** 授信意見書：企金分析管線、網絡信用分、對手多樣性、關注分數與中文敘事 |
| `smelens/api/main.py` | **修改** 新增 `POST /credit`、`POST /group` 端點；既有 `/score` `/screen` `/graph` 不動 |
| `smelens/api/serialize.py` | **修改** `graph_to_json` 新增選配 `role_zh` 參數（預設維持 AML 劇本對照表），使企金角色能正確中文化 |
| `smelens/sna/motifs.py` | **不動** 詐騙圖樣（防詐分支沿用） |
| `smelens/sna/metrics.py`、`community.py` | **不動** 通用圖演算法 |
| `smelens/explain/evidence.py`、`screening.py` | **不動**（本計畫不改；企金語意走新的 `credit/` 子套件，避免破壞既有 89 項測試） |
| `tests/test_sme_motifs.py` | **新增** 三個圖樣的獨立測試 |
| `tests/test_sme_scenario.py` | **新增** 劇本圖的圖樣命中與對照組乾淨性測試 |
| `tests/test_group.py` | **新增** 集團歸戶測試 |
| `tests/test_credit_opinion.py` | **新增** 授信意見書測試 |
| `tests/test_api_credit.py` | **新增** 兩個新端點的 API 測試 |

**決策紀錄：** 企金語意放在新的 `smelens/credit/` 子套件，而非改寫 `explain/evidence.py`。原因：`evidence.py` 是 89 項既有測試的基礎，改它的評分權重會造成大量回歸；新增子套件則能複用它的 `PipelineResult` 型別與百分位處理慣例，同時讓防詐分支與企金分支各自獨立演進。

---

### Task 1: Repo bootstrap 與套件改名

把已複製到 `C:\Users\sanketsu\sme-lens` 的 ChainLens 程式碼改名為 `smelens`，換上企鏡的專案身分，建立 git 歷史並推上 GitHub。

**Files:**
- Rename: `chainlens/` → `smelens/`
- Modify: `pyproject.toml`, `Makefile`, `Dockerfile`, `render.yaml`, `vercel.json`, `api/index.py`, `requirements.txt`, `.env.example`, `LICENSE`
- Create: `README.md`（全新覆寫）
- Test: 既有 `tests/` 全部（89 項）

**Interfaces:**
- Consumes: 無（起點）
- Produces: 套件根命名空間 `smelens`；環境變數前綴 `SMELENS_`（`SMELENS_CORS_ORIGINS`、`SMELENS_API_KEY`、`SMELENS_CACHE_DIR`）；後續所有 Task 的 import 皆以 `from smelens.…` 起頭

- [ ] **Step 1: 確認起點乾淨**

```bash
cd /c/Users/sanketsu/sme-lens
ls -d chainlens .venv docs/superpowers/specs
git rev-parse --show-toplevel
git log --oneline 2>/dev/null | wc -l
```

Expected: 三個目錄都存在；`git rev-parse --show-toplevel` 印出 `C:/Users/sanketsu/sme-lens`；commit 數為 `0`。

（git repo 已於 SDD Setup 階段初始化，故本 Task **不要**再執行 `git init`。）

- [ ] **Step 2: 跑一次既有測試，建立基準**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
```
Expected: `89 passed`

- [ ] **Step 3: 重新命名套件目錄**

```bash
cd /c/Users/sanketsu/sme-lens
mv chainlens smelens
find . -path ./.venv -prune -o -name '__pycache__' -type d -print | xargs rm -rf
```

- [ ] **Step 4: 機械替換識別字與環境變數前綴**

只替換小寫識別字 `chainlens` 與環境變數前綴 `CHAINLENS`。**品牌字串 `ChainLens` 不在此步替換**（Step 5 手動處理，以保留 attribution）。

**排除清單不可省略，每一項都擋掉一種實際損壞：**
- `-I`：跳過二進位檔。`checkpoints/*.pt` 是 pickle，`sed -i` 會靜默毀損它們。
- `--exclude-dir=.git`：改寫 git 內部物件會毀掉整個 repo。
- `--exclude-dir=.superpowers --exclude-dir=superpowers`：`docs/superpowers/` 內就是你正在讀的這份計畫與規格書。若不排除，本 Step 3 的 `mv chainlens smelens` 會被改寫成 `mv smelens smelens`，指令當場失效；`.superpowers/` 則是 SDD 的工作紀錄。這兩處刻意保留 `chainlens` 字樣作為淵源引用，**本來就不該改名**。

```bash
cd /c/Users/sanketsu/sme-lens
EXCL="--exclude-dir=.venv --exclude-dir=node_modules --exclude-dir=dist \
--exclude-dir=.git --exclude-dir=.superpowers --exclude-dir=superpowers"
grep -rlI $EXCL -e 'chainlens' -e 'CHAINLENS' . | while read -r f; do
    sed -i 's/chainlens/smelens/g; s/CHAINLENS/SMELENS/g' "$f"
done
grep -rnI $EXCL -e 'chainlens' -e 'CHAINLENS' . || echo "clean"
```
Expected: 最後印出 `clean`

驗證排除確實生效（這兩行必須維持原樣）：
```bash
cd /c/Users/sanketsu/sme-lens
grep -c 'mv chainlens smelens' docs/superpowers/plans/2026-09-08-sme-lens-core-engine.md
```
Expected: `1`（計畫書未被自我改寫）

- [ ] **Step 5: 手動更新品牌字串與專案身分**

`pyproject.toml` 開頭改為：
```toml
[project]
name = "smelens"
version = "0.1.0"
description = "企鏡 SME Lens — 中小企業關係網絡風控引擎：可解釋的圖結構授信證據"
```

`smelens/api/main.py` 的 FastAPI 建構子改為：
```python
app = FastAPI(
    title="SME Lens API",
    description="中小企業關係網絡風控：授信意見書、集團歸戶與結構證據",
    version="0.1.0",
)
```

`LICENSE` 第三行改為：
```
Copyright (c) 2026 SME Lens Team
```

- [ ] **Step 6: 覆寫 README.md**

```markdown
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

## 淵源與授權

核心圖引擎（SNA 指標、Louvain 社群偵測、GNN 模型、圖譜序列化）衍生自同作者的
[ChainLens](https://github.com/zuemen/ChainLens)（MIT 授權），該專案已在虛擬資產
詐騙金流場域驗證。企鏡在其上新增企金語意層：企業風險圖樣、集團歸戶與授信意見書。

MIT License. See [LICENSE](LICENSE).
```

- [ ] **Step 7: 跑完整測試，確認改名未造成回歸**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
```
Expected: `89 passed`

- [ ] **Step 8: Lint**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m ruff check . --exclude .venv
```
Expected: `All checks passed!`

- [ ] **Step 9: 建立初始 commit 並推上 GitHub**

repo 已於 SDD Setup 初始化，此處不再 `git init`。

```bash
cd /c/Users/sanketsu/sme-lens
git add -A
git commit -F - <<'EOF'
feat: 企鏡 SME Lens 初始化——中小企業關係網絡風控引擎

核心圖引擎衍生自 ChainLens（MIT，同作者），套件改名 chainlens → smelens、
環境變數前綴改 SMELENS_，換上企鏡專案身分。既有 89 項測試全綠。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
git remote add origin https://github.com/zuemen/sme-lens.git
git push -u origin main
```

Expected: push 成功，GitHub 上可見 `smelens/` 目錄與新 README。

---

### Task 2: 企金圖樣——循環交易 `detect_cycle_trade`

**Files:**
- Create: `smelens/sna/sme_motifs.py`
- Test: `tests/test_sme_motifs.py`

**Interfaces:**
- Consumes: `smelens.sna.motifs.MotifHit`（dataclass，欄位 `motif: str`、`center: Any`、`nodes: list[Any]`、`description_zh: str`）
- Produces: `detect_cycle_trade(g: nx.DiGraph, max_len: int = 4, min_amount: float = 0.0) -> list[MotifHit]`，`motif` 值為 `"cycle_trade"`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_sme_motifs.py`：

```python
"""企金風險圖樣測試：循環交易、空殼中介、買方集中。"""

from __future__ import annotations

import networkx as nx

from smelens.sna.sme_motifs import detect_cycle_trade


def test_detect_cycle_trade_finds_three_node_cycle():
    """三家公司構成封閉資金環，應命中且只回報一次。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000_000.0)
    g.add_edge("B", "C", amount=980_000.0)
    g.add_edge("C", "A", amount=960_000.0)
    g.add_edge("D", "E", amount=50_000.0)  # 非環，不應命中

    hits = detect_cycle_trade(g, max_len=4, min_amount=100_000.0)

    assert len(hits) == 1
    assert hits[0].motif == "cycle_trade"
    assert hits[0].center == "A"
    assert hits[0].nodes == ["A", "B", "C"]
    assert "封閉資金環" in hits[0].description_zh


def test_detect_cycle_trade_skips_cycle_below_min_amount():
    """環上最小金額低於門檻的零星往來不應誤報。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000.0)
    g.add_edge("B", "A", amount=900.0)

    assert detect_cycle_trade(g, min_amount=100_000.0) == []


def test_detect_cycle_trade_respects_max_len():
    """長度超過 max_len 的環不應命中。"""
    g = nx.DiGraph()
    g.add_edge("A", "B", amount=1_000_000.0)
    g.add_edge("B", "C", amount=1_000_000.0)
    g.add_edge("C", "D", amount=1_000_000.0)
    g.add_edge("D", "A", amount=1_000_000.0)

    assert detect_cycle_trade(g, max_len=3) == []
    assert len(detect_cycle_trade(g, max_len=4)) == 1
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: FAIL，`ModuleNotFoundError: No module named 'smelens.sna.sme_motifs'`

- [ ] **Step 3: 寫最小實作**

建立 `smelens/sna/sme_motifs.py`：

```python
"""企金風險圖樣偵測：循環交易、空殼中介、買方集中。

與 `smelens.sna.motifs`（詐騙金流圖樣）的分工：該模組服務防詐分支，
本模組服務企金授信分支，兩者共用 `MotifHit` 結構以便同一套證據產生器
與圖譜著色邏輯能同時消費。

邊屬性慣例：`amount`（新台幣元）、`timestamp`（Unix 秒）。
邊方向 u → v 表示 **u 付款給 v**，故 v 的收入為其 in-edges 金額總和。
"""

from __future__ import annotations

import networkx as nx

from smelens.sna.motifs import MotifHit


def detect_cycle_trade(
    g: nx.DiGraph, max_len: int = 4, min_amount: float = 0.0
) -> list[MotifHit]:
    """偵測長度 2..max_len 的封閉資金環（循環交易／資金迴流）。

    企金意義：A→B→C→A 的封閉資金環在正常商流中罕見——正常交易的錢會
    流向供應鏈下游或轉為薪資、稅負而離開網絡。封閉環常見於循環開票虛增
    營收，或關係人之間資金迴流以粉飾財報周轉率。

    環上**最小**金額須 >= min_amount 才計入，避免零星小額往來構成的環誤報。
    center 取環上字典序最小的節點，確保同一個環只回報一次且結果穩定。
    """
    hits: list[MotifHit] = []
    seen: set[tuple[str, ...]] = set()
    for cycle in nx.simple_cycles(g, length_bound=max_len):
        if len(cycle) < 2:  # 自環非交易環
            continue
        amounts = [
            float(g[cycle[i]][cycle[(i + 1) % len(cycle)]].get("amount", 0.0))
            for i in range(len(cycle))
        ]
        if min(amounts) < min_amount:
            continue
        key = tuple(sorted(str(n) for n in cycle))
        if key in seen:
            continue
        seen.add(key)
        center = min(cycle, key=str)
        hits.append(
            MotifHit(
                motif="cycle_trade",
                center=center,
                nodes=sorted(cycle, key=str),
                description_zh=(
                    f"節點 {center} 位於長度 {len(cycle)} 的封閉資金環"
                    f"（環上最小金額 {min(amounts):,.0f}），"
                    "符合循環交易／資金迴流圖樣。"
                ),
            )
        )
    return hits
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/sna/sme_motifs.py tests/test_sme_motifs.py
git commit -F - <<'EOF'
feat(sme-motifs): 循環交易圖樣偵測

封閉資金環在正常商流中罕見，常見於循環開票虛增營收與關係人資金迴流。
環上最小金額須達門檻才計入，避免零星往來誤報；center 取字典序最小節點，
確保同一環只回報一次。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 3: 企金圖樣——空殼中介 `detect_shell_intermediary`

**Files:**
- Modify: `smelens/sna/sme_motifs.py`
- Test: `tests/test_sme_motifs.py`

**Interfaces:**
- Consumes: `MotifHit`
- Produces: `detect_shell_intermediary(g: nx.DiGraph, min_passthrough: float = 0.9, max_counterparties: int = 3) -> list[MotifHit]`，`motif` 值為 `"shell_intermediary"`

- [ ] **Step 1: 寫失敗的測試**

在 `tests/test_sme_motifs.py` 的 import 區塊加入 `detect_shell_intermediary`，使該行成為：

```python
from smelens.sna.sme_motifs import detect_cycle_trade, detect_shell_intermediary
```

並在檔案末尾追加：

```python
def test_detect_shell_intermediary_flags_passthrough_node():
    """錢進來就出去、對手方極少者為空殼；有留存毛利者不是。"""
    g = nx.DiGraph()
    g.add_edge("買方甲", "宏益企業", amount=5_000_000.0)
    g.add_edge("宏益企業", "供應商乙", amount=4_950_000.0)  # 過水比 99%
    g.add_edge("買方甲", "實營公司", amount=5_000_000.0)
    g.add_edge("實營公司", "供應商乙", amount=3_000_000.0)  # 留存 40%，非空殼

    hits = detect_shell_intermediary(g, min_passthrough=0.9, max_counterparties=3)

    assert [h.center for h in hits] == ["宏益企業"]
    assert hits[0].motif == "shell_intermediary"
    assert "過水比" in hits[0].description_zh


def test_detect_shell_intermediary_ignores_many_counterparties():
    """對手方眾多的樞紐是集散中心而非空殼，不應命中。"""
    g = nx.DiGraph()
    for i in range(5):
        g.add_edge(f"進{i}", "樞紐", amount=1_000_000.0)
    g.add_edge("樞紐", "出0", amount=5_000_000.0)

    assert detect_shell_intermediary(g, max_counterparties=3) == []


def test_detect_shell_intermediary_ignores_endpoints():
    """只有進或只有出的端點不構成過水中介。"""
    g = nx.DiGraph()
    g.add_edge("起點", "終點", amount=1_000_000.0)

    assert detect_shell_intermediary(g) == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: FAIL，`ImportError: cannot import name 'detect_shell_intermediary'`

- [ ] **Step 3: 寫最小實作**

在 `smelens/sna/sme_motifs.py` 末尾追加：

```python
def detect_shell_intermediary(
    g: nx.DiGraph, min_passthrough: float = 0.9, max_counterparties: int = 3
) -> list[MotifHit]:
    """偵測空殼過水中介：錢進來就出去、自己幾乎不留，且對手方極少。

    企金意義：正常營運企業會留下毛利、繳稅與發薪，流入與流出金額不會近乎
    相等。流入 ≈ 流出且對手方高度集中，是空殼公司代開發票、代收轉付的典型
    特徵——這種節點會讓資金流向在帳面上「合理化」，是關係人交易的遮蔽層。

    對手方數以進、出**度數**衡量（非金額），任一方向超過 max_counterparties
    即視為集散樞紐而非空殼。
    """
    hits: list[MotifHit] = []
    for node in g.nodes():
        in_amount = sum(float(d.get("amount", 0.0)) for _, _, d in g.in_edges(node, data=True))
        out_amount = sum(float(d.get("amount", 0.0)) for _, _, d in g.out_edges(node, data=True))
        if in_amount <= 0 or out_amount <= 0:
            continue
        in_degree = g.in_degree(node)
        out_degree = g.out_degree(node)
        if in_degree > max_counterparties or out_degree > max_counterparties:
            continue
        ratio = min(in_amount, out_amount) / max(in_amount, out_amount)
        if ratio < min_passthrough:
            continue
        peers = sorted({*g.predecessors(node), *g.successors(node)}, key=str)
        hits.append(
            MotifHit(
                motif="shell_intermediary",
                center=node,
                nodes=[node, *peers],
                description_zh=(
                    f"節點 {node} 流入 {in_amount:,.0f}、流出 {out_amount:,.0f}，"
                    f"過水比 {ratio:.0%}，對手方僅 {in_degree} 進 {out_degree} 出，"
                    "自身幾無留存，符合空殼中介過水圖樣。"
                ),
            )
        )
    return hits
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/sna/sme_motifs.py tests/test_sme_motifs.py
git commit -F - <<'EOF'
feat(sme-motifs): 空殼中介過水圖樣偵測

正常營運企業會留下毛利、繳稅與發薪，流入流出不會近乎相等。以過水比搭配
對手方度數上限篩出代開發票、代收轉付的空殼節點，並排除集散樞紐。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 4: 企金圖樣——買方集中與 `detect_all_sme`

**Files:**
- Modify: `smelens/sna/sme_motifs.py`
- Test: `tests/test_sme_motifs.py`

**Interfaces:**
- Consumes: `detect_cycle_trade`、`detect_shell_intermediary`（Task 2、3）
- Produces:
  - `detect_buyer_concentration(g: nx.DiGraph, min_ratio: float = 0.7, min_revenue: float = 0.0) -> list[MotifHit]`，`motif` 值為 `"buyer_concentration"`
  - `detect_all_sme(g: nx.DiGraph) -> list[MotifHit]`（三圖樣合集，供授信意見書引用）

- [ ] **Step 1: 寫失敗的測試**

把 `tests/test_sme_motifs.py` 的 import 行改為：

```python
from smelens.sna.sme_motifs import (
    detect_all_sme,
    detect_buyer_concentration,
    detect_cycle_trade,
    detect_shell_intermediary,
)
```

並在檔案末尾追加：

```python
def test_detect_buyer_concentration_flags_single_buyer():
    """逾七成收入來自單一買方者命中；收入分散者不命中。"""
    g = nx.DiGraph()
    g.add_edge("大買方", "集中廠商", amount=9_000_000.0)
    g.add_edge("小買方", "集中廠商", amount=1_000_000.0)  # 90% 集中
    g.add_edge("大買方", "分散廠商", amount=3_000_000.0)
    g.add_edge("小買方", "分散廠商", amount=3_500_000.0)  # 54% 集中

    hits = detect_buyer_concentration(g, min_ratio=0.7)

    assert [h.center for h in hits] == ["集中廠商"]
    assert hits[0].motif == "buyer_concentration"
    assert hits[0].nodes == ["集中廠商", "大買方"]


def test_detect_buyer_concentration_respects_min_revenue():
    """營收規模低於門檻者不納入評估，避免對微型往來過度反應。"""
    g = nx.DiGraph()
    g.add_edge("大買方", "微型廠商", amount=50_000.0)

    assert detect_buyer_concentration(g, min_ratio=0.7, min_revenue=1_000_000.0) == []


def test_detect_all_sme_combines_three_motifs():
    """合集應同時涵蓋三種圖樣。"""
    g = nx.DiGraph()
    # 封閉資金環
    g.add_edge("環甲", "環乙", amount=2_000_000.0)
    g.add_edge("環乙", "環甲", amount=1_900_000.0)
    # 空殼過水
    g.add_edge("來源", "空殼", amount=3_000_000.0)
    g.add_edge("空殼", "去向", amount=2_970_000.0)

    motifs = {h.motif for h in detect_all_sme(g)}

    assert "cycle_trade" in motifs
    assert "shell_intermediary" in motifs
    assert "buyer_concentration" in motifs
```

備註：最後一個測試中，`去向` 的收入 2,970,000 全部來自 `空殼`（100% 集中），故 `buyer_concentration` 必然命中。

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: FAIL，`ImportError: cannot import name 'detect_all_sme'`

- [ ] **Step 3: 寫最小實作**

在 `smelens/sna/sme_motifs.py` 末尾追加：

```python
def detect_buyer_concentration(
    g: nx.DiGraph, min_ratio: float = 0.7, min_revenue: float = 0.0
) -> list[MotifHit]:
    """偵測單一買方營收集中：逾 min_ratio 的收入來自同一家買方。

    企金意義：買方集中度過高的供應商，一旦該買方抽單、殺價或倒閉即現金流
    斷裂。這是中小企業授信最典型的隱藏風險，卻**不會顯現在財報的獲利數字
    上**——帳面毛利可能很漂亮，風險藏在客戶結構裡。

    收入定義為 in-edges 金額總和（邊方向 u → v 表示 u 付款給 v）。
    營收低於 min_revenue 者跳過，避免對微型往來過度反應。
    """
    hits: list[MotifHit] = []
    for node in g.nodes():
        by_buyer: dict[object, float] = {}
        for u, _, d in g.in_edges(node, data=True):
            by_buyer[u] = by_buyer.get(u, 0.0) + float(d.get("amount", 0.0))
        revenue = sum(by_buyer.values())
        if revenue <= 0 or revenue < min_revenue:
            continue
        # 金額相同時以字串排序決勝，確保結果穩定可重現
        top_buyer = max(by_buyer, key=lambda b: (by_buyer[b], str(b)))
        ratio = by_buyer[top_buyer] / revenue
        if ratio < min_ratio:
            continue
        hits.append(
            MotifHit(
                motif="buyer_concentration",
                center=node,
                nodes=[node, top_buyer],
                description_zh=(
                    f"節點 {node} 收入 {revenue:,.0f} 中有 {ratio:.0%} 來自單一買方 "
                    f"{top_buyer}，符合買方集中圖樣（客戶集中度風險）。"
                ),
            )
        )
    return hits


def detect_all_sme(g: nx.DiGraph) -> list[MotifHit]:
    """企金三大風險圖樣一次偵測，供授信意見書引用。"""
    return [
        *detect_cycle_trade(g),
        *detect_shell_intermediary(g),
        *detect_buyer_concentration(g),
    ]
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_motifs.py -q
```
Expected: `9 passed`

- [ ] **Step 5: 跑完整套件與 lint**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m ruff check . --exclude .venv
```
Expected: `98 passed`；`All checks passed!`

- [ ] **Step 6: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/sna/sme_motifs.py tests/test_sme_motifs.py
git commit -F - <<'EOF'
feat(sme-motifs): 買方集中圖樣與三圖樣合集

買方集中度是中小企業授信最典型的隱藏風險，帳面毛利漂亮但風險藏在客戶
結構裡，財報看不到、關係圖看得到。detect_all_sme 提供三圖樣合集供授信
意見書引用。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 5: 中小企業供應鏈授信劇本圖

建立 demo 與測試共用的基準情境圖。這是決賽現場示範的主場景，也是後續所有模組的固定測試夾具。

**Files:**
- Create: `smelens/data/sme_scenario.py`
- Test: `tests/test_sme_scenario.py`

**Interfaces:**
- Consumes: `detect_all_sme`、`detect_shell_intermediary`、`detect_cycle_trade`（Task 2–4）
- Produces:
  - `load_supply_chain_scenario() -> nx.DiGraph`
  - 常數 `CREDIT_APPLICANT = "泰昇精密"`、`NORMAL_APPLICANT = "禾昌五金"`、`APPLICATION_AMOUNT_TWD = 30_000_000.0`
  - 節點屬性 `role`（鍵見 `ROLE_ZH`）；圖屬性 `credit_applicant`、`normal_applicant`、`application_amount_twd`、`story_zh`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_sme_scenario.py`：

```python
"""中小企業供應鏈授信劇本圖測試。"""

from __future__ import annotations

from smelens.data.sme_scenario import (
    APPLICATION_AMOUNT_TWD,
    CREDIT_APPLICANT,
    NORMAL_APPLICANT,
    load_supply_chain_scenario,
)
from smelens.sna.sme_motifs import (
    detect_all_sme,
    detect_buyer_concentration,
    detect_cycle_trade,
    detect_shell_intermediary,
)


def test_scenario_graph_metadata():
    """圖屬性須完整，供 API 與工作台直接引用。"""
    g = load_supply_chain_scenario()

    assert g.graph["credit_applicant"] == CREDIT_APPLICANT
    assert g.graph["normal_applicant"] == NORMAL_APPLICANT
    assert g.graph["application_amount_twd"] == APPLICATION_AMOUNT_TWD
    assert g.graph["story_zh"]
    assert all("role" in d for _, d in g.nodes(data=True))


def test_applicant_sits_on_a_closed_money_cycle():
    """申請人與關係人構成封閉資金環。"""
    g = load_supply_chain_scenario()

    cycles = detect_cycle_trade(g)

    assert any(CREDIT_APPLICANT in hit.nodes for hit in cycles)


def test_shell_intermediary_is_the_only_passthrough():
    """劇本中僅宏益企業為空殼過水節點。"""
    g = load_supply_chain_scenario()

    centers = {hit.center for hit in detect_shell_intermediary(g)}

    assert centers == {"宏益企業"}


def test_applicant_is_buyer_concentrated():
    """申請人逾七成收入來自單一買方。"""
    g = load_supply_chain_scenario()

    centers = {hit.center for hit in detect_buyer_concentration(g, min_ratio=0.7)}

    assert CREDIT_APPLICANT in centers


def test_normal_applicant_triggers_no_motif():
    """對照組結構乾淨，不得命中任何企金圖樣。"""
    g = load_supply_chain_scenario()

    hits = [hit for hit in detect_all_sme(g) if hit.center == NORMAL_APPLICANT]

    assert hits == []
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_scenario.py -q
```
Expected: FAIL，`ModuleNotFoundError: No module named 'smelens.data.sme_scenario'`

- [ ] **Step 3: 寫最小實作**

建立 `smelens/data/sme_scenario.py`：

```python
"""3,000 萬營運週轉金授信劇本圖（企劃書第一章招牌情境）。

劇本：「泰昇精密」向臺企銀申請 3,000 萬營運週轉金。財報表面健康——營收
成長、毛利穩定、無退票紀錄，依現行徵信流程會通過。但關係圖揭露三件財報
看不到的事：

1. **買方集中**：逾八成收入來自單一買方「鴻寶電子」，該買方抽單即斷炊。
2. **空殼過水**：資金經「宏益企業」流出，該公司流入 ≈ 流出、對手方僅各一，
   自身幾無留存，是典型代收轉付空殼。
3. **循環交易**：泰昇精密 → 宏益企業 → 昇泰貿易 → 泰昇投資 → 泰昇精密
   構成封閉資金環，疑似循環開票虛增營收。

對照組「禾昌五金」買方分散、資金留存正常、不在任何環上，用以演示本系統
不會對正常企業誤報——**能區辨才有價值，全部標紅等於沒有訊號**。

邊屬性：amount（新台幣元）、timestamp（Unix 秒）。
邊方向 u → v 表示 u 付款給 v。
"""

from __future__ import annotations

import networkx as nx

# 劇本角色 → 中文名稱（工作台 tooltip 與敘事用）
ROLE_ZH = {
    "applicant": "授信申請人",
    "anchor_buyer": "核心買方",
    "buyer": "一般買方",
    "shell": "空殼中介",
    "related": "關係人公司",
    "supplier": "供應商",
    "normal": "對照組正常企業",
}

CREDIT_APPLICANT = "泰昇精密"
NORMAL_APPLICANT = "禾昌五金"
APPLICATION_AMOUNT_TWD = 30_000_000.0

_STORY_ZH = (
    "泰昇精密申請 3,000 萬營運週轉金，財報健康、無退票；關係圖卻顯示其逾八成"
    "收入來自單一買方、資金經空殼中介過水，並與關係人構成封閉資金環。"
)

_T0 = 1_760_000_000  # 劇本基準時間


def _add(g: nx.DiGraph, u: str, v: str, amount: float, offset_days: int) -> None:
    """加一筆付款：u 付款給 v。offset_days 為距劇本基準時間的天數。"""
    g.add_edge(u, v, amount=amount, timestamp=_T0 + offset_days * 86_400)


def load_supply_chain_scenario() -> nx.DiGraph:
    """建構中小企業供應鏈授信劇本圖。"""
    g = nx.DiGraph()

    roles = {
        CREDIT_APPLICANT: "applicant",
        "鴻寶電子": "anchor_buyer",
        "中部機電": "buyer",
        "宏益企業": "shell",
        "昇泰貿易": "related",
        "泰昇投資": "related",
        NORMAL_APPLICANT: "normal",
        "大安工業": "buyer",
        "永康鋼鐵": "buyer",
        "南方塑膠": "buyer",
        "華隆貿易": "buyer",
    }
    for name, role in roles.items():
        g.add_node(name, role=role)

    # --- 第一幕：申請人的收入結構（總收入 31,400,000，單一買方佔 84%）---
    _add(g, "鴻寶電子", CREDIT_APPLICANT, 26_400_000.0, 0)
    _add(g, "中部機電", CREDIT_APPLICANT, 1_200_000.0, 5)

    # --- 第二幕：資金經空殼中介流出，再繞經關係人回到申請人（封閉環）---
    _add(g, CREDIT_APPLICANT, "宏益企業", 6_000_000.0, 10)
    _add(g, "宏益企業", "昇泰貿易", 5_940_000.0, 12)  # 過水比 99%
    _add(g, "昇泰貿易", "泰昇投資", 4_500_000.0, 20)
    _add(g, "泰昇投資", CREDIT_APPLICANT, 3_800_000.0, 28)  # 資金迴流，環長 4

    # --- 第三幕：對照組——買方分散、資金留存正常、不在任何環上 ---
    _add(g, "大安工業", NORMAL_APPLICANT, 3_000_000.0, 2)
    _add(g, "永康鋼鐵", NORMAL_APPLICANT, 2_800_000.0, 7)
    _add(g, "南方塑膠", NORMAL_APPLICANT, 2_600_000.0, 14)
    _add(g, "華隆貿易", NORMAL_APPLICANT, 2_400_000.0, 21)
    _add(g, NORMAL_APPLICANT, "中部機電", 4_000_000.0, 25)  # 留存 63%，非空殼

    g.graph["credit_applicant"] = CREDIT_APPLICANT
    g.graph["normal_applicant"] = NORMAL_APPLICANT
    g.graph["application_amount_twd"] = APPLICATION_AMOUNT_TWD
    g.graph["story_zh"] = _STORY_ZH
    return g
```

**數字驗算（供審查者核對）：**
- 泰昇精密收入 = 26,400,000 + 1,200,000 + 3,800,000 = 31,400,000；最大單一買方佔比 = 26,400,000 / 31,400,000 = **84.1% ≥ 70%** → 買方集中命中
- 宏益企業：流入 6,000,000、流出 5,940,000，過水比 **99% ≥ 90%**，進出度數各 1 → 空殼命中
- 昇泰貿易：流入 5,940,000、流出 4,500,000，過水比 75.8% < 90% → 不命中
- 泰昇投資：流入 4,500,000、流出 3,800,000，過水比 84.4% < 90% → 不命中
- 泰昇精密：流入 31,400,000、流出 6,000,000，過水比 19% → 不命中空殼
- 環：泰昇精密 → 宏益企業 → 昇泰貿易 → 泰昇投資 → 泰昇精密，長度 4 ≤ max_len 預設 4 → 命中
- 禾昌五金：收入 10,800,000，最大買方佔 27.8% < 70%；流出 4,000,000／流入 10,800,000 過水比 37% < 90%；無入邊來自其下游，故不在任何環上 → 三圖樣皆不命中

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_sme_scenario.py -q
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/data/sme_scenario.py tests/test_sme_scenario.py
git commit -F - <<'EOF'
feat(scenario): 3000 萬營運週轉金授信劇本圖

財報健康但關係圖揭露買方集中、空殼過水與封閉資金環三項風險，並附結構
乾淨的對照組——能區辨才有價值，全部標紅等於沒有訊號。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 6: 集團歸戶

**Files:**
- Create: `smelens/credit/__init__.py`, `smelens/credit/group.py`
- Test: `tests/test_group.py`

**Interfaces:**
- Consumes: networkx
- Produces:
  - `Affiliation`（frozen dataclass，欄位 `company: str`、`person: str`、`role: str = "董監事"`）
  - `build_company_graph(affiliations: Iterable[Affiliation]) -> nx.Graph`（邊屬性 `weight: int`、`shared: list[str]`）
  - `detect_groups(company_graph: nx.Graph) -> dict[str, int]`
  - `group_exposure(groups: dict[str, int], exposures: Mapping[str, float]) -> dict[int, float]`
  - `hidden_links(company_graph: nx.Graph, declared: Mapping[str, str]) -> list[dict[str, Any]]`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_group.py`：

```python
"""集團歸戶測試：公司關聯圖、遞移歸戶、曝險彙總與隱性關聯揭露。"""

from __future__ import annotations

from smelens.credit.group import (
    Affiliation,
    build_company_graph,
    detect_groups,
    group_exposure,
    hidden_links,
)

_AFFILIATIONS = [
    Affiliation("泰昇精密", "陳大明", "董事長"),
    Affiliation("泰昇投資", "陳大明", "董事"),
    Affiliation("昇泰貿易", "王秀英", "董事"),
    Affiliation("泰昇投資", "王秀英", "監察人"),
    Affiliation("禾昌五金", "林志豪", "董事長"),
]


def test_build_company_graph_links_companies_sharing_a_person():
    """共用同一自然人的兩家公司之間應連邊，未共用者不連。"""
    g = build_company_graph(_AFFILIATIONS)

    assert g.has_edge("泰昇精密", "泰昇投資")
    assert g["泰昇精密"]["泰昇投資"]["weight"] == 1
    assert g["泰昇精密"]["泰昇投資"]["shared"] == ["陳大明"]
    assert not g.has_edge("泰昇精密", "禾昌五金")
    assert "禾昌五金" in g  # 無共用者仍須入圖，否則歸戶會漏掉單獨公司


def test_detect_groups_is_transitive():
    """A-B 共用、B-C 共用，則 A、B、C 同屬一個歸戶群組。"""
    g = build_company_graph(_AFFILIATIONS)

    groups = detect_groups(g)

    assert groups["泰昇精密"] == groups["泰昇投資"] == groups["昇泰貿易"]
    assert groups["禾昌五金"] != groups["泰昇精密"]


def test_group_exposure_sums_by_group():
    """集團曝險為群組內各公司授信餘額之和。"""
    g = build_company_graph(_AFFILIATIONS)
    groups = detect_groups(g)
    exposures = {
        "泰昇精密": 30_000_000.0,
        "泰昇投資": 12_000_000.0,
        "昇泰貿易": 8_000_000.0,
        "禾昌五金": 5_000_000.0,
    }

    totals = group_exposure(groups, exposures)

    assert totals[groups["泰昇精密"]] == 50_000_000.0
    assert totals[groups["禾昌五金"]] == 5_000_000.0


def test_group_exposure_ignores_unknown_company():
    """不在關係圖中的公司不計入任何集團。"""
    groups = {"甲公司": 0}

    totals = group_exposure(groups, {"甲公司": 100.0, "查無此公司": 999.0})

    assert totals == {0: 100.0}


def test_hidden_links_reports_undeclared_relation():
    """客戶申報為不同集團、但關係圖上存在連結者，應列為隱性關聯。"""
    g = build_company_graph(_AFFILIATIONS)
    declared = {
        "泰昇精密": "泰昇集團",
        "泰昇投資": "泰昇集團",
        "昇泰貿易": "昇泰集團",  # 客戶申報為獨立集團，實際共用王秀英
    }

    found = hidden_links(g, declared)

    assert len(found) == 1
    assert found[0]["company_a"] == "昇泰貿易"
    assert found[0]["company_b"] == "泰昇投資"
    assert found[0]["shared_persons"] == ["王秀英"]
    assert found[0]["declared_group_a"] == "昇泰集團"
    assert found[0]["declared_group_b"] == "泰昇集團"
```

備註：`hidden_links` 回傳依 `(company_a, company_b)` 排序，且每筆的兩家公司名以字串排序放置，故「昇泰貿易」在前、「泰昇投資」在後。

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_group.py -q
```
Expected: FAIL，`ModuleNotFoundError: No module named 'smelens.credit'`

- [ ] **Step 3: 寫最小實作**

建立 `smelens/credit/__init__.py`：

```python
"""企金授信語意層：集團歸戶與授信意見書。"""
```

建立 `smelens/credit/group.py`：

```python
"""集團歸戶：以公司—自然人關係投影出公司關聯圖，揭露隱性集團。

現行實務中，集團授信歸戶主要倚賴客戶自行申報的關係企業表，行員再以人工
比對。共用董監事、交叉持股、共用登記地址等隱性關聯查不出來，導致集團曝
險在帳面上被拆散、實際上超限。本模組把這件事變成一個圖問題。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from itertools import combinations
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class Affiliation:
    """一筆公司—自然人關係（董監事、股東或負責人）。"""

    company: str
    person: str
    role: str = "董監事"


def build_company_graph(affiliations: Iterable[Affiliation]) -> nx.Graph:
    """由關係名冊建立公司關聯無向圖：共用同一自然人的兩家公司之間連邊。

    邊屬性 weight = 共用的自然人數；shared = 共用自然人名單（排序後）。
    無任何共用關係的公司仍會入圖成為孤立節點——歸戶時不能把它們漏掉。
    """
    records = list(affiliations)
    by_person: dict[str, set[str]] = {}
    for item in records:
        by_person.setdefault(item.person, set()).add(item.company)

    g = nx.Graph()
    for item in records:
        g.add_node(item.company)
    for person, companies in by_person.items():
        for u, v in combinations(sorted(companies), 2):
            if g.has_edge(u, v):
                g[u][v]["weight"] += 1
                g[u][v]["shared"].append(person)
            else:
                g.add_edge(u, v, weight=1, shared=[person])
    for _, _, data in g.edges(data=True):
        data["shared"].sort()
    return g


def detect_groups(company_graph: nx.Graph) -> dict[str, int]:
    """以連通元件切分集團，回傳 {公司: 集團編號}。

    刻意**不用** Louvain：集團歸戶在授信實務上是**遞移關係**——A 與 B 共用
    董事、B 與 C 共用董事，則 A、B、C 同屬一個歸戶群組，不因群內連結稀疏
    而被模組度切開。Louvain 會把弱連結的邊緣公司切出去，那正是集團歸戶最
    怕的漏網。社群偵測適合找「結構相似的群」，歸戶要的是「連得到就算」。

    集團編號依元件內字典序最小的公司名排序後給定，確保結果穩定可重現。
    """
    groups: dict[str, int] = {}
    components = sorted(nx.connected_components(company_graph), key=lambda c: sorted(c)[0])
    for index, component in enumerate(components):
        for company in component:
            groups[company] = index
    return groups


def group_exposure(groups: dict[str, int], exposures: Mapping[str, float]) -> dict[int, float]:
    """彙總各集團的授信曝險總額。不在 groups 內的公司一律忽略。"""
    totals: dict[int, float] = {}
    for company, amount in exposures.items():
        group_id = groups.get(company)
        if group_id is None:
            continue
        totals[group_id] = totals.get(group_id, 0.0) + float(amount)
    return totals


def hidden_links(
    company_graph: nx.Graph, declared: Mapping[str, str]
) -> list[dict[str, Any]]:
    """列出關係圖上存在、但客戶申報表歸屬不同集團的公司對（隱性關聯）。

    declared 為客戶自行申報的集團代號 {公司: 申報集團}；未申報者視為各自
    獨立的集團。回傳每筆含兩家公司、共用自然人與雙方申報集團，供行員覆核
    ——本模組只負責把證據攤開，是否併入歸戶由授信人員判斷。
    """
    found: list[dict[str, Any]] = []
    for u, v, data in company_graph.edges(data=True):
        company_a, company_b = sorted([u, v])
        group_a = declared.get(company_a, f"__undeclared__{company_a}")
        group_b = declared.get(company_b, f"__undeclared__{company_b}")
        if group_a == group_b:
            continue
        found.append(
            {
                "company_a": company_a,
                "company_b": company_b,
                "shared_persons": list(data["shared"]),
                "declared_group_a": declared.get(company_a),
                "declared_group_b": declared.get(company_b),
            }
        )
    return sorted(found, key=lambda row: (row["company_a"], row["company_b"]))
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_group.py -q
```
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/credit/__init__.py smelens/credit/group.py tests/test_group.py
git commit -F - <<'EOF'
feat(credit): 集團歸戶與隱性關聯揭露

以公司—自然人二部關係投影出公司關聯圖，用連通元件而非 Louvain 做歸戶：
歸戶在授信實務上是遞移關係，模組度切分會把弱連結的邊緣公司切出去，那正
是集團曝險最怕的漏網。hidden_links 只攤開證據，併戶與否由授信人員判斷。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 7: 授信意見書產生器

**Files:**
- Create: `smelens/credit/opinion.py`
- Test: `tests/test_credit_opinion.py`

**Interfaces:**
- Consumes: `smelens.sna.metrics.compute_sna_features`、`smelens.sna.community.detect_communities`、`smelens.sna.community.community_risk_ratio`、`smelens.sna.sme_motifs.detect_all_sme`、`smelens.explain.evidence.PipelineResult`（型別別名 `tuple[pd.DataFrame, dict[Any, int], dict[int, float], list[MotifHit]]`）
- Produces:
  - `run_sme_pipeline(g: nx.DiGraph) -> PipelineResult`
  - `counterparty_diversity(g: nx.DiGraph, node: Any) -> float`
  - `network_credit(g: nx.DiGraph, node: Any, sna_df: pd.DataFrame) -> float`
  - `generate_credit_opinion(node, g, sna_df, partition, risk_ratios, motif_hits, *, group_id=None, group_exposure_twd=None, model_score=None) -> dict[str, Any]`，回傳鍵：`target`、`attention_score`、`network_credit`、`label`、`label_zh`、`counterparty_diversity`、`centrality_percentile`、`community_risk_ratio`、`group_id`、`group_exposure_twd`、`motif_hits`、`narrative_zh`、`recommendation_zh`

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_credit_opinion.py`：

```python
"""授信意見書測試。"""

from __future__ import annotations

import networkx as nx

from smelens.credit.opinion import (
    counterparty_diversity,
    generate_credit_opinion,
    network_credit,
    run_sme_pipeline,
)
from smelens.data.sme_scenario import (
    CREDIT_APPLICANT,
    NORMAL_APPLICANT,
    load_supply_chain_scenario,
)


def test_counterparty_diversity_single_buyer_is_zero():
    """收入全部來自單一買方，多樣性為 0。"""
    g = nx.DiGraph()
    g.add_edge("唯一買方", "廠商", amount=5_000_000.0)

    assert counterparty_diversity(g, "廠商") == 0.0


def test_counterparty_diversity_even_split_is_one():
    """四個買方均分收入，多樣性為 1。"""
    g = nx.DiGraph()
    for i in range(4):
        g.add_edge(f"買方{i}", "廠商", amount=1_000_000.0)

    assert counterparty_diversity(g, "廠商") == 1.0


def test_counterparty_diversity_no_revenue_is_zero():
    """無收入者多樣性為 0，且不得除以零。"""
    g = nx.DiGraph()
    g.add_edge("廠商", "供應商", amount=1_000_000.0)

    assert counterparty_diversity(g, "廠商") == 0.0


def test_network_credit_prefers_diversified_company():
    """對照組買方分散，網絡信用分應高於買方集中的申請人。"""
    g = load_supply_chain_scenario()
    sna_df, _, _, _ = run_sme_pipeline(g)

    assert network_credit(g, NORMAL_APPLICANT, sna_df) > network_credit(
        g, CREDIT_APPLICANT, sna_df
    )


def test_credit_opinion_flags_applicant_with_motifs():
    """申請人命中圖樣，關注分數應達留意以上並附中文敘事與建議。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert opinion["target"] == CREDIT_APPLICANT
    assert opinion["label"] in {"watch", "caution"}
    assert opinion["attention_score"] >= 0.4
    assert opinion["motif_hits"], "申請人應命中至少一個企金圖樣"
    assert CREDIT_APPLICANT in opinion["narrative_zh"]
    assert opinion["recommendation_zh"]


def test_credit_opinion_includes_cycle_even_when_not_center():
    """循環交易的環上成員都應被引用，不能只算 center。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert any(hit["motif"] == "cycle_trade" for hit in opinion["motif_hits"])


def test_credit_opinion_normal_company_is_not_watch():
    """對照組未命中圖樣，不得被列為關注。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        NORMAL_APPLICANT, g, sna_df, partition, risk_ratios, motif_hits
    )

    assert opinion["label"] != "watch"
    assert opinion["motif_hits"] == []


def test_credit_opinion_carries_group_context():
    """帶入集團資訊時應原樣附在意見書上，供行員覆核集團曝險。"""
    g = load_supply_chain_scenario()
    sna_df, partition, risk_ratios, motif_hits = run_sme_pipeline(g)

    opinion = generate_credit_opinion(
        CREDIT_APPLICANT,
        g,
        sna_df,
        partition,
        risk_ratios,
        motif_hits,
        group_id=0,
        group_exposure_twd=50_000_000.0,
    )

    assert opinion["group_id"] == 0
    assert opinion["group_exposure_twd"] == 50_000_000.0
    assert "集團" in opinion["narrative_zh"]
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_credit_opinion.py -q
```
Expected: FAIL，`ModuleNotFoundError: No module named 'smelens.credit.opinion'`

- [ ] **Step 3: 寫最小實作**

建立 `smelens/credit/opinion.py`：

```python
"""授信意見書產生器：把圖結構證據轉成行員可覆核的授信意見。

設計原則：**不輸出黑箱分數**。每一個判定都附帶結構證據（命中圖樣、中心性
百分位、對手多樣性、集團曝險）與中文敘事，讓授信人員能覆核、能寫進徵信
報告、能對監理交代。分數只是敘事的索引，不是結論本身。
"""

from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any

import networkx as nx
import pandas as pd

from smelens.explain.evidence import PipelineResult
from smelens.sna.community import community_risk_ratio, detect_communities
from smelens.sna.metrics import compute_sna_features
from smelens.sna.sme_motifs import detect_all_sme

_LABEL_ZH = {"watch": "關注", "caution": "留意", "normal": "正常"}

_RECOMMENDATION_ZH = {
    "watch": "建議暫緩核貸，先行實地查核關係人交易與主要買方合約之真實性。",
    "caution": "建議核貸但調降額度並縮短覆審週期，要求補提主要買方合約與出貨憑證。",
    "normal": "結構面未見異常，得依既有授信條件辦理。",
}


def run_sme_pipeline(g: nx.DiGraph) -> PipelineResult:
    """企金版分析管線：SNA → 社群 → 企金圖樣，回傳四元組。

    與 `smelens.explain.evidence.run_pipeline` 的唯一差異是圖樣集合——企金
    三圖樣取代詐騙圖樣。社群風險比以圖樣命中中心作為代理標註（企業關係圖
    無 licit/illicit 真值標註，與 ChainLens 處理 TRON 即時圖的慣例一致）。
    """
    sna_df = compute_sna_features(g)
    partition = detect_communities(g)
    motif_hits = detect_all_sme(g)
    labels = {hit.center: 1 for hit in motif_hits}
    risk_ratios = community_risk_ratio(partition, labels)
    return sna_df, partition, risk_ratios, motif_hits


def counterparty_diversity(g: nx.DiGraph, node: Any) -> float:
    """交易對手多樣性（0–1）：買方金額分布的正規化熵。

    單一買方 → 0；n 個買方平均分攤 → 1。無收入者回傳 0。
    企金意義：這是「客戶集中度」的連續版本，比二元的圖樣命中更適合放進
    信用分計算——集中度是程度問題，不是有無問題。
    """
    amounts: dict[Any, float] = {}
    for u, _, data in g.in_edges(node, data=True):
        amounts[u] = amounts.get(u, 0.0) + float(data.get("amount", 0.0))
    total = sum(amounts.values())
    if total <= 0:
        return 0.0
    shares = [amount / total for amount in amounts.values() if amount > 0]
    if len(shares) < 2:
        return 0.0
    entropy = -sum(share * math.log(share) for share in shares)
    return round(entropy / math.log(len(shares)), 4)


def network_credit(g: nx.DiGraph, node: Any, sna_df: pd.DataFrame) -> float:
    """網絡信用分（0–1，愈高信用愈佳）。

    = 0.5 × 結構中心性百分位均值 + 0.5 × 交易對手多樣性

    企金意義：在供應鏈網絡中位置愈核心、交易對手愈分散的企業，現金流韌性
    愈高——這是財報看不到、但關係圖看得到的信用證據，正是「沒有漂亮財報
    的好公司」得以被看見的依據。

    百分位採**嚴格小於**：真實圖上多數節點的 betweenness 為 0、degree 為 1，
    若用小於等於，這批節點會被算進第 85+ 百分位而虛胖成「結構核心」。
    """
    percentiles = {
        column: float((sna_df[column] < sna_df.at[node, column]).mean())
        for column in sna_df.columns
    }
    centrality = sum(percentiles.values()) / len(percentiles)
    return round(0.5 * centrality + 0.5 * counterparty_diversity(g, node), 4)


def generate_credit_opinion(
    node: Any,
    g: nx.DiGraph,
    sna_df: pd.DataFrame,
    partition: dict[Any, int],
    risk_ratios: dict[int, float],
    motif_hits: list[Any],
    *,
    group_id: int | None = None,
    group_exposure_twd: float | None = None,
    model_score: float | None = None,
) -> dict[str, Any]:
    """對單一企業產生授信意見書。

    attention_score = 0.5 × 圖樣命中 + 0.3 × (1 − 網絡信用) + 0.2 × 社群風險比；
    提供 GNN model_score 時改為 0.5 × 模型 + 0.5 × 規則分數（與 ChainLens
    的模型／規則融合慣例一致）。

    **圖樣歸屬規則**：一般圖樣只計 center，避免周邊成員連坐；但 cycle_trade
    例外——封閉資金環上的**每一個**成員都是循環交易的參與者，不是被動的
    對手方，故環上成員全部引用。
    """
    if node not in sna_df.index:
        raise KeyError(f"企業 {node} 不在關係圖中")

    relevant = [
        hit
        for hit in motif_hits
        if hit.center == node or (hit.motif == "cycle_trade" and node in hit.nodes)
    ]
    credit = network_credit(g, node, sna_df)
    diversity = counterparty_diversity(g, node)
    community = partition.get(node, -1)
    risk_ratio = float(risk_ratios.get(community, 0.0))
    percentiles = {
        column: round(float((sna_df[column] < sna_df.at[node, column]).mean() * 100), 2)
        for column in sna_df.columns
    }

    rule_score = 0.5 * (1.0 if relevant else 0.0) + 0.3 * (1.0 - credit) + 0.2 * risk_ratio
    score = 0.5 * model_score + 0.5 * rule_score if model_score is not None else rule_score
    score = min(max(score, 0.0), 1.0)
    label = "watch" if score >= 0.7 else "caution" if score >= 0.4 else "normal"

    narrative: list[str] = [
        f"企業 {node} 網絡信用分 {credit:.2f}、授信關注分數 {score:.2f}"
        f"（{_LABEL_ZH[label]}）。"
    ]
    if relevant:
        narrative.append("命中企金風險圖樣：" + "；".join(h.description_zh for h in relevant))
    else:
        narrative.append("未命中任何企金風險圖樣。")
    narrative.append(
        f"交易對手多樣性 {diversity:.2f}"
        f"（{'買方高度集中' if diversity < 0.5 else '買方結構分散'}）。"
    )
    if group_id is not None:
        exposure_text = (
            f"，該集團授信曝險合計 {group_exposure_twd:,.0f} 元"
            if group_exposure_twd is not None
            else ""
        )
        narrative.append(f"歸戶集團編號 #{group_id}{exposure_text}。")
    if model_score is not None:
        narrative.append(f"GNN 模型判定違約機率 {model_score:.2f}。")

    return {
        "target": str(node),
        "attention_score": round(score, 4),
        "network_credit": credit,
        "label": label,
        "label_zh": _LABEL_ZH[label],
        "counterparty_diversity": diversity,
        "centrality_percentile": percentiles,
        "community_risk_ratio": round(risk_ratio, 4),
        "group_id": group_id,
        "group_exposure_twd": group_exposure_twd,
        "motif_hits": [asdict(hit) for hit in relevant],
        "narrative_zh": "".join(narrative),
        "recommendation_zh": _RECOMMENDATION_ZH[label],
    }
```

- [ ] **Step 4: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_credit_opinion.py -q
```
Expected: `8 passed`

- [ ] **Step 5: 跑完整套件與 lint**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m ruff check . --exclude .venv
```
Expected: `116 passed`；`All checks passed!`

- [ ] **Step 6: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/credit/opinion.py tests/test_credit_opinion.py
git commit -F - <<'EOF'
feat(credit): 授信意見書產生器

不輸出黑箱分數：每個判定都附結構證據與中文敘事，行員可覆核、可寫進徵信
報告、可對監理交代。網絡信用分讓「沒有漂亮財報的好公司」被看見；循環交易
的環上成員全部引用，不比照 fan-in 只計 center——環上每一位都是參與者。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 8: API 端點 `/credit` 與 `/group`

**Files:**
- Modify: `smelens/api/serialize.py`, `smelens/api/main.py`
- Test: `tests/test_api_credit.py`

**Interfaces:**
- Consumes: Task 5–7 的全部產出
- Produces:
  - `graph_to_json(..., role_zh: Mapping[str, str] | None = None)` — 新增選配參數，`None` 時沿用既有 AML 劇本對照表
  - `POST /credit`，請求 `{"target": str, "group_id": int | null, "group_exposure_twd": float | null}`；回應為 `generate_credit_opinion` 的輸出，另加 `"graph"`（`graph_to_json` 產物）
  - `POST /group`，請求 `{"affiliations": [{"company": str, "person": str, "role": str}], "declared_groups": {...}, "exposures": {...}}`；回應 `{"groups": {公司: 集團編號}, "exposures": {集團編號字串: 金額}, "hidden_links": [...]}`

**已知陷阱（本 Task 必須處理，否則會靜默劣化）：**
`graph_to_json` 以 `evidence.get("score", 0.0)` 與 `evidence.get("label", "low")` 讀取著色欄位，而授信意見書的對應鍵是 `attention_score` 與 `label`（值域為 `watch`／`caution`／`normal`）。因為有預設值，**不會拋錯**，只會把整張圖染成 0 分——這比報錯更糟。同理，`serialize.py` 的 `ROLE_ZH` 硬綁 AML 劇本，企金角色（`applicant`、`anchor_buyer`…）會回退成英文鍵。兩者都必須明確處理。

- [ ] **Step 1: 寫失敗的測試**

建立 `tests/test_api_credit.py`：

```python
"""授信與集團歸戶 API 測試。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from smelens.api.main import app
from smelens.data.sme_scenario import CREDIT_APPLICANT, NORMAL_APPLICANT

client = TestClient(app)


def test_credit_endpoint_returns_opinion_with_graph():
    """授信意見書須含分數、敘事、建議與可繪製的圖譜。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    assert response.status_code == 200
    body = response.json()
    assert body["target"] == CREDIT_APPLICANT
    assert body["label"] in {"watch", "caution", "normal"}
    assert body["recommendation_zh"]
    assert body["narrative_zh"]
    assert body["graph"]["nodes"]
    assert body["graph"]["edges"]


def test_credit_graph_nodes_carry_real_scores():
    """圖譜節點的 score 必須是真實關注分數，不得整張圖靜默染成 0。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    nodes = response.json()["graph"]["nodes"]
    scores = [node["score"] for node in nodes]

    assert max(scores) > 0.0
    assert len(set(scores)) > 1, "所有節點同分代表著色欄位沒接上"


def test_credit_graph_nodes_carry_chinese_roles():
    """企金角色必須中文化，不得回退成英文鍵。"""
    response = client.post("/credit", json={"target": CREDIT_APPLICANT})

    nodes = {node["id"]: node for node in response.json()["graph"]["nodes"]}

    assert nodes[CREDIT_APPLICANT]["role"] == "applicant"
    assert nodes[CREDIT_APPLICANT]["role_zh"] == "授信申請人"


def test_credit_endpoint_rejects_unknown_company():
    """查無此公司應回 404，不得靜默回傳空意見書。"""
    response = client.post("/credit", json={"target": "查無此公司"})

    assert response.status_code == 404


def test_credit_endpoint_normal_company_is_not_watch():
    """對照組不得被列為關注。"""
    response = client.post("/credit", json={"target": NORMAL_APPLICANT})

    assert response.json()["label"] != "watch"


def test_group_endpoint_returns_groups_and_hidden_links():
    """集團歸戶須回傳歸戶結果、集團曝險與隱性關聯。"""
    response = client.post(
        "/group",
        json={
            "affiliations": [
                {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
                {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
                {"company": "昇泰貿易", "person": "王秀英", "role": "董事"},
                {"company": "泰昇投資", "person": "王秀英", "role": "監察人"},
                {"company": "禾昌五金", "person": "林志豪", "role": "董事長"},
            ],
            "declared_groups": {
                "泰昇精密": "泰昇集團",
                "泰昇投資": "泰昇集團",
                "昇泰貿易": "昇泰集團",
            },
            "exposures": {"泰昇精密": 30_000_000, "泰昇投資": 12_000_000},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["groups"]["泰昇精密"] == body["groups"]["昇泰貿易"]
    assert body["groups"]["禾昌五金"] != body["groups"]["泰昇精密"]
    assert sum(body["exposures"].values()) == 42_000_000
    assert len(body["hidden_links"]) == 1
    assert body["hidden_links"][0]["shared_persons"] == ["王秀英"]


def test_group_endpoint_rejects_empty_affiliations():
    """空名冊無從歸戶，應回 400。"""
    response = client.post("/group", json={"affiliations": []})

    assert response.status_code == 400
```

- [ ] **Step 2: 跑測試確認失敗**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_api_credit.py -q
```
Expected: FAIL，`/credit` 回應 404（路由不存在）

- [ ] **Step 3: 讓 `graph_to_json` 支援企金角色對照表**

在 `smelens/api/serialize.py` 中，把 `graph_to_json` 的簽章與角色查表兩處改為：

```python
def graph_to_json(
    g: nx.DiGraph,
    evidences: dict[Any, dict[str, Any]],
    sna_df: pd.DataFrame,
    *,
    motif_centers: set[Any],
    degraded: bool = False,
    limit: int = MAX_GRAPH_NODES,
    role_zh: Mapping[str, str] | None = None,
) -> dict[str, Any]:
```

並在函式開頭（`pagerank = ...` 之前）插入一行：

```python
    role_names = ROLE_ZH if role_zh is None else role_zh
```

再把節點組裝處的 `"role_zh": ROLE_ZH.get(role, role),` 改為：

```python
                "role_zh": role_names.get(role, role),
```

同時在檔案的 import 區塊補上 `Mapping`，使該行成為：

```python
from collections.abc import Mapping
```

docstring 需說明新參數：

```
    role_zh：角色代碼 → 中文名稱的對照表。預設為 AML 劇本的 ROLE_ZH；企金
    劇本圖須傳入 sme_scenario.ROLE_ZH，否則角色會回退成英文鍵。
```

- [ ] **Step 4: 寫最小實作**

在 `smelens/api/main.py` 的 import 區塊追加：

```python
from smelens.credit.group import (
    Affiliation,
    build_company_graph,
    detect_groups,
    group_exposure,
    hidden_links,
)
from smelens.credit.opinion import generate_credit_opinion, run_sme_pipeline
from smelens.data import sme_scenario
```

在檔案末尾追加請求模型與兩個端點：

```python
class CreditRequest(BaseModel):
    """授信意見書請求：target 為劇本圖中的企業名稱。"""

    target: str = Field(description="授信對象企業名稱")
    group_id: int | None = Field(default=None, description="歸戶集團編號（選配）")
    group_exposure_twd: float | None = Field(
        default=None, description="該集團授信曝險合計（新台幣元，選配）"
    )


class AffiliationInput(BaseModel):
    """一筆公司—自然人關係。"""

    company: str
    person: str
    role: str = "董監事"


class GroupRequest(BaseModel):
    """集團歸戶請求。"""

    affiliations: list[AffiliationInput] = Field(description="公司—自然人關係名冊")
    declared_groups: dict[str, str] = Field(
        default_factory=dict, description="客戶自行申報的集團代號"
    )
    exposures: dict[str, float] = Field(
        default_factory=dict, description="各公司授信餘額（新台幣元）"
    )


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
    # graph_to_json 以 "score"／"label" 著色；授信意見書用 attention_score，
    # 且 label 值域是 watch/caution/normal。兩者都有預設值不會拋錯，漏接會
    # 靜默把整張圖染成 0 分——比報錯更難察覺，故在此明確補上相容鍵。
    evidences: dict[Any, dict[str, Any]] = {}
    for node in g.nodes():
        item = generate_credit_opinion(node, g, sna_df, partition, risk_ratios, motif_hits)
        item["score"] = item["attention_score"]
        evidences[node] = item

    opinion["graph"] = graph_to_json(
        g,
        evidences,
        sna_df,
        motif_centers={hit.center for hit in motif_hits},
        role_zh=sme_scenario.ROLE_ZH,
    )
    return opinion


@app.post("/group")
def group(req: GroupRequest, x_api_key: str | None = Header(default=None)) -> dict[str, Any]:
    """集團歸戶：回傳歸戶結果、各集團曝險與未申報的隱性關聯。"""
    _check_api_key(x_api_key)
    if not req.affiliations:
        raise HTTPException(status_code=400, detail="affiliations 不得為空")

    company_graph = build_company_graph(
        Affiliation(company=a.company, person=a.person, role=a.role) for a in req.affiliations
    )
    groups = detect_groups(company_graph)
    totals = group_exposure(groups, req.exposures)
    return {
        "groups": groups,
        "exposures": {str(gid): amount for gid, amount in totals.items()},
        "hidden_links": hidden_links(company_graph, req.declared_groups),
    }
```

- [ ] **Step 5: 跑測試確認通過**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest tests/test_api_credit.py -q
```
Expected: `7 passed`

- [ ] **Step 6: 跑完整套件，確認 serialize.py 的改動未影響防詐分支**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m ruff check . --exclude .venv
```
Expected: `123 passed`；`All checks passed!`
（`role_zh` 預設為 `None` 時沿用原本的 `ROLE_ZH`，既有 `/screen`、`/graph` 的測試不得有任何改變。）

- [ ] **Step 7: 手動驗證端點可用**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -c "
from fastapi.testclient import TestClient
from smelens.api.main import app
c = TestClient(app)
r = c.post('/credit', json={'target': '泰昇精密'}).json()
print(r['label_zh'], r['attention_score'])
print(r['narrative_zh'])
print(r['recommendation_zh'])
"
```
Expected: 印出中文授信敘事，內含買方集中與封閉資金環的具體金額描述。

- [ ] **Step 8: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add smelens/api/main.py smelens/api/serialize.py tests/test_api_credit.py
git commit -F - <<'EOF'
feat(api): /credit 授信意見書與 /group 集團歸戶端點

/credit 回傳含結構證據與圖譜的授信意見書；/group 回傳歸戶結果、集團曝險
與未申報的隱性關聯。查無此公司回 404，不靜默回傳空意見書。

graph_to_json 新增選配 role_zh 並在 /credit 補上 score 相容鍵：兩者都有
預設值不會拋錯，漏接只會讓整張圖靜默染成 0 分、角色回退成英文鍵——比
報錯更難察覺，故以測試明確釘住。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 9: CI 綠燈與文件收尾

**Files:**
- Modify: `.github/workflows/`（既有 workflow 檔）、`README.md`、`Makefile`
- Test: 完整套件

**Interfaces:**
- Consumes: Task 1–8 全部
- Produces: GitHub Actions 綠燈；README 含 API 使用範例

- [ ] **Step 1: 檢查既有 workflow 是否仍指向舊套件名**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ls .github/workflows/ && cat .github/workflows/*.yml
```

檢查點：若 workflow 使用 `uv sync` / `uv run`，改為標準 pip 流程（CI runner 上沒有預先安裝 uv）：

```yaml
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          python -m pip install -e .
          python -m pip install pytest ruff
      - name: Lint
        run: ruff check .
      - name: Test
        run: pytest -q
```

並確認 `python-version` 為 `"3.11"`。

- [ ] **Step 2: 在 README 追加 API 章節**

在 README 的「快速開始」之後、「淵源與授權」之前插入：

```markdown
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
```

- [ ] **Step 3: 更新 Makefile（供 CI 與他人使用）**

把 `Makefile` 全文替換為：

```makefile
.PHONY: setup test lint api app

PYTHON ?= .venv/Scripts/python.exe

setup:
	$(PYTHON) -m pip install -e .
	$(PYTHON) -m pip install pytest ruff

test:
	$(PYTHON) -m pytest -q

lint:
	$(PYTHON) -m ruff check . --exclude .venv

api:
	$(PYTHON) -m uvicorn smelens.api.main:app --reload --port 8000

app:
	$(PYTHON) -m streamlit run smelens/app/workbench.py
```

- [ ] **Step 4: 跑完整套件與 lint**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -3
cd /c/Users/sanketsu/sme-lens && ./.venv/Scripts/python.exe -m ruff check . --exclude .venv
```
Expected: `123 passed`；`All checks passed!`

- [ ] **Step 5: Commit 並推上 GitHub**

```bash
cd /c/Users/sanketsu/sme-lens
git add .github README.md Makefile
git commit -F - <<'EOF'
chore: CI 改用 pip 流程、README 補 API 章節、Makefile 去 uv 依賴

CI runner 未預裝 uv，改標準 pip 安裝；Makefile 統一走 .venv 直譯器，
與本機環境一致。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
git push
```

- [ ] **Step 6: 確認 GitHub Actions 綠燈**

Run:
```bash
cd /c/Users/sanketsu/sme-lens && gh run list --limit 3
```
Expected: 最新一筆 status 為 `completed`、conclusion 為 `success`。若失敗，讀 `gh run view --log-failed` 修正後重推。

---

## 完成後的下一步

本計畫交付後，依 spec 第 6 節續寫：

- **計畫 2**：`data/tw_sme.py` — 接經濟部商業司公司登記開放資料，把 Task 6 的 `Affiliation` 名冊換成真實董監事資料
- **計畫 3**：`web/` 四頁改造為行員授信工作台
- **計畫 4**：可驗證憑證第二引擎 `smelens/attest/`
- **計畫 5**：一頁式企劃書（A4 單頁 PDF ＋ demo QR code），10/14 截止
