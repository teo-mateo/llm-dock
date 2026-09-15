import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import ParameterReference from './ParameterReference'

// Click-to-add inserts the metadata default as the flag value (`f.default || ''`).
// That seam is the landmine for bool flags: on a parser that rejects
// `--flag value`, a non-empty default renders a command the parser refuses.
// These tests pin the call shape: no default -> bare flag (''), and an
// already-added row adds nothing.

function renderRef(flagMetadata, existingFlags = [], onAddFlag = vi.fn()) {
  render(
    <ParameterReference
      flagMetadata={flagMetadata}
      existingFlags={existingFlags}
      onAddFlag={onAddFlag}
    />
  )
  return onAddFlag
}

describe('ParameterReference click-to-add', () => {
  afterEach(cleanup)

  it('inserts an empty value for a bool flag without a default', () => {
    const onAddFlag = renderRef({
      enable_auto_tool_choice: {
        cli: '--enable-auto-tool-choice',
        type: 'bool',
        category: 'Features & Tools',
        description: 'Enable automatic tool choice in function calling.',
      },
    })
    fireEvent.click(screen.getByText('--enable-auto-tool-choice'))
    expect(onAddFlag).toHaveBeenCalledTimes(1)
    expect(onAddFlag).toHaveBeenCalledWith('--enable-auto-tool-choice', '')
  })

  it('inserts the stored default when the entry carries one', () => {
    const onAddFlag = renderRef({
      performance_mode: {
        cli: '--performance-mode',
        type: 'string',
        category: 'Performance & Compilation',
        description: 'High-level performance knob.',
        default: 'balanced',
      },
    })
    fireEvent.click(screen.getByText('--performance-mode'))
    expect(onAddFlag).toHaveBeenCalledWith('--performance-mode', 'balanced')
  })

  it('does not re-add a flag that is already in the parameters', () => {
    const onAddFlag = renderRef(
      {
        enforce_eager: {
          cli: '--enforce-eager',
          type: 'bool',
          category: 'Performance & Compilation',
          description: 'Always run in eager mode.',
        },
      },
      ['--enforce-eager']
    )
    fireEvent.click(screen.getByText('--enforce-eager'))
    expect(onAddFlag).not.toHaveBeenCalled()
  })
})
