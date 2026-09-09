import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkHealth } from '../api/client'
import { Panel } from '../components/Panel'

const PILLARS = [
  {
    stage: '貸前',
    title: '集團歸戶',
    body: '客戶申報的關係企業表漏掉共用董監事，集團曝險被拆散在看似無關的借款人身上——關係圖把它們併回同一個集團。',
    to: '/group',
    cta: '看集團歸戶 Demo',
  },
  {
    stage: '貸中',
    title: '無財報授信',
    body: '以交易網絡結構作為信用證據，讓沒有漂亮財報的好公司被看見，而不是只憑財報數字放行或拒絕。',
    to: '/credit',
    cta: '看授信意見書 Demo',
  },
  {
    stage: '貸後',
    title: '早期預警',
    body: '上下游一家出事，圖上的鄰居就該亮燈——用同一張關係圖持續監控授信戶的關聯風險，而不是等到逾期才發現。',
    to: '/credit',
    cta: '看授信意見書 Demo',
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
          企鏡 <span className="text-muted">SME Lens</span>
        </h1>
        <p className="mt-3 text-xl text-muted">銀行不缺分數，缺的是看得見的理由</p>
        <p className="mt-5 max-w-2xl leading-relaxed text-muted">
          以企業關係圖與交易網絡結構作為信用證據，讓授信人員在核貸前看見財報看不到的
          集團曝險、在核貸中看見沒有漂亮財報也值得信任的好公司、在核貸後及早看見上下游風險的擴散。
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/credit" className="rounded bg-ink px-5 py-2 font-semibold text-base">
            看授信意見書 Demo
          </Link>
          <Link to="/group" className="rounded border border-line px-5 py-2">
            看集團歸戶 Demo
          </Link>
        </div>
      </section>

      <section>
        <h2 className="mb-4 text-sm text-muted">三個核心應用</h2>
        <div className="grid gap-5 lg:grid-cols-3">
          {PILLARS.map((pillar) => (
            <Panel key={pillar.title} title={`${pillar.stage}．${pillar.title}`}>
              <p className="text-sm leading-relaxed text-muted">{pillar.body}</p>
              <Link to={pillar.to} className="mt-4 inline-block text-sm font-semibold text-ink">
                {pillar.cta} →
              </Link>
            </Panel>
          ))}
        </div>
      </section>

      <section className="rounded-lg border border-line bg-panel p-8">
        <h2 className="text-xl font-semibold">同一套圖引擎，也能看見詐騙金流</h2>
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          企金授信與虛擬資產防詐看的是同一種問題——資金與關係怎麼在網絡裡流動。
          這套企業關係圖引擎同時支援出金審查：偵測從未被通報、僅憑自身分數看不出異常的
          可疑地址，攔下黑名單攔不住的出金。
        </p>
        <Link
          to="/screening"
          className="mt-6 inline-block rounded border border-line px-5 py-2 text-sm font-semibold"
        >
          看出金審查 Demo
        </Link>
      </section>
    </div>
  )
}
