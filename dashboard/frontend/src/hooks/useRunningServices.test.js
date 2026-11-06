import { describe, it, expect } from 'vitest'
import { isChatService } from './useRunningServices'

describe('isChatService', () => {
  it('accepts every engine by template_type, even off its name prefix', () => {
    for (const t of ['llamacpp', 'ik_llamacpp', 'vllm', 'ds4', 'tabbyapi', 'ninfer', 'sglang', 'maya']) {
      expect(isChatService({ name: 'renamed-service', template_type: t, kind: 'chat' })).toBe(true)
    }
  })

  it('falls back to the name prefix when template_type is absent', () => {
    expect(isChatService({ name: 'maya-glm53-flash-maya-l' })).toBe(true)
    expect(isChatService({ name: 'PAIR_x' })).toBe(true)
  })

  it('rejects embedders and unknown containers', () => {
    expect(isChatService({ name: 'vllm-bge-m3', template_type: 'vllm', kind: 'embedding' })).toBe(false)
    expect(isChatService({ name: 'open-webui', kind: 'chat' })).toBe(false)
  })
})
