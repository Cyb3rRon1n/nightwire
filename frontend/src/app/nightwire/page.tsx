"use client";

import { useEffect, useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";

const READY_STATE_LABEL: Record<ReadyState, string> = {
  [ReadyState.CONNECTING]: "Connecting…",
  [ReadyState.OPEN]: "Connected",
  [ReadyState.CLOSING]: "Closing…",
  [ReadyState.CLOSED]: "Disconnected",
  [ReadyState.UNINSTANTIATED]: "Idle",
};

// Client-side text transform only, no protocol-level mode field - same
// pattern as open-dungeon's own Do/Say/Story composer (frontend/src/app/page.tsx).
type ComposerMode = "do" | "say" | "think";

const COMPOSER_MODES: Array<{ value: ComposerMode; label: string; placeholder: string }> = [
  { value: "do", label: "Do", placeholder: "What do you do?" },
  { value: "say", label: "Say", placeholder: "What do you say?" },
  { value: "think", label: "Think", placeholder: "What do you think?" },
];

function formatComposerInput(mode: ComposerMode, text: string): string {
  const trimmed = text.trim();
  if (mode === "do") return `> ${trimmed}`;
  const quoted = /^["'].*["']$/.test(trimmed) ? trimmed : `"${trimmed}"`;
  return mode === "say" ? `> You say ${quoted}` : `> You think ${quoted}`;
}

export default function NightwirePage() {
  const [sessionId, setSessionId] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [lifepath, setLifepath] = useState("");
  const [connected, setConnected] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("do");
  const [composerText, setComposerText] = useState("");
  const [sending, setSending] = useState(false);

  const { view, error, send, readyState } = useNightwireSocket(
    connected ? sessionId : null,
    connected ? playerId : null,
  );

  // The only signal a sent action actually resolved is the next broadcast
  // this connection receives - the protocol has no per-request ack.
  useEffect(() => {
    setSending(false);
  }, [view]);

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

  function handleSendAction(event: React.FormEvent) {
    event.preventDefault();
    if (!composerText.trim() || sending) return;
    send({ type: "action", text: formatComposerInput(composerMode, composerText) });
    setComposerText("");
    setSending(true);
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
            <>
              <div className="flex-1 space-y-1 overflow-y-auto text-sm">
                {view.log.map((line, i) => (
                  <p key={i} className="whitespace-pre-wrap text-stone-300">
                    {line}
                  </p>
                ))}
              </div>

              <form onSubmit={handleSendAction} className="flex flex-col gap-2">
                <div className="flex rounded-lg border border-stone-800 bg-stone-950 p-0.5">
                  {COMPOSER_MODES.map((m) => (
                    <button
                      key={m.value}
                      type="button"
                      aria-pressed={composerMode === m.value}
                      onClick={() => setComposerMode(m.value)}
                      className={`flex-1 rounded-md px-2.5 py-1 text-xs font-medium text-stone-400 hover:text-stone-200 ${
                        composerMode === m.value ? "bg-stone-800 text-stone-100" : ""
                      }`}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>
                <textarea
                  rows={2}
                  value={composerText}
                  onChange={(e) => setComposerText(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                      e.currentTarget.form?.requestSubmit();
                    }
                  }}
                  placeholder={COMPOSER_MODES.find((m) => m.value === composerMode)?.placeholder}
                  disabled={sending}
                  className="resize-none rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm outline-none placeholder:text-stone-600 disabled:cursor-not-allowed disabled:text-stone-600"
                />
                <button
                  type="submit"
                  disabled={sending || !composerText.trim()}
                  className="rounded bg-amber-200 px-3 py-2 text-sm font-medium text-stone-950 disabled:opacity-50"
                >
                  {sending ? "Waiting for the GM…" : "Send"}
                </button>
              </form>
            </>
          )}
        </>
      )}
    </main>
  );
}
