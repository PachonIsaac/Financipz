import { describe, expect, it } from 'vitest'
import { Briefcase, Ellipsis, ShoppingCart } from 'lucide-react'
import { categoryLook, TONES } from './appearance'

const base = { icon: null, color: null, type: 'expense' as const }

describe('category look', () => {
  it('guesses the icon and color from the name, ignoring accents and case', () => {
    expect(categoryLook({ ...base, name: 'Mercado del mes' })).toEqual({ Icon: ShoppingCart, color: TONES.orange })
    expect(categoryLook({ ...base, name: 'SUELDO', type: 'income' })).toEqual({ Icon: Briefcase, color: TONES.green })
  })

  it('uses what the category stores before guessing', () => {
    expect(categoryLook({ ...base, name: 'Mercado', icon: 'briefcase', color: '#112233' })).toEqual({
      Icon: Briefcase,
      color: '#112233',
    })
  })

  it('ignores a color that is not a hex value and falls back to a neutral look', () => {
    expect(categoryLook({ ...base, name: 'Cosas', color: 'red' })).toEqual({ Icon: Ellipsis, color: TONES.gray })
    expect(categoryLook(undefined).Icon).toBe(Ellipsis)
  })
})
