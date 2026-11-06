import type { CharacterSheet, RedactedCharacter, StateView } from "./protocol";

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
export const SPEAKER_LINE = /^([A-Za-z][A-Za-z0-9' -]{0,29}): ([\s\S]+)$/;

// Reuses the same [tag: value] bracket convention tool results already use
// in session.log - no new StateView field for image lines.
export const IMAGE_LINE = /^\[image: (.+)\]$/;
export const ROLL_LINE = /^\[roll: (.+)\]$/;
export const ROLL_PENDING_LINE = /^\[roll pending: .+\]$/;
// Same bracket-tag convention as IMAGE_LINE above, for synthesized narration audio.
export const AUDIO_LINE = /^\[audio: (.+)\]$/;
// Catch-all for every other bracket-tagged system line ([initiative: ...],
// [tool: ...], [tool error: ...], [audio error: ...]) - rendered as compact
// HUD meta text instead of narration prose.
export const BRACKET_LINE = /^\[.+\]$/;

export type LogEntry =
  | { kind: "own"; text: string }
  | { kind: "speaking"; text: string; name: string; character: CharacterSheet | RedactedCharacter | null }
  | { kind: "meta"; text: string }
  | { kind: "narration"; text: string };

export function classifyLine(line: string, view: StateView, playerId: string): LogEntry {
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

// Grouping key for messenger labels: speech from one speaker in a row shows
// the name and avatar once. Everything else breaks no group and starts none.
export function speakerKey(entry: LogEntry): string | null {
  if (entry.kind === "own") return "own";
  if (entry.kind === "speaking") return `npc:${entry.name.toLowerCase()}`;
  return null;
}

// true where a line needs its speaker label: the first line of each run.
// null entries (narration, rolls, images) end the run.
export function groupStarts(keys: (string | null)[]): boolean[] {
  return keys.map((key, i) => key !== null && keys[i - 1] !== key);
}

export function sceneImages(log: string[]): string[] {
  return log.flatMap((line) => {
    const match = line.match(IMAGE_LINE);
    return match ? [match[1]] : [];
  });
}
