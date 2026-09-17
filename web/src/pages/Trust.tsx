import { useEffect, useRef, useState } from 'react'
import { ApiError, postTrustVerify } from '../api/client'
import TRUST_FIXTURE from '../api/trust-fixture.json'
import type { TrustVerifyResult } from '../api/types'
import { ErrorNotice } from '../components/ErrorNotice'
import { Panel } from '../components/Panel'

/** 示範資料：憑證的簽章由 scripts/make_trust_fixture.py 真實產生（見該檔說明）。 */
const FIXTURE = TRUST_FIXTURE as {
  trust_root: string
  authorised_by: Record<string, string>
  lei_to_company_id: Record<string, string>
  revoked_credential_ids: string[]
  anchor_reference: string
  affiliations: {
    company: string
    person: string
    role: string
    company_id: string
    tier: string
    merge: boolean
  }[]
  presentation: Record<string, unknown>
}

function shortDid(did: string): string {
  return did.length > 26 ? `${did.slice(0, 18)}…${did.slice(-6)}` : did
}

export default function Trust() {
  const [result, setResult] = useState<TrustVerifyResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [announcement, setAnnouncement] = useState('')
  const resultsRef = useRef<HTMLDivElement>(null)

  async function run() {
    setLoading(true)
    setError(null)
    setAnnouncement('正在驗證可驗證憑證…')
    try {
      const payload = await postTrustVerify({
        affiliations: FIXTURE.affiliations,
        presentation: FIXTURE.presentation,
        trust_root: FIXTURE.trust_root,
        authorised_by: FIXTURE.authorised_by,
        lei_to_company_id: FIXTURE.lei_to_company_id,
        revoked_credential_ids: FIXTURE.revoked_credential_ids,
        anchor_reference: FIXTURE.anchor_reference,
      })
      setResult(payload)
      setAnnouncement(
        `驗證完成：升級 ${payload.promoted.length} 筆，歸戶由 ${payload.groups_before} 戶變為 ${payload.groups_after} 戶。`,
      )
    } catch (err) {
      // 這一頁沒有離線快照：憑證驗證的結果不能用預錄的答案冒充，那會讓
      // 「我們真的驗了簽章」這個主張失去意義。
      setResult(null)
      const detail = err instanceof ApiError ? err.detail : '憑證驗證失敗，請稍後再試。'
      setError(detail)
      setAnnouncement(`驗證失敗：${detail}`)
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
        <h1 className="text-2xl font-semibold">可驗證憑證：把候選變成證據</h1>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          公開登記資料<b>沒有身分證字號</b>，所以自然人董監事只能是 B 層候選——全台
          「陳建宏」一個姓名就掛 411 家公司，程式不敢也不該自動合併。原本的解法是等銀行
          拿行內 KYC 的身分證字號來解析，但那要求銀行把身分資料送進本系統，是導入上最大
          的阻力。
        </p>
        <p className="mt-3 max-w-3xl text-sm leading-relaxed text-muted">
          <b>vLEI</b>（GLEIF 的可驗證法人識別碼框架）給了第三條路：企業自己出示一份
          可驗證憑證，證明「某人確實在本法人擔任某法定職務」。銀行不必交出任何身分資料，
          本系統也不持有任何個資——只驗證一份帶簽章的憑證，就能把那條關聯從候選升為證據。
        </p>
      </div>

      <Panel title="五道驗證關卡（缺一不可）">
        <ol className="ml-5 list-decimal space-y-1 text-sm leading-relaxed text-muted">
          <li>
            <b className="text-ink">結構</b>：型別、簽發者、主體、有效期間欄位齊備
          </li>
          <li>
            <b className="text-ink">簽章</b>：以 <span className="tabular">did:key</span>{' '}
            解出簽發者公鑰，驗 Ed25519（RFC 8032）
          </li>
          <li>
            <b className="text-ink">有效期間</b>：未生效或已過期都不算
          </li>
          <li>
            <b className="text-ink">信任鏈</b>：簽發者須沿授權鏈回溯至信任根（GLEIF 根 →
            QVI → 法人），不是隨便一個 DID 說了算
          </li>
          <li>
            <b className="text-ink">撤銷狀態</b>：憑證可能在有效期內被撤銷
          </li>
        </ol>
        <div className="mt-4">
          <button
            type="button"
            onClick={run}
            disabled={loading}
            data-testid="trust-submit"
            className="tap rounded bg-ink px-5 font-semibold text-base disabled:opacity-50"
          >
            {loading ? '驗證中…' : '驗證憑證並升級歸戶'}
          </button>
        </div>
        <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted">
          示範用的三份憑證由開源腳本以固定種子<b>真實簽章</b>產生，其中一份刻意自簽、
          回溯不到信任根，用來示範「簽章有效但簽發者不可信」也會被擋下。真實的 vLEI 由
          GLEIF 認證的 QVI 簽發，私鑰不會出現在任何原始碼庫。
        </p>
      </Panel>

      {error && <ErrorNotice message={error} action={{ label: '重試', onClick: run }} />}

      {result && (
        <div ref={resultsRef} className="space-y-6">
          <Panel title="憑證讓歸戶結果改變了">
            <div className="grid gap-6 sm:grid-cols-3">
              <div>
                <div className="text-xs text-muted">驗證前歸戶</div>
                <div className="numeral mt-1 text-4xl font-semibold text-muted">
                  {result.groups_before}
                </div>
                <div className="mt-1 text-xs text-muted">戶（姓名相同但無法確認）</div>
              </div>
              <div>
                <div className="text-xs text-muted">驗證後歸戶</div>
                <div
                  className="numeral mt-1 text-4xl font-semibold"
                  style={{ color: 'var(--color-risk-low)' }}
                  data-testid="trust-groups-after"
                >
                  {result.groups_after}
                </div>
                <div className="mt-1 text-xs text-muted">戶（身分經憑證確認）</div>
              </div>
              <div>
                <div className="text-xs text-muted">升級筆數</div>
                <div className="numeral mt-1 text-4xl font-semibold" data-testid="trust-promoted">
                  {result.promoted.length}
                </div>
                <div className="mt-1 text-xs text-muted">筆 B 層候選 → A 層證據</div>
              </div>
            </div>
          </Panel>

          {result.promoted.length > 0 && (
            <Panel title="升級紀錄（含簽發者回溯到信任根的完整授權鏈）">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <caption className="sr-only">
                    經可驗證憑證升級的關聯，欄位為公司、自然人、職務、LEI 與簽發者授權鏈
                  </caption>
                  <thead>
                    <tr className="border-b border-line text-xs text-muted">
                      <th scope="col" className="py-2 pr-4">
                        公司
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        自然人
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        法定職務
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        LEI
                      </th>
                      <th scope="col" className="py-2 pr-4">
                        簽發者授權鏈
                      </th>
                    </tr>
                  </thead>
                  <tbody data-testid="trust-table">
                    {result.promoted.map((item) => (
                      <tr key={item.credential_id} className="border-b border-line/50">
                        <td className="py-2 pr-4">{item.company}</td>
                        <td className="py-2 pr-4">{item.person}</td>
                        <td className="py-2 pr-4">{item.role}</td>
                        <td className="tabular py-2 pr-4 text-xs">{item.lei}</td>
                        <td className="py-2 pr-4 text-xs text-muted">
                          {item.issuer_chain.map(shortDid).join(' → ')}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted">
                自然人姓名一律遮蔽後輸出（與集團歸戶頁同一套標準）。授權鏈由右往左看即是
                GLEIF 根 → QVI → 法人——最右邊那個 DID 是信任根。
              </p>
            </Panel>
          )}

          {result.rejected.length > 0 && (
            <Panel title="被擋下來的憑證（以及為什麼）">
              <ul className="space-y-2 text-sm leading-relaxed" data-testid="trust-rejected">
                {result.rejected.map((reason) => (
                  <li key={reason} className="border-l-4 pl-4" style={{ borderColor: 'var(--color-risk-med)' }}>
                    {reason}
                  </li>
                ))}
              </ul>
              <p className="mt-3 max-w-3xl text-xs leading-relaxed text-muted">
                失敗要說得出原因。只回「驗證失敗」的系統，沒辦法讓授信人員判斷是憑證過期、
                簽發者不可信，還是內容被改過。
              </p>
            </Panel>
          )}

          <Panel title="撤銷清單與鏈上錨定">
            <dl className="space-y-3 text-sm">
              <div>
                <dt className="text-xs text-muted">撤銷清單的 Merkle 根</dt>
                <dd className="tabular mt-1 break-all text-xs" data-testid="trust-root-hash">
                  {result.revocation.merkle_root}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-muted">已撤銷憑證數</dt>
                <dd className="numeral mt-1">{result.revocation.revoked_count}</dd>
              </div>
              <div>
                <dt className="text-xs text-muted">鏈上錨定狀態</dt>
                <dd className="mt-1" data-testid="trust-anchored">
                  {result.revocation.anchored ? (
                    <span style={{ color: 'var(--color-risk-low)' }}>
                      已錨定：{result.revocation.anchor_reference}
                    </span>
                  ) : (
                    <span style={{ color: 'var(--color-risk-med)' }}>
                      尚未錨定（本機清單）
                    </span>
                  )}
                </dd>
              </div>
            </dl>
            <p className="mt-4 max-w-3xl text-xs leading-relaxed text-muted">
              撤銷清單若只由簽發者自己保管，他就能事後悄悄改寫歷史——把當時有效的憑證講成
              早已撤銷，或反之。把清單的 Merkle 根錨定在公開鏈上就不可改，任何人都能用一條
              log₂(n) 長度的包含性證明驗證某個狀態確實屬於某個時點的清單，不必下載整份清單。
            </p>
            <p className="mt-2 max-w-3xl text-xs leading-relaxed text-muted">
              <b>誠實邊界</b>：Merkle 根與包含性證明是本系統真的算出來的密碼學結果，
              可獨立驗算；<b>把根雜湊送上鏈則尚未實作</b>——那需要私鑰與金流，屬營運步驟。
              上方狀態顯示「尚未錨定」就是字面意思，不把本機清單講成已上鏈。
            </p>
          </Panel>

          <p className="max-w-3xl text-xs leading-relaxed text-muted">{result.method_zh}</p>
        </div>
      )}
    </div>
  )
}
