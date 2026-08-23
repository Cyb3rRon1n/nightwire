"use client";

import { useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";

const READY_STATE_LABEL: Record<ReadyState, string> = {
  [ReadyState.CONNECTING]: "Connecting…",
  [ReadyState.OPEN]: "Connected",
  [ReadyState.CLOSING]: "Closing…",
  [ReadyState.CLOSED]: "Disconnected",
  [ReadyState.UNINSTANTIATED]: "Idle",
};

export default function NightwirePage() {
  const [sessionId, setSessionId] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [lifepath, setLifepath] = useState("");
  const [connected, setConnected] = useState(false);

  const { view, error, send, readyState } = useNightwireSocket(
    connected ? sessionId : null,
    connected ? playerId : null,
  );

  function handleConnect(event: React.FormEvent) {
    event.preventDefault();
    if (!sessionId.trim() || !playerId.trim()) return;
    setConnected(true);
  }

  function handleJoin() {
    send({
      type: "join",
      character: { player_id: playerId, name, role, lifepath },
    });
  }

  return (
    <main className="mx-auto flex h-dvh w-full max-w-2xl flex-col gap-4 p-6 text-stone-100">
      <h1 className="text-lg font-semibold">Nightwire — live feed</h1>

      {!connected ? (
        <form onSubmit={handleConnect} className="flex flex-col gap-2">
          <input
            className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm"
            placeholder="Session ID"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          />
          <input
            className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm"
            placeholder="Player ID"
            value={playerId}
            onChange={(e) => setPlayerId(e.target.value)}
          />
          <button
            type="submit"
            className="rounded bg-amber-200 px-3 py-2 text-sm font-medium text-stone-950"
          >
            Connect
          </button>
        </form>
      ) : (
        <>
          <p className="text-xs text-stone-500">{READY_STATE_LABEL[readyState]}</p>

          {!view && (
            <div className="flex flex-col gap-2">
              <input
                className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm"
                placeholder="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <input
                className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm"
                placeholder="Role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              />
              <input
                className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm"
                placeholder="Lifepath"
                value={lifepath}
                onChange={(e) => setLifepath(e.target.value)}
              />
              <button
                type="button"
                onClick={handleJoin}
                disabled={readyState !== ReadyState.OPEN}
                className="rounded bg-amber-200 px-3 py-2 text-sm font-medium text-stone-950 disabled:opacity-50"
              >
                Join
              </button>
            </div>
          )}

          {error && <p className="text-sm text-red-400">{error}</p>}

          {view && (
            <div className="flex-1 space-y-1 overflow-y-auto text-sm">
              {view.log.map((line, i) => (
                <p key={i} className="whitespace-pre-wrap text-stone-300">
                  {line}
                </p>
              ))}
            </div>
          )}
        </>
      )}
    </main>
  );
}
