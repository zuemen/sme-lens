import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import { SCREENING_SNAPSHOT } from '../api/snapshot'
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

    // 0.66：社群風險比缺陷修正後的正確值（原為 0.73，見 snapshot.test.ts 的說明）。
    await waitFor(() => expect(screen.getByText('0.66')).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('後端 5xx（例如 Vercel 冷啟動逾時的 504）也要退回離線快照', async () => {
    mockedPostScreen.mockRejectedValue(new ApiError(504, '分析服務回應異常（HTTP 504）。'))
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByText('0.66')).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('4xx（例如 API base 設錯導致的 404）不觸發快照，只顯示錯誤訊息', async () => {
    mockedPostScreen.mockRejectedValue(new ApiError(404, '查無資料。'))
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText(/離線快照/)).toBeNull()
    expect(screen.queryByText('0.66')).toBeNull()
  })
})

describe('Screening 頁面對後端降級旗標的呈現（FIX 2）', () => {
  beforeEach(() => {
    mockedPostScreen.mockReset()
  })

  // insufficient_data 是後端明確標示「目標不在圖中，此為資料不足下的放行，不是查過確認乾淨」；
  // 畫面過去完全不讀這個欄位，會讓 review 團隊看到一份看起來篤定的放行結果。
  it('insufficient_data 為 true 時，顯示查無交易紀錄的提示，而不是靜默放行', async () => {
    mockedPostScreen.mockResolvedValue({
      ...SCREENING_SNAPSHOT,
      insufficient_data: true,
      risk_score: 0,
      self_score: 0,
      association_score: 0,
      decision: 'pass',
      decision_zh: '予以放行',
      associations: [],
      evidence: null,
    })
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/查無交易紀錄/)).toBeDefined()
  })

  it('graph.meta.truncated 為 true 時，顯示截斷提示', async () => {
    mockedPostScreen.mockResolvedValue({
      ...SCREENING_SNAPSHOT,
      graph: {
        ...SCREENING_SNAPSHOT.graph,
        meta: {
          ...SCREENING_SNAPSHOT.graph.meta,
          truncated: true,
          node_count: 10,
          total_node_count: 60,
        },
      },
    })
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/節點數過多/)).toBeDefined()
  })

  it('graph.meta.degraded 為 true 時，顯示降級提示', async () => {
    mockedPostScreen.mockResolvedValue({
      ...SCREENING_SNAPSHOT,
      graph: { ...SCREENING_SNAPSHOT.graph, meta: { ...SCREENING_SNAPSHOT.graph.meta, degraded: true } },
    })
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/已降級/)).toBeDefined()
  })

  it('insufficient_data／truncated／degraded 皆未設定時，不顯示任何一則提示', async () => {
    mockedPostScreen.mockResolvedValue(SCREENING_SNAPSHOT)
    render(<Screening />)
    screen.getByRole('button', { name: '執行出金審查' }).click()

    await waitFor(() => expect(screen.getByText('0.66')).toBeDefined())
    expect(screen.queryByText(/查無交易紀錄/)).toBeNull()
    expect(screen.queryByText(/節點數過多/)).toBeNull()
    expect(screen.queryByText(/已降級/)).toBeNull()
  })
})
