import type { ServerMessage, StateView } from './protocol'

export interface ClientState {
  view: StateView | null
  error: string | null
}

export const initialClientState: ClientState = { view: null, error: null }

export function reducer(state: ClientState, message: ServerMessage): ClientState {
  if (message.type === 'error') {
    return { ...state, error: message.message }
  }
  return { view: message, error: null }
}
