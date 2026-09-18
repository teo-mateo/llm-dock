import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import TokenSparkline from './TokenSparkline'

function points(values, dt = 0.2) {
  return values.map(generationTokensRate => ({ promptTokensRate: 0, generationTokensRate, dt }))
}

describe('TokenSparkline', () => {
  it('renders canvas element with class', () => {
    const { container } = render(<TokenSparkline history={[
      { promptTokensRate: 10, generationTokensRate: 20 },
      { promptTokensRate: 15, generationTokensRate: 25 }
    ]} />)
    const canvas = container.querySelector('canvas')
    expect(canvas).toBeTruthy()
  })

  it('label renders with rate values', () => {
    const { container } = render(<TokenSparkline history={[
      { promptTokensRate: 12.5, generationTokensRate: 33.3 }
    ]} />)
    // Label and value are separate spans (spaced via CSS flex gap), so
    // textContent has no literal space between them — match optionally.
    expect(container.textContent).toMatch(/Prompt:\s*12\.5 t\/s/)
    expect(container.textContent).toMatch(/Gen:\s*33\.3 t\/s/)
  })

  it('empty history still renders canvas (placeholder drawn on canvas)', () => {
    const { container } = render(<TokenSparkline history={[]} />)
    expect(container.querySelector('canvas')).toBeTruthy()
  })

  it('renders prompt and gen legend labels', () => {
    const { container } = render(<TokenSparkline history={[
      { promptTokensRate: 0, generationTokensRate: 0 },
      { promptTokensRate: 0, generationTokensRate: 0 }
    ]} />)
    expect(container.textContent).toContain('Prompt')
    expect(container.textContent).toContain('Gen')
  })

  it('reads the rate off the smoothed series and names the window', () => {
    const { container } = render(<TokenSparkline history={points([140, 20, 140, 20, 140])} />)
    expect(container.textContent).toMatch(/Gen:\s*92\.0 t\/s/)
    expect(container.textContent).toContain('1s avg')
  })

  it('shows no peak badge until a second point arrives', () => {
    const { container } = render(<TokenSparkline history={points([80])} />)
    expect(container.textContent).not.toContain('peak')
  })

  it('badges the peak rate, not the padded axis scale', () => {
    const { container } = render(<TokenSparkline history={points([100, 100, 100, 100, 100, 20, 100])} />)
    expect(container.textContent).toContain('peak 100.0 t/s')
    expect(container.textContent).not.toContain('150.0')
    expect(container.textContent).toMatch(/Gen:\s*84\.0 t\/s/)
  })

  it('paints a running sprite while tokens flow', () => {
    const { container } = render(<TokenSparkline history={points([80, 82, 79, 81, 80])} />)
    const canvas = container.querySelector('canvas')
    const drawn = canvas.getContext('2d').__getDrawCalls()
    expect(drawn.filter(call => call.type === 'fillRect').length).toBeGreaterThan(0)
  })

  it('paints a standing sprite when nothing is generating', () => {
    const { container } = render(<TokenSparkline history={points([0, 0, 0, 0, 0])} />)
    const canvas = container.querySelector('canvas')
    expect(canvas.getContext('2d').__getDrawCalls().filter(c => c.type === 'fillRect').length).toBeGreaterThan(0)
  })
})
