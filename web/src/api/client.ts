import { describeError } from './errors'
import type { CreditOpinion, GroupResult, ScreenResult, WorkbenchPayload } from './types'

const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
  ) {
    super(detail)
    this.name = 'ApiError'
  }
}

async function post<T>(path: string, body: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, describeError(0))
  }
  if (!response.ok) {
    const detail = await response
      .json()
      .then((payload: { detail?: unknown }) =>
        typeof payload.detail === 'string' ? payload.detail : undefined,
      )
      .catch(() => undefined)
    throw new ApiError(response.status, describeError(response.status, detail))
  }
  return (await response.json()) as T
}

export function postScreen(target: string, amountUsdt: number): Promise<ScreenResult> {
  return post<ScreenResult>('/screen', {
    target,
    amount_usdt: amountUsdt,
    request_id: 'DEMO-2026-001',
  })
}

export function postGraph(body: {
  mode: 'example' | 'tron'
  address?: string
}): Promise<WorkbenchPayload> {
  return post<WorkbenchPayload>('/graph', body)
}

export function postCredit(
  target: string,
  groupId?: number,
  groupExposureTwd?: number,
): Promise<CreditOpinion> {
  return post<CreditOpinion>('/credit', {
    target,
    group_id: groupId ?? null,
    group_exposure_twd: groupExposureTwd ?? null,
  })
}

export function postGroup(body: {
  affiliations: { company: string; person: string; role?: string }[]
  declared_groups?: Record<string, string>
  exposures?: Record<string, number>
}): Promise<GroupResult> {
  return post<GroupResult>('/group', body)
}

/** 背景喚醒 serverless 函式。冷啟動實測約 5 秒，趁使用者閱讀時吃掉。
 *
 * 打 /ready 而非 /health：所有路徑都由同一個 serverless function 承接
 * （見 repo 根目錄 vercel.json 的 rewrite），暖一條就等於暖全部，而 /ready
 * 順帶驗證接的是不是正確的後端。 */
export function warmUp(): void {
  void fetch(`${API_BASE}/ready`).catch(() => undefined)
}

/** 分析服務是否可用，供首頁的即時狀態指示使用。
 *
 * 刻意不只看 HTTP 狀態碼：/health 回 200 不代表這個站台是 sme-lens 後端。
 * 實際踩過兩次——指向舊的 ChainLens 部署時 /health 是 200 但 /credit 與
 * /group 是 404；VITE_API_BASE 沒設時請求會打到前端自己的靜態站台，拿回
 * index.html 一樣 ok。故要求回應必須是 sme-lens 的 /ready 且企金端點齊備，
 * 否則一律當作未就緒——寧可誤報紅燈，也不要讓失敗留到台上按下按鈕才爆。 */
export async function checkHealth(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/ready`)
    if (!response.ok) return false
    const body: unknown = await response.json()
    if (typeof body !== 'object' || body === null) return false
    const payload = body as { service?: unknown; ready?: unknown }
    return payload.service === 'sme-lens' && payload.ready === true
  } catch {
    return false
  }
}
