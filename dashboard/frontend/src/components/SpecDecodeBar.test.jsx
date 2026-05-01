import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import SpecDecodeBar from './SpecDecodeBar'

describe('SpecDecodeBar', () => {
  it('renders bars when specPerPos data provided', () => {
    const { container } = render(<SpecDecodeBar specPerPos={{ position_0: 150, position_1: 120 }} />)
    expect(container.textContent).toContain('Pos 0')
    expect(container.textContent).toContain('Pos 1')
    expect(container.textContent).toContain('150')
    expect(container.textContent).toContain('120')
  })

  it('renders nothing when specPerPos is empty', () => {
    const { container } = render(<SpecDecodeBar specPerPos={{}} />)
    expect(container.querySelector('.space-y-2')).toBeFalsy()
  })

  it('renders nothing when specPerPos is null', () => {
    const { container } = render(<SpecDecodeBar specPerPos={null} />)
    expect(container.querySelector('.space-y-2')).toBeFalsy()
  })

  it('normalizes bar width to max value', () => {
    const { container } = render(<SpecDecodeBar specPerPos={{ position_0: 200, position_1: 100 }} />)
    const bars = container.querySelectorAll('.bg-amber-500')
    expect(bars.length).toBe(2)
    expect(bars[0].style.width).toBe('100%')
    expect(bars[1].style.width).toBe('50%')
  })
})
