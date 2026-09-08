import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RiskBadge, riskColor } from './RiskBadge'

describe('riskColor', () => {
  it('三個風險等級各有不同顏色', () => {
    const colors = new Set([riskColor('high'), riskColor('medium'), riskColor('low')])
    expect(colors.size).toBe(3)
  })
})

describe('RiskBadge', () => {
  it('顯示兩位小數的分數與中文等級', () => {
    render(<RiskBadge score={0.7307} label="high" />)
    expect(screen.getByText('0.73')).toBeDefined()
    expect(screen.getByText('高風險')).toBeDefined()
  })

  it('低風險顯示對應中文', () => {
    render(<RiskBadge score={0.0962} label="low" />)
    expect(screen.getByText('0.10')).toBeDefined()
    expect(screen.getByText('低風險')).toBeDefined()
  })
})
