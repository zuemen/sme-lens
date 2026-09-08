import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkHealth } from '../api/client'
import { Panel } from '../components/Panel'

const METRICS = [
  { value: '0.806', label: '最佳模型 F1', note: 'Random Forest，illicit 類別' },
  { value: '0.795', label: 'PR-AUC', note: '遵守官方時間切分，無資料洩漏' },
  { value: '203k', label: 'Elliptic 節點數', note: '公開比特幣交易圖基準' },
  { value: '4', label: '洗錢圖樣規則', note: '扇入／分散／集散／剝洋蔥' },
]

const FLOW = [
  { stage: '資料層', detail: 'Elliptic 203k 節點 BTC 交易圖／TronGrid TRC-20 USDT 2-hop 圖' },
  { stage: '分析層', detail: 'SNA 指標、Louvain 社群偵測、詐騙圖樣規則' },
  { stage: '模型層', detail: 'GCN／GraphSAGE（PyTorch Geometric）、Random Forest 基線' },
  { stage: '解釋層', detail: '風險證據產生器、出金審查引擎、STR 草稿' },
]

const PILLARS = [
  {
    title: '結構證據，不是黑箱分數',
    body: '每個風險判定都附中心性百分位、社群風險佔比與命中的資金圖樣，法遵人員看得懂、稽核追得到。',
  },
  {
    title: '不依賴黑名單',
    body: '從未被通報的地址，仍可經由上游關聯追溯攔下——集資扇入、快速分散、剝洋蔥鏈由圖樣庫主動掃出。',
  },
  {
    title: '人在迴路中',
    body: '高風險的處置是「暫緩並啟動人工審查」而非直接拒絕，並自動產出 STR 草稿作為人工審查的起點。',
  },
]

function ServiceStatus() {
  const [online, setOnline] = useState<boolean | null>(null)
  useEffect(() => {
    void checkHealth().then(setOnline)
  }, [])

  const color =
    online === null
      ? 'var(--color-muted)'
      : online
        ? 'var(--color-risk-low)'
        : 'var(--color-risk-med)'
  const text = online === null ? '檢查分析服務…' : online ? '分析服務運作中' : '分析服務未回應'

  return (
    <span className="inline-flex items-center gap-2 text-sm" style={{ color }}>
      {/* 狀態不只靠顏色傳達，同時有文字說明 */}
      <span
        aria-hidden="true"
        className="inline-block h-2 w-2 rounded-full"
        style={{ backgroundColor: color }}
      />
      {text}
    </span>
  )
}

export default function Landing() {
  return (
    <div className="space-y-12">
      <section className="py-8">
        <ServiceStatus />
        <h1 className="mt-4 text-4xl font-semibold leading-tight">
          鏈鏡 <span className="text-muted">ChainLens</span>
        </h1>
        <p className="mt-3 text-xl text-muted">基於社會網路分析之虛擬資產詐騙金流偵測平台</p>
        <p className="mt-5 max-w-2xl leading-relaxed text-muted">
          以社會網路分析（SNA）與圖神經網路（GNN）偵測虛擬資產詐騙金流，
          服務對象為 VASP 業者的法遵篩查。核心賣點是可解釋性。
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/screening" className="rounded bg-ink px-5 py-2 font-semibold text-base">
            看 50 萬 USDT 攔阻 Demo
          </Link>
          <Link to="/workbench" className="rounded border border-line px-5 py-2">
            自己試查一個地址
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-sm text-muted">關鍵指標</h2>
        <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
          {METRICS.map((metric) => (
            <Panel key={metric.label}>
              <div className="tabular text-3xl font-semibold">{metric.value}</div>
              <div className="mt-1 text-sm">{metric.label}</div>
              <div className="mt-1 text-xs text-muted">{metric.note}</div>
            </Panel>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-sm text-muted">運作方式</h2>
        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="四層架構">
            <ol className="space-y-3">
              {FLOW.map((step, index) => (
                <li key={step.stage} className="flex gap-4">
                  <span className="tabular w-6 shrink-0 text-muted">{index + 1}</span>
                  <div>
                    <div className="font-semibold">{step.stage}</div>
                    <div className="text-sm text-muted">{step.detail}</div>
                  </div>
                </li>
              ))}
            </ol>
          </Panel>
          <div className="space-y-5">
            {PILLARS.map((pillar) => (
              <Panel key={pillar.title} title={pillar.title}>
                <p className="text-sm leading-relaxed text-muted">{pillar.body}</p>
              </Panel>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-8 text-center">
        <h2 className="text-xl font-semibold">看它攔下一筆黑名單攔不住的出金</h2>
        <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted">
          目標地址從未被通報、自身結構分數只有 0.33。真正攔下它的是上游二階的資金關聯。
        </p>
        <Link
          to="/screening"
          className="mt-6 inline-block rounded bg-ink px-6 py-2.5 font-semibold text-base"
        >
          執行出金審查 Demo
        </Link>
      </section>
    </div>
  )
}
