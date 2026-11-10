import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import EngineBadge from './EngineBadge'
import { SAMPLE_ENGINES } from '../test/engineCatalogue'

const { catalogue } = vi.hoisted(() => ({ catalogue: { byType: {} } }))
vi.mock('../hooks/useEngineCatalogue', () => ({ default: () => catalogue }))

afterEach(() => cleanup())

const EXPECTED = {
  llamacpp: ['llama.cpp', 'badge-llamacpp'],
  ik_llamacpp: ['ik_llama', 'badge-llamacpp'],
  vllm: ['vLLM', 'badge-vllm'],
  ds4: ['DS4', 'badge-ds4'],
  tabbyapi: ['EXL3', 'badge-exl3'],
  sglang: ['SGLang', 'badge-sglang'],
  maya: ['Maya', 'badge-maya'],
  ninfer: ['NInfer', 'badge-ninfer'],
}

describe('EngineBadge', () => {
  it.each(Object.entries(EXPECTED))('shows the catalogue label and the colour of %s', (type, [label, colour]) => {
    catalogue.byType = Object.fromEntries(SAMPLE_ENGINES.map(e => [e.type, e]))

    render(<EngineBadge templateType={type} />)

    const badge = screen.getByText(label)
    expect(badge.className).toContain(colour)
  })

  it('labels a type the catalogue does not know with the type, in the neutral colour', () => {
    catalogue.byType = Object.fromEntries(SAMPLE_ENGINES.map(e => [e.type, e]))

    render(<EngineBadge templateType="future_engine" />)

    expect(screen.getByText('future_engine').className).toContain('badge-neutral')
  })

  it('takes the label from the catalogue even for a type with no colour of its own', () => {
    catalogue.byType = { future_engine: { type: 'future_engine', badge_label: 'Future' } }

    render(<EngineBadge templateType="future_engine" />)

    expect(screen.getByText('Future').className).toContain('badge-neutral')
  })

  it('falls back to the type while the catalogue has not loaded', () => {
    catalogue.byType = {}

    render(<EngineBadge templateType="vllm" />)

    expect(screen.getByText('vllm').className).toContain('badge-vllm')
  })

  it('says Unknown for a service with no type at all', () => {
    catalogue.byType = {}

    render(<EngineBadge templateType="" />)

    expect(screen.getByText('Unknown').className).toContain('badge-neutral')
  })

  it('keeps the infrastructure badge', () => {
    catalogue.byType = {}

    render(<EngineBadge templateType="" infra />)

    expect(screen.getByText('WebUI').className).toContain('badge-webui')
  })
})
