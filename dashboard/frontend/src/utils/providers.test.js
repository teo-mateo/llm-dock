import { describe, it, expect } from 'vitest'
import { isProviderService, parseProviderService, providerServiceName } from './providers'
import { formatModelLabel } from './openrouter'

describe('provider service strings', () => {
  it('parses <provider>:<model> and splits on the first colon only', () => {
    expect(parseProviderService('mistral:mistral-large-latest')).toEqual({ providerId: 'mistral', modelId: 'mistral-large-latest' })
    expect(parseProviderService('acme:org/m:tag')).toEqual({ providerId: 'acme', modelId: 'org/m:tag' })
    expect(providerServiceName('mistral', 'x')).toBe('mistral:x')
  })

  it('rejects local names, openrouter strings and malformed ids', () => {
    for (const s of ['llamacpp-gemma', 'openrouter:vendor/m', 'mistral:', 'Bad:x', null]) {
      expect(isProviderService(s)).toBe(false)
    }
  })

  it('labels provider models with their provider', () => {
    expect(formatModelLabel('mistral:mistral-small-latest')).toBe('mistral-small-latest · mistral')
  })
})
