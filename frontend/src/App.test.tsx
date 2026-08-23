import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ReadyState } from 'react-use-websocket'
import { describe, expect, it, vi } from 'vitest'
import App from './App'
import * as socketModule from './ws/useNightwireSocket'

function mockSocket(overrides: Partial<ReturnType<typeof socketModule.useNightwireSocket>> = {}) {
  const send = vi.fn()
  vi.spyOn(socketModule, 'useNightwireSocket').mockReturnValue({
    view: null,
    error: null,
    send,
    readyState: ReadyState.OPEN,
    ...overrides,
  })
  return send
}

describe('App', () => {
  it('shows the connect form before joining', () => {
    mockSocket()
    render(<App />)
    expect(screen.getByLabelText(/your name/i)).toBeInTheDocument()
  })

  it('sends a join message and renders the feed after submitting the connect form', async () => {
    const send = mockSocket({
      view: {
        type: 'state', session_id: 'test', in_combat: false, current_turn: null,
        is_your_turn: true, log: ['Rook joins the session.'], location: null, scene_mood: null,
        active_objectives: [], characters: {},
      },
    })

    render(<App />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Rook')
    await userEvent.click(screen.getByRole('button', { name: /join/i }))

    expect(await screen.findByText('Rook joins the session.')).toBeInTheDocument()
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ type: 'join' }))
  })

  it('sends an action message when submitting the composer', async () => {
    const send = mockSocket({
      view: {
        type: 'state', session_id: 'test', in_combat: false, current_turn: null,
        is_your_turn: true, log: [], location: null, scene_mood: null,
        active_objectives: [], characters: {},
      },
    })

    render(<App />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Rook')
    await userEvent.click(screen.getByRole('button', { name: /join/i }))
    send.mockClear()

    await userEvent.type(screen.getByPlaceholderText(/what do you do/i), 'I look around.')
    await userEvent.click(screen.getByRole('button', { name: /send/i }))

    expect(send).toHaveBeenCalledWith({ type: 'action', text: 'I look around.' })
  })

  it('shows an error message from the server', async () => {
    mockSocket({
      view: {
        type: 'state', session_id: 'test', in_combat: false, current_turn: null,
        is_your_turn: true, log: [], location: null, scene_mood: null,
        active_objectives: [], characters: {},
      },
      error: 'missing text in action message',
    })

    render(<App />)
    await userEvent.type(screen.getByLabelText(/your name/i), 'Rook')
    await userEvent.click(screen.getByRole('button', { name: /join/i }))

    expect(screen.getByRole('alert')).toHaveTextContent('missing text in action message')
  })
})
