import { useCallback, useReducer } from 'react'
import * as ReactUseWebSocket from 'react-use-websocket'
import { initialClientState, reducer } from './reducer'
import type { ClientMessage, ServerMessage } from './protocol'

// react-use-websocket is legacy CJS with `exports.default = useWebSocket`
// alongside named exports (ReadyState, etc.), and no package.json "exports"
// field, so namespace-import interop can wrap `.default` in an extra layer
// depending on the bundler. Peel `.default` until we land on something
// callable rather than guessing the wrap depth.
function unwrapDefault<T>(value: unknown): T {
  while (value && typeof value !== 'function' && typeof value === 'object' && 'default' in value) {
    const next = (value as { default: unknown }).default
    if (next === value) break
    value = next
  }
  return value as T
}

const useWebSocket = unwrapDefault<typeof ReactUseWebSocket.default>(ReactUseWebSocket)

const DEFAULT_WS_URL = 'ws://localhost:8000'

export function useNightwireSocket(sessionId: string | null, playerId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialClientState)

  const base = process.env.NEXT_PUBLIC_NIGHTWIRE_WS_URL || DEFAULT_WS_URL
  const url = sessionId && playerId ? `${base}/ws/${sessionId}/${playerId}` : null

  const { sendJsonMessage, readyState } = useWebSocket(url, {
    share: true,
    onMessage: (event) => {
      const message = JSON.parse(event.data) as ServerMessage
      dispatch(message)
    },
    shouldReconnect: () => true,
    reconnectAttempts: 10,
    reconnectInterval: (attemptNumber) => Math.min(1000 * 2 ** attemptNumber, 10000) + Math.random() * 1000,
  })

  const send = useCallback((message: ClientMessage) => {
    sendJsonMessage(message)
  }, [sendJsonMessage])

  return { view: state.view, error: state.error, errorSeq: state.errorSeq, send, readyState }
}
