import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import GaugesRow from './GaugesRow'

describe('GaugesRow', () => {
  it('displays correct percentage for KV cache', () => {
    const { container } = render(<GaugesRow kvCache={0.72} prefixHitRatio={0.8} specAcceptRatio={0.5} />)
    expect(container.textContent).toContain('72%')
  })

  it('shows green color below 60%', () => {
    const { container } = render(<GaugesRow kvCache={0.4} prefixHitRatio={0} specAcceptRatio={0} />)
    const svg = container.querySelectorAll('svg')[0]
    const indicator = svg.querySelectorAll('circle')[1]
    expect(indicator.getAttribute('stroke')).toBe('#22c55e')
  })

  it('shows yellow color at 70%', () => {
    const { container } = render(<GaugesRow kvCache={0.7} prefixHitRatio={0} specAcceptRatio={0} />)
    const svg = container.querySelectorAll('svg')[0]
    const indicator = svg.querySelectorAll('circle')[1]
    expect(indicator.getAttribute('stroke')).toBe('#eab308')
  })

  it('shows red color above 85%', () => {
    const { container } = render(<GaugesRow kvCache={0.9} prefixHitRatio={0} specAcceptRatio={0} />)
    const svg = container.querySelectorAll('svg')[0]
    const indicator = svg.querySelectorAll('circle')[1]
    expect(indicator.getAttribute('stroke')).toBe('#ef4444')
  })

  it('prefix hit ratio displays correctly', () => {
    const { container } = render(<GaugesRow kvCache={0} prefixHitRatio={0.8} specAcceptRatio={0} />)
    expect(container.textContent).toContain('80%')
  })

  it('spec accept ratio displays correctly', () => {
    const { container } = render(<GaugesRow kvCache={0} prefixHitRatio={0} specAcceptRatio={0.5} />)
    expect(container.textContent).toContain('50%')
  })

  it('missing data renders dash', () => {
    const { container } = render(<GaugesRow kvCache={undefined} prefixHitRatio={undefined} specAcceptRatio={undefined} />)
    expect(container.textContent).toContain('—')
  })
})
