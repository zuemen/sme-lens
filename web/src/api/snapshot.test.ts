import { describe, expect, it } from 'vitest'
import { SCREENING_SNAPSHOT } from './snapshot'

/**
 * 快照是現場演示唯一的離線保險（見 Screening.tsx 的 offline fallback），
 * 但它是用 `as unknown as ScreenResult` 匯入 JSON，型別系統完全不驗證內容。
 * 這支測試把「快照悄悄漂移」變成 CI 紅燈，而不是演示現場螢幕上一個錯的數字。
 * 斷言的數字對應 DEMO_SCRIPT.md 與 e2e/screening.spec.ts 演示的口白內容，不得改動。
 */
describe('SCREENING_SNAPSHOT 形狀驗證', () => {
  it('目標與金額與演示劇本一致', () => {
    expect(SCREENING_SNAPSHOT.target).toBe('TOtcOut01')
    expect(SCREENING_SNAPSHOT.amount_usdt).toBe(500000)
  })

  // 此處刻意不是 block：劇本中的出金地址本身不命中任何圖樣、也不在黑名單上，
  // self_score 僅 0.149，全部的指控來自二階關聯鏈。先前之所以達到 block，是因為
  // 社群風險比被固定成 1.0 而灌高了自身分數；該缺陷修正後，對一個自身無結構異常
  // 的地址給予 EDD 而非硬擋，才是站得住腳的風險立場。門檻未動。
  it('三個分數與決策與演示口白一致（0.66 / 0.15 / 0.60 → review／EDD）', () => {
    expect(SCREENING_SNAPSHOT.risk_score).toBe(0.6596)
    expect(SCREENING_SNAPSHOT.self_score).toBe(0.149)
    expect(SCREENING_SNAPSHOT.association_score).toBe(0.6)
    expect(SCREENING_SNAPSHOT.decision).toBe('review')
  })

  it('關聯證據鏈與圖譜節點/邊數與演示口白一致', () => {
    expect(SCREENING_SNAPSHOT.associations.length).toBe(6)
    expect(SCREENING_SNAPSHOT.graph.nodes.length).toBe(53)
    expect(SCREENING_SNAPSHOT.graph.edges.length).toBe(63)
    expect(SCREENING_SNAPSHOT.highlight_path).toEqual(['TAggregator01', 'TMule03', 'TOtcOut01'])
  })

  it('DecisionCard／STR 下載／證據 JSON 面板依賴的欄位都存在', () => {
    expect(SCREENING_SNAPSHOT.decision_zh.length).toBeGreaterThan(0)
    expect(SCREENING_SNAPSHOT.narrative_zh.length).toBeGreaterThan(0)
    expect(typeof SCREENING_SNAPSHOT.str_draft_zh).toBe('string')
    expect(SCREENING_SNAPSHOT.str_draft_zh!.length).toBeGreaterThan(0)
    expect(SCREENING_SNAPSHOT.evidence).not.toBeNull()
    expect(SCREENING_SNAPSHOT.evidence!.label).toBe('low')
  })

  it('每一條關聯證據都有 GraphView／文字替代表格渲染需要的欄位', () => {
    for (const association of SCREENING_SNAPSHOT.associations) {
      expect(typeof association.risky_node).toBe('string')
      expect(typeof association.distance).toBe('number')
      expect(Array.isArray(association.path)).toBe(true)
      expect(association.path.length).toBeGreaterThan(0)
      expect(Array.isArray(association.motifs)).toBe(true)
    }
  })
})
