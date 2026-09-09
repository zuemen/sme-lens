import { describe, expect, it } from 'vitest'
import { CREDIT_SNAPSHOT, DEMO_ROSTER, GROUP_SNAPSHOT, SCREENING_SNAPSHOT } from './snapshot'

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

/**
 * CREDIT_SNAPSHOT 是 Credit.tsx 唯一的離線保險（見該檔的 offline fallback），
 * 但它同樣是用 `as unknown as CreditOpinion` 匯入 JSON，型別系統不驗證內容。
 * 若重新產生時算錯（例如泰昇精密變成「正常／得依既有授信條件辦理」），
 * Credit.test.tsx 的斷言全部改抓 CREDIT_SNAPSHOT 自己的欄位，仍會全數通過，
 * 錯的數字會直接上台演示螢幕。這支測試把「快照悄悄漂移」變成 CI 紅燈。
 * 數字對應 web/e2e/credit.spec.ts 與決賽口白稿；不得改動。
 */
describe('CREDIT_SNAPSHOT 形狀驗證', () => {
  it('目標企業與關注等級與演示口白一致', () => {
    expect(CREDIT_SNAPSHOT.target).toBe('泰昇精密')
    expect(CREDIT_SNAPSHOT.label).toBe('watch')
    expect(CREDIT_SNAPSHOT.label_zh).toBe('關注')
  })

  it('授信關注分數與演示口白一致（0.82）', () => {
    expect(CREDIT_SNAPSHOT.attention_score).toBe(0.82)
  })

  it('命中的企金風險圖樣種類與演示口白一致（封閉資金環、買方集中）', () => {
    const motifs = CREDIT_SNAPSHOT.motif_hits.map((hit) => hit.motif).sort()
    expect(motifs).toEqual(['buyer_concentration', 'cycle_trade'])
  })

  it('關係圖節點數與演示口白一致（11 個）', () => {
    expect(CREDIT_SNAPSHOT.graph.nodes.length).toBe(11)
  })
})

/**
 * GROUP_SNAPSHOT 同理：Group.tsx 的頭條數字（客戶申報 2 個 vs 歸戶後 1 個、
 * 42,000,000 → 50,000,000，落差 8,000,000）全部從這份快照算出來，
 * Group.test.tsx 也只驗證這份快照自身內部一致。這裡改為釘死字面值。
 */
describe('GROUP_SNAPSHOT 形狀驗證', () => {
  it('三家申報名冊內的公司都歸入同一集團（0），對照組禾昌五金另成一團（1）', () => {
    expect(GROUP_SNAPSHOT.groups['泰昇精密']).toBe(0)
    expect(GROUP_SNAPSHOT.groups['泰昇投資']).toBe(0)
    expect(GROUP_SNAPSHOT.groups['昇泰貿易']).toBe(0)
    expect(GROUP_SNAPSHOT.groups['禾昌五金']).toBe(1)
  })

  it('合併後集團 0 的曝險為 50,000,000（三家申報曝險合計）', () => {
    expect(GROUP_SNAPSHOT.exposures['0']).toBe(50_000_000)
  })

  it('唯一的隱性關聯是昇泰貿易與泰昇投資因共用王秀英而併團', () => {
    expect(GROUP_SNAPSHOT.hidden_links.length).toBe(1)
    const [link] = GROUP_SNAPSHOT.hidden_links
    expect(link.company_a).toBe('昇泰貿易')
    expect(link.company_b).toBe('泰昇投資')
    expect(link.shared_persons).toEqual(['王秀英'])
  })
})

/**
 * DEMO_ROSTER（web/src/api/demo-roster.json）與 GROUP_SNAPSHOT（group-snapshot.json）
 * 都由 scripts/make_snapshots.py 同一輪執行、用同一份 DEMO_AFFILIATIONS / DEMO_DECLARED /
 * DEMO_EXPOSURES 產生：demo-roster.json 是輸入本身落盤，group-snapshot.json 是拿那份輸入
 * 對後端 /group 發出請求後的輸出。Group.tsx 只從 DEMO_ROSTER 匯入畫面上的名冊，
 * 若有人手動改了其中一份 JSON 卻忘了重跑腳本重新產生另一份，畫面上的名冊表就會
 * 跟歸戶結果（GROUP_SNAPSHOT）互相矛盾——這支測試把那種漂移變成 CI 紅燈。
 */
describe('DEMO_ROSTER 與 GROUP_SNAPSHOT 一致性', () => {
  it('GROUP_SNAPSHOT.groups 涵蓋的每家公司，都能在 DEMO_ROSTER 的申報名冊或曝險資料中找到', () => {
    const rosterCompanies = new Set([
      ...DEMO_ROSTER.affiliations.map((row) => row.company),
      ...Object.keys(DEMO_ROSTER.exposures),
    ])
    for (const company of Object.keys(GROUP_SNAPSHOT.groups)) {
      expect(rosterCompanies.has(company)).toBe(true)
    }
  })

  it('DEMO_ROSTER 申報名冊內的公司，合計曝險與 GROUP_SNAPSHOT 歸戶後的集團曝險吻合', () => {
    const declaredCompanies = Object.keys(DEMO_ROSTER.declared)
    const total = declaredCompanies.reduce(
      (sum, company) => sum + (DEMO_ROSTER.exposures[company] ?? 0),
      0,
    )
    const groupIds = new Set(declaredCompanies.map((company) => GROUP_SNAPSHOT.groups[company]))
    expect(groupIds.size).toBe(1)
    const [groupId] = groupIds
    expect(GROUP_SNAPSHOT.exposures[String(groupId)]).toBe(total)
  })

  it('隱性關聯裡點名的自然人，確實同時出現在 DEMO_ROSTER 兩家公司的申報名冊上', () => {
    for (const link of GROUP_SNAPSHOT.hidden_links) {
      for (const person of link.shared_persons) {
        const companiesForPerson = new Set(
          DEMO_ROSTER.affiliations
            .filter((row) => row.person === person)
            .map((row) => row.company),
        )
        expect(companiesForPerson.has(link.company_a)).toBe(true)
        expect(companiesForPerson.has(link.company_b)).toBe(true)
      }
    }
  })
})
