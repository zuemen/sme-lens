import { useState } from 'react'
import { ApiError, postScreen } from '../api/client'
import { SCREENING_SNAPSHOT } from '../api/snapshot'
import type { ScreenResult } from '../api/types'
import { DecisionCard } from '../components/DecisionCard'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'
import { GraphView } from '../graph/GraphView'

const TARGETS = [
  { value: 'TOtcOut01', label: 'TOtcOut01（本案：未通報之 OTC 收款地址）' },
  { value: 'TNormalUser01', label: 'TNormalUser01（對照組：正常用戶地址）' },
]

const MOTIF_ZH: Record<string, string> = {
  fan_in: '集資扇入',
  fan_out: '快速分散',
  gather_scatter: '集散（smurfing）',
  peeling_chain: '剝洋蔥鏈',
}

export default function Screening() {
  const [target, setTarget] = useState(TARGETS[0].value)
  const [amount, setAmount] = useState(500000)
  const [result, setResult] = useState<ScreenResult | null>(null)
  const [offline, setOffline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function run() {
    setLoading(true)
    setError(null)
    try {
      setResult(await postScreen(target, amount))
      setOffline(false)
    } catch (err) {
      // 完全無法連線（斷網/DNS/CORS）或後端本身出錯（5xx，含 Vercel 冷啟動逾時）時
      // 退回內建快照，讓現場演示不中斷；畫面會明確標示為離線快照。
      // 4xx（例如 VITE_API_BASE 設錯導致的 404/405）不算——那是設定問題，
      // 假裝查詢成功反而會掩蓋它。
      if (
        err instanceof ApiError &&
        (err.status === 0 || err.status >= 500) &&
        target === 'TOtcOut01'
      ) {
        setResult(SCREENING_SNAPSHOT)
        setOffline(true)
      } else {
        // 清掉上一次的結果，避免畫面同時顯示錯誤條與舊的（且可能是別的目標地址的）決策卡。
        setResult(null)
        setOffline(false)
        setError(err instanceof ApiError ? err.detail : '審查失敗，請稍後再試。')
      }
    } finally {
      setLoading(false)
    }
  }

  function downloadStr() {
    if (!result?.str_draft_zh) return
    const url = URL.createObjectURL(new Blob([result.str_draft_zh], { type: 'text/plain' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `STR_draft_${result.target}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold">出金審查</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          交易所用戶申請將 50 萬 USDT 提領至外部地址。該地址從未被通報、不在任何黑名單上——
          傳統名單比對會直接放行。以下展示結構化關聯追溯如何攔下它。
        </p>
      </div>

      <Panel>
        <div className="grid gap-4 md:grid-cols-[2fr_1fr_auto] md:items-end">
          <label className="block">
            <span className="text-xs text-muted">出金目標地址</span>
            <select
              value={target}
              onChange={(event) => setTarget(event.target.value)}
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            >
              {TARGETS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className="block">
            <span className="text-xs text-muted">申請金額（USDT）</span>
            <input
              type="number"
              min={1}
              step={10000}
              value={amount}
              onChange={(event) => setAmount(Number(event.target.value))}
              className="tabular mt-1 w-full rounded border border-line bg-panel-raised p-2"
            />
          </label>

          <button
            type="button"
            onClick={run}
            disabled={loading}
            className="rounded bg-ink px-5 py-2 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '審查中…' : '執行出金審查'}
          </button>
        </div>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {offline && (
        <ErrorNotice message="目前顯示的是內建離線快照（案例金額固定為 500,000 USDT，與上方輸入的申請金額無關），非即時查詢結果。" />
      )}

      {result && (
        <>
          <DecisionCard result={result} />

          {result.associations.length > 0 && (
            <Panel title="資金關聯證據鏈">
              <ul className="space-y-3 text-sm">
                {result.associations.map((association) => (
                  <li key={association.risky_node} className="border-l-2 border-line pl-4">
                    <div className="tabular">
                      {association.risky_node}
                      <span className="ml-2 text-muted">{association.distance} 階關聯</span>
                    </div>
                    <div className="mt-1 text-muted">
                      命中圖樣：
                      {association.motifs.map((m) => MOTIF_ZH[m] ?? m).join('、')}
                    </div>
                    <div className="tabular mt-1 text-xs text-muted">
                      {association.path.join(' → ')}
                    </div>
                  </li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel title="金流圖譜（橘色路徑＝風險資金流向出金地址；金色＝審查目標）">
            <GraphView
              payload={result.graph}
              highlightPath={result.highlight_path}
              focus={result.target}
              layout="dagre"
              scheme="role"
            />
          </Panel>

          {result.str_draft_zh && (
            <Panel
              title="可疑交易申報（STR）草稿"
              actions={
                <button
                  type="button"
                  onClick={downloadStr}
                  className="rounded border border-line px-3 py-1 text-sm"
                >
                  下載草稿（.txt）
                </button>
              }
            >
              <pre className="tabular max-h-96 overflow-auto whitespace-pre-wrap text-xs leading-relaxed text-muted">
                {result.str_draft_zh}
              </pre>
            </Panel>
          )}

          <Panel title="結構證據 JSON（稽核軌跡）">
            <pre className="tabular max-h-96 overflow-auto text-xs text-muted">
              {JSON.stringify(result.evidence, null, 2)}
            </pre>
          </Panel>
        </>
      )}
    </div>
  )
}
