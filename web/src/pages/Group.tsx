import { useState } from 'react'
import { ApiError, postGroup } from '../api/client'
import { GROUP_SNAPSHOT } from '../api/snapshot'
import type { AffiliationInput, GroupResult } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'

// 與 scripts/make_snapshots.py 的 DEMO_AFFILIATIONS / DEMO_DECLARED / DEMO_EXPOSURES
// 保持逐字一致，避免頁面預填資料與離線快照的生成來源脫鉤。
const DEMO_AFFILIATIONS: Required<AffiliationInput>[] = [
  { company: '泰昇精密', person: '陳大明', role: '董事長' },
  { company: '泰昇投資', person: '陳大明', role: '董事' },
  { company: '昇泰貿易', person: '王秀英', role: '董事' },
  { company: '泰昇投資', person: '王秀英', role: '監察人' },
  { company: '禾昌五金', person: '林志豪', role: '董事長' },
]

const DEMO_DECLARED: Record<string, string> = {
  泰昇精密: '泰昇集團',
  泰昇投資: '泰昇集團',
  昇泰貿易: '昇泰集團',
}

const DEMO_EXPOSURES: Record<string, number> = {
  泰昇精密: 30_000_000,
  泰昇投資: 12_000_000,
  昇泰貿易: 8_000_000,
}

function formatTwd(amount: number): string {
  return `${amount.toLocaleString('zh-TW')} 元`
}

/** 客戶申報的獨立集團數（依 declared_groups 的相異值數）。 */
const DECLARED_GROUP_COUNT = new Set(Object.values(DEMO_DECLARED)).size

function declaredTotal(): number {
  return Object.values(DEMO_EXPOSURES).reduce((sum, value) => sum + value, 0)
}

export default function Group() {
  const [affiliations] = useState(DEMO_AFFILIATIONS)
  const [declared] = useState(DEMO_DECLARED)
  const [exposures] = useState(DEMO_EXPOSURES)
  const [result, setResult] = useState<GroupResult | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(
        await postGroup({
          affiliations,
          declared_groups: declared,
          exposures,
        }),
      )
      setOffline(false)
    } catch (err) {
      // 完全無法連線（斷網/DNS/CORS）或後端本身出錯（5xx，含 Vercel 冷啟動逾時）時
      // 退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      // 4xx（例如 VITE_API_BASE 設錯導致的 404/405）不算——那是設定問題，
      // 假裝查詢成功反而會掩蓋它。
      if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
        setResult(GROUP_SNAPSHOT)
        setOffline(true)
      } else {
        // 清掉上一次的結果，避免畫面同時顯示錯誤條與舊的歸戶結果。
        setResult(null)
        setOffline(false)
        setError(err instanceof ApiError ? err.detail : '執行集團歸戶失敗，請稍後再試。')
      }
    } finally {
      setLoading(false)
    }
  }

  const actualGroupCount = result ? new Set(Object.values(result.groups)).size : null
  const actualTotal = result
    ? Object.values(result.exposures).reduce((sum, value) => sum + value, 0)
    : null

  return (
    <div className="space-y-6">
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

      {result && actualGroupCount !== null && actualTotal !== null && (
        <>
          <Panel title="申報 vs. 實際：曝險被拆散在幾個看似無關的借款戶之間">
            <div className="grid gap-6 sm:grid-cols-2">
              <div className="rounded-lg border border-line p-4">
                <div className="text-xs text-muted">客戶申報</div>
                <div className="tabular mt-1 text-4xl font-semibold text-muted">
                  <span data-testid="group-count-declared">{DECLARED_GROUP_COUNT}</span> 個集團
                </div>
                <div className="tabular mt-2 text-lg text-muted">
                  合計申報曝險 {formatTwd(declaredTotal())}
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
                  className="tabular mt-2 text-lg font-semibold"
                  style={{ color: 'var(--color-risk-high)' }}
                >
                  實際合計曝險 {formatTwd(actualTotal)}
                </div>
              </div>
            </div>
            <p
              className="mt-4 rounded border-l-4 pl-4 text-2xl font-semibold leading-relaxed text-ink"
              style={{ borderColor: 'var(--color-risk-high)' }}
            >
              客戶申報 {DECLARED_GROUP_COUNT} 個獨立集團（合計 {formatTwd(declaredTotal())}），
              關係圖證明其實是同一個集團——實際曝險應為 {formatTwd(actualTotal)}，
              比申報數字高出 {formatTwd(actualTotal - declaredTotal())}，且這個落差在申報名冊裡完全看不見。
            </p>
          </Panel>

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
        </>
      )}
    </div>
  )
}
