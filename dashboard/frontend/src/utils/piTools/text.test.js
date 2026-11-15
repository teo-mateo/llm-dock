import { describe, it, expect } from 'vitest'
import { firstCollapsedLine, numberText, splitPath } from './text'

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

describe('numberText', () => {
  it('numbers lines from the first line, ignoring a trailing newline', () => {
    expect(numberText('a\nb\n', 1)).toEqual([
      { number: 1, text: 'a' },
      { number: 2, text: 'b' },
    ])
    expect(numberText('a\nb', 120).map((line) => line.number)).toEqual([120, 121])
    expect(numberText('', 1)).toEqual([])
  })
})
