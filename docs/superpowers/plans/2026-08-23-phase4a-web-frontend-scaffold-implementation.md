# Phase 4a: Web Frontend Scaffold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the WebSocket wire-up end to end with a real browser client — a bare, unstyled React app that connects, joins a session, sends a free-text action, and shows the narrator's reply arrive live. This is deliberately not the real UI (no chat bubbles, no vitals band, no character sheet overlay, no Tailwind styling) — that's a separate follow-up plan (4b), matching how prior phases split engine-wiring from feature-complete work.

**Architecture:** The backend gets two small prerequisites first: `server/views.py`'s broadcast gains a `"type": "state"` discriminator (it currently has none — error messages have `type: "error"`, but state broadcasts are distinguished only by the *absence* of a `type` key, which a real client can't cleanly branch on), and `server/__main__.py` becomes a runnable entrypoint (nothing can currently serve the app outside of tests). Then the frontend: a Vite + React 19 + TypeScript scaffold with Vitest/RTL/MSW test tooling, a `protocol.ts` module of TypeScript types mirroring the *actual* implemented WebSocket protocol (not the spec's original speculative `{type, session_id, sender_id, payload}` envelope shape, which was written before the real protocol existed and doesn't match it), a pure `reducer.ts` for server-pushed state, a `useNightwireSocket` hook wrapping `react-use-websocket`, and a minimal `App.tsx` (connect form → plain log list → text input).

**Tech Stack:** Vite + React 19 + TypeScript (already decided, `ROADMAP.md`). Tailwind CSS is a dependency of this scaffold (per the spec) but this plan doesn't use it for any real styling yet — it's installed and wired so 4b doesn't need a second scaffold pass. `react-use-websocket` for the connection (per spec — avoids the hand-rolled-reconnect-logic failure mode). Vitest + React Testing Library + MSW's `ws` namespace for testing (per spec). `npm` as the package manager (already installed on this machine; no `pnpm`/`yarn` present, no reason to add one).

**Spec:** `docs/superpowers/specs/2026-08-22-web-frontend-design.md` (state architecture, WS connection management, testing). Its "Protocol integration" section describes a speculative envelope shape from before the real protocol was built — this plan's `protocol.ts` (Task 4) supersedes that section with the actual shape, sourced directly from `server/dispatch.py`, `server/narration.py`, and `server/views.py`.

## Global Constraints

- Backend: no new Python dependencies (`uvicorn[standard]` is already installed, from Phase 2b).
- Frontend lives in `frontend/` at the repo root, sibling to `engine/`/`ruleset/`/`server/`/`narrator/` — it has no `__init__.py` and isn't a Python package, so it's naturally excluded from `pyproject.toml`'s `packages.find` allowlist without needing any config change.
- The WebSocket URL is hardcoded to `ws://localhost:8000` for this phase — dev-only, no environment-variable configuration. Real deployment config is later work.
- No character-creation UI — the join message hardcodes `role: "solo"`, `lifepath: "streetkid"`. A real picker is explicit 4b/later scope (the spec's own "exact component boundaries... implementation-phase work" deferral).
- No Do/Say/Think composer modes — plain text action only. No chat-bubble styling, no vitals/party/objectives band, no character sheet overlay. All of that is 4b.
- Third-party CLI/library version notes: `npm create vite@latest` and MSW's `ws` mocking API are real, current (2026) tools, but their exact CLI prompts / method signatures can shift between minor versions faster than this plan can pin. Where a step depends on one, the plan states the *intent* precisely (scaffold a Vite+React+TS project; mock a WS connection and verify a round-trip) — if the installed version's exact interaction differs from the example given, match the intent, not the letter, and note the deviation in the task's report.
- Tailwind CSS 4's setup (`@tailwindcss/vite`, CSS-first config via `@import "tailwindcss"`, no `tailwind.config.js`/`postcss.config.js` needed) is what this plan installs and configures — if `npm install tailwindcss` resolves a pre-4.x version, stop and flag it rather than silently falling back to the old PostCS-config setup, since that changes several other steps.
- Task 7's browser verification requires invoking the `claude-in-chrome` skill first, per that skill's own trigger rule, before any `mcp__claude-in-chrome__*` tool call.

---

## File Structure

- Modify: `server/views.py` — `build_view` gains a `"type": "state"` key.
- Create: `server/__main__.py` — `build_app()` factory + `uvicorn.run` entrypoint.
- Modify: `tests/test_views.py`, create `tests/test_server_main.py`.
- Create (via `npm create vite@latest`): `frontend/` — standard Vite React-TS scaffold, plus:
  - `frontend/src/protocol.ts` — TypeScript types for the real WS protocol.
  - `frontend/src/reducer.ts` — pure reducer for server-pushed state.
  - `frontend/src/ws/useNightwireSocket.ts` — the connection hook.
  - `frontend/src/App.tsx` — connect form → feed, replacing Vite's default template content.
  - `frontend/src/test/setup.ts` — Vitest/RTL setup (jest-dom matchers).
  - `frontend/src/protocol.test.ts`, `frontend/src/reducer.test.ts`, `frontend/src/ws/useNightwireSocket.test.tsx`, `frontend/src/App.test.tsx`.

## The real protocol (source of truth for Task 4 — read directly from the backend, not the spec)

```python
# Inbound (client -> server), matched on message["type"]:
{"type": "join", "character": {"player_id": str, "name": str, "role": str, "lifepath": str,
                                 "attributes"?: dict[str, int], "health"?: int, "max_health"?: int,
                                 "armor"?: int, "conditions"?: list[str], "inventory"?: list[str]}}
{"type": "action", "text": str}
{"type": "start_combat", "initiative_rolls": dict[str, int]}
{"type": "advance_turn"}
{"type": "end_combat"}

# Outbound (server -> client):
{"type": "error", "message": str}
{"type": "state", "session_id": str, "in_combat": bool, "current_turn": str | None,
 "is_your_turn": bool, "log": list[str], "location": str | None, "scene_mood": str | None,
 "active_objectives": list[str],
 "characters": dict[str, FullCharacter | RedactedCharacter]}
# FullCharacter (your own sheet): player_id, name, role, lifepath, attributes, health,
#   max_health, armor, conditions, inventory
# RedactedCharacter (everyone else's): name, role, health, max_health, armor, conditions
```

---

### Task 1: Add a type discriminator to state broadcasts

**Files:**
- Modify: `server/views.py`
- Modify: `tests/test_views.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `build_view`'s return dict gains `"type": "state"` — used by Task 4's `protocol.ts` types and every frontend task after it.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_views.py`:

```python
def test_view_has_a_state_type_discriminator():
    session = Session(session_id="s1")
    session.characters["p1"] = _character("p1", "Rook")

    view = build_view(session, "p1")

    assert view["type"] == "state"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_views.py -v`
Expected: FAIL with `KeyError: 'type'`

- [ ] **Step 3: Write minimal implementation**

In `server/views.py`, add `"type": "state",` as the first key of `build_view`'s return dict:

```python
    return {
        "type": "state",
        "session_id": session.session_id,
        "in_combat": session.in_combat,
        "current_turn": current_turn(session),
        "is_your_turn": is_players_turn(session, viewer_id),
        "log": session.log[-50:],
        "location": session.location,
        "scene_mood": session.scene_mood,
        "active_objectives": session.active_objectives,
        "characters": characters,
    }
```

(Everything else in the file — the redaction logic, the `log[-50:]` cap from Phase 3b's final review — is unchanged.)

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_views.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add server/views.py tests/test_views.py
git commit -m "feat: add a type discriminator to state broadcasts"
```

---

### Task 2: Runnable server entrypoint

**Files:**
- Create: `server/__main__.py`
- Test: `tests/test_server_main.py`

**Interfaces:**
- Consumes: `server.app.create_app`, `engine.persistence.JSONFileSessionStore`, `narrator.client.NarratorClient` — all unchanged.
- Produces: `server.__main__.build_app() -> FastAPI` — used by Task 7's manual browser verification (via `python -m server`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_server_main.py
from fastapi import FastAPI


def test_build_app_returns_a_fastapi_app(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from server.__main__ import build_app

    app = build_app()

    assert isinstance(app, FastAPI)
```

(`monkeypatch.chdir(tmp_path)` keeps the `JSONFileSessionStore("./sessions")` directory `build_app()` creates confined to a throwaway pytest temp dir, not the repo root.)

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_server_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'server.__main__'`

- [ ] **Step 3: Write minimal implementation**

```python
# server/__main__.py
import uvicorn

from engine.persistence import JSONFileSessionStore
from narrator.client import NarratorClient
from server.app import create_app


def build_app():
    store = JSONFileSessionStore("./sessions")
    narrator_client = NarratorClient(model="qwen3:8b", system_prompt="You are a cyberpunk tabletop game master.")
    return create_app(store, narrator_client)


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_server_main.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add server/__main__.py tests/test_server_main.py
git commit -m "feat: add a runnable server entrypoint (python -m server)"
```

---

### Task 3: Frontend scaffold

**Files:**
- Create: `frontend/` (via `npm create vite@latest`), plus Tailwind and test-tooling config on top.

**Interfaces:**
- Consumes: nothing.
- Produces: a working `npm run dev` / `npm run build` / `npm test` toolchain in `frontend/` — every later task in this plan builds on it.

- [ ] **Step 1: Scaffold the Vite project**

```bash
cd /home/sentinel/projects/github/repos/nightwire
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
```

Expected result: a `frontend/` directory with `package.json`, `tsconfig.json`, `vite.config.ts`, `index.html`, `src/main.tsx`, `src/App.tsx`, `src/App.css`, `src/index.css` — Vite's standard React-TS template. If the CLI prompts interactively, accept the defaults (React, TypeScript, no additional variant).

- [ ] **Step 2: Add Tailwind CSS 4**

```bash
npm install tailwindcss @tailwindcss/vite
```

Check `node_modules/tailwindcss/package.json`'s `version` field — confirm it's `4.x`. If not, stop and flag it (see Global Constraints).

Edit `vite.config.ts` to add the Tailwind plugin:

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
})
```

Replace the contents of `src/index.css` with:

```css
@import "tailwindcss";
```

(`src/App.css` can be left as-is or deleted — Task 6 replaces `App.tsx`'s content anyway and won't import it.)

- [ ] **Step 3: Add test tooling**

```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom msw
npm pkg set scripts.test="vitest run"
```

Add a `test` block to `vite.config.ts` (Vitest reads config from the same file):

```ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
  },
})
```

```ts
// frontend/src/test/setup.ts
import '@testing-library/jest-dom/vitest'
```

- [ ] **Step 4: Write the failing smoke test**

```tsx
// frontend/src/App.test.tsx (temporary content for this step — Task 6 replaces this file)
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the nightwire title', () => {
    render(<App />)
    expect(screen.getByText(/nightwire/i)).toBeInTheDocument()
  })
})
```

Run: `npm test`
Expected: FAIL — Vite's default template renders "Vite + React", not "Nightwire".

- [ ] **Step 5: Make it pass with a minimal placeholder**

Replace `frontend/src/App.tsx`'s contents with:

```tsx
export default function App() {
  return <h1>Nightwire</h1>
}
```

Run: `npm test`
Expected: PASS (1 passed)

Also run: `npm run build` — expected: succeeds with no TypeScript errors (confirms the whole toolchain — Vite, React, TS, Tailwind — is wired correctly before any real feature code is written).

- [ ] **Step 6: Commit**

```bash
git add frontend/
git commit -m "feat: scaffold the Vite + React + TypeScript + Tailwind frontend"
```

(`frontend/node_modules/` should already be excluded by the `.gitignore` Vite's template generates inside `frontend/` — confirm `git status` doesn't show `node_modules/` staged before committing; if it does, add `frontend/node_modules/` to the repo root `.gitignore` first.)

---

### Task 4: Protocol types

**Files:**
- Create: `frontend/src/protocol.ts`
- Test: `frontend/src/protocol.test.ts`

**Interfaces:**
- Consumes: nothing (pure types + one type-guard function).
- Produces: `ServerMessage`, `StateView`, `ErrorMessage`, `ClientMessage` (and its 5 variants), `isErrorMessage` — used by Task 5's reducer and hook, and Task 6's `App.tsx`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/protocol.test.ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test`
Expected: FAIL — `Cannot find module './protocol'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/protocol.ts

export interface CharacterSheet {
  player_id: string
  name: string
  role: string
  lifepath: string
  attributes: Record<string, number>
  health: number
  max_health: number
  armor: number
  conditions: string[]
  inventory: string[]
}

export interface RedactedCharacter {
  name: string
  role: string
  health: number
  max_health: number
  armor: number
  conditions: string[]
}

export interface StateView {
  type: 'state'
  session_id: string
  in_combat: boolean
  current_turn: string | null
  is_your_turn: boolean
  log: string[]
  location: string | null
  scene_mood: string | null
  active_objectives: string[]
  characters: Record<string, CharacterSheet | RedactedCharacter>
}

export interface ErrorMessage {
  type: 'error'
  message: string
}

export type ServerMessage = StateView | ErrorMessage

export function isErrorMessage(message: ServerMessage): message is ErrorMessage {
  return message.type === 'error'
}

export interface JoinMessage {
  type: 'join'
  character: {
    player_id: string
    name: string
    role: string
    lifepath: string
    attributes?: Record<string, number>
    health?: number
    max_health?: number
    armor?: number
    conditions?: string[]
    inventory?: string[]
  }
}

export interface ActionMessage {
  type: 'action'
  text: string
}

export interface StartCombatMessage {
  type: 'start_combat'
  initiative_rolls: Record<string, number>
}

export interface AdvanceTurnMessage {
  type: 'advance_turn'
}

export interface EndCombatMessage {
  type: 'end_combat'
}

export type ClientMessage =
  | JoinMessage
  | ActionMessage
  | StartCombatMessage
  | AdvanceTurnMessage
  | EndCombatMessage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test`
Expected: PASS (2 passed, plus the 1 from Task 3 = 3 total)

Also run: `npx tsc --noEmit` from `frontend/` — expected: no errors (this is the real verification for a types-only module; the runtime test above only exercises `isErrorMessage`, not the type shapes themselves).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/protocol.ts frontend/src/protocol.test.ts
git commit -m "feat: TypeScript protocol types matching the real WebSocket API"
```

---

### Task 5: Reducer and WebSocket hook

**Files:**
- Create: `frontend/src/reducer.ts`
- Test: `frontend/src/reducer.test.ts`
- Create: `frontend/src/ws/useNightwireSocket.ts`
- Test: `frontend/src/ws/useNightwireSocket.test.tsx`
- Modify: `frontend/package.json` — add `react-use-websocket` as a dependency.

**Interfaces:**
- Consumes: `frontend/src/protocol.ts`'s `ServerMessage`, `ClientMessage`, `StateView` (Task 4).
- Produces: `reducer(state: ClientState, message: ServerMessage): ClientState`, `initialClientState`, `useNightwireSocket(sessionId: string | null, playerId: string | null) -> { view, error, send, readyState }` — used by Task 6's `App.tsx`.

- [ ] **Step 1: Write the failing tests**

```ts
// frontend/src/reducer.test.ts
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
```

```tsx
// frontend/src/ws/useNightwireSocket.test.tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `Cannot find module './reducer'` / `Cannot find module './useNightwireSocket'`

- [ ] **Step 3: Write minimal implementation**

```ts
// frontend/src/reducer.ts
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
```

```bash
npm install react-use-websocket
```

```ts
// frontend/src/ws/useNightwireSocket.ts
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
  })

  const send = useCallback((message: ClientMessage) => {
    sendJsonMessage(message)
  }, [sendJsonMessage])

  return { view: state.view, error: state.error, send, readyState }
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS (3 reducer tests, 1 hook test, plus the 3 from Tasks 3-4 = 7 total)

- [ ] **Step 5: Commit**

```bash
git add frontend/src/reducer.ts frontend/src/reducer.test.ts frontend/src/ws/ frontend/package.json frontend/package-lock.json
git commit -m "feat: server-pushed-state reducer and WebSocket connection hook"
```

---

### Task 6: Minimal connect + feed UI

**Files:**
- Modify: `frontend/src/App.tsx` (replaces Task 3's placeholder)
- Modify: `frontend/src/App.test.tsx` (replaces Task 3's smoke test)

**Interfaces:**
- Consumes: `useNightwireSocket` (Task 5), `ClientMessage`/`StateView` types (Task 4).
- Produces: the rendered app — the terminal deliverable of this plan (before Task 7's verification).

- [ ] **Step 1: Write the failing tests**

```tsx
// frontend/src/App.test.tsx
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `npm test`
Expected: FAIL — `App.tsx` still renders only `<h1>Nightwire</h1>` from Task 3, no connect form exists.

- [ ] **Step 3: Write minimal implementation**

```tsx
// frontend/src/App.tsx
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
```

Note: the join `useEffect` gates on `readyState === ReadyState.OPEN` rather than firing unconditionally on mount — `react-use-websocket` does not guarantee messages sent before the socket is actually open are queued, so this is the correct, race-free way to send the first message.

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test`
Expected: PASS (10 total: Task 4's 2 + Task 5's 4 + this task's 4 new App tests — Task 3's 1 smoke test is replaced, not kept, since this step overwrites `App.test.tsx`)

Also run: `npm run build` — expected: succeeds, no TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: minimal connect form and live action feed"
```

---

### Task 7: Full verification — automated suites plus a real browser

**Files:** none created — verification only, and a fix commit if anything surfaces.

- [ ] **Step 1: Run the backend test suite**

Run: `pytest -v`
Expected: all tests from every prior phase plus this plan's Tasks 1-2 pass; only the 2 pre-existing expected skips remain.

- [ ] **Step 2: Run the frontend test suite and build**

```bash
cd frontend
npm test
npx tsc --noEmit
npm run build
```

Expected: all pass, no type errors, a clean production build.

- [ ] **Step 3: Start the real backend**

```bash
cd /home/sentinel/projects/github/repos/nightwire
python -m server &
```

Expected: listens on `http://localhost:8000` (uvicorn's startup log confirms the port).

- [ ] **Step 4: Start the real frontend dev server**

```bash
cd frontend
npm run dev &
```

Expected: Vite reports a local URL, typically `http://localhost:5173`.

- [ ] **Step 5: Verify in a real browser**

Invoke the `claude-in-chrome` skill first (required before any `mcp__claude-in-chrome__*` tool call, per that skill's own trigger rule). Then:

1. Navigate to the Vite dev server's URL.
2. Confirm the page renders "Nightwire" and a connect form (session ID + name inputs, a Join button).
3. Type a player name, click Join.
4. Confirm the feed renders (may show nothing yet, or an initial join broadcast line).
5. Type an action into the composer (e.g. "I look around.") and click Send.
6. Confirm a narration line eventually appears in the log — this involves a real call to the local `qwen3:8b` model, so allow up to a minute.
7. Check the browser's console for any uncaught errors during this flow.

This is the first time this phase's own stated goal ("type a line, hit enter, see the narrator's reply appear live") is verified in an actual browser rather than against test fakes — required per this project's own standing rule for UI changes.

- [ ] **Step 6: Stop the background servers**

```bash
kill %1 %2  # or find and kill the uvicorn/vite processes by port if job control isn't available in this shell
```

- [ ] **Step 7: Commit if anything was fixed during this check**

```bash
git add -A
git commit -m "fix: address issues found in Phase 4a full-verification check"
```

(Skip this step if Steps 1-2 passed clean and Step 5's browser check needed no code changes — nothing to commit.)
