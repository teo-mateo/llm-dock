import { describe, it, expect } from 'vitest'
import {
  sanitizeServiceName,
  generateServiceName,
  aliasFromModelName,
} from './serviceNaming'

describe('sanitizeServiceName', () => {
  it('lowercases, swaps underscores/spaces for hyphens and strips other characters', () => {
    expect(sanitizeServiceName('Foo Bar_Baz!')).toBe('foo-bar-baz')
  })

  it('collapses consecutive hyphens and trims leading/trailing ones', () => {
    expect(sanitizeServiceName('a---b')).toBe('a-b')
    expect(sanitizeServiceName('-a-')).toBe('a')
  })

  it('caps at 63 characters, never ending on a hyphen', () => {
    const long = sanitizeServiceName('a'.repeat(70))
    expect(long.length).toBe(63)
    const hyphenEdge = sanitizeServiceName(`${'a'.repeat(62)}-bbbb`)
    expect(hyphenEdge).toBe('a'.repeat(62))
  })
})

describe('generateServiceName', () => {
  it('uses the template type as prefix', () => {
    expect(generateServiceName('llamacpp', 'qwen3-8b')).toBe('llamacpp-qwen3-8b')
    expect(generateServiceName('vllm', 'qwen')).toBe('vllm-qwen')
  })

  it('applies the prefix overrides', () => {
    expect(generateServiceName('ik_llamacpp', 'qwen3-8b')).toBe('ik-qwen3-8b')
    expect(generateServiceName('tabbyapi', 'qwen3-8b')).toBe('exl3-qwen3-8b')
  })

  it('sanitizes the composed name', () => {
    expect(generateServiceName('ds4', 'My Model!!')).toBe('ds4-my-model')
  })
})

describe('aliasFromModelName', () => {
  it('takes the last path segment and strips the quantization bracket', () => {
    expect(aliasFromModelName('Qwen/Qwen3-8B [Q4_K_M]')).toBe('qwen3-8b')
  })

  it('strips common repo suffixes', () => {
    expect(aliasFromModelName('unsloth/Qwen3-8B-GGUF')).toBe('qwen3-8b')
    expect(aliasFromModelName('Qwen/Qwen3-8B-Instruct')).toBe('qwen3-8b')
  })

  it('sanitizes the result', () => {
    expect(aliasFromModelName('org/My Model--XL!')).toBe('my-model-xl')
  })
})
