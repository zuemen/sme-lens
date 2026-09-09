# 企鏡 SME Lens 企金前端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓「企鏡 SME Lens」這個參賽作品在 demo 網站上真的看得到——目前 `web/` 只有繼承自 ChainLens 的防詐流程，`/credit` 與 `/group` 在 UI 上完全不存在，首頁品牌仍是「鏈鏡 ChainLens」。

**Architecture:** 沿用既有的 Vite + React 18 + TypeScript + Tailwind v4 + Cytoscape 結構與元件（`Panel`、`ErrorNotice`、`RiskBadge`、`GraphView`）。新增兩個頁面（授信意見書、集團歸戶）、擴充型別與 API client、把企金角色加進 Cytoscape 配色、改寫品牌與首頁。防詐頁面（`/screening`、`/workbench`）保持可用，改為次要導覽。

**Tech Stack:** React 18、TypeScript、Tailwind v4、Cytoscape、react-router-dom、vitest、Playwright

**Spec:** `docs/superpowers/specs/2026-09-08-sme-lens-spec.md`（第 6 節「計畫 3：行員工作台」）

## Global Constraints

- **前端用 npm**，指令一律 `npm --prefix web <script>`：`test`（vitest）、`run typecheck`、`run build`、`run e2e`
- **後端 Python** 一律 `./.venv/Scripts/python.exe -m <module>`；本機無 `uv`、無 `make`
- 基準：**140 pytest、34 vitest、typecheck 乾淨**。任何任務結束時三者都不得退步
- 所有使用者可見字串一律**繁體中文**
- Ruff（Python）：line-length 100、target py311、select `["E","F","I","W","UP"]`
- Commit 訊息結尾必須附上：
  ```
  Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
  ```
- Commit 一律用明確檔案路徑，**不得 `git add -A`**

## 已知會再踩的坑（來自本專案上游 ChainLens 的實戰紀錄，全部務必遵守）

1. **Cytoscape 畫在 canvas，解析不了 CSS 變數。** `web/src/graph/elements.ts` 必須用原始 hex 色碼；DOM 文字才用 `var(--color-*)`。兩套配色是刻意的，**不可統一**。
2. **`GraphView` 的 effect 依賴 `onSelect`，清理時 `cy.destroy()`。** 呼叫端若傳行內箭頭函式，會導致「點一次節點就重建整張圖」。傳進去的 handler **必須用 `useCallback` 穩定身分**。
3. **網路圖的無障礙評級是 D，永遠不能是資料的唯一載體。** 任何放圖的頁面都必須同時提供等價的表格。
4. **Tailwind v4 下字體不能用 CSS `@import`** —— 已在 `web/index.html` 用 `<link rel="stylesheet">` 處理好，**不要改動**。
5. **SPA rewrite** 已在 `web/vercel.json` 設好，**不要改動**；Playwright 抓不到這個缺陷（`vite preview` 自帶 history fallback）。
6. **色票需過 WCAG AA**：`--color-risk-high` 用 `#F87171`（`#EF4444` 在面板底上只有 4.16:1 不過關）。邊框分兩階：裝飾 `#334155`、控制項 `#64748B`。
7. **產生離線快照時要加 `PYTHONIOENCODING=utf-8`**，否則 Windows stdout 會弄壞中文。
8. **不要開 git worktree**：`.venv` 以 editable 方式指向本 checkout，開 worktree 會靜默測到錯的程式碼。

---

## File Structure

| 檔案 | 責任 |
|---|---|
| `web/src/api/types.ts` | **修改** 新增 `CreditOpinion`、`GroupResult`、`HiddenLink`、`AffiliationInput`、`CreditMotifHit` |
| `web/src/api/client.ts` | **修改** 新增 `postCredit`、`postGroup` |
| `web/src/api/credit-snapshot.json` | **新增** `/credit` 離線快照（現場斷網仍能演示） |
| `web/src/api/group-snapshot.json` | **新增** `/group` 離線快照 |
| `web/src/api/snapshot.ts` | **修改** 匯出兩個新快照 |
| `web/src/graph/elements.ts` | **修改** `ROLE_COLOR` 補上六個企金角色 |
| `web/src/pages/Credit.tsx` | **新增** 授信意見書頁 |
| `web/src/pages/Group.tsx` | **新增** 集團歸戶頁 |
| `web/src/pages/Landing.tsx` | **改寫** 以企金為主敘事，防詐為次 |
| `web/src/App.tsx` | **修改** 品牌改為「企鏡 SME Lens」、導覽加兩頁 |
| `web/src/pages/Credit.test.tsx`、`Group.test.tsx` | **新增** 元件測試 |
| `web/e2e/credit.spec.ts` | **新增** e2e |
| `scripts/make_snapshots.py` | **新增** 產生兩個離線快照的腳本 |

---

### Task 1: 型別、API client、離線快照、角色配色

四件機械性且互相依賴的小改動，合為一個任務。

**Files:**
- Modify: `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/api/snapshot.ts`, `web/src/graph/elements.ts`
- Create: `scripts/make_snapshots.py`, `web/src/api/credit-snapshot.json`, `web/src/api/group-snapshot.json`
- Test: `web/src/graph/elements.test.ts`

**Interfaces:**
- Consumes: 後端 `POST /credit`、`POST /group` 的實際回應
- Produces: `postCredit(target, groupId?, groupExposureTwd?)`、`postGroup(body)`、`CREDIT_SNAPSHOT`、`GROUP_SNAPSHOT`、擴充後的 `ROLE_COLOR`

- [ ] **Step 1: 在 `web/src/api/types.ts` 末尾追加企金型別**

```typescript
/** 授信關注等級。與防詐分支的 RiskLabel 刻意分開：值域與語意都不同。 */
export type AttentionLabel = 'watch' | 'caution' | 'normal'

export interface CreditMotifHit {
  motif: string
  center: string
  nodes: string[]
  description_zh: string
}

export interface CreditOpinion {
  target: string
  attention_score: number
  network_credit: number
  label: AttentionLabel
  label_zh: string
  counterparty_diversity: number
  centrality_percentile: Record<string, number>
  community_risk_ratio: number
  group_id: number | null
  group_exposure_twd: number | null
  motif_hits: CreditMotifHit[]
  narrative_zh: string
  recommendation_zh: string
  graph: GraphPayload
}

export interface AffiliationInput {
  company: string
  person: string
  role?: string
}

export interface HiddenLink {
  company_a: string
  company_b: string
  shared_persons: string[]
  declared_group_a: string | null
  declared_group_b: string | null
}

export interface GroupResult {
  /** 公司 → 集團編號 */
  groups: Record<string, number>
  /** 集團編號（字串鍵）→ 曝險合計 */
  exposures: Record<string, number>
  hidden_links: HiddenLink[]
  /** 有曝險但不在名冊中的公司；後端刻意列名而非靜默丟棄 */
  unattributed: string[]
}
```

- [ ] **Step 2: 在 `web/src/api/client.ts` 的 `postGraph` 之後追加兩個函式**

先把 import 行改為：

```typescript
import type { CreditOpinion, GroupResult, ScreenResult, WorkbenchPayload } from './types'
```

再追加：

```typescript
export function postCredit(
  target: string,
  groupId?: number,
  groupExposureTwd?: number,
): Promise<CreditOpinion> {
  return post<CreditOpinion>('/credit', {
    target,
    group_id: groupId ?? null,
    group_exposure_twd: groupExposureTwd ?? null,
  })
}

export function postGroup(body: {
  affiliations: { company: string; person: string; role?: string }[]
  declared_groups?: Record<string, string>
  exposures?: Record<string, number>
}): Promise<GroupResult> {
  return post<GroupResult>('/group', body)
}
```

- [ ] **Step 3: 建立 `scripts/make_snapshots.py`**

```python
"""產生前端離線快照：現場斷網或後端冷啟動逾時時，demo 仍能演完。

Windows 下務必以 PYTHONIOENCODING=utf-8 執行，否則 stdout 會弄壞中文。
用法：
    PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/make_snapshots.py
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smelens.api.main import app

OUT_DIR = Path("web/src/api")

DEMO_AFFILIATIONS = [
    {"company": "泰昇精密", "person": "陳大明", "role": "董事長"},
    {"company": "泰昇投資", "person": "陳大明", "role": "董事"},
    {"company": "昇泰貿易", "person": "王秀英", "role": "董事"},
    {"company": "泰昇投資", "person": "王秀英", "role": "監察人"},
    {"company": "禾昌五金", "person": "林志豪", "role": "董事長"},
]
DEMO_DECLARED = {
    "泰昇精密": "泰昇集團",
    "泰昇投資": "泰昇集團",
    "昇泰貿易": "昇泰集團",
}
DEMO_EXPOSURES = {"泰昇精密": 30_000_000, "泰昇投資": 12_000_000, "昇泰貿易": 8_000_000}


def main() -> None:
    client = TestClient(app)

    credit = client.post("/credit", json={"target": "泰昇精密"})
    credit.raise_for_status()
    (OUT_DIR / "credit-snapshot.json").write_text(
        json.dumps(credit.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    group = client.post(
        "/group",
        json={
            "affiliations": DEMO_AFFILIATIONS,
            "declared_groups": DEMO_DECLARED,
            "exposures": DEMO_EXPOSURES,
        },
    )
    group.raise_for_status()
    (OUT_DIR / "group-snapshot.json").write_text(
        json.dumps(group.json(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("wrote credit-snapshot.json / group-snapshot.json")


if __name__ == "__main__":
    main()
```

執行它：

```bash
cd /c/Users/sanketsu/sme-lens
PYTHONIOENCODING=utf-8 ./.venv/Scripts/python.exe scripts/make_snapshots.py
```

Expected: 印出 `wrote credit-snapshot.json / group-snapshot.json`，且兩個檔案內含正常中文（用 `head -5` 目視確認，不可是亂碼）。

- [ ] **Step 4: 在 `web/src/api/snapshot.ts` 追加匯出**

現有檔案匯出 `SCREENING_SNAPSHOT`。照同樣寫法追加：

```typescript
import creditSnapshot from './credit-snapshot.json'
import groupSnapshot from './group-snapshot.json'
import type { CreditOpinion, GroupResult } from './types'

/** 現場斷網或後端冷啟動逾時時的備援；畫面必須明確標示為離線快照。 */
export const CREDIT_SNAPSHOT = creditSnapshot as unknown as CreditOpinion
export const GROUP_SNAPSHOT = groupSnapshot as unknown as GroupResult
```

保留檔案中既有的 `SCREENING_SNAPSHOT` 匯出不動。

- [ ] **Step 5: 在 `web/src/graph/elements.ts` 的 `ROLE_COLOR` 補上企金角色**

把 `ROLE_COLOR` 常數整個換成：

```typescript
/**
 * 角色色碼。前八個沿用 smelens/app/workbench.py 的防詐劇本配色，與既有截圖一致；
 * 後六個是企金劇本的角色。
 *
 * 這裡必須是原始 hex：Cytoscape 畫在 canvas 上，解析不了 CSS 變數。
 * DOM 文字用 var(--color-*)，兩套配色是刻意分開的。
 */
const ROLE_COLOR: Record<string, string> = {
  // 防詐劇本
  victim: '#f5b041',
  support: '#e74c3c',
  aggregator: '#c0392b',
  mule: '#e67e22',
  peel: '#d35400',
  peel_side: '#7f8c8d',
  otc: '#9b59b6',
  normal: '#5dade2',
  // 企金劇本
  applicant: '#f1c40f',
  anchor_buyer: '#16a085',
  buyer: '#5dade2',
  shell: '#c0392b',
  related: '#e67e22',
  supplier: '#7f8c8d',
}
```

- [ ] **Step 6: 在 `web/src/graph/elements.test.ts` 末尾追加測試**

```typescript
describe('企金角色配色', () => {
  const base = {
    id: '泰昇精密',
    role_zh: '授信申請人',
    score: 0.1,
    label: 'low' as const,
    is_motif_center: false,
    pagerank: 0,
    narrative_zh: '',
  }

  it('六個企金角色都有專屬色，不會退回 normal 藍', () => {
    const roles = ['applicant', 'anchor_buyer', 'buyer', 'shell', 'related', 'supplier']
    const colors = roles.map((role) =>
      nodeColor({ ...base, role }, { scheme: 'role' }),
    )

    // buyer 與 normal 共用藍色是刻意的（兩者都是「一般往來對象」），其餘四個必須各自不同
    const distinctive = colors.filter((_, index) => roles[index] !== 'buyer')
    expect(new Set(distinctive).size).toBe(distinctive.length)
  })

  it('未知角色仍安全退回 normal 色而不是 undefined', () => {
    expect(nodeColor({ ...base, role: '沒見過的角色' }, { scheme: 'role' })).toBe('#5dade2')
  })
})
```

若檔案頂端尚未 import `describe`/`it`/`expect` 或 `nodeColor`，依既有寫法補上。

- [ ] **Step 7: 驗證**

```bash
cd /c/Users/sanketsu/sme-lens
npm --prefix web test 2>&1 | tail -6
npm --prefix web run typecheck 2>&1 | tail -3
./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -2
./.venv/Scripts/python.exe -m ruff check . 2>&1 | tail -1
```
Expected: vitest `36 passed`（34 + 2 新增）、typecheck 無輸出即通過、pytest `140 passed`、ruff `All checks passed!`

- [ ] **Step 8: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add web/src/api/types.ts web/src/api/client.ts web/src/api/snapshot.ts \
        web/src/api/credit-snapshot.json web/src/api/group-snapshot.json \
        web/src/graph/elements.ts web/src/graph/elements.test.ts scripts/make_snapshots.py
git commit -F - <<'EOF'
feat(web): 企金 API 型別、client、離線快照與角色配色

前端此前完全沒有 /credit 與 /group 的接點。本次補上型別與呼叫函式，
並產生兩份離線快照——現場斷網或後端冷啟動逾時時 demo 仍能演完。
Cytoscape 的角色色碼補上六個企金角色，維持原始 hex（canvas 解析不了 CSS 變數）。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 2: 授信意見書頁 `/credit`

**Files:**
- Create: `web/src/pages/Credit.tsx`, `web/src/pages/Credit.test.tsx`
- Modify: `web/src/App.tsx`（僅加路由，品牌與導覽留給 Task 4）

**Interfaces:**
- Consumes: Task 1 的 `postCredit`、`CREDIT_SNAPSHOT`、`CreditOpinion`
- Produces: 預設匯出的 `Credit` 元件，掛在路由 `/credit`

**這頁要說的一句話：** 財報看起來健康的公司，關係圖揭露了三件財報看不到的事。

- [ ] **Step 1: 寫失敗的測試 `web/src/pages/Credit.test.tsx`**

參照既有的 `web/src/pages/Screening.test.tsx` 寫法（`@testing-library/react` + `vi.mock` 掉 `../api/client`）。必須涵蓋：

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { CREDIT_SNAPSHOT } from '../api/snapshot'
import Credit from './Credit'

vi.mock('../api/client', () => ({
  postCredit: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail)
    }
  },
}))

const { postCredit } = await import('../api/client')

describe('授信意見書頁', () => {
  it('查詢後顯示等級、建議與命中圖樣的中文描述', async () => {
    vi.mocked(postCredit).mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    await userEvent.click(screen.getByRole('button', { name: /產生授信意見書/ }))

    await waitFor(() => expect(screen.getByText(CREDIT_SNAPSHOT.label_zh)).toBeInTheDocument())
    expect(screen.getByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeInTheDocument()
    // 命中圖樣的中文描述必須逐條列出，不能只給一個分數
    for (const hit of CREDIT_SNAPSHOT.motif_hits) {
      expect(screen.getByText(hit.description_zh)).toBeInTheDocument()
    }
  })

  it('圖譜之外必須提供等價的節點表格（網路圖無障礙評級為 D，不能是唯一載體）', async () => {
    vi.mocked(postCredit).mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    await userEvent.click(screen.getByRole('button', { name: /產生授信意見書/ }))

    await waitFor(() => expect(screen.getByRole('table')).toBeInTheDocument())
    const rows = screen.getAllByRole('row')
    // 表頭 + 每個節點各一列
    expect(rows.length).toBe(CREDIT_SNAPSHOT.graph.nodes.length + 1)
  })
})
```

若既有 `Screening.test.tsx` 的 mock 寫法與此不同，**以既有寫法為準**並據以調整——一致性比照抄本檔重要。

- [ ] **Step 2: 跑測試確認失敗**

```bash
cd /c/Users/sanketsu/sme-lens && npm --prefix web test 2>&1 | tail -8
```
Expected: FAIL，找不到 `./Credit` 模組。

- [ ] **Step 3: 寫 `web/src/pages/Credit.tsx`**

JSX 版面由你設計，但**必須滿足下列合約**：

- 目標選擇器：`泰昇精密（授信申請人）` 與 `禾昌五金（對照組）` 兩個選項，預設前者
- 一個 `帶入集團歸戶脈絡` 勾選框；勾選時以 `groupId=0`、`groupExposureTwd=50000000` 呼叫
- 送出按鈕文字必須包含「產生授信意見書」
- 結果區塊，由上而下：
  1. **決策帶**：`label_zh` 大字、`attention_score` 與 `network_credit` 兩個數字並列。等級用顏色**加上文字**標示，不可只靠顏色
  2. **建議**：`recommendation_zh`，視覺權重最高——這是行員唯一據以行動的一句話
  3. **敘事**：`narrative_zh` 全文
  4. **命中圖樣**：逐條列出 `description_zh`
  5. **結構證據**：`centrality_percentile` 五個欄位、`counterparty_diversity`、`community_risk_ratio`
  6. **關係圖譜**：`<GraphView>` 用 `scheme="role"`、`focus` 設為目標公司
  7. **節點表格**：每個節點一列，欄位含 id、`role_zh`、`score`、`label`。這是圖的等價替代，不可省略
- 錯誤處理與離線備援**照抄 `Screening.tsx` 的模式**：`status === 0 || status >= 500` 時退回 `CREDIT_SNAPSHOT` 並在畫面明示「離線快照」；4xx 不退回（那是設定問題，假裝成功會掩蓋它）
- 傳給 `<GraphView>` 的 `onSelect` **必須用 `useCallback` 包起來**，否則點一次節點就會重建整張圖
- 沿用既有元件 `Panel`、`ErrorNotice`；顏色用 `var(--color-*)`（DOM 文字），不要在 DOM 寫死 hex

- [ ] **Step 4: 在 `web/src/App.tsx` 加路由**

只加 import 與 `<Route path="/credit" element={<Credit />} />`，**導覽列與品牌留給 Task 4**，避免與該任務衝突。

- [ ] **Step 5: 驗證**

```bash
cd /c/Users/sanketsu/sme-lens
npm --prefix web test 2>&1 | tail -6
npm --prefix web run typecheck 2>&1 | tail -3
npm --prefix web run build 2>&1 | tail -4
```
Expected: vitest `38 passed`、typecheck 乾淨、build 成功

- [ ] **Step 6: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add web/src/pages/Credit.tsx web/src/pages/Credit.test.tsx web/src/App.tsx
git commit -F - <<'EOF'
feat(web): 授信意見書頁

財報健康的公司，關係圖揭露財報看不到的三件事。等級、建議、敘事、命中圖樣、
結構證據、關係圖譜一次呈現；圖之外附等價節點表格——網路圖的無障礙評級是 D，
永遠不能是資料的唯一載體。斷網時退回離線快照並明示，4xx 不退回以免掩蓋設定錯誤。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 3: 集團歸戶頁 `/group`

**Files:**
- Create: `web/src/pages/Group.tsx`, `web/src/pages/Group.test.tsx`
- Modify: `web/src/App.tsx`（僅加路由）

**Interfaces:**
- Consumes: Task 1 的 `postGroup`、`GROUP_SNAPSHOT`、`GroupResult`
- Produces: 預設匯出的 `Group` 元件，掛在路由 `/group`

**這頁的爆點，也是全案最有說服力的一幕：** 客戶申報兩個獨立集團，關係圖證明是同一個；曝險從 3,000 萬變成 5,000 萬。版面必須讓這個對比一眼看見。

- [ ] **Step 1: 寫失敗的測試 `web/src/pages/Group.test.tsx`**

```typescript
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { GROUP_SNAPSHOT } from '../api/snapshot'
import Group from './Group'

vi.mock('../api/client', () => ({
  postGroup: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail)
    }
  },
}))

const { postGroup } = await import('../api/client')

describe('集團歸戶頁', () => {
  it('把客戶未申報的隱性關聯逐條列出，並點名共用的自然人', async () => {
    vi.mocked(postGroup).mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    await userEvent.click(screen.getByRole('button', { name: /執行集團歸戶/ }))

    await waitFor(() => expect(screen.getByText(/隱性關聯/)).toBeInTheDocument())
    for (const link of GROUP_SNAPSHOT.hidden_links) {
      expect(screen.getByText(new RegExp(link.company_a))).toBeInTheDocument()
      for (const person of link.shared_persons) {
        expect(screen.getByText(new RegExp(person))).toBeInTheDocument()
      }
    }
  })

  it('顯示申報集團數與實際歸戶數的對比', async () => {
    vi.mocked(postGroup).mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    await userEvent.click(screen.getByRole('button', { name: /執行集團歸戶/ }))

    // 客戶申報 2 個集團，實際歸戶 1 個——這個落差就是本頁的重點
    const actual = new Set(Object.values(GROUP_SNAPSHOT.groups)).size
    await waitFor(() =>
      expect(screen.getByTestId('group-count-actual')).toHaveTextContent(String(actual)),
    )
    expect(screen.getByTestId('group-count-declared')).toHaveTextContent('2')
  })
})
```

- [ ] **Step 2: 跑測試確認失敗**

```bash
cd /c/Users/sanketsu/sme-lens && npm --prefix web test 2>&1 | tail -8
```
Expected: FAIL，找不到 `./Group` 模組。

- [ ] **Step 3: 寫 `web/src/pages/Group.tsx`**

JSX 版面由你設計，但**必須滿足下列合約**：

- 名冊以可編輯的表格或 textarea 呈現，**預先填入** Task 1 `scripts/make_snapshots.py` 裡的 `DEMO_AFFILIATIONS`、`DEMO_DECLARED`、`DEMO_EXPOSURES`（五筆關係、三家申報、三筆曝險）
- 送出按鈕文字必須包含「執行集團歸戶」
- 結果區塊必須有：
  1. **對比帶**（版面最上方、視覺權重最高）：`客戶申報 N 個集團` vs `實際歸戶 M 個集團`，以及對應的曝險合計對比。兩個數字分別掛 `data-testid="group-count-declared"` 與 `data-testid="group-count-actual"`
  2. **隱性關聯**：逐條列出，每條要寫出兩家公司、共用的自然人姓名、以及雙方各自申報的集團。標題須含「隱性關聯」
  3. **歸戶結果表**：公司 → 集團編號
  4. **集團曝險**：集團編號 → 合計金額
  5. **`unattributed`**：若非空，明確列出「有曝險但不在名冊中」的公司，並說明這是刻意列名而非靜默丟棄
- 錯誤處理與離線備援同 Task 2：5xx／斷網退回 `GROUP_SNAPSHOT` 並明示，4xx 不退回
- 顏色用 `var(--color-*)`

- [ ] **Step 4: 在 `web/src/App.tsx` 加路由**（同 Task 2，只加 `<Route path="/group" ... />`）

- [ ] **Step 5: 驗證**

```bash
cd /c/Users/sanketsu/sme-lens
npm --prefix web test 2>&1 | tail -6
npm --prefix web run typecheck 2>&1 | tail -3
npm --prefix web run build 2>&1 | tail -4
```
Expected: vitest `40 passed`、typecheck 乾淨、build 成功

- [ ] **Step 6: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add web/src/pages/Group.tsx web/src/pages/Group.test.tsx web/src/App.tsx
git commit -F - <<'EOF'
feat(web): 集團歸戶頁

客戶申報兩個獨立集團，共用董監事證明是同一個，曝險隨之改寫——版面以這個
對比為主軸。隱性關聯逐條點名共用的自然人；有曝險但不在名冊中的公司明確列出，
不靜默丟棄——對銀行而言曝險憑空消失正是集團歸戶上限存在的理由。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

### Task 4: 品牌、導覽、首頁改寫與 e2e

**Files:**
- Modify: `web/src/App.tsx`, `web/src/pages/Landing.tsx`, `web/index.html`
- Create: `web/e2e/credit.spec.ts`
- Test: 全部

**Interfaces:**
- Consumes: Task 2、3 的兩個頁面
- Produces: 以企鏡 SME Lens 為主體的網站

- [ ] **Step 1: 改寫 `web/src/App.tsx` 的品牌與導覽**

- 品牌字樣從 `鏈鏡 ChainLens` 改為 `企鏡 <span class="text-muted">SME Lens</span>`
- `NAV` 改為：
  ```typescript
  const NAV = [
    { to: '/', label: '首頁' },
    { to: '/credit', label: '授信意見書' },
    { to: '/group', label: '集團歸戶' },
    { to: '/screening', label: '出金審查' },
    { to: '/workbench', label: '金流圖譜' },
    { to: '/research', label: '研究成果' },
  ]
  ```
- 右上「看 Demo」按鈕的 `to` 從 `/screening` 改為 `/credit`
- 頁尾文字保持不變

- [ ] **Step 2: 改寫 `web/src/pages/Landing.tsx`**

改為以企金為主敘事。必須包含：

- 主標題：企鏡 SME Lens
- 一句話定位：**銀行不缺分數，缺的是看得見的理由**
- 三個核心應用（貸前集團歸戶／貸中無財報授信／貸後早期預警），各一句話
- 主要行動呼籲指向 `/credit`，次要指向 `/group`
- 防詐能力降為次要段落，說明它與企金共用同一套圖引擎，並保留往 `/screening` 的連結
- 保留既有的健康狀態指示（`checkHealth`）與其無障礙處理

- [ ] **Step 3: 更新 `web/index.html` 的 `<title>` 與 meta description**

改為企鏡 SME Lens 的說明。**不要動 `<link rel="stylesheet">` 的字體載入**——Tailwind v4 下字體只能這樣載，改成 CSS `@import` 會被靜默丟棄。

- [ ] **Step 4: 寫 e2e `web/e2e/credit.spec.ts`**

參照既有 `web/e2e/` 內的寫法。至少涵蓋：導覽到 `/credit` → 按下產生 → 出現等級與建議 → 導覽到 `/group` → 按下執行 → 出現隱性關聯。

- [ ] **Step 5: 驗證**

```bash
cd /c/Users/sanketsu/sme-lens
npm --prefix web test 2>&1 | tail -6
npm --prefix web run typecheck 2>&1 | tail -3
npm --prefix web run build 2>&1 | tail -4
./.venv/Scripts/python.exe -m pytest -q 2>&1 | tail -2
```
Expected: vitest `40 passed`（e2e 不在 vitest 內）、typecheck 乾淨、build 成功、pytest `140 passed`

e2e 需要後端在跑，且 `VITE_API_BASE` 是**建置期烘入**的：

```bash
cd /c/Users/sanketsu/sme-lens
./.venv/Scripts/python.exe -m uvicorn smelens.api.main:app --port 8000 &
sleep 3
VITE_API_BASE=http://localhost:8000 npm --prefix web run build
npm --prefix web run e2e 2>&1 | tail -10
```
若 Playwright 瀏覽器未安裝而無法執行，記錄於報告即可，不要卡住——e2e 刻意不進 CI。

- [ ] **Step 6: Commit**

```bash
cd /c/Users/sanketsu/sme-lens
git add web/src/App.tsx web/src/pages/Landing.tsx web/index.html web/e2e/credit.spec.ts
git commit -F - <<'EOF'
feat(web): 品牌改為企鏡 SME Lens，首頁以企金為主敘事

網站此前展示的是繼承來的防詐流程，參賽作品本身在 UI 上並不存在。
導覽補上授信意見書與集團歸戶並置於前，「看 Demo」改指向授信意見書；
防詐降為次要段落，說明兩者共用同一套圖引擎。

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01RP9fg6Rn2Jr1Vn9v9bg1Ls
EOF
```

---

## 完成後

網站可 demo 之後，剩下的交件工作是一頁式企劃書（10/14 截止）與組隊、在學資格——後者只有專案擁有者本人能處理。
