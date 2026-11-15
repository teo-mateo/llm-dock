import { describe, it, expect } from 'vitest'
import { splitCdPrefix } from './shell'

describe('splitCdPrefix', () => {
  it('strips a plain, quoted or semicolon cd prefix', () => {
    expect(splitCdPrefix('cd /a && ls')).toEqual({ dir: '/a', command: 'ls' })
    expect(splitCdPrefix("cd '/a b' && ls")).toEqual({ dir: '/a b', command: 'ls' })
    expect(splitCdPrefix('cd "/a b" && ls')).toEqual({ dir: '/a b', command: 'ls' })
    expect(splitCdPrefix('cd /a; ls')).toEqual({ dir: '/a', command: 'ls' })
  })

  it('leaves a command without a prefix, or a bare cd, alone', () => {
    expect(splitCdPrefix('ls')).toEqual({ dir: null, command: 'ls' })
    expect(splitCdPrefix('cd /a')).toEqual({ dir: null, command: 'cd /a' })
  })

  it('strips the prefix of a multi-line command', () => {
    expect(splitCdPrefix('cd /a && ls\nfoo')).toEqual({ dir: '/a', command: 'ls\nfoo' })
  })
})
