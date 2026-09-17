export type RiskLabel = 'high' | 'medium' | 'low'
export type Decision = 'block' | 'review' | 'pass'

export interface GraphNode {
  id: string
  role: string
  role_zh: string
  score: number
  label: RiskLabel
  is_motif_center: boolean
  pagerank: number
  narrative_zh: string
}

export interface GraphEdge {
  source: string
  target: string
  amount: number
  timestamp: number | null
}

export interface GraphMeta {
  /** 實際回傳（可能已截斷）的節點數 */
  node_count: number
  /** 截斷前的原始節點數 */
  total_node_count: number
  edge_count: number
  /** 超過 300 節點上限而截斷；前端必須告知使用者 */
  truncated: boolean
  story_zh: string | null
  degraded: boolean
}

export interface GraphPayload {
  nodes: GraphNode[]
  edges: GraphEdge[]
  meta: GraphMeta
}

export interface MotifHit {
  motif: string
  center: string
  nodes: string[]
  description_zh: string
}

export interface Evidence {
  score: number
  label: RiskLabel
  top_features: string[]
  centrality_percentile: Record<string, number>
  community_risk_ratio: number
  motif_hits: MotifHit[]
  narrative_zh: string
}

export interface Association {
  risky_node: string
  distance: number
  path: string[]
  motifs: string[]
}

export interface ScreenResult {
  target: string
  amount_usdt: number
  risk_score: number
  self_score: number
  association_score: number
  decision: Decision
  decision_zh: string
  narrative_zh: string
  associations: Association[]
  evidence: Evidence | null
  str_draft_zh: string | null
  /** 目標不在圖中時後端才會帶這個鍵，正常路徑完全沒有此欄位 */
  insufficient_data?: true
  graph: GraphPayload
  highlight_path: string[]
}

export interface SnaRow {
  node: string
  in_degree: number
  out_degree: number
  pagerank: number
  kcore: number
  betweenness: number
  score: number
}

export interface WorkbenchPayload extends GraphPayload {
  sna: SnaRow[]
}

/** 授信關注等級。與防詐分支的 RiskLabel 刻意分開：值域與語意都不同。 */
export type AttentionLabel = 'watch' | 'caution' | 'normal'

export interface CreditMotifHit {
  motif: string
  center: string
  nodes: string[]
  description_zh: string
}

export interface CreditOpinion {
  target: string
  attention_score: number
  /** 無收入者（純買方，in-degree 為 0）沒有「買方結構」可評估，後端回傳 null 而非 0——
   * 未評估不是最差評估。畫面須對 null 明確說明原因，不能當數字硬 toFixed。 */
  network_credit: number | null
  label: AttentionLabel
  label_zh: string
  /** 與 network_credit 同一個立場：無收入可看時後端回 null（不可評估），
   * 回 0 專指「收入全部來自單一買方」這個最集中、風險最高的情形。 */
  counterparty_diversity: number | null
  centrality_percentile: Record<string, number>
  community_risk_ratio: number
  group_id: number | null
  group_exposure_twd: number | null
  motif_hits: CreditMotifHit[]
  narrative_zh: string
  recommendation_zh: string
  graph: GraphPayload
}

export interface AffiliationInput {
  company: string
  person: string
  role?: string
  /** 公司統一編號；提供時歸戶以此為準，而非公司名稱字串 */
  company_id?: string
  /** 自然人識別碼；提供時歸戶以此為準，而非姓名字串（同名不同人／同人換名都靠它判斷） */
  person_id?: string
}

export interface HiddenLink {
  company_a: string
  company_b: string
  shared_persons: string[]
  declared_group_a: string | null
  declared_group_b: string | null
  /** 共用實體數。後端依此由高到低排序後截斷，是「優先看哪幾筆」的依據。 */
  weight: number
  /** "A"＝法人董事（無姓名歧義）；"B"＝純姓名比對，只能是候選。 */
  tier: 'A' | 'B'
  /** true＝這條關聯只是橋接（機構股東／合資公司），呈現為證據但不作為歸戶依據。 */
  bridge_only: boolean
}

export interface GroupResult {
  /** 公司 → 集團編號 */
  groups: Record<string, number>
  /** 集團編號（字串鍵）→ 曝險合計 */
  exposures: Record<string, number>
  /** 依共用自然人數由高到低排序，可能已截斷；見 hidden_links_total／truncated */
  hidden_links: HiddenLink[]
  /** 截斷前，關係圖上實際找到的隱性關聯總筆數 */
  hidden_links_total: number
  /** 超過上限而截斷；前端必須告知使用者畫面上並非全部隱性關聯 */
  truncated: boolean
  /** 有曝險但不在名冊中的公司；後端刻意列名而非靜默丟棄 */
  unattributed: string[]
}

/** GET /gcis/group 的回應：用真實統一編號從公開登記資料現場展開的歸戶結果。 */
export interface GcisGroupResult {
  company_id: string
  company: string
  group_members: string[]
  group_size: number
  /** 可作為歸戶依據的 A 層（法人董事）關係；parent 是所代表法人（母公司）。 */
  evidence: {
    company: string
    company_id: string | null
    parent: string
    parent_id: string | null
    role: string
  }[]
  /** B 層候選（自然人同名），僅供覆核，不參與合併。 */
  candidates: { company: string; person: string }[]
  elapsed_seconds: number
  neighborhood_companies: number
  neighborhood_truncated: boolean
  neighborhood_frontier_remaining: number
  /** 證據強度與適用範圍的說明，由後端提供，畫面必須原樣呈現。 */
  scope: string
  source: string
}
