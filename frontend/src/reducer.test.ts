import { describe, expect, it } from 'vitest'
import { initialClientState, reducer } from './reducer'
import type { StateView } from './protocol'

const sampleView: StateView = {
  type: 'state', session_id: 's1', in_combat: false, current_turn: null,
  is_your_turn: true, log: ['hello'], location: null, scene_mood: null,
  active_objectives: [], characters: {},
}

describe('reducer', () => {
  it('replaces the view on a state message', () => {
    const next = reducer(initialClientState, sampleView)
    expect(next.view).toEqual(sampleView)
    expect(next.error).toBeNull()
  })

  it('sets error and preserves the last view on an error message', () => {
    const withView = reducer(initialClientState, sampleView)
    const next = reducer(withView, { type: 'error', message: 'bad input' })
    expect(next.error).toBe('bad input')
    expect(next.view).toEqual(sampleView)
  })

  it('clears a stale error once a new state message arrives', () => {
    const errored = reducer(initialClientState, { type: 'error', message: 'bad input' })
    const next = reducer(errored, sampleView)
    expect(next.error).toBeNull()
  })
})
