import { render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
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
  })
})
