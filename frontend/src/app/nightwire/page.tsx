"use client";

import { useEffect, useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";
import type { CharacterSheet, RedactedCharacter, StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";
import { CharacterSheetOverlay } from "./CharacterSheetOverlay";
import { SkillPicker, STARTING_SKILL_POINTS } from "./SkillPicker";
import { AttributePicker, attributeBudgetRemaining, startingAttributes } from "./AttributePicker";
import "./theme.css";

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

// Downscales an uploaded reference photo client-side before sending it
// inline over the websocket - full phone-camera resolution buys nothing for
// a reference image and bloats the message (see docs/superpowers/specs/
// 2026-08-25-photo-reference-portrait-design.md).
async function fileToResizedDataUrl(file: File, maxDimension: number): Promise<string> {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, maxDimension / Math.max(bitmap.width, bitmap.height));
  const width = Math.round(bitmap.width * scale);
  const height = Math.round(bitmap.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d context unavailable");
  ctx.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", 0.85);
}

// Mirrors ruleset/roles.py and ruleset/lifepaths.py - same duplication
// pattern server/portrait.py's own _ROLE_VISUALS/_LIFEPATH_VISUALS already
// use for this exact key set, rather than a new REST endpoint for static
// reference data. Keep in sync if the ruleset's roster changes.
const ROLES: Array<{ value: string; label: string; description: string; primaryAttribute: string }> = [
  { value: "solo", label: "Solo", description: "Front-line combat specialist. Best attack rolls, highest Health, a passive Initiative/Awareness edge.", primaryAttribute: "reflexes" },
  { value: "netrunner", label: "Netrunner", description: "Hacking specialist. Bypasses locks, pulls data, and disables weapons/cameras/drones mid-combat.", primaryAttribute: "tech" },
  { value: "techie", label: "Techie", description: "Gear specialist. Repairs damaged equipment and cyberware, installs upgrades, crafts - keeps the party's equipment working, not a healer.", primaryAttribute: "tech" },
  { value: "fixer", label: "Fixer", description: "Social specialist. Negotiation, contacts, contraband access - talks past trouble instead of shooting through it.", primaryAttribute: "presence" },
];

const LIFEPATHS: Array<{ value: string; label: string; description: string }> = [
  { value: "corpo", label: "Corpo", description: "Came from megacorp life - contacts inside corporate structures, insider knowledge, expects to be listened to." },
  { value: "streetkid", label: "Streetkid", description: "Grew up in the sprawl - gang contacts, street cred, knows how things really work at ground level." },
  { value: "nomad", label: "Nomad", description: "Raised outside the city in a clan/family - vehicle know-how, an outsider's read on the corps, strong found-family loyalty." },
];

// Every spoken/acted log line is server-authored as "{who}: {text}" - either
// a real player_id for the player's own typed action (server/narration.py's
// `session.log.append(f"{player_id}: {action_text}")`) or an in-fiction
// character name for narrator-voiced dialogue (same file's segment loop:
// `f"{segment.speaker}: {segment.text}"`, speaker "narrator" itself getting
// no prefix at all - that's plain prose, the "narration" case below). A
// short "word(s): " prefix is dialogue by construction: the system prompt
// reserves the unprefixed form for the narrator's own prose, so this is
// safe to match on shape without a new protocol field for known speakers.
// Case isn't a signal here - the model doesn't always capitalize a
// role-based NPC name (observed live: "fixer: Rook, you don't just...").
const SPEAKER_LINE = /^([A-Za-z][A-Za-z0-9' -]{0,29}): ([\s\S]+)$/;

type LogEntry =
  | { kind: "own"; text: string }
  | { kind: "speaking"; text: string; name: string; character: CharacterSheet | RedactedCharacter | null }
  | { kind: "meta"; text: string }
  | { kind: "narration"; text: string };

function classifyLine(line: string, view: StateView, playerId: string): LogEntry {
  for (const [pid, character] of Object.entries(view.characters)) {
    const prefix = `${pid}: `;
    if (line.startsWith(prefix)) {
      const text = line.slice(prefix.length);
      return pid === playerId ? { kind: "own", text } : { kind: "speaking", text, name: character.name, character };
    }
  }
  if (BRACKET_LINE.test(line)) return { kind: "meta", text: line };
  const match = line.match(SPEAKER_LINE);
  if (match) {
    const [, name, text] = match;
    const own = view.characters[playerId];
    if (own && own.name === name) return { kind: "own", text };
    const teammate = Object.entries(view.characters).find(([pid, c]) => pid !== playerId && c.name === name);
    return { kind: "speaking", text, name, character: teammate ? teammate[1] : null };
  }
  return { kind: "narration", text: line };
}

// Cheap placeholder avatar next to a speech/action bubble - a real portrait
// when the viewer is allowed to see one (their own character only; teammates'
// portrait_path is redacted server-side, see server/views.py), initials
// otherwise. NPCs have no CharacterSheet at all, so they always get initials,
// colored off their own name since they have no role to hash instead.
function SpeakerAvatar({ name, character }: { name: string; character?: CharacterSheet | RedactedCharacter | null }) {
  const portraitPath = character && "portrait_path" in character ? character.portrait_path : null;
  if (portraitPath) {
    return (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={mediaUrl(portraitPath)} alt="" className="size-8 shrink-0 rounded-full object-cover" />
    );
  }
  const { initials, colorClass } = portraitFor(character?.role ?? name, name);
  return (
    <span className={`flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${colorClass}`}>
      {initials}
    </span>
  );
}

// Reuses the same [tag: value] bracket convention tool results already use
// in session.log - no new StateView field for image lines.
const IMAGE_LINE = /^\[image: (.+)\]$/;
// Same bracket-tag convention as IMAGE_LINE above, for synthesized narration audio.
const AUDIO_LINE = /^\[audio: (.+)\]$/;
// Catch-all for every other bracket-tagged system line ([initiative: ...],
// [tool: ...], [tool error: ...], [audio error: ...]) - rendered as compact
// HUD meta text instead of narration prose.
const BRACKET_LINE = /^\[.+\]$/;

function VitalsBand({ view, playerId }: { view: StateView; playerId: string }) {
  const characters = Object.entries(view.characters);
  return (
    <div className="nw-divider nw-hud flex flex-col gap-1.5 border-t pt-2 text-xs nw-text-muted">
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {characters.map(([id, c]) => {
          const { initials, colorClass } = portraitFor(c.role, c.name);
          const portraitPath = "portrait_path" in c ? c.portrait_path : null;
          return (
            <span
              key={id}
              className="inline-flex items-center gap-1.5"
              style={id === playerId ? { color: "var(--nw-text)" } : undefined}
            >
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
          {view.in_combat && (
            <span className="nw-text-danger"> · in combat{view.current_turn && ` (${view.current_turn}'s turn)`}</span>
          )}
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
  const [skills, setSkills] = useState<Record<string, number>>({});
  const [attributes, setAttributes] = useState<Record<string, number>>({});
  const primaryAttribute = ROLES.find((r) => r.value === role)?.primaryAttribute ?? null;
  const mergedAttributes = { ...startingAttributes(primaryAttribute), ...attributes };
  const [connected, setConnected] = useState(false);
  const [composerMode, setComposerMode] = useState<ComposerMode>("do");
  const [composerText, setComposerText] = useState("");
  const [sending, setSending] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [approvingPortrait, setApprovingPortrait] = useState(false);
  const [portraitSkipped, setPortraitSkipped] = useState(false);
  const [referencePhotos, setReferencePhotos] = useState<string[]>([]);
  const [combatActionPending, setCombatActionPending] = useState(false);

  const { view, error, errorSeq, send, readyState } = useNightwireSocket(
    connected ? sessionId : null,
    connected ? playerId : null,
  );

  // The only signal a sent action actually resolved is the next broadcast
  // this connection receives - the protocol has no per-request ack. Key on
  // errorSeq, not error: a repeated identical error string is Object.is-equal
  // and would otherwise leave the button stuck at "Generating..." on retry.
  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- syncing to an
     * external system (websocket broadcasts), not derivable during render. */
    setSending(false);
    setApprovingPortrait(false);
    setCombatActionPending(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [view, errorSeq]);

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
      character: { player_id: playerId, name, role, lifepath, skills, attributes },
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
    send({
      type: "approve_character",
      ...(referencePhotos.length > 0 ? { reference_photos: referencePhotos } : {}),
    });
    setApprovingPortrait(true);
  }

  async function handleReferencePhotosSelected(event: React.ChangeEvent<HTMLInputElement>) {
    const files = Array.from(event.target.files ?? []).slice(0, 2 - referencePhotos.length);
    event.target.value = "";
    for (const file of files) {
      try {
        const dataUrl = await fileToResizedDataUrl(file, 1024);
        setReferencePhotos((photos) => [...photos, dataUrl].slice(0, 2));
      } catch {
        // Unreadable/corrupt image - skip it, the upload is optional.
      }
    }
  }

  function handleRemoveReferencePhoto(index: number) {
    setReferencePhotos((photos) => photos.filter((_, i) => i !== index));
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
    <main className="nw-theme mx-auto flex h-dvh w-full max-w-2xl flex-col gap-4 p-6 lg:max-w-3xl xl:max-w-4xl 2xl:max-w-5xl">
      <h1 className="nw-heading text-lg">Nightwire — live feed</h1>

      {!connected ? (
        <form onSubmit={handleConnect} className="flex flex-col gap-2">
          <input
            className="nw-field"
            placeholder="Session ID"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          />
          <input
            className="nw-field"
            placeholder="Player ID"
            value={playerId}
            onChange={(e) => setPlayerId(e.target.value)}
          />
          <button type="submit" className="nw-btn-primary">
            Connect
          </button>
        </form>
      ) : (
        <>
          <p className="nw-hud text-xs nw-text-faint">{READY_STATE_LABEL[readyState]}</p>

          {!view && (
            <div className="flex flex-col gap-2">
              <input
                className="nw-field"
                placeholder="Name"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
              <select className="nw-field" value={role} onChange={(e) => { setRole(e.target.value); setAttributes({}); }}>
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
                <p className="text-xs nw-text-faint">{ROLES.find((r) => r.value === role)?.description}</p>
              )}
              <select className="nw-field" value={lifepath} onChange={(e) => setLifepath(e.target.value)}>
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
                <p className="text-xs nw-text-faint">{LIFEPATHS.find((l) => l.value === lifepath)?.description}</p>
              )}
              <AttributePicker
                attributes={attributes}
                primaryAttribute={primaryAttribute}
                remaining={attributeBudgetRemaining(mergedAttributes, primaryAttribute)}
                onIncrement={(attrName) =>
                  setAttributes((a) => ({
                    ...a,
                    [attrName]: (a[attrName] ?? mergedAttributes[attrName]) + 1,
                  }))
                }
                onDecrement={(attrName) =>
                  setAttributes((a) => ({
                    ...a,
                    [attrName]: (a[attrName] ?? mergedAttributes[attrName]) - 1,
                  }))
                }
              />
              <SkillPicker
                skills={skills}
                attributes={mergedAttributes}
                remaining={STARTING_SKILL_POINTS - Object.values(skills).reduce((a, b) => a + b, 0)}
                onIncrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: (s[name] ?? 0) + 1 }))
                }
                onDecrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: Math.max(0, (s[name] ?? 0) - 1) }))
                }
              />
              <button
                type="button"
                onClick={handleJoin}
                disabled={readyState !== ReadyState.OPEN}
                className="nw-btn-primary"
              >
                Join
              </button>
            </div>
          )}

          {error && <p className="text-sm nw-text-danger">{error}</p>}

          {view && "player_id" in view.characters[playerId] &&
            !(view.characters[playerId] as CharacterSheet).portrait_path &&
            !portraitSkipped && (
              <div className="nw-divider flex flex-col gap-2 rounded-lg border p-3 text-sm">
                <p className="nw-text-body">
                  {name} — {role} · {lifepath}. Generate a portrait before playing?
                </p>
                <div className="flex flex-col gap-1">
                  <label className="nw-hud text-xs nw-text-muted">
                    Optional — upload 1–2 photos of yourself to guide your portrait&apos;s likeness. Photos are sent once to generate your portrait and are not stored.
                  </label>
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp"
                    multiple
                    onChange={handleReferencePhotosSelected}
                    disabled={approvingPortrait || referencePhotos.length >= 2}
                    className="nw-field text-xs"
                  />
                  {referencePhotos.length > 0 && (
                    <div className="flex gap-2">
                      {referencePhotos.map((photo, i) => (
                        <div key={i} className="relative">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={photo} alt="" className="size-14 rounded object-cover" />
                          <button
                            type="button"
                            onClick={() => handleRemoveReferencePhoto(i)}
                            className="nw-btn-ghost absolute -right-1 -top-1 flex size-4 items-center justify-center rounded-full p-0 text-[10px] leading-none"
                          >
                            ×
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleApprovePortrait}
                    disabled={approvingPortrait}
                    className="nw-btn-primary flex-1"
                  >
                    {approvingPortrait ? "Generating…" : "Approve & Generate Portrait"}
                  </button>
                  <button
                    type="button"
                    onClick={() => setPortraitSkipped(true)}
                    disabled={approvingPortrait}
                    className="nw-btn-ghost"
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
                  if (entry.kind === "meta") {
                    return (
                      <p key={i} className="nw-hud text-xs nw-text-faint">
                        {entry.text}
                      </p>
                    );
                  }
                  return (
                    <p key={i} className="nw-prose whitespace-pre-wrap text-pretty">
                      {entry.text}
                    </p>
                  );
                })}
              </div>

              <VitalsBand view={view} playerId={playerId} />

              <div className="nw-hud flex items-center justify-between text-xs">
                {view.in_combat ? (
                  <>
                    <span className="nw-text-muted">
                      {view.is_your_turn ? "Your turn" : `${view.current_turn ?? "…"}'s turn`}
                    </span>
                    <div className="flex gap-2">
                      {view.is_your_turn && (
                        <button
                          type="button"
                          onClick={handleAdvanceTurn}
                          disabled={combatActionPending}
                          className="nw-btn-ghost py-1 text-xs"
                        >
                          End Turn
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={handleEndCombat}
                        disabled={combatActionPending}
                        className="nw-btn-danger py-1 text-xs"
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
                    className="nw-btn-ghost py-1 text-xs"
                  >
                    Roll Initiative
                  </button>
                )}
              </div>

              <form onSubmit={handleSendAction} className="flex flex-col gap-2">
                <div className="nw-divider flex rounded-lg border bg-black/20 p-0.5">
                  {COMPOSER_MODES.map((m) => (
                    <button
                      key={m.value}
                      type="button"
                      aria-pressed={composerMode === m.value}
                      onClick={() => setComposerMode(m.value)}
                      className="nw-tab flex-1"
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
                  className="nw-field resize-none outline-none disabled:cursor-not-allowed"
                />
                <button
                  type="submit"
                  disabled={sending || !composerText.trim()}
                  className="nw-btn-primary"
                >
                  {sending ? "Waiting for the GM…" : "Send"}
                </button>
              </form>

              {sheetOpen && "player_id" in view.characters[playerId] && (
                <CharacterSheetOverlay
                  character={view.characters[playerId] as CharacterSheet}
                  onClose={() => setSheetOpen(false)}
                  onAllocateSkill={(skill) => send({ type: "allocate_skill_points", skill, amount: 1 })}
                  onAllocateAttribute={(attribute) => send({ type: "allocate_attribute_points", attribute, amount: 1 })}
                />
              )}
            </>
          )}
        </>
      )}
    </main>
  );
}
