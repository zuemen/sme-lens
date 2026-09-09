import type { CreditOpinion, GroupResult, ScreenResult } from './types'
import raw from './screening-snapshot.json'
import creditSnapshot from './credit-snapshot.json'
import creditControlSnapshot from './credit-control-snapshot.json'
import groupSnapshot from './group-snapshot.json'
import demoRoster from './demo-roster.json'

/**
 * 現場保險：API 完全無法連線時，出金審查頁改用這份快照把 Demo 演完。
 * 使用時畫面必須顯示「離線快照」標記，不得偽裝成即時查詢結果。
 */
export const SCREENING_SNAPSHOT = raw as unknown as ScreenResult

/** 現場斷網或後端冷啟動逾時時的備援；畫面必須明確標示為離線快照。 */
export const CREDIT_SNAPSHOT = creditSnapshot as unknown as CreditOpinion
/** 對照組（禾昌五金）的離線備援，讓「不是逢公司必標」的示範也有斷網保險。 */
export const CREDIT_CONTROL_SNAPSHOT = creditControlSnapshot as unknown as CreditOpinion
export const GROUP_SNAPSHOT = groupSnapshot as unknown as GroupResult

/**
 * 集團歸戶頁的示範名冊，唯一來源是 scripts/make_snapshots.py：
 * 該腳本用同一份 DEMO_AFFILIATIONS / DEMO_DECLARED / DEMO_EXPOSURES 對後端發出請求
 * 產生 group-snapshot.json，並把輸入本身落盤成這份 JSON，避免 Python／TypeScript
 * 兩邊各存一份、只靠註解「保持逐字一致」。
 */
export const DEMO_ROSTER = demoRoster as unknown as {
  affiliations: Required<import('./types').AffiliationInput>[]
  declared: Record<string, string>
  exposures: Record<string, number>
}
