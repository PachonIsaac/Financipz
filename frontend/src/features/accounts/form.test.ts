import { describe, expect, it } from 'vitest'
import { account } from '../../test/utils'
import {
  accountToValues,
  buildAccountCreate,
  buildAccountUpdate,
  emptyAccountValues,
  validateAccountForm,
} from './form'

function parse(values = emptyAccountValues()) {
  const { parsed } = validateAccountForm({ ...values, name: 'Cuenta' })
  if (!parsed) throw new Error('expected valid values')
  return parsed
}

describe('including an account in the balance', () => {
  it('counts by default and only sends the flag when it is turned off', () => {
    expect(emptyAccountValues().includeInBalance).toBe(true)
    expect(buildAccountCreate(parse())).not.toHaveProperty('include_in_balance')
    expect(buildAccountCreate(parse({ ...emptyAccountValues(), includeInBalance: false }))).toMatchObject({
      include_in_balance: false,
    })
  })

  it('sends a change on update only when it differs from the saved value', () => {
    const saved = account({ id: 'a', name: 'Cuenta', initial_balance: '0.00' })
    const values = accountToValues(saved)

    expect(buildAccountUpdate(parse(values), saved)).toEqual({})
    expect(buildAccountUpdate(parse({ ...values, includeInBalance: false }), saved)).toEqual({
      include_in_balance: false,
    })
  })

  it('shows a saved account that was left out as unchecked', () => {
    expect(accountToValues(account({ id: 'a', include_in_balance: false })).includeInBalance).toBe(false)
  })
})
