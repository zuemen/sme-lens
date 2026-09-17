import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { checkHealth } from '../api/client'
import { Panel } from '../components/Panel'

/**
 * 首屏的實證數字。全部出自 scripts/ 底下的開源腳本對全量公開資料重跑，
 * 重跑方式與來源見 docs/GCIS_FINDINGS.md——這一排數字是整個網站的可信度基礎，
 * 任何一個都不得憑印象填寫。
 */
const EVIDENCE = [
  { value: '102萬', unit: '家', label: '全國公司登記資料', note: '經濟部商業發展署' },
  { value: '67,838', unit: '條', label: '法人控股關係', note: '零姓名歧義' },
  { value: '75.8%', unit: '', label: '名稱看不出關聯', note: '只有關係圖找得到' },
  { value: '<1', unit: '秒', label: '單一統編查詢', note: '二階鄰域展開' },
]

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
    body: '上下游一家出事，圖上的鄰居就該亮燈——以既有逾期戶為種子在關係圖上擴散風險，產出帶證據路徑的關注名單。',
    to: '/earlywarn',
    cta: '看貸後早期預警 Demo',
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
      {/* 首屏：評審多半是掃 QR 進來的，第一眼要同時看到「主張」與「證據」。
          hero-grid 是純 CSS 畫的淡格線，呼應本作品的主題（關係圖），不載入圖片。 */}
      <section className="hero-grid relative -mx-4 px-4 py-10 sm:-mx-6 sm:px-6">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          <ServiceStatus />
          <span aria-hidden="true" className="text-xs text-muted">
            ·
          </span>
          <span className="text-xs text-muted">2026 臺灣中小企業銀行校園金融科技創意挑戰賽</span>
          <span className="rounded border border-line px-2 py-0.5 text-xs text-muted">
            企業金融服務創新
          </span>
          <span className="rounded border border-line px-2 py-0.5 text-xs text-muted">
            科技防詐
          </span>
        </div>

        <h1 className="mt-5 text-4xl font-semibold leading-tight sm:text-5xl">
          企鏡 <span className="text-muted">SME Lens</span>
        </h1>
        <p className="mt-4 max-w-3xl text-xl leading-snug sm:text-2xl">
          銀行不缺分數，缺的是<span className="claim-underline">看得見的理由</span>
          ——把已經在行內的資料，變成集團歸戶的證據。
        </p>
        <p className="mt-5 max-w-2xl leading-relaxed text-muted">
          以企業關係圖與交易網絡結構作為信用證據，讓授信人員在核貸前看見財報看不到的
          集團曝險、在核貸中看見沒有漂亮財報也值得信任的好公司、在核貸後及早看見上下游風險的擴散。
        </p>

        <div className="mt-7 flex flex-wrap gap-3">
          <Link to="/group" className="rounded bg-ink px-5 py-2 font-semibold text-base">
            查任一真實統一編號
          </Link>
          <Link to="/credit" className="rounded border border-line-strong px-5 py-2">
            看授信意見書 Demo
          </Link>
        </div>

        {/* 實證帶：不是構想，是已經跑完的結果。數字用等寬等距，與全站數值排版一致。 */}
        <dl className="mt-10 grid grid-cols-2 gap-x-6 gap-y-6 border-t border-line pt-7 lg:grid-cols-4">
          {EVIDENCE.map((item) => (
            <div key={item.label}>
              <dd className="numeral text-3xl font-semibold leading-none sm:text-4xl">
                {item.value}
                {item.unit && (
                  <span className="ml-1 text-base font-normal text-muted">{item.unit}</span>
                )}
              </dd>
              <dt className="mt-2 text-sm">{item.label}</dt>
              <p className="mt-0.5 text-xs text-muted">{item.note}</p>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs leading-relaxed text-muted">
          每一個數字皆由開源腳本對全量公開資料重跑產生，非估計值；重跑方式見原始碼的{' '}
          <span className="tabular">docs/GCIS_FINDINGS.md</span>。
        </p>
      </section>

      {/* 鉤子：為什麼銀行需要這個。主管機關自己的裁罰理由書比任何行銷文案有力。 */}
      <section>
        <h2 className="mb-4 text-sm text-muted">為什麼銀行需要這個</h2>
        <div className="grid gap-5 lg:grid-cols-5">
          <blockquote
            className="rounded-lg border border-line bg-panel p-6 lg:col-span-3"
            style={{ borderLeftWidth: '4px', borderLeftColor: 'var(--color-risk-med)' }}
          >
            <p className="leading-relaxed">
              「貴行於 105 年 8 月 3 日自行發現鼎興貿易及英毅有限公司為利害關係人，
              <b style={{ color: 'var(--color-risk-med)' }}>
                顯示即使前董事未申報，貴行仍可透過相關資訊檢核發現
              </b>
              。貴行未……妥善建立利害關係人資料建檔之確認機制。」
            </p>
            <footer className="mt-4 text-xs leading-relaxed text-muted">
              金管會裁罰永豐商業銀行鼎興集團授信案，罰鍰新臺幣 1,000 萬元（金管銀控字第
              10560005322 號，105/11/08）；同案華南銀行罰 800 萬元。
            </footer>
          </blockquote>

          <div className="space-y-5 lg:col-span-2">
            <Panel title="失職不在沒有資料">
              <p className="text-sm leading-relaxed text-muted">
                主管機關自己認定：資料在銀行手上，缺的是
                <b className="text-ink">跨戶比對的機制</b>。
                《銀行公會會員徵信準則》早已要求企業授信徵提董監事名冊——資料一直在流程裡。
              </p>
            </Panel>
            <Panel title="觸及的是法定上限">
              <p className="text-sm leading-relaxed text-muted">
                《銀行法》§33-3：對同一關係企業授信總餘額不得逾銀行淨值
                <b className="numeral text-ink"> 40%</b>
                （同一法人 15%、同一自然人 3%）。歸戶漏掉一家，曝險就少算一筆。
              </p>
            </Panel>
          </div>
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
        <p className="mx-auto mt-3 max-w-2xl text-sm leading-relaxed text-muted">
          因此本作品同時落在主辦的<b>「企業金融服務創新」</b>與<b>「科技防詐」</b>兩個情境。
          AI 科技應用的主體是<b>圖結構分析</b>、<b>半監督式標籤擴散</b>（貸後預警）與
          <b>圖神經網路</b>——線上服務一律以可覆核的規則與圖結構分析運作，
          GNN 的評估結果另頁公開，尚未上線。
        </p>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link
            to="/screening"
            className="inline-block rounded border border-line-strong px-5 py-2 text-sm font-semibold"
          >
            看出金審查 Demo
          </Link>
          <Link to="/research" className="inline-block rounded border border-line px-5 py-2 text-sm">
            看 AI 模型評估
          </Link>
        </div>
      </section>
    </div>
  )
}
