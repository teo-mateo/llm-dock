import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import RequestStrip from './RequestStrip'

describe('RequestStrip', () => {
  it('renders running count', () => {
    const { container } = render(<RequestStrip running={3} waiting={1} preemptRate={0.2} />)
    expect(container.textContent).toContain('Running:')
    expect(container.textContent).toMatch(/3/)
  })

  it('renders waiting count', () => {
    const { container } = render(<RequestStrip running={3} waiting={5} preemptRate={0} />)
    expect(container.textContent).toContain('Waiting:')
    expect(container.textContent).toMatch(/5/)
  })

  it('renders preemption rate with /s', () => {
    const { container } = render(<RequestStrip running={0} waiting={0} preemptRate={1.5} />)
    expect(container.textContent).toContain('Preempt:')
    expect(container.textContent).toMatch(/1\.5/)
    expect(container.textContent).toContain('/s')
  })

  it('shows dash when data missing', () => {
    const { container } = render(<RequestStrip running={undefined} waiting={undefined} preemptRate={undefined} />)
    expect(container.textContent).toContain('—')
  })

  it('shows dash for null values', () => {
    const { container } = render(<RequestStrip running={null} waiting={null} preemptRate={null} />)
    expect(container.textContent).toContain('—')
  })
})
