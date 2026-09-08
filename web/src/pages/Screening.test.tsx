import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import Screening from './Screening'

// 只 mock postScreen；ApiError 用真的 class，因為頁面用 `instanceof ApiError` 判斷。
vi.mock('../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../api/client')>()
  return { ...actual, postScreen: vi.fn() }
})

// jsdom 沒有 2d canvas，cytoscape 初始化會丟例外把整棵樹炸掉；
// 這支測試在意的是頁面的 offline-fallback 狀態邏輯，不是圖譜本身怎麼畫，故 stub 掉。
vi.mock('../graph/GraphView', () => ({
  GraphView: () => null,
}))

import { postScreen } from '../api/client'

const mockedPostScreen = vi.mocked(postScreen)

describe('Screening 離線快照保險網（I5）', () => {
  beforeEach(() => {
    mockedPostScreen.mockReset()
  })

  it('完全無法連線（status 0）時退回離線快照', async () => {
    mockedPostScreen.mockRejectedValue(new ApiError(0, '無法連線到分析服務，請確認網路後重試。'))
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByText('0.73')).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('後端 5xx（例如 Vercel 冷啟動逾時的 504）也要退回離線快照', async () => {
    mockedPostScreen.mockRejectedValue(new ApiError(504, '分析服務回應異常（HTTP 504）。'))
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByText('0.73')).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('4xx（例如 API base 設錯導致的 404）不觸發快照，只顯示錯誤訊息', async () => {
    mockedPostScreen.mockRejectedValue(new ApiError(404, '查無資料。'))
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText(/離線快照/)).toBeNull()
    expect(screen.queryByText('0.73')).toBeNull()
  })
})
