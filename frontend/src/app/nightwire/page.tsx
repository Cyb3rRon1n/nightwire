"use client";

import { useEffect, useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";
import type { CharacterSheet, StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
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

// Mirrors ruleset/roles.py and ruleset/lifepaths.py - same duplication
// pattern server/portrait.py's own _ROLE_VISUALS/_LIFEPATH_VISUALS already
// use for this exact key set, rather than a new REST endpoint for static
// reference data. Keep in sync if the ruleset's roster changes.
const ROLES: Array<{ value: string; label: string; description: string }> = [
  { value: "solo", label: "Solo", description: "Front-line combat specialist. Best attack rolls, highest Health, a passive Initiative/Awareness edge." },
  { value: "netrunner", label: "Netrunner", description: "Hacking specialist. Bypasses locks, pulls data, and disables weapons/cameras/drones mid-combat." },
  { value: "techie", label: "Techie", description: "Gear specialist. Repairs damaged equipment and cyberware, installs upgrades, crafts - keeps the party's equipment working, not a healer." },
  { value: "fixer", label: "Fixer", description: "Social specialist. Negotiation, contacts, contraband access - talks past trouble instead of shooting through it." },
];

const LIFEPATHS: Array<{ value: string; label: string; description: string }> = [
  { value: "corpo", label: "Corpo", description: "Came from megacorp life - contacts inside corporate structures, insider knowledge, expects to be listened to." },
  { value: "streetkid", label: "Streetkid", description: "Grew up in the sprawl - gang contacts, street cred, knows how things really work at ground level." },
  { value: "nomad", label: "Nomad", description: "Raised outside the city in a clan/family - vehicle know-how, an outsider's read on the corps, strong found-family loyalty." },
];

// The viewer's own log lines are server-authored as "{player_id}: {text}" -
// same split open-dungeon's own page.tsx draws between user/assistant messages.
function isOwnLine(line: string, playerId: string): boolean {
  return line.startsWith(`${playerId}: `);
}

// A teammate's own action lines are server-authored the same way
// ("{their_player_id}: {text}") - every other party member's id is a known,
// client-visible key of view.characters, so this is distinguishable from
// narrator prose (including NPC "Speaker: text" segments, which are keyed
// by in-fiction name, not a real player_id) without any new protocol field.
function otherPlayerName(line: string, view: StateView, playerId: string): string | null {
  for (const [pid, character] of Object.entries(view.characters)) {
    if (pid !== playerId && line.startsWith(`${pid}: `)) return character.name;
  }
  return null;
}

// Reuses the same [tag: value] bracket convention tool results already use
// in session.log - no new StateView field for image lines.
const IMAGE_LINE = /^\[image: (.+)\]$/;
// Same bracket-tag convention as IMAGE_LINE above, for synthesized narration audio.
const AUDIO_LINE = /^\[audio: (.+)\]$/;

function VitalsBand({ view, playerId }: { view: StateView; playerId: string }) {
  const characters = Object.entries(view.characters);
  return (
    <div className="flex flex-col gap-1.5 border-t border-stone-800 pt-2 text-xs text-stone-400">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {characters.map(([id, c]) => {
          const { initials, colorClass } = portraitFor(c.role, c.name);
          const portraitPath = "portrait_path" in c ? c.portrait_path : null;
          return (
            <span key={id} className={`inline-flex items-center gap-1.5 ${id === playerId ? "text-stone-100" : ""}`}>
              {portraitPath ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={mediaUrl(portraitPath)} alt="" className="size-5 rounded object-cover" />
              ) : (
                <span className={`flex size-5 items-center justify-center rounded text-[10px] font-semibold ${colorClass}`}>
                  {initials}
                </span>
              )}
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
  const [approvingPortrait, setApprovingPortrait] = useState(false);
  const [portraitSkipped, setPortraitSkipped] = useState(false);
  const [combatActionPending, setCombatActionPending] = useState(false);

  const { view, error, send, readyState } = useNightwireSocket(
    connected ? sessionId : null,
    connected ? playerId : null,
  );

  // The only signal a sent action actually resolved is the next broadcast
  // this connection receives - the protocol has no per-request ack.
  useEffect(() => {
    setSending(false);
    setApprovingPortrait(false);
    setCombatActionPending(false);
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

  function handleApprovePortrait() {
    send({ type: "approve_character" });
    setApprovingPortrait(true);
  }

  function handleRollInitiative() {
    send({ type: "roll_initiative" });
    setCombatActionPending(true);
  }

  function handleAdvanceTurn() {
    send({ type: "advance_turn" });
    setCombatActionPending(true);
  }

  function handleEndCombat() {
    send({ type: "end_combat" });
    setCombatActionPending(true);
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
              <select
                className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm text-stone-100"
                value={role}
                onChange={(e) => setRole(e.target.value)}
              >
                <option value="" disabled>
                  Role
                </option>
                {ROLES.map((r) => (
                  <option key={r.value} value={r.value}>
                    {r.label}
                  </option>
                ))}
              </select>
              {role && (
                <p className="text-xs text-stone-500">{ROLES.find((r) => r.value === role)?.description}</p>
              )}
              <select
                className="rounded border border-stone-700 bg-stone-900 px-3 py-2 text-sm text-stone-100"
                value={lifepath}
                onChange={(e) => setLifepath(e.target.value)}
              >
                <option value="" disabled>
                  Lifepath
                </option>
                {LIFEPATHS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
              {lifepath && (
                <p className="text-xs text-stone-500">{LIFEPATHS.find((l) => l.value === lifepath)?.description}</p>
              )}
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

          {view && "player_id" in view.characters[playerId] &&
            !(view.characters[playerId] as CharacterSheet).portrait_path &&
            !portraitSkipped && (
              <div className="flex flex-col gap-2 rounded-lg border border-stone-800 p-3 text-sm">
                <p className="text-stone-300">
                  {name} — {role} · {lifepath}. Generate a portrait before playing?
                </p>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleApprovePortrait}
                    disabled={approvingPortrait}
                    className="flex-1 rounded bg-amber-200 px-3 py-2 text-sm font-medium text-stone-950 disabled:opacity-50"
                  >
                    {approvingPortrait ? "Generating…" : "Approve & Generate Portrait"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPortraitSkipped(true)}
                    disabled={approvingPortrait}
                    className="rounded bg-stone-900 px-3 py-2 text-sm text-stone-400 hover:bg-stone-800 disabled:opacity-50"
                  >
                    Skip for now
                  </button>
                </div>
              </div>
            )}

          {view && (
            <>
              <div className="flex-1 space-y-3 overflow-y-auto">
                {view.log.map((line, i) => {
                  const imageMatch = line.match(IMAGE_LINE);
                  if (imageMatch) {
                    // eslint-disable-next-line @next/next/no-img-element
                    return <img key={i} src={mediaUrl(imageMatch[1])} alt="" className="max-w-[85%] rounded-xl" />;
                  }
                  const audioMatch = line.match(AUDIO_LINE);
                  if (audioMatch) {
                    return <audio key={i} controls src={mediaUrl(audioMatch[1])} className="max-w-[85%]" />;
                  }
                  if (isOwnLine(line, playerId)) {
                    return (
                      <div key={i} className="ml-auto max-w-[85%]">
                        <div className="rounded-2xl rounded-br-md border border-stone-800/70 bg-stone-900/60 px-4 py-3 text-sm leading-6 text-stone-300">
                          <p className="whitespace-pre-wrap text-pretty">{line}</p>
                        </div>
                      </div>
                    );
                  }
                  const teammate = otherPlayerName(line, view, playerId);
                  if (teammate) {
                    return (
                      <div key={i} className="mr-auto max-w-[85%]">
                        <p className="mb-1 text-xs text-stone-500">{teammate}</p>
                        <div className="rounded-2xl rounded-bl-md border border-stone-800/40 bg-stone-900/30 px-4 py-3 text-sm leading-6 text-stone-400">
                          <p className="whitespace-pre-wrap text-pretty">{line}</p>
                        </div>
                      </div>
                    );
                  }
                  return (
                    <p key={i} className="whitespace-pre-wrap text-pretty font-serif text-stone-100">
                      {line}
                    </p>
                  );
                })}
              </div>

              <VitalsBand view={view} playerId={playerId} />

              <div className="flex items-center justify-between text-xs">
                {view.in_combat ? (
                  <>
                    <span className="text-stone-400">
                      {view.is_your_turn ? "Your turn" : `${view.current_turn ?? "…"}'s turn`}
                    </span>
                    <div className="flex gap-2">
                      {view.is_your_turn && (
                        <button
                          type="button"
                          onClick={handleAdvanceTurn}
                          disabled={combatActionPending}
                          className="rounded bg-stone-900 px-2.5 py-1 font-medium text-stone-200 hover:bg-stone-800 disabled:opacity-50"
                        >
                          End Turn
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={handleEndCombat}
                        disabled={combatActionPending}
                        className="rounded bg-stone-900 px-2.5 py-1 font-medium text-red-300 hover:bg-stone-800 disabled:opacity-50"
                      >
                        End Combat
                      </button>
                    </div>
                  </>
                ) : (
                  <button
                    type="button"
                    onClick={handleRollInitiative}
                    disabled={combatActionPending}
                    className="rounded bg-stone-900 px-2.5 py-1 font-medium text-stone-200 hover:bg-stone-800 disabled:opacity-50"
                  >
                    Roll Initiative
                  </button>
                )}
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
