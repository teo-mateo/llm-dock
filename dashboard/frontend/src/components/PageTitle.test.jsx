import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import PageTitle from './PageTitle'

afterEach(cleanup)

describe('PageTitle', () => {
  it('provides the shared page heading hierarchy', () => {
    render(<PageTitle>Settings</PageTitle>)
    expect(screen.getByRole('heading', { level: 1, name: 'Settings' })).toHaveClass('text-xl', 'font-semibold', 'leading-7', 'tracking-tight')
  })

  it('keeps section semantics and layout constraints without a different type style', () => {
    render(<PageTitle as="h2" className="truncate">Sessions</PageTitle>)
    expect(screen.getByRole('heading', { level: 2, name: 'Sessions' })).toHaveClass('truncate', 'text-xl', 'font-semibold')
  })
})
