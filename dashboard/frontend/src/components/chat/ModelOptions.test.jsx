import { describe, it, expect, afterEach } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import ModelOptions from './ModelOptions'

afterEach(cleanup)

const GROUPS = [{ id: 'mistral', name: 'Mistral', models: [{ id: 'mistral-small-latest', label: 'mistral-small-latest' }] }]

function options(selected) {
  const { container } = render(
    <select value={selected} onChange={() => {}}>
      <ModelOptions services={[{ name: 'llamacpp-a' }]} openRouterModels={[]} providerGroups={GROUPS} selected={selected} />
    </select>,
  )
  return [...container.querySelectorAll('option')].map(o => [o.value, o.textContent, o.parentElement.label || null])
}

describe('ModelOptions provider groups', () => {
  it('renders one optgroup per provider with <provider>:<model> values', () => {
    expect(options('llamacpp-a')).toContainEqual(['mistral:mistral-small-latest', 'mistral-small-latest', 'Mistral'])
  })

  it('keeps a no-longer-offered provider model visible', () => {
    expect(options('mistral:gone-model')).toContainEqual(['mistral:gone-model', 'gone-model · mistral (not available)', null])
  })
})
