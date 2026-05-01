import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import TokenSparkline from './TokenSparkline'

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
    expect(container.textContent).toMatch(/Prompt: 12\.5 t\/s/)
    expect(container.textContent).toMatch(/Gen: 33\.3 t\/s/)
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
})
