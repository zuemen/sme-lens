import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Trust from './Trust'

vi.mock('../api/client', () => ({
  postTrustVerify: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail)
    }
  },
}))

const { postTrustVerify, ApiError } = await import('../api/client')
const mocked = vi.mocked(postTrustVerify)

const GLEIF = 'did:key:zGLEIFROOT0000000000000000000000'
const QVI = 'did:key:zQVI000000000000000000000000000'
const ENTITY = 'did:key:zENTITY00000000000000000000000'

const RESULT = {
  promoted: [
    {
      company: '一詮精密工業股份有限公司',
      person: '王○明',
      role: '董事',
      lei: '5493001KJTIIGC8Y1R12',
      company_id: '35866232',
      issuer: ENTITY,
      issuer_chain: [ENTITY, QVI, GLEIF],
      credential_id: 'urn:vc:oor:yichuan-wang',
    },
  ],
  rejected: ['憑證 3：簽發者無法回溯到信任根：did:key:zROGUE'],
  affiliations: [],
  groups_before: 2,
  groups_after: 1,
  revocation: {
    merkle_root: '7b8b37d6a6bdff4a' + '0'.repeat(48),
    anchored: false,
    anchor_reference: '',
    revoked_count: 2,
  },
  method_zh: '以 W3C 可驗證憑證驗證自然人在法人的法定職務。',
}

describe('可驗證憑證頁', () => {
  // 一定要用大括號：`() => mocked.mockReset()` 會隱式回傳 mock 本身，而 vitest
  // 把 beforeEach 回傳的函式當作 teardown callback，於測試結束後「呼叫」它
  // ——等於在沒人 await 的情況下再呼叫一次 postTrustVerify，mockRejectedValue
  // 的那個 promise 就成了 unhandled rejection，測試明明通過卻被判失敗。
  // 這個坑找了三輪才定位，別改回箭頭簡寫。
  beforeEach(() => {
    mocked.mockReset()
  })

  it('顯示歸戶因憑證而改變、升級紀錄與完整授權鏈', async () => {
    mocked.mockResolvedValue(RESULT)
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByTestId('trust-groups-after')).toBeDefined())
    // 這一頁的頭條就是「憑證讓歸戶從 2 戶變 1 戶」
    expect(screen.getByTestId('trust-groups-after').textContent).toBe('1')
    expect(screen.getByTestId('trust-promoted').textContent).toBe('1')

    const table = screen.getByTestId('trust-table').textContent ?? ''
    expect(table).toContain('一詮精密工業股份有限公司')
    expect(table).toContain('5493001KJTIIGC8Y1R12')
    // 授權鏈三層都要看得到（縮寫後仍含頭尾）
    expect(table).toContain('did:key:zENTITY000')
    expect(table).toContain('did:key:zGLEIFROOT')
  })

  it('自然人姓名顯示的是遮蔽後的字串', async () => {
    mocked.mockResolvedValue(RESULT)
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByTestId('trust-table')).toBeDefined())
    expect(screen.getByTestId('trust-table').textContent).toContain('王○明')
  })

  it('被擋下來的憑證要連原因一起顯示', async () => {
    mocked.mockResolvedValue(RESULT)
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByTestId('trust-rejected')).toBeDefined())
    expect(screen.getByTestId('trust-rejected').textContent).toContain('無法回溯到信任根')
  })

  it('尚未錨定上鏈時必須照實顯示，不得說成已上鏈', async () => {
    mocked.mockResolvedValue(RESULT)
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByTestId('trust-anchored')).toBeDefined())
    expect(screen.getByTestId('trust-anchored').textContent).toContain('尚未錨定')
  })

  it('已錨定時顯示鏈上參照', async () => {
    mocked.mockResolvedValue({
      ...RESULT,
      revocation: {
        ...RESULT.revocation,
        anchored: true,
        anchor_reference: 'base-sepolia:0xabc:12345678',
      },
    })
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByTestId('trust-anchored')).toBeDefined())
    expect(screen.getByTestId('trust-anchored').textContent).toContain('base-sepolia:0xabc')
  })

  it('這一頁沒有離線快照——驗證失敗就顯示錯誤，不得用預錄答案冒充', async () => {
    mocked.mockRejectedValue(new ApiError(500, '伺服器錯誤'))
    render(<Trust />)

    screen.getByTestId('trust-submit').click()

    await waitFor(() => expect(screen.getByRole('alert')).toBeDefined())
    expect(screen.queryByTestId('trust-groups-after')).toBeNull()
  })
})
