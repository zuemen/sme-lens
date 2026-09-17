import { useEffect, useRef, useState } from 'react'
import { ApiError, getGcisGroup, postGroup } from '../api/client'
import { DEMO_ROSTER, GROUP_SNAPSHOT } from '../api/snapshot'
import type { GcisGroupResult, GroupResult } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'

// 單一來源：scripts/make_snapshots.py 產生 group-snapshot.json 用的正是這份名冊，
// 並把它落盤成 demo-roster.json 讓這裡匯入，兩邊不會再各存一份而漂移。
const DEMO_AFFILIATIONS = DEMO_ROSTER.affiliations
const DEMO_DECLARED = DEMO_ROSTER.declared
const DEMO_EXPOSURES = DEMO_ROSTER.exposures

function formatTwd(amount: number): string {
  return `${amount.toLocaleString('zh-TW')} 元`
}

/** 預設查詢的統一編號：一詮精密工業，決賽現場的即席重現案例。
 *  它的 4 家成員全由 A 層（法人董事）證據支撐，不需要任何附註解釋。 */
const DEFAULT_COMPANY_ID = '35866232'

/** 客戶申報的獨立集團數（依 declared_groups 的相異值數）。 */
const DECLARED_GROUP_COUNT = new Set(Object.values(DEMO_DECLARED)).size

/** 每個「申報集團名稱」的申報曝險合計（例如「泰昇集團」= 泰昇精密 + 泰昇投資）。 */
function declaredGroupTotals(): Record<string, number> {
  const totals: Record<string, number> = {}
  for (const [company, groupName] of Object.entries(DEMO_DECLARED)) {
    const exposure = DEMO_EXPOSURES[company] ?? 0
    totals[groupName] = (totals[groupName] ?? 0) + exposure
  }
  return totals
}

/** 客戶申報曝險最高的那個集團名稱——對比的基準必須是「最大申報集團」，不是全部加總。 */
function largestDeclaredGroupName(): string {
  const totals = declaredGroupTotals()
  const [name] = Object.entries(totals).sort(([, a], [, b]) => b - a)[0]
  return name
}

/**
 * 實際歸戶集團數，**只**看客戶申報名單內的公司。
 * 名單外但曝險資料裡出現的公司（例如禾昌五金）不申報，本來就跟「客戶申報 vs 實際歸戶」
 * 的對比無關；把它算進去會把分母灌水，讓「合併」在頭條數字上消失不見。
 */
function actualDeclaredGroupCount(result: GroupResult): number {
  const ids = new Set(
    Object.keys(DEMO_DECLARED)
      .map((company) => result.groups[company])
      .filter((id): id is number => id !== undefined),
  )
  return ids.size
}

/** 給定一個申報集團名稱，找出歸戶後對應的實際集團編號（從屬於該申報集團的公司反查，不假設為 0）。 */
function mergedGroupIdFor(result: GroupResult, declaredGroupName: string): number | null {
  const companies = Object.entries(DEMO_DECLARED)
    .filter(([, name]) => name === declaredGroupName)
    .map(([company]) => company)
  for (const company of companies) {
    if (company in result.groups) return result.groups[company]
  }
  return null
}

export default function Group() {
  const [affiliations] = useState(DEMO_AFFILIATIONS)
  const [declared] = useState(DEMO_DECLARED)
  const [exposures] = useState(DEMO_EXPOSURES)
  const [result, setResult] = useState<GroupResult | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  // 供 aria-live 區域播報非視覺回饋：查詢中／結果就緒／失敗，按鈕文字改變本身
  // 螢幕報讀器聽不到。
  const [announcement, setAnnouncement] = useState('')
  const resultsRef = useRef<HTMLDivElement>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setAnnouncement('歸戶中，正在執行集團歸戶…')
    try {
      setResult(
        await postGroup({
          affiliations,
          declared_groups: declared,
          exposures,
        }),
      )
      setOffline(false)
      setAnnouncement('集團歸戶結果已產生。')
    } catch (err) {
      // 完全無法連線（斷網/DNS/CORS）或後端本身出錯（5xx，含 Vercel 冷啟動逾時）時
      // 退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      // 4xx（例如 VITE_API_BASE 設錯導致的 404/405）不算——那是設定問題，
      // 假裝查詢成功反而會掩蓋它。
      if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
        setResult(GROUP_SNAPSHOT)
        setOffline(true)
        setAnnouncement('無法連線即時服務，已改用內建備援資料顯示歸戶結果。')
      } else {
        // 清掉上一次的結果，避免畫面同時顯示錯誤條與舊的歸戶結果。
        setResult(null)
        setOffline(false)
        const detail = err instanceof ApiError ? err.detail : '執行集團歸戶失敗，請稍後再試。'
        setError(detail)
        setAnnouncement(`查詢失敗：${detail}`)
      }
    } finally {
      setLoading(false)
    }
  }

  // ── 真實統編查詢（GET /gcis/group）──────────────────────────────
  // 與上方示範名冊是兩件不同的事，刻意共存在同一頁：上方證明「方法對」
  // （名冊可控、落差算得出來），這裡證明「資料真」（任意公開登記統編都查得到）。
  const [companyId, setCompanyId] = useState(DEFAULT_COMPANY_ID)
  const [gcis, setGcis] = useState<GcisGroupResult | null>(null)
  const [gcisLoading, setGcisLoading] = useState(false)
  const [gcisError, setGcisError] = useState<string | null>(null)

  async function runGcis() {
    setGcisLoading(true)
    setGcisError(null)
    setAnnouncement('正在以統一編號查詢公開登記資料…')
    try {
      const payload = await getGcisGroup(companyId.trim())
      setGcis(payload)
      setAnnouncement(`查得 ${payload.company}，歸戶集團共 ${payload.group_size} 家。`)
    } catch (err) {
      // 這一段刻意**不**退回離線快照：離線快照是那份示範名冊的結果，拿它來
      // 冒充「你輸入的那個統編查到的東西」等於給出假答案——比顯示錯誤更糟。
      // 503 代表隨附的精簡索引沒進到部署裡（見 vercel.json 的 includeFiles），
      // 4xx 代表統編格式錯或不在索引內，兩者都要讓人看見真正的原因。
      setGcis(null)
      const detail = err instanceof ApiError ? err.detail : '查詢公開登記資料失敗，請稍後再試。'
      setGcisError(detail)
      setAnnouncement(`統編查詢失敗：${detail}`)
    } finally {
      setGcisLoading(false)
    }
  }

  // FIX 5：查詢結果出現後，把焦點移到結果區第一個標題，螢幕報讀器使用者按下
  // 「執行集團歸戶」後不必自己往下找。用 resultsRef 而非整個頁面根節點，
  // 是因為本頁「申報名冊」表格在查詢前就已經有自己的標題，不能被誤抓為結果標題。
  useEffect(() => {
    if (!result) return
    const heading = resultsRef.current?.querySelector<HTMLElement>('h2')
    heading?.focus()
  }, [result])

  const largestGroupName = largestDeclaredGroupName()
  const declaredLargestExposure = declaredGroupTotals()[largestGroupName]

  const actualGroupCount = result ? actualDeclaredGroupCount(result) : null
  const mergedGroupId = result ? mergedGroupIdFor(result, largestGroupName) : null
  const actualExposureForMergedGroup =
    result && mergedGroupId !== null ? (result.exposures[String(mergedGroupId)] ?? null) : null
  const exposureGap =
    actualExposureForMergedGroup !== null ? actualExposureForMergedGroup - declaredLargestExposure : null

  // 隱性關聯裡「不屬於最大申報集團」的那一條，用來在頭條句子點名是哪家公司、哪個自然人
  // 讓合併從無到有——資料驅動，不在文案裡寫死公司名。
  const revealingLink =
    result?.hidden_links.find(
      (link) =>
        link.declared_group_a !== largestGroupName || link.declared_group_b !== largestGroupName,
    ) ?? null

  return (
    <div className="space-y-6">
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div>
        <h1 className="text-2xl font-semibold">集團歸戶</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          銀行對每個企業集團設有總曝險上限，但集團名冊多半來自客戶自行申報，
          再由授信人員人工比對。共用的董監事、交叉持股或同一登記地址一旦漏看，
          原本應合併計算的曝險就會被拆散在看似無關的借款戶之間，悄悄超過上限而不自知。
        </p>
      </div>

      <Panel title="申報名冊（董監事關係）">
        <div className="overflow-x-auto">
          <table className="tabular w-full text-left text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-muted">
                <th className="py-2 pr-4">公司</th>
                <th className="py-2 pr-4">自然人</th>
                <th className="py-2 pr-4">職務</th>
                <th className="py-2 pr-4">申報集團</th>
                <th className="py-2 pr-4">申報曝險</th>
              </tr>
            </thead>
            <tbody>
              {affiliations.map((row, index) => (
                <tr key={`${row.company}-${row.person}-${index}`} className="border-b border-line/50">
                  <td className="py-2 pr-4">{row.company}</td>
                  <td className="py-2 pr-4">{row.person}</td>
                  <td className="py-2 pr-4">{row.role}</td>
                  <td className="py-2 pr-4">{declared[row.company] ?? '—'}</td>
                  <td className="py-2 pr-4">
                    {row.company in exposures ? formatTwd(exposures[row.company]) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="mt-4">
          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '歸戶中…' : '執行集團歸戶'}
          </button>
        </div>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {offline && (
        <ErrorNotice message="目前顯示的是內建離線快照（案例固定為泰昇集團／昇泰集團名冊），非即時查詢結果——已標示為離線快照。" />
      )}

      {result?.truncated && (
        <ErrorNotice
          message={`本次隱性關聯筆數過多，僅列出共用自然人數最高的 ${result.hidden_links.length} 筆（依共用人數排序，實際共找到 ${result.hidden_links_total} 筆）。下方清單並非全部隱性關聯，其餘筆數請一併交付人工覆核。`}
        />
      )}

      {result && (
        <div ref={resultsRef} className="space-y-6">
          {actualGroupCount !== null &&
            actualExposureForMergedGroup !== null &&
            exposureGap !== null && (
            <Panel title="申報 vs. 實際：客戶申報的集團數與最大集團曝險，關係圖歸戶後怎麼變">
              <div className="grid gap-6 sm:grid-cols-2">
                <div className="rounded-lg border border-line p-4">
                  <div className="text-xs text-muted">客戶申報</div>
                  <div className="tabular mt-1 text-4xl font-semibold text-muted">
                    <span data-testid="group-count-declared">{DECLARED_GROUP_COUNT}</span> 個集團
                  </div>
                  <div
                    className="tabular mt-3 text-4xl font-semibold text-muted"
                    data-testid="group-exposure-declared"
                  >
                    {formatTwd(declaredLargestExposure)}
                  </div>
                  <div className="mt-1 text-xs text-muted">
                    最大申報集團「{largestGroupName}」的申報曝險
                  </div>
                </div>
                <div
                  className="rounded-lg border-2 p-4"
                  style={{ borderColor: 'var(--color-risk-high)' }}
                >
                  <div className="text-xs" style={{ color: 'var(--color-risk-high)' }}>
                    關係圖歸戶後
                  </div>
                  <div
                    className="tabular mt-1 text-4xl font-semibold"
                    style={{ color: 'var(--color-risk-high)' }}
                  >
                    <span data-testid="group-count-actual">{actualGroupCount}</span> 個集團
                  </div>
                  <div
                    className="tabular mt-3 text-4xl font-semibold"
                    style={{ color: 'var(--color-risk-high)' }}
                    data-testid="group-exposure-actual"
                  >
                    {formatTwd(actualExposureForMergedGroup)}
                    <span className="ml-2 text-xl" data-testid="group-exposure-gap">
                      （{exposureGap >= 0 ? '+' : ''}
                      {formatTwd(exposureGap)}）
                    </span>
                  </div>
                  <div className="mt-1 text-xs" style={{ color: 'var(--color-risk-high)' }}>
                    同一集團的實際合併曝險（含被拆散在外的部分）
                  </div>
                </div>
              </div>
              <p className="mt-4 text-base leading-relaxed text-muted">
                客戶申報 {DECLARED_GROUP_COUNT} 個獨立集團，關係圖歸戶後只剩 {actualGroupCount} 個
                ——
                {revealingLink ? (
                  <>
                    <span className="font-semibold text-ink">{revealingLink.company_a}</span> 與{' '}
                    <span className="font-semibold text-ink">{revealingLink.company_b}</span>{' '}
                    因共用自然人{' '}
                    <span className="font-semibold text-ink">
                      {revealingLink.shared_persons.join('、')}
                    </span>{' '}
                    而併為同一集團。
                  </>
                ) : (
                  '關係圖比對出客戶未申報的共同持有／共用董監事關係。'
                )}{' '}
                最大申報集團「{largestGroupName}」原申報曝險為 {formatTwd(declaredLargestExposure)}，
                併入後實際曝險為 {formatTwd(actualExposureForMergedGroup)}，
                多出的 {formatTwd(exposureGap)} 原本以另一個獨立集團的名義申報，在名冊裡完全看不出來。
              </p>
            </Panel>
          )}

          <Panel title="隱性關聯（客戶未申報，關係圖比對出來的共同持有／共用董監事）">
            {result.hidden_links.length > 0 ? (
              <ul className="space-y-3 text-sm">
                {result.hidden_links.map((link) => (
                  <li
                    key={`${link.company_a}-${link.company_b}`}
                    className="border-l-2 pl-4"
                    style={{ borderColor: 'var(--color-risk-high)' }}
                  >
                    <span className="font-semibold">{link.company_a}</span>
                    {'（申報：'}
                    {link.declared_group_a ?? '未申報'}
                    {'）'} 與 <span className="font-semibold">{link.company_b}</span>
                    {'（申報：'}
                    {link.declared_group_b ?? '未申報'}
                    {'）'} 共用自然人：
                    <span className="font-semibold"> {link.shared_persons.join('、')}</span>
                    ——兩者應歸為同一集團，但申報名冊上是兩個不同集團。
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted">
                未偵測到申報名冊之外的隱性關聯——本次名冊的集團歸屬與客戶申報一致。
              </p>
            )}
          </Panel>

          <Panel title="歸戶結果：公司 → 集團編號">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-muted">
                    <th className="py-2 pr-4">公司</th>
                    <th className="py-2 pr-4">歸戶集團編號</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.groups).map(([company, groupId]) => (
                    <tr key={company} className="border-b border-line/50">
                      <td className="py-2 pr-4">{company}</td>
                      <td className="py-2 pr-4">{groupId}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="集團曝險：集團編號 → 合計金額">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-line text-xs text-muted">
                    <th className="py-2 pr-4">集團編號</th>
                    <th className="py-2 pr-4">合計曝險</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(result.exposures).map(([groupId, amount]) => (
                    <tr key={groupId} className="border-b border-line/50">
                      <td className="py-2 pr-4">{groupId}</td>
                      <td className="py-2 pr-4">{formatTwd(amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          {result.unattributed.length > 0 && (
            <Panel title="有曝險但不在名冊中的公司">
              <p className="mb-3 text-sm text-muted">
                以下公司在曝險資料中出現，但未列於本次申報的董監事名冊，因此無法歸入任何集團。
                這裡刻意逐一列名，而不是靜默丟棄——對銀行而言，「曝險不明」與「曝險為零」是完全不同的兩件事。
              </p>
              <ul className="list-inside list-disc text-sm">
                {result.unattributed.map((company) => (
                  <li key={company}>{company}</li>
                ))}
              </ul>
            </Panel>
          )}
        </div>
      )}

      <Panel title="查真實統一編號（公開登記資料）">
        <p className="mb-4 max-w-3xl text-sm leading-relaxed text-muted">
          上方是可控的示範名冊，用來說明方法；這裡直接對<b>全國公司登記資料</b>發問。
          輸入任何 8 碼統一編號，系統會現場展開它的關係圖並歸戶——名冊不由使用者提供，
          而是來自經濟部商業發展署的董監事資料集。
        </p>

        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="gcis-company-id" className="block text-xs text-muted">
              統一編號（8 碼）
            </label>
            <input
              id="gcis-company-id"
              type="text"
              inputMode="numeric"
              maxLength={8}
              value={companyId}
              onChange={(event) => setCompanyId(event.target.value)}
              className="tabular mt-1 w-40 rounded border border-line bg-panel px-3 py-2 text-base"
            />
          </div>
          <button
            type="button"
            onClick={runGcis}
            disabled={gcisLoading}
            data-testid="gcis-submit"
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {gcisLoading ? '查詢中…' : '查集團歸戶'}
          </button>
        </div>

        {gcisError && (
          <div className="mt-4">
            <ErrorNotice message={gcisError} action={{ label: '重試', onClick: runGcis }} />
          </div>
        )}

        {gcis && (
          <div className="mt-6 space-y-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="rounded-lg border border-line p-4">
                <div className="text-xs text-muted">查詢對象</div>
                <div className="mt-1 text-lg font-semibold" data-testid="gcis-company">
                  {gcis.company}
                </div>
                <div className="tabular mt-1 text-xs text-muted">{gcis.company_id}</div>
              </div>
              <div className="rounded-lg border border-line p-4">
                <div className="text-xs text-muted">歸戶集團成員</div>
                <div className="tabular mt-1 text-4xl font-semibold" data-testid="gcis-group-size">
                  {gcis.group_size}
                </div>
                <div className="mt-1 text-xs text-muted">家</div>
              </div>
              <div className="rounded-lg border border-line p-4">
                <div className="text-xs text-muted">查詢耗時</div>
                <div className="tabular mt-1 text-4xl font-semibold">{gcis.elapsed_seconds}</div>
                <div className="mt-1 text-xs text-muted">
                  秒（展開 {gcis.neighborhood_companies} 家鄰域
                  {gcis.neighborhood_truncated ? '，已達上限' : ''}）
                </div>
              </div>
            </div>

            <div>
              <h3 className="text-sm font-semibold">歸戶集團成員</h3>
              <ul className="mt-2 list-inside list-disc text-sm" data-testid="gcis-members">
                {gcis.group_members.map((member) => (
                  <li key={member}>{member}</li>
                ))}
              </ul>
            </div>

            <div>
              <h3 className="text-sm font-semibold">歸戶證據（A 層：法人董事，無姓名歧義）</h3>
              <div className="mt-2 overflow-x-auto">
                <table className="tabular w-full text-left text-sm">
                  <caption className="sr-only">
                    集團歸戶的法人董事證據，欄位為公司、所代表法人（母公司）與職稱
                  </caption>
                  <thead>
                    <tr className="border-b border-line text-xs text-muted">
                      <th scope="col" className="py-2 pr-4">
                        公司
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        所代表法人（母公司）
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        職稱
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {gcis.evidence.map((row, index) => (
                      <tr
                        key={`${row.company}-${row.parent}-${index}`}
                        className="border-b border-line/50"
                      >
                        <td className="py-2 pr-4">{row.company}</td>
                        <td className="py-2 pr-4">{row.parent}</td>
                        <td className="py-2 pr-4">{row.role}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {gcis.candidates.length > 0 && (
              <div>
                <h3 className="text-sm font-semibold">
                  B 層候選（自然人同名，{gcis.candidates.length} 筆，不參與合併）
                </h3>
                <p className="mt-1 text-xs leading-relaxed text-muted">
                  公開資料沒有身分證字號，同名不同人必然存在（全台「陳建宏」一個姓名就掛
                  411 家公司），故這些只是候選，交由銀行以 KYC 既有身分資料解析。
                </p>
                <ul className="mt-2 list-inside list-disc text-sm">
                  {gcis.candidates.slice(0, 12).map((row, index) => (
                    <li key={`${row.company}-${row.person}-${index}`}>
                      {row.company}　·　{row.person}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* scope 與 source 由後端提供並原樣呈現：證據強度的適用範圍不該由
                前端文案自行改寫，兩邊各寫一份就是漂移的開始。 */}
            <p className="text-xs leading-relaxed text-muted" data-testid="gcis-scope">
              {gcis.scope}
            </p>
            <p className="text-xs leading-relaxed text-muted">資料來源：{gcis.source}</p>
          </div>
        )}
      </Panel>
    </div>
  )
}
