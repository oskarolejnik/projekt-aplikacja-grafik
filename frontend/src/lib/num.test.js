import { describe, it, expect } from 'vitest'
import { num } from './num'

describe('num — parsowanie kwoty z inputu', () => {
  it('akceptuje polski przecinek dziesiętny (nie gubi groszy)', () => {
    expect(num('1234,56')).toBe(1234.56)
    expect(num('89,90')).toBe(89.9)
    expect(num('0,05')).toBe(0.05)
  })
  it('obsługuje kropkę i liczby całkowite', () => {
    expect(num('1234.56')).toBe(1234.56)
    expect(num('1000')).toBe(1000)
    expect(num(1000)).toBe(1000)
  })
  it('puste/niepoprawne → 0', () => {
    expect(num('')).toBe(0)
    expect(num(null)).toBe(0)
    expect(num(undefined)).toBe(0)
    expect(num('abc')).toBe(0)
  })
})
