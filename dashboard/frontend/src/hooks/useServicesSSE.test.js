import { describe, it, expect } from 'vitest'
import { applyDeltaToState } from './useServicesSSE'

const state = (...services) => ({
  services,
  total: services.length,
  running: services.filter(s => s.status === 'running').length,
  stopped: services.filter(s => s.status === 'exited' || s.status === 'not-created').length,
  deleted: [],
})

const delta = (service_name, over = {}) => ({
  service_name,
  status: null,
  action: 'status-changed',
  container_id: '',
  ...over,
})

const deleted = delta('vllm-gone', { action: 'service-deleted', status: 'deleted' })

describe('useServicesSSE delete delta', () => {
  it('drops the row and recounts the totals', () => {
    const next = applyDeltaToState(
      state({ name: 'vllm-gone', status: 'running' }, { name: 'llamacpp-keep', status: 'exited' }),
      deleted,
    )
    expect(next.services.map(s => s.name)).toEqual(['llamacpp-keep'])
    expect(next.total).toBe(1)
    expect(next.running).toBe(0)
    expect(next.stopped).toBe(1)
  })

  it('keeps the row out when the engine reports teardown after the delete', () => {
    let next = applyDeltaToState(state({ name: 'vllm-gone', status: 'running' }), deleted)
    for (const late of ['stop', 'die', 'destroy', 'metadata-changed']) {
      next = applyDeltaToState(next, delta('vllm-gone', {
        action: late,
        status: late === 'destroy' ? 'removed' : 'exited',
      }))
      expect(next.services).toEqual([])
      expect(next.total).toBe(0)
    }
  })

  it('lets a service re-added under the same name back in', () => {
    const afterDelete = applyDeltaToState(state({ name: 'vllm-gone', status: 'running' }), deleted)
    const afterStart = applyDeltaToState(afterDelete, delta('vllm-gone', { action: 'start', status: 'running' }))
    expect(afterStart.services.map(s => ({ name: s.name, status: s.status })))
      .toEqual([{ name: 'vllm-gone', status: 'running' }])
    expect(afterStart.running).toBe(1)
  })

  it('still recounts a service that was already listed when it dies', () => {
    const next = applyDeltaToState(
      state({ name: 'llamacpp-a', status: 'running' }, { name: 'llamacpp-b', status: 'running' }),
      delta('llamacpp-a', { action: 'die', status: 'exited' }),
    )
    expect(next.services.find(s => s.name === 'llamacpp-a').status).toBe('exited')
    expect(next.running).toBe(1)
    expect(next.stopped).toBe(1)
  })
})
