"use client";

import { useEffect, useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";
import type { CharacterSheet, StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { CharacterSheetOverlay } from "./CharacterSheetOverlay";

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

// The viewer's own log lines are server-authored as "{player_id}: {text}" -
// everything else (narrator prose, other players) reads left-aligned, same
// split open-dungeon's own page.tsx draws between user/assistant messages.
function isOwnLine(line: string, playerId: string): boolean {
  return line.startsWith(`${playerId}: `);
}

function VitalsBand({ view, playerId }: { view: StateView; playerId: string }) {
  const characters = Object.entries(view.characters);
  return (
    <div className="flex flex-col gap-1.5 border-t border-stone-800 pt-2 text-xs text-stone-400">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {characters.map(([id, c]) => {
          const { initials, colorClass } = portraitFor(c.role, c.name);
          return (
            <span key={id} className={`inline-flex items-center gap-1.5 ${id === playerId ? "text-stone-100" : ""}`}>
              <span className={`flex size-5 items-center justify-center rounded text-[10px] font-semibold ${colorClass}`}>
                {initials}
              </span>
              {c.name} · {c.health}/{c.max_health} HP
              {c.armor > 0 && ` · ${c.armor} armor`}
              {c.conditions.length > 0 && ` · ${c.conditions.join(", ")}`}
            </span>
          );
        })}
      </div>
      {(view.location || view.scene_mood || view.in_combat) && (
        <div>
          {view.location && <span>{view.location}</span>}
          {view.location && view.scene_mood && " · "}
          {view.scene_mood && <span>{view.scene_mood}</span>}
          {view.in_combat && <span> · in combat{view.current_turn && ` (${view.current_turn}'s turn)`}</span>}
        </div>
      )}
      {view.active_objectives.length > 0 && <div>{view.active_objectives.join(" · ")}</div>}
    </div>
  );
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
  const [sheetOpen, setSheetOpen] = useState(false);

  const { view, error, send, readyState } = useNightwireSocket(
    connected ? sessionId : null,
    connected ? playerId : null,
  );

  // The only signal a sent action actually resolved is the next broadcast
  // this connection receives - the protocol has no per-request ack.
  useEffect(() => {
    setSending(false);
  }, [view]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        setSheetOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

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
              <div className="flex-1 space-y-3 overflow-y-auto">
                {view.log.map((line, i) =>
                  isOwnLine(line, playerId) ? (
                    <div key={i} className="ml-auto max-w-[85%]">
                      <div className="rounded-2xl rounded-br-md border border-stone-800/70 bg-stone-900/60 px-4 py-3 text-sm leading-6 text-stone-300">
                        <p className="whitespace-pre-wrap text-pretty">{line}</p>
                      </div>
                    </div>
                  ) : (
                    <p key={i} className="whitespace-pre-wrap text-pretty font-serif text-stone-100">
                      {line}
                    </p>
                  ),
                )}
              </div>

              <VitalsBand view={view} playerId={playerId} />

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

              {sheetOpen && "player_id" in view.characters[playerId] && (
                <CharacterSheetOverlay
                  character={view.characters[playerId] as CharacterSheet}
                  onClose={() => setSheetOpen(false)}
                />
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
