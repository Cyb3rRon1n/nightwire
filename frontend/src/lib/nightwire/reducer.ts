import type { ServerMessage, StateView } from './protocol'

export interface ClientState {
  view: StateView | null
  error: string | null
  errorSeq: number
}

export const initialClientState: ClientState = { view: null, error: null, errorSeq: 0 }

export function reducer(state: ClientState, message: ServerMessage): ClientState {
  if (message.type === 'error') {
    // errorSeq bumps on every error, including an identical repeat, so an
    // effect keyed on it re-runs when the same failure recurs (retrying
    // against a still-down backend produces the same error string).
    return { ...state, error: message.message, errorSeq: state.errorSeq + 1 }
  }
  return { view: message, error: null, errorSeq: state.errorSeq }
}
