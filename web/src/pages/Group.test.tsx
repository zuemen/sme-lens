import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
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

const { postGroup, ApiError } = await import('../api/client')
const mockedPostGroup = vi.mocked(postGroup)

describe('集團歸戶頁', () => {
  beforeEach(() => {
    mockedPostGroup.mockReset()
  })

  it('把客戶未申報的隱性關聯逐條列出，並點名共用的自然人', async () => {
    mockedPostGroup.mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByText(/隱性關聯/)).toBeDefined())
    // 公司名稱在名冊表、歸戶結果表與隱性關聯區塊都會出現，故用 getAllByText
    // 確認「至少出現一次」，而非要求整頁唯一——唯一性不是這裡要驗證的重點。
    for (const link of GROUP_SNAPSHOT.hidden_links) {
      expect(screen.getAllByText(new RegExp(link.company_a)).length).toBeGreaterThan(0)
      expect(screen.getAllByText(new RegExp(link.company_b)).length).toBeGreaterThan(0)
      for (const person of link.shared_persons) {
        expect(screen.getAllByText(new RegExp(person)).length).toBeGreaterThan(0)
      }
    }
  })

  it('顯示申報集團數與實際歸戶數的對比：客戶申報 2 個，關係圖歸戶後只剩 1 個', async () => {
    mockedPostGroup.mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    // 這裡刻意斷言這個 fixture 的字面正確值，不能用跟實作相同的公式反推期望值
    // ——否則測試只會驗證「實作內部一致」，驗證不出「實作算錯了」。
    // 客戶申報 2 個集團（泰昇集團、昇泰集團）；限縮到申報名單後，
    // 三家全落在 group 0，關係圖歸戶後只剩 1 個。
    await waitFor(() =>
      expect(screen.getByTestId('group-count-actual').textContent).toContain('1'),
    )
    expect(screen.getByTestId('group-count-declared').textContent).toContain('2')
  })

  it('顯示曝險落差：最大申報集團 4,200 萬 vs 併入後實際 5,000 萬，差 800 萬', async () => {
    mockedPostGroup.mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    // 對比的基準是「最大申報集團」（泰昇集團 = 泰昇精密 30,000,000 + 泰昇投資 12,000,000
    // = 42,000,000），不是三家全部加總（那樣兩邊都是 50,000,000，落差恆為 0）。
    await waitFor(() =>
      expect(screen.getByTestId('group-exposure-declared').textContent).toContain('42,000,000'),
    )
    expect(screen.getByTestId('group-exposure-actual').textContent).toContain('50,000,000')
    expect(screen.getByTestId('group-exposure-gap').textContent).toContain('8,000,000')
  })

  it('完全無法連線（status 0）時退回離線快照', async () => {
    mockedPostGroup.mockRejectedValue(new ApiError(0, '無法連線到分析服務，請確認網路後重試。'))
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByText(/隱性關聯/)).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  it('後端 5xx（例如 Vercel 冷啟動逾時的 504）也要退回離線快照', async () => {
    mockedPostGroup.mockRejectedValue(new ApiError(504, '分析服務回應異常（HTTP 504）。'))
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByText(/隱性關聯/)).toBeDefined())
    expect(screen.getByText(/離線快照/)).toBeDefined()
  })

  // FIX 1：hidden_links 可能已被後端截斷（依共用自然人數排序只回傳前 N 筆），
  // 畫面必須明確告知真正的總筆數，不能讓人以為表格裡的就是全部隱性關聯。
  it('truncated 為 true 時，顯示截斷提示並點名真正的總筆數', async () => {
    mockedPostGroup.mockResolvedValue({
      ...GROUP_SNAPSHOT,
      hidden_links_total: 137,
      truncated: true,
    })
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.getByText(/137/)).toBeDefined()
  })

  it('truncated 為 false 時，不顯示截斷提示', async () => {
    mockedPostGroup.mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByText(/隱性關聯/)).toBeDefined())
    expect(screen.queryAllByRole('alert')).toHaveLength(0)
  })

  it('4xx（例如 API base 設錯導致的 404）不觸發快照，只顯示錯誤訊息', async () => {
    mockedPostGroup.mockRejectedValue(new ApiError(404, '查無資料。'))
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText(/離線快照/)).toBeNull()
    expect(screen.queryByText(/隱性關聯/)).toBeNull()
  })
})
