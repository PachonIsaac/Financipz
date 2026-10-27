import { describe, expect, it } from 'vitest'
import { translateProblem } from './client'

describe('translateProblem', () => {
  it.each([
    ['Field required', 'es obligatorio'],
    ['Input should be greater than 0', 'debe ser mayor que cero'],
    ['String should have at most 500 characters', 'es demasiado largo'],
    ['Decimal input should have no more than 2 decimal places', 'tiene demasiados decimales'],
    ["String should match pattern '^#[0-9a-fA-F]{6}$'", 'no tiene un formato válido'],
    ['Input should be a valid UUID', 'no tiene un formato válido'],
    ['Value error, algo raro', 'no es válido'],
  ])('%s', (input, expected) => {
    expect(translateProblem(input)).toBe(expected)
  })
})
