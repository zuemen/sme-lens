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

  it('顯示申報集團數與實際歸戶數的對比', async () => {
    mockedPostGroup.mockResolvedValue(GROUP_SNAPSHOT)
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    // 客戶申報 2 個集團，實際歸戶 1 個——這個落差就是本頁的重點
    const actual = new Set(Object.values(GROUP_SNAPSHOT.groups)).size
    await waitFor(() =>
      expect(screen.getByTestId('group-count-actual').textContent).toContain(String(actual)),
    )
    expect(screen.getByTestId('group-count-declared').textContent).toContain('2')
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

  it('4xx（例如 API base 設錯導致的 404）不觸發快照，只顯示錯誤訊息', async () => {
    mockedPostGroup.mockRejectedValue(new ApiError(404, '查無資料。'))
    render(<Group />)

    screen.getByRole('button', { name: /執行集團歸戶/ }).click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByText(/離線快照/)).toBeNull()
    expect(screen.queryByText(/隱性關聯/)).toBeNull()
  })
})
