import { describe, it, expect } from 'vitest'
import {
  OPENROUTER_PREFIX,
  isOpenRouterService,
  openRouterModelId,
  serviceNameForModel,
  formatModelLabel,
} from './openrouter'

describe('openrouter service-string helpers', () => {
  it('detects the prefix', () => {
    expect(isOpenRouterService('openrouter:anthropic/claude-sonnet-5')).toBe(true)
    expect(isOpenRouterService('vllm-qwen')).toBe(false)
    expect(isOpenRouterService(null)).toBe(false)
    expect(isOpenRouterService(undefined)).toBe(false)
    expect(isOpenRouterService('')).toBe(false)
  })

  it('round-trips model id <-> service name', () => {
    const name = serviceNameForModel('vendor/model-a')
    expect(name).toBe(OPENROUTER_PREFIX + 'vendor/model-a')
    expect(openRouterModelId(name)).toBe('vendor/model-a')
  })

  it('formatModelLabel passes local names through unchanged', () => {
    expect(formatModelLabel('vllm-qwen')).toBe('vllm-qwen')
    expect(formatModelLabel(null)).toBe(null)
    expect(formatModelLabel(undefined)).toBe(undefined)
  })

  it('formatModelLabel uses the curated label when known', () => {
    const models = [{ id: 'vendor/model-a', label: 'Model A' }]
    expect(formatModelLabel('openrouter:vendor/model-a', models)).toBe('Model A · OpenRouter')
  })

  it('formatModelLabel falls back to the bare model id', () => {
    expect(formatModelLabel('openrouter:vendor/model-x')).toBe('vendor/model-x · OpenRouter')
    expect(formatModelLabel('openrouter:vendor/model-x', [{ id: 'other', label: 'O' }]))
      .toBe('vendor/model-x · OpenRouter')
  })
})
