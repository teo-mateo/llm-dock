import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import PiNotice from './PiNotice'

afterEach(cleanup)

describe('PiNotice', () => {
  it('renders a model change as labelled values', () => {
    render(<PiNotice change={{ label: 'Model', from: 'mistral/old', to: 'llm-dock/new' }} />)
    expect(screen.getByText('Model')).toBeInTheDocument()
    expect(screen.getByText('mistral/old')).toBeInTheDocument()
    expect(screen.getByText('llm-dock/new')).toBeInTheDocument()
  })

  it('renders a thinking change as labelled values', () => {
    render(<PiNotice change={{ label: 'Thinking', from: 'max', to: 'xhigh' }} />)
    expect(screen.getByText('Thinking')).toBeInTheDocument()
    expect(screen.getByText('max')).toBeInTheDocument()
    expect(screen.getByText('xhigh')).toBeInTheDocument()
  })

  it('renders other notices as a simple pill', () => {
    render(<PiNotice text="Context compacted (12k tokens)" />)
    expect(screen.getByText('Context compacted (12k tokens)')).toBeInTheDocument()
  })

  it('renders nothing without a change or a text', () => {
    const { container } = render(<PiNotice />)
    expect(container).toBeEmptyDOMElement()
  })
})
