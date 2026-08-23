import { describe, expect, it } from 'vitest'
import { isErrorMessage, type ServerMessage } from './protocol'

describe('isErrorMessage', () => {
  it('identifies an error message', () => {
    const message: ServerMessage = { type: 'error', message: 'oops' }
    expect(isErrorMessage(message)).toBe(true)
  })

  it('identifies a state message as not an error', () => {
    const message: ServerMessage = {
      type: 'state', session_id: 's1', in_combat: false, current_turn: null,
      is_your_turn: true, log: [], location: null, scene_mood: null,
      active_objectives: [], characters: {},
    }
    expect(isErrorMessage(message)).toBe(false)
  })
})
