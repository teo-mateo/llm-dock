import { describe, it, expect } from 'vitest'
import { parseModelCommand, resolveModelRef, formatModelList } from './modelSlashCommand'
import { isChatService } from '../hooks/useRunningServices'

const ENGINES = []

function unfilteredServices() {
  return [
    { name: 'vllm-qwen', template_type: 'vllm', status: 'running', kind: 'chat' },
    { name: 'llamacpp-27b', template_type: 'llamacpp', status: 'exited', kind: 'chat' },
    { name: 'vllm-nomic-embed', template_type: 'vllm', status: 'running', kind: 'embedding' },
  ]
}

// Mirrors how ChatArea builds the models argument: the SSE list filtered to
// chat-capable services (all statuses), plus the curated and provider lists.
function models(overrides = {}) {
  return {
    services: unfilteredServices().filter(s => isChatService(s, ENGINES)),
    openRouterModels: [
      { id: 'anthropic/claude-sonnet-5', label: 'Claude Sonnet 5' },
    ],
    providerGroups: [
      { id: 'mistral', name: 'Mistral', models: [{ id: 'mistral-large-latest', label: 'Mistral Large' }] },
    ],
    ...overrides,
  }
}

describe('parseModelCommand', () => {
  it('parses bare /model', () => {
    expect(parseModelCommand('/model')).toEqual({ arg: null })
    expect(parseModelCommand('  /model  ')).toEqual({ arg: null })
  })

  it('parses /model with a ref, collapsing surrounding whitespace', () => {
    expect(parseModelCommand('/model vllm-qwen')).toEqual({ arg: 'vllm-qwen' })
    expect(parseModelCommand('/model   foo ')).toEqual({ arg: 'foo' })
    expect(parseModelCommand('/model\tfoo')).toEqual({ arg: 'foo' })
  })

  it('keeps a multi-word ref intact (resolution will reject it)', () => {
    expect(parseModelCommand('/model foo bar')).toEqual({ arg: 'foo bar' })
  })

  it('rejects /modelx and other commands that merely start with /model', () => {
    expect(parseModelCommand('/modelx')).toBeNull()
    expect(parseModelCommand('/models x')).toBeNull()
  })

  it('rejects multi-line input', () => {
    expect(parseModelCommand('/model a\nb')).toBeNull()
    expect(parseModelCommand('/model\n')).toBeNull()
  })

  it('rejects /model that is not at the start of the message', () => {
    expect(parseModelCommand('hello /model x')).toBeNull()
  })

  it('rejects non-string and empty input', () => {
    expect(parseModelCommand(null)).toBeNull()
    expect(parseModelCommand(42)).toBeNull()
    expect(parseModelCommand('')).toBeNull()
    expect(parseModelCommand('   ')).toBeNull()
  })
})

describe('resolveModelRef', () => {
  it('resolves exact local service names, running or stopped', () => {
    expect(resolveModelRef('vllm-qwen', models())).toEqual({ service: 'vllm-qwen' })
    expect(resolveModelRef('llamacpp-27b', models())).toEqual({ service: 'llamacpp-27b' })
  })

  it('does not resolve a service ChatArea filtered out (embedding)', () => {
    expect(resolveModelRef('vllm-nomic-embed', models())).toBeNull()
  })

  it('resolves an offered exact openrouter: string', () => {
    expect(resolveModelRef('openrouter:anthropic/claude-sonnet-5', models()))
      .toEqual({ service: 'openrouter:anthropic/claude-sonnet-5' })
  })

  it('rejects an unoffered exact openrouter: string, unless it is the current model', () => {
    const stale = models({ openRouterModels: [] })
    expect(resolveModelRef('openrouter:old/model-x', stale)).toBeNull()
    expect(resolveModelRef('openrouter:old/model-x', {
      ...stale, currentService: 'openrouter:old/model-x',
    })).toEqual({ service: 'openrouter:old/model-x' })
    expect(resolveModelRef('openrouter:', stale)).toBeNull()
  })

  it('resolves curated OpenRouter models by id or label', () => {
    expect(resolveModelRef('anthropic/claude-sonnet-5', models()))
      .toEqual({ service: 'openrouter:anthropic/claude-sonnet-5' })
    expect(resolveModelRef('Claude Sonnet 5', models()))
      .toEqual({ service: 'openrouter:anthropic/claude-sonnet-5' })
  })

  it('matches labels case-insensitively, ids exactly', () => {
    expect(resolveModelRef('claude sonnet 5', models()))
      .toEqual({ service: 'openrouter:anthropic/claude-sonnet-5' })
    expect(resolveModelRef('MISTRAL-LARGE-LATEST', models())).toBeNull()
  })

  it('resolves provider models by exact service string, id, or label', () => {
    expect(resolveModelRef('mistral:mistral-large-latest', models()))
      .toEqual({ service: 'mistral:mistral-large-latest' })
    expect(resolveModelRef('mistral-large-latest', models()))
      .toEqual({ service: 'mistral:mistral-large-latest' })
    expect(resolveModelRef('Mistral Large', models()))
      .toEqual({ service: 'mistral:mistral-large-latest' })
  })

  it('rejects an unoffered model of a configured provider, unless it is the current model', () => {
    expect(resolveModelRef('mistral:gone-model', models())).toBeNull()
    expect(resolveModelRef('mistral:gone-model', {
      ...models(), currentService: 'mistral:gone-model',
    })).toEqual({ service: 'mistral:gone-model' })
    expect(resolveModelRef('noprovider:model', models())).toBeNull()
  })

  it('flags labels that match several models as ambiguous', () => {
    const m = models({
      providerGroups: [
        { id: 'mistral', name: 'Mistral', models: [{ id: 'm1', label: 'Claude Sonnet 5' }] },
      ],
    })
    expect(resolveModelRef('Claude Sonnet 5', m)).toEqual({
      ambiguous: ['openrouter:anthropic/claude-sonnet-5', 'mistral:m1'],
    })
  })

  it('rejects unknown refs and empty input', () => {
    expect(resolveModelRef('nope', models())).toBeNull()
    expect(resolveModelRef('foo bar', models())).toBeNull()
    expect(resolveModelRef('', models())).toBeNull()
    expect(resolveModelRef(null, models())).toBeNull()
    expect(resolveModelRef('vllm-qwen', {})).toBeNull()
  })
})

describe('formatModelList', () => {
  it('lists local (with status), then OpenRouter, then providers', () => {
    expect(formatModelList(models())).toEqual([
      'Local models:',
      '  vllm-qwen (running)',
      '  llamacpp-27b (stopped)',
      'OpenRouter:',
      '  openrouter:anthropic/claude-sonnet-5',
      'Mistral:',
      '  mistral:mistral-large-latest',
    ])
  })

  it('skips provider groups without models', () => {
    const lines = formatModelList(models({
      providerGroups: [
        { id: 'empty', name: 'Empty', models: [] },
        { id: 'mistral', name: 'Mistral', models: [{ id: 'm1' }] },
      ],
    }))
    expect(lines).not.toContain('Empty:')
    expect(lines).toContain('  mistral:m1')
  })

  it('says so when nothing is offered', () => {
    expect(formatModelList({})).toEqual(['No models available.'])
  })
})
