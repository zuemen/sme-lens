import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { GROUP_SNAPSHOT } from '../api/snapshot'
import Group from './Group'

vi.mock('../api/client', () => ({
  postGroup: vi.fn(),
  getGcisGroup: vi.fn(),
  ApiError: class ApiError extends Error {
    constructor(
      public status: number,
      public detail: string,
    ) {
      super(detail)
    }
  },
}))

const { postGroup, getGcisGroup, ApiError } = await import('../api/client')
const mockedPostGroup = vi.mocked(postGroup)
const mockedGetGcisGroup = vi.mocked(getGcisGroup)

/** 一詮精密工業的真實查詢結果（與線上 GET /gcis/group 的回應同形狀）。 */
const GCIS_FIXTURE = {
  company_id: '35866232',
  company: '一詮精密工業股份有限公司',
  group_members: [
    '一詮精密工業股份有限公司',
    '世銓科技股份有限公司',
    '惠智先進股份有限公司',
    '立誠光電股份有限公司',
  ],
  group_size: 4,
  evidence: [
    {
      company: '世銓科技股份有限公司',
      company_id: '54318252',
      parent: '一詮精密工業股份有限公司',
      parent_id: '35866232',
      role: '法人董事',
    },
  ],
  candidates: [{ company: '世銓科技股份有限公司', person: '王○明', masked: true }],
  elapsed_seconds: 0.23,
  neighborhood_companies: 128,
  neighborhood_truncated: false,
  neighborhood_frontier_remaining: 98,
  scope: '歸戶僅採 A 層（法人董事）證據，與全國索引一致；B 層只列候選，不合併。',
  privacy: '本端點為公開展示用途，自然人姓名一律遮蔽為「陳○宏」形式後輸出。',
  source: '經濟部商業發展署 董監事資料集（政府資料開放授權條款－第 1 版）',
}

describe('集團歸戶頁', () => {
  beforeEach(() => {
    mockedPostGroup.mockReset()
    mockedGetGcisGroup.mockReset()
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

  it('用真實統一編號查詢時，顯示查到的公司、成員名與 A 層證據', async () => {
    // 斷言的是**內容**而非長度：只驗「有 4 筆」的話，把成員清單換成別家公司
    // 的名字也照樣綠，而這一頁的全部說服力就在那幾個名字是真的。
    mockedGetGcisGroup.mockResolvedValue(GCIS_FIXTURE)
    render(<Group />)

    screen.getByTestId('gcis-submit').click()

    await waitFor(() => expect(screen.getByTestId('gcis-company')).toBeDefined())
    expect(screen.getByTestId('gcis-company').textContent).toBe('一詮精密工業股份有限公司')
    expect(screen.getByTestId('gcis-group-size').textContent).toBe('4')

    const members = screen.getByTestId('gcis-members').textContent ?? ''
    for (const name of GCIS_FIXTURE.group_members) {
      expect(members).toContain(name)
    }

    // 預設值就是決賽案例，presenter 不必現場打字
    expect(screen.getByLabelText(/統一編號/)).toHaveProperty('value', '35866232')
    // A 層證據要點名母公司，這才是「說出它們的老闆是誰」
    expect(screen.getByText('法人董事')).toBeDefined()
    // 適用範圍說明由後端提供並原樣呈現
    expect(screen.getByTestId('gcis-scope').textContent).toBe(GCIS_FIXTURE.scope)
    // 個資處理方式必須原樣呈現：這是公開站台上對外的承諾，不能只寫在文件裡。
    expect(screen.getByTestId('gcis-privacy').textContent).toBe(GCIS_FIXTURE.privacy)
    // 候選姓名顯示的是後端遮蔽後的字串，畫面不得出現未遮蔽的真實姓名
    expect(screen.getByText(/王○明/)).toBeDefined()
  })

  it('後端回 503（示範資料未就緒）時顯示後端訊息，不得退回離線快照', async () => {
    // 拿示範名冊的快照去冒充「你輸入的統編查到的結果」是給假答案，比報錯更糟。
    mockedGetGcisGroup.mockRejectedValue(new ApiError(503, '示範資料未就緒：找不到隨附的精簡索引'))
    render(<Group />)

    screen.getByTestId('gcis-submit').click()

    // 鎖進 role="alert" 的錯誤框：訊息同時也會進 aria-live 播報區，
    // 用 getByText 會抓到兩個節點而失敗。
    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('示範資料未就緒'),
    )
    expect(screen.queryByTestId('gcis-company')).toBeNull()
    expect(screen.queryByTestId('gcis-members')).toBeNull()
  })

  it('後端回 404（統編不在索引內）時顯示後端訊息，不得退回離線快照', async () => {
    mockedGetGcisGroup.mockRejectedValue(
      new ApiError(404, '統一編號 00000000 不在示範索引內（僅含有法人董事關係的公司）'),
    )
    render(<Group />)

    screen.getByTestId('gcis-submit').click()

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('不在示範索引內'),
    )
    expect(screen.queryByTestId('gcis-company')).toBeNull()
  })
})
