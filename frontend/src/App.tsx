import { useEffect, useState } from 'react'
import { ReadyState } from 'react-use-websocket'
import { useNightwireSocket } from './ws/useNightwireSocket'

function ConnectForm({ onJoin }: { onJoin: (sessionId: string, playerName: string) => void }) {
  const [sessionId, setSessionId] = useState('test')
  const [playerName, setPlayerName] = useState('')

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (playerName.trim()) onJoin(sessionId, playerName.trim())
      }}
    >
      <label>
        Session ID
        <input value={sessionId} onChange={(e) => setSessionId(e.target.value)} />
      </label>
      <label>
        Your name
        <input value={playerName} onChange={(e) => setPlayerName(e.target.value)} />
      </label>
      <button type="submit">Join</button>
    </form>
  )
}

function Feed({ sessionId, playerId }: { sessionId: string; playerId: string }) {
  const { view, error, send, readyState } = useNightwireSocket(sessionId, playerId)
  const [actionText, setActionText] = useState('')

  useEffect(() => {
    if (readyState === ReadyState.OPEN) {
      send({
        type: 'join',
        character: { player_id: playerId, name: playerId, role: 'solo', lifepath: 'streetkid' },
      })
    }
  }, [readyState, playerId, send])

  return (
    <div>
      {error && <div role="alert">{error}</div>}
      <ul>
        {view?.log.map((line, i) => <li key={i}>{line}</li>)}
      </ul>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          if (actionText.trim()) {
            send({ type: 'action', text: actionText.trim() })
            setActionText('')
          }
        }}
      >
        <input
          value={actionText}
          onChange={(e) => setActionText(e.target.value)}
          placeholder="What do you do?"
        />
        <button type="submit">Send</button>
      </form>
    </div>
  )
}

export default function App() {
  const [session, setSession] = useState<{ sessionId: string; playerId: string } | null>(null)

  return (
    <div>
      <h1>Nightwire</h1>
      {session
        ? <Feed sessionId={session.sessionId} playerId={session.playerId} />
        : <ConnectForm onJoin={(sessionId, playerName) => setSession({ sessionId, playerId: playerName })} />}
    </div>
  )
}
