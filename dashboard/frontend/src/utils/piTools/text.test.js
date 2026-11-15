import { describe, it, expect } from 'vitest'
import { firstCollapsedLine, splitPath } from './text'

describe('firstCollapsedLine', () => {
  it('keeps the first line with whitespace collapsed', () => {
    expect(firstCollapsedLine('  ls   -la \nsecond')).toBe('ls -la')
    expect(firstCollapsedLine('')).toBe('')
  })
})

describe('splitPath', () => {
  it('splits the directory from the name', () => {
    expect(splitPath('/a/b/c.kt')).toEqual({ dir: '/a/b/', name: 'c.kt' })
    expect(splitPath('c.kt')).toEqual({ dir: '', name: 'c.kt' })
  })
})
