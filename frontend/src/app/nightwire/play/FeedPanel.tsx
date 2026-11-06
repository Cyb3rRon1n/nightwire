"use client";

import { useEffect, useRef, useState } from "react";
import type { CharacterSheet, ClientMessage, RedactedCharacter, RollResult, StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
import { AUDIO_LINE, IMAGE_LINE, ROLL_LINE, ROLL_PENDING_LINE, classifyLine, groupStarts, isPlayerFacing, sceneImages, speakerKey } from "@/lib/nightwire/feed";
import { npcColour } from "@/lib/nightwire/npcColour";
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

// server/narration.py rejects actions over 1000 characters, and the Say/Think
// wrapper below adds up to 14 ('> You think ""'), so the box stops at 980.
const MAX_INPUT = 980;
const COUNTER_FROM = 800;

function formatComposerInput(mode: ComposerMode, text: string): string {
  const trimmed = text.trim();
  if (mode === "do") return `> ${trimmed}`;
  const quoted = /^["'].*["']$/.test(trimmed) ? trimmed : `"${trimmed}"`;
  return mode === "say" ? `> You say ${quoted}` : `> You think ${quoted}`;
}

const isAiOf = (view: StateView, pid: string) =>
  (view.characters[pid] as { lifepath?: string } | undefined)?.lifepath === "tsukumogami";

const reducedMotion = () => typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// A real portrait when the viewer may see one (their own character only;
// teammates' portrait_path is redacted server-side, see server/views.py),
// initials otherwise. NPCs have no CharacterSheet, so they always get initials.
function SpeakerAvatar({ name, character, colour }: { name: string; character?: CharacterSheet | RedactedCharacter | null; colour: string }) {
  const portraitPath = character && "portrait_path" in character ? character.portrait_path : null;
  const frame = { border: `1.5px solid ${colour}` };
  if (portraitPath) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={mediaUrl(portraitPath)} alt="" className="size-10 shrink-0 object-cover" style={frame} />;
  }
  const { initials } = portraitFor(character?.role ?? name, name);
  return (
    <span className="flex size-10 shrink-0 items-center justify-center text-xs font-semibold" style={{ ...frame, color: colour, background: "#0b0d11" }}>
      {initials}
    </span>
  );
}

// Keeps the old image under the new one until it has loaded, then fades it in.
function SceneBackdrop({ src }: { src: string }) {
  const [shown, setShown] = useState(src);
  const [incoming, setIncoming] = useState<string | null>(null);
  if (src !== shown && src !== incoming) setIncoming(src); // derived state, set during render
  const settle = () => {
    if (incoming) setShown(incoming);
    setIncoming(null);
  };
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="nw-scene-bg" src={shown} alt="" />
      {incoming && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          className="nw-scene-bg"
          src={incoming}
          alt=""
          style={{ opacity: 0 }}
          onLoad={(e) => {
            if (reducedMotion()) settle();
            else e.currentTarget.style.opacity = "1";
          }}
          onTransitionEnd={settle}
        />
      )}
    </>
  );
}

export function FeedPanel({ view, playerId, send, error, errorSeq, sceneArt, onOpenGallery, compact = false }: {
  view: StateView;
  playerId: string;
  send: (msg: ClientMessage) => void;
  error: string | null;
  errorSeq: number;
  sceneArt: boolean;
  onOpenGallery: (index: number) => void;
  compact?: boolean;
}) {
  const [composerMode, setComposerMode] = useState<ComposerMode>("do");
  const [composerText, setComposerText] = useState("");
  const [sending, setSending] = useState(false);
  const [rolling, setRolling] = useState(false);
  const [combatActionPending, setCombatActionPending] = useState(false);
  const listRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const [pinned, setPinned] = useState(true);
  const pinnedRef = useRef(true);
  const [unseen, setUnseen] = useState(false);

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

  // Stick to the newest line unless the player has scrolled up to read.
  useEffect(() => {
    const el = listRef.current;
    if (!el) return;
    if (pinned) el.scrollTop = el.scrollHeight;
    else setUnseen(true); // eslint-disable-line react-hooks/set-state-in-effect -- reacting to new socket lines
  }, [view.log.length, sending]); // eslint-disable-line react-hooks/exhaustive-deps -- only new lines matter

  // Images load after the jump to the bottom and push the newest lines out of
  // view, so a loading image re-pins the feed if the player was at the bottom.
  function stickToBottom() {
    const el = listRef.current;
    if (el && pinnedRef.current) el.scrollTop = el.scrollHeight;
  }

  function onScroll() {
    const el = listRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
    pinnedRef.current = atBottom;
    setPinned(atBottom);
    if (atBottom) setUnseen(false);
  }

  const me = view.characters[playerId];
  const myRollPending = Boolean(view.pending_rolls?.[playerId]);
  const lastRollIndex = view.log.findLastIndex((l) => ROLL_LINE.test(l));
  const entries = view.log.map((line) => classifyLine(line, view, playerId));
  // Images and rolls end a speaker's run; lines that render nothing (or only an audio player) don't.
  const starts = groupStarts(entries.map((entry, i) => {
    const line = view.log[i];
    if (IMAGE_LINE.test(line) || ROLL_LINE.test(line)) return null;
    if (AUDIO_LINE.test(line) || ROLL_PENDING_LINE.test(line) || (entry.kind === "meta" && !isPlayerFacing(entry.text))) return undefined;
    return speakerKey(entry);
  }));
  const images = sceneImages(view.log);
  const latest = images.at(-1) ?? null;
  const backdrop = sceneArt && latest && !compact;
  let imageIndex = -1;

  function handleSendAction(event: React.FormEvent) {
    event.preventDefault();
    if (!composerText.trim() || sending) return;
    send({ type: "action", text: formatComposerInput(composerMode, composerText) });
    setComposerText("");
    setSending(true);
    setPinned(true);
    pinnedRef.current = true;
    if (inputRef.current) inputRef.current.style.height = "auto";
  }

  function combat(message: ClientMessage) {
    send(message);
    setCombatActionPending(true);
  }

  return (
    <section aria-label="Conversation" className="relative flex h-full min-h-0 flex-col overflow-hidden">
      {backdrop && <SceneBackdrop src={mediaUrl(latest)} />}
      {backdrop && <div className="nw-scene-scrim" aria-hidden="true" />}

      {compact && sceneArt && latest && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={mediaUrl(latest)} alt="" className="w-full shrink-0 object-cover" style={{ height: 150, borderBottom: "1.5px solid var(--nw-frame-cool)" }} />
      )}
      <div className={backdrop ? "nw-scene-title" : "nw-scene-title nw-scene-title-plain"}>
        <h1>{view.location ?? "Kuroshio"}</h1>
        <p className="nw-session-id">SES {view.session_id}{view.scene_mood ? ` · ${view.scene_mood.toUpperCase()}` : ""}</p>
      </div>

      <div ref={listRef} onScroll={onScroll} className="nw-feed relative min-h-0 flex-1 overflow-y-auto px-4 pb-4 sm:px-8">
        {view.log.map((line, i) => {
          if (ROLL_PENDING_LINE.test(line)) return null;
          const rollMatch = line.match(ROLL_LINE);
          if (rollMatch) {
            try {
              const roll = JSON.parse(rollMatch[1]) as RollResult;
              return <RollResultCard key={i} roll={roll} animate={i === lastRollIndex} isAi={isAiOf(view, roll.player_id)} />;
            } catch {
              return <p key={i} className="nw-hud text-xs" style={{ color: "#9aa3ad" }}>{line}</p>;
            }
          }
          const imageMatch = line.match(IMAGE_LINE);
          if (imageMatch) {
            const index = ++imageIndex;
            return (
              <button key={i} type="button" className="nw-scene-frame" onClick={() => onOpenGallery(index)} aria-label={`Open scene image ${index + 1} in the gallery`}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={mediaUrl(imageMatch[1])} alt="" className="block w-full" onLoad={stickToBottom} />
              </button>
            );
          }
          const audioMatch = line.match(AUDIO_LINE);
          if (audioMatch) return <audio key={i} controls src={mediaUrl(audioMatch[1])} className="w-full" />;

          const entry = entries[i];
          if (entry.kind === "own") {
            return (
              <div key={i} className="nw-line-own">
                {starts[i] ? <SpeakerAvatar name={me.name} character={me} colour="var(--nw-cyan)" /> : <span className="nw-avatar-gap" />}
                <div>
                  {starts[i] && <div className="nw-speaker" style={{ color: "var(--nw-cyan)" }}>{me.name}</div>}
                  <div className="nw-speech" style={{ color: "#c9f6f7" }}>{entry.text}</div>
                </div>
              </div>
            );
          }
          if (entry.kind === "speaking") {
            const teammate = entry.character !== null;
            const colour = teammate ? "var(--nw-cyan)" : npcColour(entry.name);
            return (
              <div key={i} className={teammate ? "nw-line-own nw-line-teammate" : "nw-line-npc"}>
                {starts[i] ? <SpeakerAvatar name={entry.name} character={entry.character} colour={colour} /> : <span className="nw-avatar-gap" />}
                <div>
                  {starts[i] && <div className="nw-speaker" style={{ color: colour }}>{entry.name}</div>}
                  <div className="nw-speech" style={{ color: teammate ? "#c9f6f7" : colour }}>{entry.text}</div>
                </div>
              </div>
            );
          }
          if (entry.kind === "meta" && !isPlayerFacing(entry.text)) return null;
          const notice = entry.kind === "meta" && ["[torite: ", "[selfhood: ", "[utsusemi: "].find((p) => entry.text.startsWith(p));
          if (notice) {
            return (
              <p key={i} className="nw-system">
                {notice === "[selfhood: " ? `Selfhood ${entry.text.slice(notice.length, -1)}` : entry.text.slice(notice.length, -1)}
              </p>
            );
          }
          if (entry.kind === "meta") return <p key={i} className="nw-hud text-center text-xs" style={{ color: "#9aa3ad" }}>{entry.text.slice(1, -1)}</p>;
          return <p key={i} className="nw-line-narrator">{entry.text}</p>;
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
        {sending && (
          <div className="nw-typing" role="status" aria-live="polite">
            <span>NARRATOR</span><i /><i /><i />
          </div>
        )}
      </div>

      {unseen && (
        <button
          type="button"
          className="nw-new-lines"
          onClick={() => {
            const el = listRef.current;
            if (el) el.scrollTop = el.scrollHeight;
          }}
        >
          NEW LINES ↓
        </button>
      )}

      <form onSubmit={handleSendAction} className="nw-composer relative flex shrink-0 flex-col gap-2">
        {error && <p className="text-sm" style={{ color: "#ff8a80" }}>{error}</p>}
        <div className="flex flex-wrap items-center gap-2">
          {COMPOSER_MODES.map((m) => (
            <button key={m.value} type="button" aria-pressed={composerMode === m.value} onClick={() => setComposerMode(m.value)} className="nw-chip">
              {m.label}
            </button>
          ))}
          <span className="flex-1" />
          {view.in_combat ? (
            <>
              <span className="nw-hud text-xs" style={{ color: "#9aa3ad" }}>{view.is_your_turn ? "YOUR TURN" : `${view.current_turn ?? "…"}'S TURN`}</span>
              {view.is_your_turn && (
                <button type="button" onClick={() => combat({ type: "advance_turn" })} disabled={combatActionPending} className="nw-chip">End turn</button>
              )}
              <button type="button" onClick={() => combat({ type: "end_combat" })} disabled={combatActionPending} className="nw-chip" style={{ borderColor: "var(--nw-red)", color: "#ff8a80" }}>End combat</button>
            </>
          ) : (
            <button type="button" onClick={() => combat({ type: "roll_initiative" })} disabled={combatActionPending} className="nw-chip">Roll initiative</button>
          )}
        </div>
        <div className="flex items-end gap-2">
          <span aria-hidden="true" className="nw-prompt">&gt;</span>
          <textarea
            ref={inputRef}
            rows={1}
            maxLength={MAX_INPUT}
            value={composerText}
            aria-label="Your action"
            onChange={(e) => {
              setComposerText(e.target.value);
              e.target.style.height = "auto";
              e.target.style.height = `${e.target.scrollHeight}px`; // CSS max-height caps it at 4 lines
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                e.currentTarget.form?.requestSubmit();
              }
            }}
            placeholder={myRollPending ? "Roll first" : COMPOSER_MODES.find((m) => m.value === composerMode)?.placeholder}
            disabled={sending || myRollPending}
          />
          <button type="submit" className="nw-send" disabled={sending || myRollPending || !composerText.trim()}>SEND</button>
        </div>
        {composerText.length > COUNTER_FROM && (
          <p className="nw-hud text-right text-xs" style={{ color: composerText.length >= MAX_INPUT ? "#ff8a80" : "#9aa3ad" }}>
            {composerText.length} / {MAX_INPUT}
          </p>
        )}
      </form>
    </section>
  );
}
