import { render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { CREDIT_SNAPSHOT } from '../api/snapshot'
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

    await waitFor(() => expect(screen.getByText(CREDIT_SNAPSHOT.label_zh)).toBeDefined())
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
})
