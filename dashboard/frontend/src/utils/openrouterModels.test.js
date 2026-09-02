import { describe, it, expect } from 'vitest'
import {
  CONTEXT_PRESETS,
  deriveLabel,
  formatContext,
  formatPricePerMtok,
  modelsToJson,
  validateModels,
  validateModelsJson,
} from './openrouterModels'

describe('validateModelsJson', () => {
  it('accepts the shape the backend accepts', () => {
    expect(validateModelsJson('[{"id": "a/b", "label": "A B"}]')).toBe(null)
    expect(validateModelsJson('[]')).toBe(null)
  })

  it('reports malformed JSON', () => {
    expect(validateModelsJson('{')).toMatch(/^Invalid JSON/)
  })

  it('rejects a non-array top level', () => {
    expect(validateModelsJson('{"id": "a/b"}')).toMatch(/array/)
  })

  it('rejects entries without a non-empty string id', () => {
    expect(validateModelsJson('[{"label": "x"}]')).toMatch(/non-empty string "id"/)
    expect(validateModelsJson('[{"id": "  "}]')).toMatch(/non-empty string "id"/)
    expect(validateModelsJson('[["a/b"]]')).toMatch(/object with an "id"/)
  })

  it('rejects a non-string label', () => {
    expect(validateModelsJson('[{"id": "a/b", "label": 3}]')).toMatch(/"label" must be a string/)
  })

  it('rejects duplicate ids', () => {
    expect(validateModelsJson('[{"id": "a/b"},{"id": "a/b"}]')).toMatch(/Duplicate model id: a\/b/)
  })

  it('flags duplicates after trimming, like the server', () => {
    expect(validateModelsJson('[{"id": "a/b"},{"id": " a/b "}]')).toMatch(/Duplicate/)
  })
})

describe('validateModels', () => {
  it('applies the same rules to a parsed value', () => {
    expect(validateModels([{ id: 'a/b' }])).toBe(null)
    expect(validateModels([{ id: '' }])).toMatch(/non-empty string "id"/)
    expect(validateModels(null)).toMatch(/array/)
  })
})

describe('modelsToJson', () => {
  it('renders two-space-indented JSON and tolerates null', () => {
    expect(modelsToJson([{ id: 'a/b', label: 'A' }])).toBe('[\n  {\n    "id": "a/b",\n    "label": "A"\n  }\n]')
    expect(modelsToJson(null)).toBe('[]')
  })
})

describe('deriveLabel', () => {
  it('prefers the server-stripped label', () => {
    expect(deriveLabel({ id: 'tencent/hy4', name: 'Tencent: Hy4 preview', label: 'Hy4 preview' })).toBe('Hy4 preview')
  })

  it('falls back to name, then id', () => {
    expect(deriveLabel({ id: 'tencent/hy4', name: 'Hy4 preview' })).toBe('Hy4 preview')
    expect(deriveLabel({ id: 'tencent/hy4' })).toBe('tencent/hy4')
    expect(deriveLabel(null)).toBe('')
  })
})

describe('formatPricePerMtok', () => {
  it('renders the $/1M form the picker reads at a glance', () => {
    expect(formatPricePerMtok(0.834)).toBe('$0.83/M')
    expect(formatPricePerMtok(2.5)).toBe('$2.50/M')
    expect(formatPricePerMtok(0)).toBe('Free')
    expect(formatPricePerMtok(null)).toBe('—')
  })

  it('keeps two significant digits for fractions too small for 2 decimals', () => {
    expect(formatPricePerMtok(0.0008)).toBe('$0.00080/M')
  })
})

describe('formatContext', () => {
  it('uses K and M units', () => {
    expect(formatContext(131072)).toBe('131K')
    expect(formatContext(200000)).toBe('200K')
    expect(formatContext(1048576)).toBe('1M')
    expect(formatContext(2_000_000)).toBe('2M')
    expect(formatContext(null)).toBe('—')
  })
})

describe('CONTEXT_PRESETS', () => {
  it('offers any/128K/256K/1M', () => {
    expect(CONTEXT_PRESETS.map((p) => p.value)).toEqual([0, 128000, 256000, 1000000])
  })
})
