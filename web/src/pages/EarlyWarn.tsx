import { useEffect, useRef, useState } from 'react'
import { ApiError, postEarlyWarn } from '../api/client'
import { EARLYWARN_SNAPSHOT } from '../api/snapshot'
import type { EarlyWarnResult } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'

/** 劇本圖裡最可能先出事的那一家：空殼中介，過水比 99%、自身幾無留存。 */
const DEFAULT_SEED = '宏益企業'

/** 可選的出事戶。限定在劇本圖的公司內，避免使用者打錯字換來一個 404。 */
const SEED_OPTIONS = [
  { value: '宏益企業', label: '宏益企業（空殼中介，過水比 99%）' },
  { value: '鴻寶電子', label: '鴻寶電子（核心買方，佔申請人收入 84%）' },
  { value: '泰昇投資', label: '泰昇投資（關係人，資金環上一站）' },
]

/** 示範用授信餘額。與集團歸戶頁的示範名冊同一套劇本，數字刻意一致。 */
const DEMO_EXPOSURES: Record<string, number> = {
  泰昇精密: 30_000_000,
  昇泰貿易: 12_000_000,
  宏益企業: 8_000_000,
  鴻寶電子: 50_000_000,
  中部機電: 4_000_000,
  禾昌五金: 6_000_000,
}

function formatTwd(amount: number | null): string {
  if (amount === null) return '—'
  return `${amount.toLocaleString('zh-TW')} 元`
}

const HOP_LABEL: Record<number, string> = {
  0: '已出事戶',
  1: '直接對手方',
  2: '第二層',
}

export default function EarlyWarn() {
  const [seed, setSeed] = useState(DEFAULT_SEED)
  const [result, setResult] = useState<EarlyWarnResult | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const resultsRef = useRef<HTMLDivElement>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setAnnouncement('正在計算關聯風險擴散…')
    try {
      const payload = await postEarlyWarn({ seeds: [seed], exposures: DEMO_EXPOSURES })
      setResult(payload)
      setOffline(false)
      setAnnouncement(
        `關注名單已產生，共 ${payload.watchlist.length} 筆，受影響曝險 ${formatTwd(
          payload.exposure_at_risk_twd,
        )}。`,
      )
    } catch (err) {
      // 與其他 demo 頁同一套規則：斷線或後端 5xx 才退回離線快照，4xx 不退
      // （那是設定問題，假裝查詢成功只會掩蓋它）。
      if (err instanceof ApiError && (err.status === 0 || err.status >= 500)) {
        setResult(EARLYWARN_SNAPSHOT)
        setOffline(true)
        setAnnouncement('無法連線即時服務，已改用內建備援資料顯示關注名單。')
      } else {
        setResult(null)
        setOffline(false)
        const detail = err instanceof ApiError ? err.detail : '計算早期預警失敗，請稍後再試。'
        setError(detail)
        setAnnouncement(`查詢失敗：${detail}`)
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!result) return
    resultsRef.current?.querySelector<HTMLElement>('h2')?.focus()
  }, [result])

  return (
    <div className="space-y-6">
      <div role="status" aria-live="polite" className="sr-only">
        {announcement}
      </div>

      <div>
        <h1 className="text-2xl font-semibold">貸後早期預警</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          貸前有集團歸戶、貸中有授信意見書，貸後管理卻仍倚賴季報與逾期通報——上下游一家
          出事，銀行往往要等到自己的戶頭也逾期才知道。但「誰跟出事那家連得到」這件事，
          關係圖現在就答得出來。
        </p>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
          方法是<b>帶夾制的標籤擴散（label spreading）</b>，半監督式圖學習的經典解法：
          只需要銀行手上本來就有的<b>少量出事戶名單</b>，就能把風險推論到還沒出事的戶上。
          之所以不訓練分類器，是因為企業關係圖這一側沒有真值標註，監督式模型沒有可信的
          訓練集；而這個方法要的正是少量種子。更關鍵的是它<b>可解釋</b>
          ——每一筆都說得出風險從哪一家、經過幾跳、沿哪條路徑傳過來。
        </p>
      </div>

      <Panel title="指定已出事的授信戶">
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label htmlFor="seed" className="block text-xs text-muted">
              出事戶（種子）
            </label>
            <select
              id="seed"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              className="mt-1 rounded border border-line bg-panel px-3 py-2 text-base"
            >
              {SEED_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            onClick={run}
            disabled={loading}
            data-testid="earlywarn-submit"
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '計算中…' : '產生關注名單'}
          </button>
        </div>
        <p className="mt-3 text-xs leading-relaxed text-muted">
          擴散只在關係圖上進行，不需要客戶配合、不需要新增任何申報欄位。
          授信餘額採與集團歸戶頁同一套示範數字。
        </p>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {offline && (
        <ErrorNotice message="目前顯示的是內建離線快照，非即時查詢結果——已標示為離線快照。" />
      )}

      {result && (
        <div ref={resultsRef} className="space-y-6">
          <Panel title="這件事會影響多少錢">
            <div className="grid gap-6 sm:grid-cols-3">
              <div>
                <div className="text-xs text-muted">關注名單</div>
                <div className="tabular mt-1 text-4xl font-semibold" data-testid="warn-count">
                  {result.watchlist.length}
                </div>
                <div className="mt-1 text-xs text-muted">家（含已出事戶）</div>
              </div>
              <div>
                <div className="text-xs text-muted">受影響授信餘額</div>
                <div
                  className="tabular mt-1 text-4xl font-semibold"
                  style={{ color: 'var(--color-risk-high)' }}
                  data-testid="warn-exposure"
                >
                  {result.exposure_at_risk_twd.toLocaleString('zh-TW')}
                </div>
                <div className="mt-1 text-xs text-muted">元（已排除出事戶本身）</div>
              </div>
              <div>
                <div className="text-xs text-muted">參數</div>
                <div className="tabular mt-1 text-sm leading-relaxed">
                  擴散強度 α={result.parameters.alpha}
                  <br />
                  分數門檻 {result.parameters.threshold}
                  <br />
                  最遠 {result.parameters.max_hops} 跳
                </div>
              </div>
            </div>
            <p className="mt-4 text-xs leading-relaxed text-muted">
              受影響曝險刻意<b>排除出事戶本身</b>：它的餘額已進催收程序，不屬於「因為這次
              擴散而新被點名」的曝險，算進來會虛增這份名單的價值。
            </p>
          </Panel>

          <Panel title="關注名單（依預警分數排序；分數只決定順序，要看的是路徑）">
            <div className="overflow-x-auto">
              <table className="tabular w-full text-left text-sm">
                <caption className="sr-only">
                  貸後關注名單，欄位為公司、預警分數、關聯層級、授信餘額、風險傳遞路徑與處置建議
                </caption>
                <thead>
                  <tr className="border-b border-line text-xs text-muted">
                    <th scope="col" className="py-2 pr-4">
                      公司
                    </th>
                    <th scope="col" className="py-2 pr-4">
                      預警分數
                    </th>
                    <th scope="col" className="py-2 pr-4">
                      關聯層級
                    </th>
                    <th scope="col" className="py-2 pr-4">
                      授信餘額
                    </th>
                    <th scope="col" className="py-2 pr-4">
                      風險傳遞路徑（證據）
                    </th>
                  </tr>
                </thead>
                <tbody data-testid="warn-table">
                  {result.watchlist.map((item) => (
                    <tr key={item.company} className="border-b border-line/50">
                      <td className="py-2 pr-4 font-semibold">{item.company}</td>
                      <td className="py-2 pr-4">{item.score.toFixed(4)}</td>
                      <td className="py-2 pr-4">{HOP_LABEL[item.hops] ?? `第 ${item.hops} 層`}</td>
                      <td className="py-2 pr-4">{formatTwd(item.exposure_twd)}</td>
                      <td className="py-2 pr-4">{item.path.join(' → ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>

          <Panel title="處置建議（分級，非一律拒貸）">
            <ul className="space-y-3 text-sm leading-relaxed">
              {result.watchlist.map((item) => (
                <li key={item.company} className="border-l-4 border-line pl-4">
                  <b>{item.company}</b>
                  <span className="ml-2 text-xs text-muted">
                    {HOP_LABEL[item.hops] ?? `第 ${item.hops} 層`}
                  </span>
                  <div className="mt-1">{item.action_zh}</div>
                  <div className="mt-1 text-xs text-muted">{item.reason_zh}</div>
                </li>
              ))}
            </ul>
          </Panel>

          {result.seeds_not_in_graph.length > 0 && (
            <Panel title="未納入計算的出事戶">
              <p className="mb-3 text-sm text-muted">
                以下公司不在本劇本關係圖中，因此未納入擴散計算。這裡刻意逐一列名，
                而不是靜默丟棄——否則會讓人誤以為這些戶「沒有關聯風險」。
              </p>
              <ul className="list-inside list-disc text-sm">
                {result.seeds_not_in_graph.map((company) => (
                  <li key={company}>{company}</li>
                ))}
              </ul>
            </Panel>
          )}

          <p className="text-xs leading-relaxed text-muted">{result.method_zh}</p>
        </div>
      )}
    </div>
  )
}
