import { describe, expect, it } from 'vitest'
import { formatMoney, formatRate, fromCents, isPositive, parseAmountInput, sumCents, toCents } from './money'

describe('toCents / fromCents', () => {
  it('converts decimal strings to integer cents and back', () => {
    expect(toCents('1250000.00')).toBe(125000000n)
    expect(toCents('-0.05')).toBe(-5n)
    expect(toCents('7.5')).toBe(750n)
    expect(fromCents(125000000n)).toBe('1250000.00')
    expect(fromCents(-5n)).toBe('-0.05')
    expect(fromCents(0n)).toBe('0.00')
  })

  it('rejects malformed values', () => {
    expect(() => toCents('abc')).toThrow()
    expect(() => toCents('1.234')).toThrow()
    expect(() => toCents('')).toThrow()
  })

  it('sums without floating point drift', () => {
    expect(fromCents(sumCents(['0.10', '0.20', '-0.30']))).toBe('0.00')
    expect(fromCents(sumCents(['99999999999.99', '0.01']))).toBe('100000000000.00')
  })

  it('detects positive amounts', () => {
    expect(isPositive('0.01')).toBe(true)
    expect(isPositive('0.00')).toBe(false)
    expect(isPositive('-3.00')).toBe(false)
  })
})

describe('formatMoney', () => {
  it('formats COP without decimals using es-CO separators', () => {
    expect(formatMoney('1250000.00', 'COP')).toBe('$ 1.250.000')
    expect(formatMoney('999.00', 'COP')).toBe('$ 999')
    expect(formatMoney('0.00', 'COP')).toBe('$ 0')
  })

  it('rounds COP half away from zero', () => {
    expect(formatMoney('10.50', 'COP')).toBe('$ 11')
    expect(formatMoney('10.49', 'COP')).toBe('$ 10')
    expect(formatMoney('-10.50', 'COP')).toBe('-$ 11')
  })

  it('shows two decimals for USD and when exact', () => {
    expect(formatMoney('1234.5', 'USD')).toBe('US$ 1.234,50')
    expect(formatMoney('1250000.00', 'COP', { exact: true })).toBe('$ 1.250.000,00')
  })

  it('shows negatives clearly and never "-0"', () => {
    expect(formatMoney('-45000.00', 'COP')).toBe('-$ 45.000')
    expect(formatMoney('-0.20', 'COP')).toBe('$ 0')
    expect(formatMoney('-12.30', 'USD')).toBe('-US$ 12,30')
  })

  it('can prefix a plus sign', () => {
    expect(formatMoney('5000.00', 'COP', { showPlus: true })).toBe('+$ 5.000')
    expect(formatMoney('0.00', 'COP', { showPlus: true })).toBe('$ 0')
  })

  it('handles very large amounts exactly', () => {
    expect(formatMoney('123456789012.34', 'COP', { exact: true })).toBe('$ 123.456.789.012,34')
  })
})

describe('parseAmountInput', () => {
  it('reads comma as decimal and dots as thousands', () => {
    expect(parseAmountInput('12.500,50')).toBe('12500.50')
    expect(parseAmountInput('45000')).toBe('45000.00')
    expect(parseAmountInput('1.250.000')).toBe('1250000.00')
    expect(parseAmountInput('0,5')).toBe('0.50')
    expect(parseAmountInput(',5')).toBe('0.50')
  })

  it('reads a lone dot with one or two digits as decimal', () => {
    expect(parseAmountInput('12.5')).toBe('12.50')
    expect(parseAmountInput('12.50')).toBe('12.50')
    expect(parseAmountInput('12.500')).toBe('12500.00')
  })

  it('rejects invalid input', () => {
    expect(parseAmountInput('')).toBeNull()
    expect(parseAmountInput('abc')).toBeNull()
    expect(parseAmountInput('1,234,5')).toBeNull()
    expect(parseAmountInput('1,234')).toBeNull()
    expect(parseAmountInput('-5')).toBeNull()
  })

  it('accepts negatives only when allowed', () => {
    expect(parseAmountInput('-1.500,25', { allowNegative: true })).toBe('-1500.25')
    expect(parseAmountInput('-0', { allowNegative: true })).toBe('0.00')
  })

  it('strips leading zeros and symbols', () => {
    expect(parseAmountInput('$ 007')).toBe('7.00')
  })

  it.each([
    ['1.000.50', null],
    ['1.00.000', null],
    ['12.3456', null],
    ['1..000', null],
    ['.500', null],
    ['1.000', '1000.00'],
    ['1.000.000', '1000000.00'],
    ['1.5', '1.50'],
    ['1.000,5', '1000.50'],
    ['1.00,5', null],
    ['10.000.00', null],
  ])('parses %s as %s', (input, expected) => {
    expect(parseAmountInput(input)).toBe(expected)
  })
})

describe('formatRate', () => {
  it('formats the rates the API really sends, which have four decimals', () => {
    expect(formatRate('3157.9400')).toBe('$ 3.157,94')
    expect(formatRate('4000.0000')).toBe('$ 4.000,00')
    expect(formatRate('4100')).toBe('$ 4.100,00')
    expect(formatRate('999.5')).toBe('$ 999,50')
  })

  it('rounds half up to cents', () => {
    expect(formatRate('3157.9449')).toBe('$ 3.157,94')
    expect(formatRate('3157.9450')).toBe('$ 3.157,95')
    expect(formatRate('3157.9951')).toBe('$ 3.158,00')
  })

  it('rejects what is not a rate', () => {
    expect(() => formatRate('abc')).toThrow()
    expect(() => formatRate('-4000.0000')).toThrow()
    expect(() => formatRate('3157.94001')).toThrow()
  })

  it('is needed: an amount helper refuses the same value', () => {
    expect(() => toCents('3157.9400')).toThrow()
  })
})
