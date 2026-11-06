"use client";

import { useEffect, useState } from "react";
import type { CharacterSheet, ClientMessage, RedactedCharacter, RollResult, StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
import { AUDIO_LINE, IMAGE_LINE, ROLL_LINE, ROLL_PENDING_LINE, classifyLine } from "@/lib/nightwire/feed";
import { PendingRollCard, RollResultCard } from "../RollCard";
import { ChromeOfferCard } from "../ChromeOfferCard";

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

export const isAiOf = (view: StateView, pid: string) =>
  (view.characters[pid] as { lifepath?: string } | undefined)?.lifepath === "tsukumogami";

// A real portrait when the viewer is allowed to see one (their own character
// only; teammates' portrait_path is redacted server-side, see server/views.py),
// initials otherwise. NPCs have no CharacterSheet, so they always get initials.
function SpeakerAvatar({ name, character }: { name: string; character?: CharacterSheet | RedactedCharacter | null }) {
  const portraitPath = character && "portrait_path" in character ? character.portrait_path : null;
  if (portraitPath) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={mediaUrl(portraitPath)} alt="" className="size-8 shrink-0 rounded-full object-cover" />;
  }
  const { initials, colorClass } = portraitFor(character?.role ?? name, name);
  return (
    <span className={`flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${colorClass}`}>
      {initials}
    </span>
  );
}

export function FeedPanel({ view, playerId, send, error, errorSeq }: {
  view: StateView;
  playerId: string;
  send: (msg: ClientMessage) => void;
  error: string | null;
  errorSeq: number;
  sceneArt: boolean;
  onOpenGallery: (index: number) => void;
}) {
  const [composerMode, setComposerMode] = useState<ComposerMode>("do");
  const [composerText, setComposerText] = useState("");
  const [sending, setSending] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [combatActionPending, setCombatActionPending] = useState(false);

  // The only signal a sent action resolved is the next broadcast this
  // connection receives - the protocol has no per-request ack. Key on
  // errorSeq, not error: a repeated identical error string is Object.is-equal.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- syncing to an
     * external system (websocket broadcasts), not derivable during render. */
    setSending(false);
    setRolling(false);
    setCombatActionPending(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [view, errorSeq]);

  const myRollPending = Boolean(view.pending_rolls?.[playerId]);
  const lastRollIndex = view.log.findLastIndex((l) => ROLL_LINE.test(l));

  function handleSendAction(event: React.FormEvent) {
    event.preventDefault();
    if (!composerText.trim() || sending) return;
    send({ type: "action", text: formatComposerInput(composerMode, composerText) });
    setComposerText("");
    setSending(true);
  }

  function combat(message: ClientMessage) {
    send(message);
    setCombatActionPending(true);
  }

  return (
    <section aria-label="Conversation" className="relative flex h-full min-h-0 flex-col gap-3 p-4">
      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {view.log.map((line, i) => {
          if (ROLL_PENDING_LINE.test(line)) return null;
          const rollMatch = line.match(ROLL_LINE);
          if (rollMatch) {
            try {
              const roll = JSON.parse(rollMatch[1]) as RollResult;
              return <RollResultCard key={i} roll={roll} animate={i === lastRollIndex} isAi={isAiOf(view, roll.player_id)} />;
            } catch {
              return <p key={i} className="nw-hud text-xs nw-text-faint">{line}</p>;
            }
          }
          const imageMatch = line.match(IMAGE_LINE);
          if (imageMatch) {
            // eslint-disable-next-line @next/next/no-img-element
            return <img key={i} src={mediaUrl(imageMatch[1])} alt="" className="max-w-[85%] rounded-xl" />;
          }
          const audioMatch = line.match(AUDIO_LINE);
          if (audioMatch) {
            return <audio key={i} controls src={mediaUrl(audioMatch[1])} className="max-w-[85%]" />;
          }
          const entry = classifyLine(line, view, playerId);
          if (entry.kind === "own") {
            const ownCharacter = view.characters[playerId];
            return (
              <div key={i} className="ml-auto flex max-w-[85%] flex-row-reverse items-end gap-2">
                <SpeakerAvatar name={ownCharacter.name} character={ownCharacter} />
                <div className="nw-bubble-own px-4 py-3 text-sm leading-6">
                  <p className="whitespace-pre-wrap text-pretty">{entry.text}</p>
                </div>
              </div>
            );
          }
          if (entry.kind === "speaking") {
            return (
              <div key={i} className="mr-auto flex max-w-[85%] items-end gap-2">
                <SpeakerAvatar name={entry.name} character={entry.character} />
                <div>
                  <p className="nw-name-tag mb-1">{entry.name}</p>
                  <div className="nw-bubble-teammate px-4 py-3 text-sm leading-6">
                    <p className="whitespace-pre-wrap text-pretty">{entry.text}</p>
                  </div>
                </div>
              </div>
            );
          }
          if (entry.kind === "meta" && entry.text.startsWith("[image prompt")) return null; // server-log tuning line
          const notice = entry.kind === "meta" && ["[torite: ", "[selfhood: ", "[utsusemi: "].find((p) => entry.text.startsWith(p));
          if (notice) {
            return (
              <p key={i} className="nw-hud nw-torite text-xs">
                {notice === "[selfhood: " ? `Selfhood ${entry.text.slice(notice.length, -1)}` : entry.text.slice(notice.length, -1)}
              </p>
            );
          }
          if (entry.kind === "meta") {
            return <p key={i} className="nw-hud text-xs nw-text-faint">{entry.text}</p>;
          }
          return <p key={i} className="nw-prose whitespace-pre-wrap text-pretty">{entry.text}</p>;
        })}
        {view.pending_chrome_offers?.[playerId] && (
          <ChromeOfferCard
            chromeId={view.pending_chrome_offers[playerId]}
            isAi={isAiOf(view, playerId)}
            onAccept={() => send({ type: "accept_chrome" })}
            onDecline={() => send({ type: "decline_chrome" })}
          />
        )}
        {Object.values(view.pending_rolls ?? {}).map((roll) => (
          <PendingRollCard
            key={roll.player_id}
            roll={roll}
            isMine={roll.player_id === playerId}
            isAi={isAiOf(view, playerId)}
            onRoll={(overclock) => {
              setRolling(true);
              send({ type: "roll", ...(overclock ? { overclock } : {}) });
            }}
            rolling={rolling}
          />
        ))}
      </div>

      {error && <p className="text-sm nw-text-danger">{error}</p>}

      <div className="nw-hud flex items-center justify-between text-xs">
        {view.in_combat ? (
          <>
            <span className="nw-text-muted">{view.is_your_turn ? "Your turn" : `${view.current_turn ?? "…"}'s turn`}</span>
            <div className="flex gap-2">
              {view.is_your_turn && (
                <button type="button" onClick={() => combat({ type: "advance_turn" })} disabled={combatActionPending} className="nw-btn-ghost py-1 text-xs">
                  End Turn
                </button>
              )}
              <button type="button" onClick={() => combat({ type: "end_combat" })} disabled={combatActionPending} className="nw-btn-danger py-1 text-xs">
                End Combat
              </button>
            </div>
          </>
        ) : (
          <button type="button" onClick={() => combat({ type: "roll_initiative" })} disabled={combatActionPending} className="nw-btn-ghost py-1 text-xs">
            Roll Initiative
          </button>
        )}
      </div>

      <form onSubmit={handleSendAction} className="flex flex-col gap-2">
        <div className="nw-divider flex rounded-lg border bg-black/20 p-0.5">
          {COMPOSER_MODES.map((m) => (
            <button key={m.value} type="button" aria-pressed={composerMode === m.value} onClick={() => setComposerMode(m.value)} className="nw-tab flex-1">
              {m.label}
            </button>
          ))}
        </div>
        <textarea
          rows={2}
          value={composerText}
          onChange={(e) => setComposerText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) e.currentTarget.form?.requestSubmit();
          }}
          placeholder={myRollPending ? "Roll first" : COMPOSER_MODES.find((m) => m.value === composerMode)?.placeholder}
          disabled={sending || myRollPending}
          className="nw-field resize-none outline-none disabled:cursor-not-allowed"
        />
        <button type="submit" disabled={sending || myRollPending || !composerText.trim()} className="nw-btn-primary">
          {sending ? "Waiting for the GM…" : "Send"}
        </button>
      </form>
    </section>
  );
}
