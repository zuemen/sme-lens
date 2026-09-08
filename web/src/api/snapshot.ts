import type { ScreenResult } from './types'
import raw from './screening-snapshot.json'

/**
 * 現場保險：API 完全無法連線時，出金審查頁改用這份快照把 Demo 演完。
 * 使用時畫面必須顯示「離線快照」標記，不得偽裝成即時查詢結果。
 */
export const SCREENING_SNAPSHOT = raw as unknown as ScreenResult
