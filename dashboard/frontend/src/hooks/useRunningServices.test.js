import { describe, it, expect } from 'vitest'
import { isChatService } from './useRunningServices'
import { SAMPLE_ENGINES } from '../test/engineCatalogue'

describe('isChatService', () => {
  it('accepts any service that carries a template_type, even off its name prefix', () => {
    for (const { type } of SAMPLE_ENGINES) {
      expect(isChatService({ name: 'renamed-service', template_type: type, kind: 'chat' })).toBe(true)
    }
    expect(isChatService({ name: 'renamed-service', template_type: 'an_engine_added_later' })).toBe(true)
  })

  it('falls back to the catalogue prefix when template_type is absent', () => {
    expect(isChatService({ name: 'maya-glm53-flash-maya-l' }, SAMPLE_ENGINES)).toBe(true)
    expect(isChatService({ name: 'exl3-model' }, SAMPLE_ENGINES)).toBe(true)
    expect(isChatService({ name: 'PAIR_x' })).toBe(true)
  })

  it('does not guess from a prefix the catalogue has not supplied', () => {
    expect(isChatService({ name: 'maya-glm53-flash-maya-l' })).toBe(false)
    expect(isChatService({ name: 'newengine-x' }, SAMPLE_ENGINES)).toBe(false)
  })

  it('rejects embedders and unknown containers', () => {
    expect(isChatService({ name: 'vllm-bge-m3', template_type: 'vllm', kind: 'embedding' }, SAMPLE_ENGINES)).toBe(false)
    expect(isChatService({ name: 'open-webui', kind: 'chat' }, SAMPLE_ENGINES)).toBe(false)
  })
})
