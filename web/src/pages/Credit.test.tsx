import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { CREDIT_CONTROL_SNAPSHOT, CREDIT_SNAPSHOT } from '../api/snapshot'
import Credit from './Credit'

// 只 mock postCredit；ApiError 用真的 class，因為頁面用 `instanceof ApiError` 判斷。
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, postCredit: vi.fn() }
})

// jsdom 沒有 2d canvas，cytoscape 初始化會丟例外把整棵樹炸掉；
// 這支測試在意的是頁面的決策內容與節點表格，不是圖譜本身怎麼畫，故 stub 掉。
vi.mock('../graph/GraphView', () => ({
  GraphView: () => null,
}))

import { postCredit } from '../api/client'

const mockedPostCredit = vi.mocked(postCredit)

describe('授信意見書頁', () => {
  beforeEach(() => {
    mockedPostCredit.mockReset()
  })

  it('查詢後顯示等級、建議與命中圖樣的中文描述', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    // 「關注」同時可能出現在頂部關注等級與節點表格的「關注等級」欄位（Fix 5：
    // 圖上 high／medium／low 映回 關注／留意／正常），故用 getAllByText。
    await waitFor(() =>
      expect(screen.getAllByText(CREDIT_SNAPSHOT.label_zh).length).toBeGreaterThan(0),
    )
    expect(screen.getByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeDefined()
    // 命中圖樣的中文描述必須逐條列出，不能只給一個分數
    for (const hit of CREDIT_SNAPSHOT.motif_hits) {
      expect(screen.getByText(hit.description_zh)).toBeDefined()
    }
  })

  it('圖譜之外必須提供等價的節點表格（網路圖無障礙評級為 D，不能是唯一載體）', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByRole('table')).toBeDefined())
    const rows = screen.getAllByRole('row')
    // 表頭 + 每個節點各一列
    expect(rows.length).toBe(CREDIT_SNAPSHOT.graph.nodes.length + 1)

    // 內容斷言：目標公司那一列的欄位必須真的對應到它自己的資料，
    // 不能只是列數對但欄位錯置、重複或搬到別列去了。
    const targetNode = CREDIT_SNAPSHOT.graph.nodes.find(
      (node) => node.id === CREDIT_SNAPSHOT.target,
    )
    if (!targetNode) throw new Error('fixture 缺少目標公司節點，測試前提不成立')
    const targetRow = screen.getByText(targetNode.id).closest('tr')
    if (!targetRow) throw new Error('找不到目標公司所在的表格列')
    expect(within(targetRow).getByText(targetNode.role_zh)).toBeDefined()
    expect(within(targetRow).getByText(targetNode.score.toFixed(2))).toBeDefined()
  })

  it('完全無法連線（status 0）時退回離線快照', async () => {
    mockedPostCredit.mockRejectedValue(new ApiError(0, '無法連線到分析服務，請確認網路後重試。'))
    render(<Credit />)
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('後端 5xx（例如 Vercel 冷啟動逾時的 504）也要退回離線快照', async () => {
    mockedPostCredit.mockRejectedValue(new ApiError(504, '分析服務回應異常（HTTP 504）。'))
    render(<Credit />)
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('4xx（例如 API base 設錯導致的 404）不觸發快照，只顯示錯誤訊息', async () => {
    mockedPostCredit.mockRejectedValue(new ApiError(404, '查無資料。'))
    render(<Credit />)
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText(/離線快照/)).toBeNull()
    expect(screen.queryByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeNull()
  })

  it('切到對照組（禾昌五金）後斷網（status 0），也要退回對照組自己的離線快照，而不是泰昇精密的', async () => {
    mockedPostCredit.mockRejectedValue(new ApiError(0, '無法連線到分析服務，請確認網路後重試。'))
    render(<Credit />)

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '禾昌五金' } })
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() =>
      expect(screen.getByText(CREDIT_CONTROL_SNAPSHOT.recommendation_zh)).toBeDefined(),
    )
    expect(screen.getByText(/離線快照/)).toBeDefined()
    // 不能是泰昇精密那份快照的建議文字（兩者不同，混用就代表 fallback 選錯了公司）
    expect(screen.queryByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeNull()
  })

  it('切到對照組（禾昌五金）後 5xx（含冷啟動逾時），同樣退回對照組自己的離線快照', async () => {
    mockedPostCredit.mockRejectedValue(new ApiError(504, '分析服務回應異常（HTTP 504）。'))
    render(<Credit />)

    fireEvent.change(screen.getByRole('combobox'), { target: { value: '禾昌五金' } })
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() =>
      expect(screen.getByText(CREDIT_CONTROL_SNAPSHOT.recommendation_zh)).toBeDefined(),
    )
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('勾選「帶入集團歸戶脈絡」且回傳有集團資料時，顯示集團編號與集團曝險，並標示為呼叫端提供', async () => {
    mockedPostCredit.mockResolvedValue({
      ...CREDIT_SNAPSHOT,
      group_id: 0,
      group_exposure_twd: 50_000_000,
    })
    render(<Credit />)

    fireEvent.click(screen.getByRole('checkbox', { name: '帶入集團歸戶脈絡' }))
    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getAllByText(/呼叫端提供/).length).toBeGreaterThan(0))
    expect(screen.getByText(/50,000,000/)).toBeDefined()
  })

  it('未勾選「帶入集團歸戶脈絡」時（group_id 為 null），不顯示集團歸戶脈絡區塊', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() =>
      expect(screen.getAllByText(CREDIT_SNAPSHOT.label_zh).length).toBeGreaterThan(0),
    )
    expect(screen.queryByText(/呼叫端提供/)).toBeNull()
  })

  // FIX 1：network_credit 為 null 時（純買方、無被觀察到的收入），畫面不能對 null 呼叫
  // toFixed 崩潰，也不能悄悄顯示空白——必須明確說明「未評估」與原因。
  it('network_credit 為 null 時，明確說明未評估及原因，而不是崩潰或空白', async () => {
    mockedPostCredit.mockResolvedValue({ ...CREDIT_SNAPSHOT, network_credit: null })
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByText(/未評估/)).toBeDefined())
    expect(screen.getByText(/沒有「買方結構」可供評估/)).toBeDefined()
    // 原本的數字格式（toFixed(4) 的結果）不該出現
    expect(screen.queryByText('0.5667')).toBeNull()
  })

  // FIX 3：demo 開場第一個動作是指著「建議」這行字，它必須是結果區第一個 Panel，
  // 在「授信關注等級」卡片之上，而不是要往下捲才看得到。
  it('「建議」區塊排在「授信關注等級」卡片之前', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByText(CREDIT_SNAPSHOT.recommendation_zh)).toBeDefined())
    const headings = screen.getAllByRole('heading', { level: 2 }).map((el) => el.textContent)
    const suggestionIndex = headings.indexOf('建議')
    const attentionIndex = headings.indexOf('授信關注等級')
    expect(suggestionIndex).toBeGreaterThanOrEqual(0)
    expect(attentionIndex).toBeGreaterThanOrEqual(0)
    expect(suggestionIndex).toBeLessThan(attentionIndex)
  })

  // FIX 2：後端用 meta.truncated／meta.degraded 表示這份結果有保留，畫面必須把它
  // 顯示出來，不能默默呈現一份看起來很篤定的報告。
  it('graph.meta.truncated 為 true 時，顯示截斷提示', async () => {
    mockedPostCredit.mockResolvedValue({
      ...CREDIT_SNAPSHOT,
      graph: {
        ...CREDIT_SNAPSHOT.graph,
        meta: { ...CREDIT_SNAPSHOT.graph.meta, truncated: true, node_count: 5, total_node_count: 20 },
      },
    })
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/節點數過多/)).toBeDefined()
  })

  it('graph.meta.degraded 為 true 時，顯示降級提示', async () => {
    mockedPostCredit.mockResolvedValue({
      ...CREDIT_SNAPSHOT,
      graph: {
        ...CREDIT_SNAPSHOT.graph,
        meta: { ...CREDIT_SNAPSHOT.graph.meta, degraded: true },
      },
    })
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/已降級/)).toBeDefined()
  })

  it('graph.meta.truncated／degraded 皆為 false 時，不顯示這兩則提示', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() =>
      expect(screen.getAllByText(CREDIT_SNAPSHOT.label_zh).length).toBeGreaterThan(0),
    )
    expect(screen.queryByText(/節點數過多/)).toBeNull()
    expect(screen.queryByText(/已降級/)).toBeNull()
  })

  // FIX 5：查詢中／結果就緒／失敗要有 aria-live 播報，按鈕文字改變本身螢幕報讀器聽不到。
  it('查詢成功後，aria-live 區域播報結果就緒', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    const live = screen.getByRole('status', { hidden: true })
    fireEvent.click(screen.getByRole('button', { name: '產生授信意見書' }))

    await waitFor(() => expect(live.textContent).toMatch(/已產生/))
  })

  // FIX 5：結果出現後，焦點應移到結果區第一個標題（「建議」），而不是停在送出按鈕上。
  it('查詢成功後，焦點移到「建議」標題', async () => {
    mockedPostCredit.mockResolvedValue(CREDIT_SNAPSHOT)
    render(<Credit />)

    screen.getByRole('button', { name: '產生授信意見書' }).click()

    await waitFor(() =>
      expect(screen.getByRole('heading', { level: 2, name: '建議' })).toBe(document.activeElement),
    )
  })
})
