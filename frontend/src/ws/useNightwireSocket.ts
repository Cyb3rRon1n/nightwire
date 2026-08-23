import { useCallback, useReducer } from 'react'
import useWebSocket from 'react-use-websocket'
import { initialClientState, reducer } from '../reducer'
import type { ClientMessage, ServerMessage } from '../protocol'

export function useNightwireSocket(sessionId: string | null, playerId: string | null) {
  const [state, dispatch] = useReducer(reducer, initialClientState)

  const url = sessionId && playerId ? `ws://localhost:8000/ws/${sessionId}/${playerId}` : null

  const { sendJsonMessage, readyState } = useWebSocket(url, {
    share: true,
    onMessage: (event) => {
      const message = JSON.parse(event.data) as ServerMessage
      dispatch(message)
    },
    shouldReconnect: () => true,
    reconnectAttempts: 10,
    reconnectInterval: (attemptNumber) => Math.min(1000 * 2 ** attemptNumber, 10000) + Math.random() * 1000,
    // react-use-websocket asserts `instanceof WebSocket` before sending. MSW's
    // WebSocket interceptor (used in tests, see useNightwireSocket.test.tsx)
    // hands back a socket that doesn't chain to the environment's native
    // WebSocket class, which fails that assertion even though the socket is
    // fully functional. skipAssert is react-use-websocket's own documented
    // escape hatch for exactly this case (mocked/proxied sockets).
    skipAssert: true,
  })

  const send = useCallback((message: ClientMessage) => {
    sendJsonMessage(message)
  }, [sendJsonMessage])

  return { view: state.view, error: state.error, send, readyState }
}
