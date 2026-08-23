import { renderHook, waitFor, act } from '@testing-library/react'
import { ws } from 'msw'
import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, describe, expect, it } from 'vitest'
import { useNightwireSocket } from './useNightwireSocket'

// MSW 2.6+'s `ws` namespace is real and current, but check the installed
// msw version's exact API if this doesn't match (see Global Constraints) -
// the intent is: mock a WS server at this URL pattern, echo a state message
// back when a join arrives, and verify the hook's state updates.
const link = ws.link('ws://localhost:8000/ws/:sessionId/:playerId')
const server = setupServer(
  link.addEventListener('connection', ({ client }) => {
    client.addEventListener('message', (event) => {
      const message = JSON.parse(event.data as string)
      if (message.type === 'join') {
        client.send(JSON.stringify({
          type: 'state', session_id: 's1', in_combat: false, current_turn: null,
          is_your_turn: true, log: [], location: null, scene_mood: null,
          active_objectives: [], characters: { [message.character.player_id]: message.character },
        }))
      }
    })
  }),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('useNightwireSocket', () => {
  it('receives a state message after sending join', async () => {
    const { result } = renderHook(() => useNightwireSocket('s1', 'p1'))

    act(() => {
      result.current.send({
        type: 'join',
        character: { player_id: 'p1', name: 'Rook', role: 'solo', lifepath: 'streetkid' },
      })
    })

    await waitFor(() => {
      expect(result.current.view?.session_id).toBe('s1')
    })
  })
})
