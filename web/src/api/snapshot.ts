import type { CreditOpinion, GroupResult, ScreenResult } from './types'
import raw from './screening-snapshot.json'
import creditSnapshot from './credit-snapshot.json'
import groupSnapshot from './group-snapshot.json'

/**
 * 現場保險：API 完全無法連線時，出金審查頁改用這份快照把 Demo 演完。
 * 使用時畫面必須顯示「離線快照」標記，不得偽裝成即時查詢結果。
 */
export const SCREENING_SNAPSHOT = raw as unknown as ScreenResult

/** 現場斷網或後端冷啟動逾時時的備援；畫面必須明確標示為離線快照。 */
export const CREDIT_SNAPSHOT = creditSnapshot as unknown as CreditOpinion
export const GROUP_SNAPSHOT = groupSnapshot as unknown as GroupResult
