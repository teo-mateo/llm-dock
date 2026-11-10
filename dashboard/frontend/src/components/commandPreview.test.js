import { describe, it, expect } from 'vitest'
import { renderCommandPreview } from './commandPreview'

const PARAMS = [{ flag: '--ctx', value: '4096' }, { flag: '--flash', value: '' }]

describe('renderCommandPreview', () => {
  it('keeps the bespoke shape of an engine that has one', () => {
    const preview = renderCommandPreview({ template_type: 'llamacpp', model_path: '/m/x.gguf' }, 'key', PARAMS)

    expect(preview).toContain('llama-server')
    expect(preview).toContain('-m /m/x.gguf')
    expect(preview).toContain('--api-key key')
    expect(preview).toContain('--ctx 4096')
  })

  it('renders vLLM from its model name', () => {
    const preview = renderCommandPreview({ template_type: 'vllm', model_name: 'org/model' }, '', PARAMS)

    expect(preview).toContain('vllm serve')
    expect(preview).toContain('org/model')
    expect(preview).toContain('--api-key ***')
  })

  it('gives an engine without a branch the generic model-path-plus-params preview, not another engine\'s command', () => {
    const preview = renderCommandPreview({ template_type: 'future_engine', model_path: '/m/x' }, 'key', PARAMS)

    expect(preview).toBe('/m/x \\\n  --ctx 4096 \\\n  --flash')
    expect(preview).not.toMatch(/vllm|llama-server|--api-key/)
  })

  it('uses the model name for an unknown repo-based engine and shows nothing invented without a model', () => {
    expect(renderCommandPreview({ template_type: 'future_engine', model_name: 'org/m' }, '', [])).toBe('org/m')
    expect(renderCommandPreview({ template_type: 'future_engine' }, '', [])).toBe('')
  })

  it('returns nothing without a config', () => {
    expect(renderCommandPreview(null, '', [])).toBe('')
  })
})
