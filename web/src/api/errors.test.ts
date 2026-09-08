import { describe, expect, it } from 'vitest'
import { describeError } from './errors'

describe('describeError', () => {
  it('把逾時與閘道錯誤說成鏈上查詢問題', () => {
    expect(describeError(502)).toContain('鏈上查詢')
  })

  it('查無資料時給明確訊息', () => {
    expect(describeError(404, '地址 TXxx 查無 USDT 轉帳')).toBe('地址 TXxx 查無 USDT 轉帳')
  })

  it('沒有 detail 的 404 也要有可讀訊息', () => {
    expect(describeError(404)).toContain('查無')
  })

  it('優先採用後端提供的 detail', () => {
    expect(describeError(400, 'tron 模式需提供 address')).toBe('tron 模式需提供 address')
  })

  it('401 提示金鑰問題', () => {
    expect(describeError(401)).toContain('金鑰')
  })

  it('0 代表連線失敗', () => {
    expect(describeError(0)).toContain('無法連線')
  })

  it('未知狀態碼仍回傳非空字串', () => {
    expect(describeError(418).length).toBeGreaterThan(0)
  })
})
