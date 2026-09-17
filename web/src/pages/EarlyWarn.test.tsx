import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EARLYWARN_SNAPSHOT } from '../api/snapshot'
import EarlyWarn from './EarlyWarn'

vi.mock('../api/client', () => ({
  postEarlyWarn: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail)
    }
  },
}))

const { postEarlyWarn, ApiError } = await import('../api/client')
const mockedPostEarlyWarn = vi.mocked(postEarlyWarn)

describe('貸後早期預警頁', () => {
  beforeEach(() => {
    mockedPostEarlyWarn.mockReset()
  })

  it('顯示關注名單、受影響曝險與每一筆的證據路徑', async () => {
    mockedPostEarlyWarn.mockResolvedValue(EARLYWARN_SNAPSHOT)
    render(<EarlyWarn />)

    screen.getByTestId('earlywarn-submit').click()

    await waitFor(() => expect(screen.getByTestId('warn-count')).toBeDefined())
    // 名單筆數與受影響曝險都釘字面值：這兩個數字是這一頁要交付的頭條
    expect(screen.getByTestId('warn-count').textContent).toBe('6')
    expect(screen.getByTestId('warn-exposure').textContent).toBe('96,000,000')

    // 每一筆都必須看得到證據路徑，而不只是分數
    const table = screen.getByTestId('warn-table').textContent ?? ''
    expect(table).toContain('宏益企業 → 泰昇精密')
    expect(table).toContain('宏益企業 → 昇泰貿易 → 泰昇投資')

    // 處置建議是分級的，不是一律拒貸：一跳兩家、二跳三家，各自拿到不同的建議
    // （用 getAllByText 是因為同一層級的公司共用同一句建議，本來就會出現多次）
    expect(screen.getAllByText(/應收帳款回收狀況/)).toHaveLength(2)
    expect(screen.getAllByText(/覆審時納入討論/)).toHaveLength(3)
  })

  it('對照組（結構乾淨、三跳之外）不得出現在名單上', async () => {
    // 一份把全圖都列進來的關注名單等於沒有名單，那正是本系統對其他工具的批評。
    mockedPostEarlyWarn.mockResolvedValue(EARLYWARN_SNAPSHOT)
    render(<EarlyWarn />)

    screen.getByTestId('earlywarn-submit').click()

    await waitFor(() => expect(screen.getByTestId('warn-table')).toBeDefined())
    expect(screen.getByTestId('warn-table').textContent).not.toContain('禾昌五金')
  })

  it('後端 5xx 時退回離線快照並明確標示', async () => {
    mockedPostEarlyWarn.mockRejectedValue(new ApiError(500, '伺服器錯誤'))
    render(<EarlyWarn />)

    screen.getByTestId('earlywarn-submit').click()

    await waitFor(() => expect(screen.getByText(/離線快照/)).toBeDefined())
    expect(screen.getByTestId('warn-count').textContent).toBe('6')
  })

  it('4xx 不退回快照——那是設定問題，假裝成功只會掩蓋它', async () => {
    mockedPostEarlyWarn.mockRejectedValue(new ApiError(404, '指定的出事戶都不在本劇本關係圖中'))
    render(<EarlyWarn />)

    screen.getByTestId('earlywarn-submit').click()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('不在本劇本關係圖中'),
    )
    expect(screen.queryByTestId('warn-count')).toBeNull()
  })
})
