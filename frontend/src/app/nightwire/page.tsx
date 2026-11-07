"use client";

import { useEffect, useState } from "react";
import { ReadyState } from "react-use-websocket";
import { useNightwireSocket } from "@/lib/nightwire/useNightwireSocket";
import type { CharacterSheet } from "@/lib/nightwire/protocol";
import { CHROME } from "./chrome";
import { SkillPicker, STARTING_SKILL_POINTS } from "./SkillPicker";
import { AttributePicker, attributeBudgetRemaining, startingAttributes } from "./AttributePicker";
import { PlayScreen } from "./play/PlayScreen";
import { browserStore } from "@/lib/nightwire/safeStorage";
import { normalizeId } from "@/lib/nightwire/ids";

const LAST_GAME_KEY = "nightwire-last-game";
import "./theme.css";

const READY_STATE_LABEL: Record<ReadyState, string> = {
  [ReadyState.CONNECTING]: "Connecting…",
  [ReadyState.OPEN]: "Connected",
  [ReadyState.CLOSING]: "Closing…",
  [ReadyState.CLOSED]: "Disconnected",
  [ReadyState.UNINSTANTIATED]: "Idle",
};

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
  { value: "tsukumogami", label: "Tsukumogami", description: "An old machine that ran too long and woke - a vending machine, a ticket gate, a train announcer - now walking the street in a rented utsusemi shell." },
];


export default function NightwirePage() {
  const [sessionId, setSessionId] = useState("");
  const [playerId, setPlayerId] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [lifepath, setLifepath] = useState("");
  const [presentation, setPresentation] = useState<"" | "feminine" | "masculine" | "androgynous">("");
  const [skills, setSkills] = useState<Record<string, number>>({});
  const [attributes, setAttributes] = useState<Record<string, number>>({});
  const primaryAttribute = ROLES.find((r) => r.value === role)?.primaryAttribute ?? null;
  const mergedAttributes = { ...startingAttributes(primaryAttribute), ...attributes };
  const [connected, setConnected] = useState(false);
  const [connectHint, setConnectHint] = useState("");
  const [startingChrome, setStartingChrome] = useState("");
  const [approvingPortrait, setApprovingPortrait] = useState(false);
  const [portraitSkipped, setPortraitSkipped] = useState(false);
  // The portrait question belongs to making a character: a returning player (refresh, new tab) goes straight
  // into the game (dry run 2026-11-06: a refresh asked again after the player had skipped it).
  const [justJoined, setJustJoined] = useState(false);
  const [referencePhotos, setReferencePhotos] = useState<string[]>([]);

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
    setApprovingPortrait(false);
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [view, errorSeq]);

  // Remembered per browser, so a refresh goes straight back into the game (dry run 2026-11-06: a refresh lost
  // the session and asked for the IDs and the whole character form again).
  useEffect(() => {
    const saved = browserStore.getItem(LAST_GAME_KEY);
    if (!saved) return;
    try {
      const { session, player } = JSON.parse(saved) as { session: string; player: string };
      /* eslint-disable react-hooks/set-state-in-effect -- reading browser storage once after mount */
      setSessionId(session); setPlayerId(player); setConnected(true);
      /* eslint-enable react-hooks/set-state-in-effect */
    } catch { /* ignore a damaged entry */ }
  }, []);

  function handleConnect(event: React.FormEvent) {
    event.preventDefault();
    const session = normalizeId(sessionId), player = normalizeId(playerId);
    if (!session || !player) {
      setConnectHint("Enter a session ID (the same for everyone at the table) and your own player ID.");
      return;
    }
    setSessionId(session); setPlayerId(player); setConnectHint("");
    browserStore.setItem(LAST_GAME_KEY, JSON.stringify({ session, player }));
    setConnected(true);
  }

  function handleLeave() {
    browserStore.setItem(LAST_GAME_KEY, "");
    window.location.reload();
  }

  function handleJoin() {
    setJustJoined(true);
    send({
      type: "join",
      character: { player_id: playerId, name, role, lifepath, skills, attributes, ...(startingChrome ? { starting_chrome: startingChrome } : {}), ...(presentation ? { presentation } : {}) },
    });
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

  const me = view?.characters[playerId];
  const inPlay = me && "player_id" in me && (me.portrait_path || portraitSkipped || !justJoined);
  if (view && inPlay) {
    return <PlayScreen view={view} playerId={playerId} send={send} readyLabel={READY_STATE_LABEL[readyState]} error={error} errorSeq={errorSeq} onLeave={handleLeave} />;
  }

  return (
    <main className="nw-theme mx-auto flex min-h-dvh w-full max-w-2xl flex-col gap-4 p-6 lg:max-w-3xl xl:max-w-4xl 2xl:max-w-5xl">
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
          {connectHint && <p className="text-sm nw-text-danger" role="alert">{connectHint}</p>}
        </form>
      ) : (
        <>
          <p className="nw-hud text-xs nw-text-faint">
            {READY_STATE_LABEL[readyState]} · {sessionId} / {playerId} ·{" "}
            <button type="button" className="underline" onClick={handleLeave}>use a different session</button>
          </p>

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
              {lifepath === "tsukumogami" && (
                <p className="text-xs nw-text-muted">Selfhood 20 · shell lease +4 installments</p>
              )}
              <select className="nw-field" aria-label="Presentation" value={presentation} onChange={(e) => setPresentation(e.target.value as typeof presentation)}>
                <option value="">Presentation (optional)</option>
                <option value="feminine">Feminine</option>
                <option value="masculine">Masculine</option>
                <option value="androgynous">Androgynous</option>
              </select>
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
              <select className="nw-field" aria-label="Starting chrome" value={startingChrome} onChange={(e) => setStartingChrome(e.target.value)}>
                <option value="">No starting chrome</option>
                {CHROME.map((c) => (
                  <option key={c.id} value={c.id}>
                    {`${c.name} — ${c.effect} · ${lifepath === "tsukumogami" ? "no selfhood cost" : `−${c.humanity} humanity`} · ${c.installments} installments`}
                  </option>
                ))}
              </select>
              {(() => {
                // Playthrough 2026-11-07: a character joined with every point unspent and failed roll after roll.
                const attrLeft = attributeBudgetRemaining(mergedAttributes, primaryAttribute);
                const skillLeft = STARTING_SKILL_POINTS - Object.values(skills).reduce((a, b) => a + b, 0);
                return attrLeft > 0 || skillLeft > 0 ? (
                  <p className="text-sm nw-text-warn" role="note">
                    {`Unspent: ${attrLeft} attribute and ${skillLeft} skill points. They are what your rolls add to the die; skill points can also be spent later on your sheet.`}
                  </p>
                ) : null;
              })()}
              <button
                type="button"
                onClick={handleJoin}
                disabled={readyState !== ReadyState.OPEN || !name.trim() || !role || !lifepath}
                className="nw-btn-primary"
              >
                Join
              </button>
            </div>
          )}

          {error && <p className="text-sm nw-text-danger">{error}</p>}

          {view && "player_id" in view.characters[playerId] &&
            !(view.characters[playerId] as CharacterSheet).portrait_path &&
            !portraitSkipped && justJoined && (
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

        </>
      )}
    </main>
  );
}
