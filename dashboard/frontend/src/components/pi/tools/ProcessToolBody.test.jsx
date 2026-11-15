import { describe, it, expect, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import ProcessToolBody from './ProcessToolBody'
import { parseProcess } from '../../../utils/piTools/process'
import { parseToolCall } from '../../../utils/piTools/payload'

function tool(args, output, status = 'done') {
  const item = { id: 't1', name: 'process', args, output, status, durationMs: 3, truncated: false }
  return { ...parseToolCall(args, output, parseProcess), item }
}

afterEach(cleanup)

describe('ProcessToolBody', () => {
  it('shows action, toned status, name, pid and the details grid', () => {
    const output = JSON.stringify({
      content: [{ type: 'text', text: 'Started process vite (proc_7) with pid 48211.' }],
      details: {
        action: 'start',
        process: { id: 'proc_7', name: 'vite', pid: 48211, command: 'npm run dev', cwd: '/repo/web', status: 'running' },
      },
    })
    render(<ProcessToolBody tool={tool('{"action":"start","command":"npm run dev","name":"vite"}', output)} />)
    expect(screen.getByText('start')).toBeInTheDocument()
    expect(screen.getByText('running')).toHaveClass('text-warning-fg')
    expect(screen.getByText('pid 48211')).toBeInTheDocument()
    expect(screen.getByText('npm run dev')).toBeInTheDocument()
    expect(screen.getByText('/repo/web')).toBeInTheDocument()
    expect(screen.getByText('proc_7')).toBeInTheDocument()
    expect(screen.getByText('Started process vite (proc_7) with pid 48211.')).toBeInTheDocument()
  })

  it('a non-zero exit reads as a failure', () => {
    const output =
      '{"content":[],"details":{"action":"output","processName":"job","processStatus":"exited","exitCode":3}}'
    render(<ProcessToolBody tool={tool('{"action":"output","id":"proc_1"}', output)} />)
    expect(screen.getByText('exited')).toHaveClass('text-danger-fg')
    expect(screen.getByText('3')).toBeInTheDocument()
  })
})
