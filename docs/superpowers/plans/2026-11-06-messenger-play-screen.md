# Messenger Play Screen (Step 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `/nightwire`'s single play column with a resizable three-panel screen (Status, Feed, World): the current scene's art sits behind the conversation, lines are styled as a messenger, a Gallery overlay is available on demand, and phones get a tab bar.

**Architecture:** Pure logic (classifying log lines, grouping by speaker, NPC colours, safe storage) moves into plain `.ts` modules under `frontend/src/lib/nightwire/`, tested with Node's built-in test runner. React components under `frontend/src/app/nightwire/play/` render the layout with `react-resizable-panels` 4.14.8. `page.tsx` keeps the connect, character-creation and portrait screens, then hands the live `view` to `<PlayScreen>`. No backend protocol change.

**Tech Stack:** Next.js 16.2.6, React 19.2.4, Tailwind 4, `react-resizable-panels` 4.14.8 (MIT, new), `@radix-ui/react-dialog` (already installed), Node 24 `node --test`, Python 3.11 (one export script).

**Spec:** `docs/superpowers/specs/2026-11-06-messenger-play-screen-design.md` (read it first). Visual reference: the "A + B · Chosen" board on the private design canvas https://claude.ai/artifact/StQrxmSU8MXd4gQt3Qx3Ya.

## Global Constraints

- `react-resizable-panels` pinned to exactly `4.14.8` (no caret). 4.19.x is too new. No other new dependency.
- This is Next.js 16: read the relevant guide in `frontend/node_modules/next/dist/docs/` before using any Next API (frontend `AGENTS.md`).
- v4 API (verified from the 4.14.8 typings): `Group` (with `orientation`, `groupRef`, `defaultLayout`, `onLayoutChanged`), `Panel` (with `id`, `defaultSize`, `minSize`, `collapsible`, `collapsedSize`, `panelRef`, `onResize`), `Separator`, `useDefaultLayout({ id, storage })`. **There is no `autoSaveId` in v4; `useDefaultLayout` replaces it.** In size props, numbers mean pixels and unitless strings mean percent (`"20"` = 20%).
- Panel sizes: Status 20% default / 14% min / collapsible; Feed 58% / 40% min / not collapsible; World 22% / 14% min / collapsible and **collapsed by default**. Collapsed rail is 28px.
- Desktop panels at ≥1024px; below that, a single column with tabs Feed, Status, World (Phone arrives in step 2), with Feed as the default.
- Colours: `--nw-ink #07080b`, `--nw-gold #f9d066`, `--nw-cyan #7aeaee`, `--nw-red #d2453a`, `--nw-frame #4a3a26`, `--nw-frame-cool #2a4647`, `--nw-prose #e6dccb`. Scope them to `.nw-play` so the pre-game screens keep the old violet tokens (`.nw-theme` already defines a different `--nw-cyan`).
- Every text/background pair ≥ 4.5:1. Square corners, 1.5px borders.
- Scene scrim: `linear-gradient(180deg, rgba(7,8,11,.15) 0%, rgba(7,8,11,.25) 28%, rgba(7,8,11,.86) 46%, rgba(7,8,11,.93) 100%)`. Crossfade 600ms, instant under `prefers-reduced-motion`.
- Input: 1,000-character limit, counter shown after 800, Enter sends, Shift+Enter adds a new line, grows to 4 lines.
- No Cyberpunk 2077 names, assets or fonts.
- Commits: no `Co-Authored-By` or AI trailers (workspace rule). Work on a branch, never on `main`.
- Frontend checks after every task: `cd frontend && npx tsc --noEmit && npm run lint && npm run test:nightwire`.

## File map

| File | Status | Responsibility |
|---|---|---|
| `frontend/src/lib/nightwire/feed.ts` | create | line regexes, `classifyLine` (moved from page.tsx), `speakerKey`, `groupStarts`, `sceneImages` |
| `frontend/src/lib/nightwire/npcColour.ts` | create | WCAG contrast, `npcColour(name)` |
| `frontend/src/lib/nightwire/npcPalettes.ts` | create (generated) | approved character palettes |
| `tools/export_npc_palettes.py` | create | writes `npcPalettes.ts` from `narrator/worlds/designs/*.toml` |
| `tests/test_npc_palettes.py` | create | fails when the generated file is stale |
| `frontend/src/lib/nightwire/safeStorage.ts` | create | storage that never throws, boolean flags |
| `frontend/tests/nightwire/*.test.ts` | create | node tests for the three modules |
| `frontend/src/app/nightwire/CharacterSheetOverlay.tsx` | modify | split out `CharacterSheetBody` |
| `frontend/src/app/nightwire/play/PlayScreen.tsx` | create | header, panel group, mobile tabs, gallery state |
| `frontend/src/app/nightwire/play/StatusPanel.tsx` | create | sheet, humanity, debt, objectives |
| `frontend/src/app/nightwire/play/WorldPanel.tsx` | create | party and scene |
| `frontend/src/app/nightwire/play/FeedPanel.tsx` | create | scene art, messenger lines, cards, input |
| `frontend/src/app/nightwire/play/Rail.tsx` | create | collapsed-panel rail button |
| `frontend/src/app/nightwire/play/GalleryOverlay.tsx` | create | full-screen scene image gallery |
| `frontend/src/app/nightwire/play/play.css` | create | `.nw-play` tokens and messenger styles |
| `frontend/src/app/nightwire/page.tsx` | modify | pre-game screens only, then `<PlayScreen>` |

---

### Task 1: Test runner and the feed module

Moves line classification out of `page.tsx` unchanged, adds speaker grouping and scene-image lookup, and sets up the Node test runner.

**Files:**
- Create: `frontend/src/lib/nightwire/feed.ts`
- Create: `frontend/tests/nightwire/feed.test.ts`
- Modify: `frontend/tsconfig.json` (add `allowImportingTsExtensions`)
- Modify: `frontend/package.json` (add `test:nightwire` script)
- Modify: `frontend/src/app/nightwire/page.tsx:79-152` (delete the moved code, import it instead)

**Interfaces:**
- Produces: `SPEAKER_LINE`, `IMAGE_LINE`, `ROLL_LINE`, `ROLL_PENDING_LINE`, `AUDIO_LINE`, `BRACKET_LINE` (RegExp); `type LogEntry`; `classifyLine(line: string, view: StateView, playerId: string): LogEntry`; `speakerKey(entry: LogEntry): string | null`; `groupStarts(keys: (string | null)[]): boolean[]`; `sceneImages(log: string[]): string[]`.

- [ ] **Step 1: Branch and set up the runner**

```bash
cd /home/sentinel/projects/github/repos/nightwire
git switch -c feat/messenger-play-screen
```

In `frontend/tsconfig.json` `compilerOptions`, add `"allowImportingTsExtensions": true,` (valid because `noEmit` is already true; Node needs the `.ts` extension in test imports).

In `frontend/package.json` `scripts`, add:

```json
"test:nightwire": "node --test --experimental-strip-types tests/nightwire/",
```

- [ ] **Step 2: Write the failing test**

`frontend/tests/nightwire/feed.test.ts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyLine, groupStarts, sceneImages, speakerKey } from "../../src/lib/nightwire/feed.ts";
import type { StateView } from "../../src/lib/nightwire/protocol.ts";

const view = {
  characters: {
    p1: { player_id: "p1", name: "Rin" },
    p2: { name: "Kaede", role: "solo" },
  },
} as unknown as StateView;

test("classifies own, teammate, npc, meta and narration lines", () => {
  assert.deepEqual(classifyLine("p1: I wait.", view, "p1"), { kind: "own", text: "I wait." });
  assert.equal(classifyLine("p2: Move.", view, "p1").kind, "speaking");
  const npc = classifyLine("Mama Sato: Sit, Rin.", view, "p1");
  assert.equal(npc.kind, "speaking");
  assert.equal(npc.kind === "speaking" && npc.name, "Mama Sato");
  assert.equal(classifyLine("[torite: amber]", view, "p1").kind, "meta");
  assert.equal(classifyLine("Rain drums on the awning.", view, "p1").kind, "narration");
});

test("consecutive lines from one speaker share one label", () => {
  const keys = ["npc:mama sato", "npc:mama sato", "own", null, "own", "npc:mama sato"];
  assert.deepEqual(groupStarts(keys), [true, false, true, false, true, true]);
});

test("speakerKey only groups speech", () => {
  assert.equal(speakerKey({ kind: "own", text: "x" }), "own");
  assert.equal(speakerKey({ kind: "speaking", text: "x", name: "Mama Sato", character: null }), "npc:mama sato");
  assert.equal(speakerKey({ kind: "narration", text: "x" }), null);
  assert.equal(speakerKey({ kind: "meta", text: "[x]" }), null);
});

test("scene images in log order", () => {
  assert.deepEqual(sceneImages(["a", "[image: scenes/1.png]", "b", "[image: scenes/2.png]"]), ["scenes/1.png", "scenes/2.png"]);
  assert.deepEqual(sceneImages(["no images"]), []);
});
```

- [ ] **Step 3: Run it to see it fail**

Run: `cd frontend && npm run test:nightwire`
Expected: FAIL, cannot find module `feed.ts`.

- [ ] **Step 4: Create `feed.ts`**

Cut these from `page.tsx` into `frontend/src/lib/nightwire/feed.ts`, unchanged except for `export`: the comment block and `SPEAKER_LINE` (lines 79-90), `LogEntry` (92-96), `classifyLine` (101-119), and the regex block `IMAGE_LINE` … `BRACKET_LINE` with its comments (142-152). `classifyLine` uses `BRACKET_LINE`, so keep both in the module. Head the file with:

```ts
import type { CharacterSheet, RedactedCharacter, StateView } from "./protocol";
```

(`import type` is erased by Node's type stripping, so the extensionless path is fine here.) Then append:

```ts
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
```

In `page.tsx`, delete the moved code and add:

```ts
import { AUDIO_LINE, IMAGE_LINE, ROLL_LINE, ROLL_PENDING_LINE, classifyLine } from "@/lib/nightwire/feed";
```

Leave `isAiOf` (line 98) in `page.tsx`.

- [ ] **Step 5: Run the checks**

Run: `cd frontend && npm run test:nightwire && npx tsc --noEmit && npm run lint`
Expected: 4 tests pass; tsc and lint clean. The page renders exactly as before.

- [ ] **Step 6: Commit**

```bash
git add frontend/tsconfig.json frontend/package.json frontend/src/lib/nightwire/feed.ts frontend/tests/nightwire/feed.test.ts frontend/src/app/nightwire/page.tsx
git commit -m "refactor(frontend): move log-line parsing into lib/nightwire/feed with node tests"
```

---

### Task 2: NPC colours from approved designs

**Files:**
- Create: `tools/export_npc_palettes.py`
- Create: `frontend/src/lib/nightwire/npcPalettes.ts` (generated)
- Create: `frontend/src/lib/nightwire/npcColour.ts`
- Create: `tests/test_npc_palettes.py`
- Create: `frontend/tests/nightwire/npcColour.test.ts`

**Interfaces:**
- Produces: `NPC_PALETTES: Record<string, string[]>`; `GOLD = "#f9d066"`; `WORST_BG = "#2a2b2d"`; `contrast(a: string, b: string): number`; `npcColour(name: string): string` (a `#rrggbb` that is ≥ 4.5:1 against `WORST_BG`).

`WORST_BG` is 86% ink over pure white, the brightest background the scrim lets text sit on.

- [ ] **Step 1: Write the failing Python test**

`tests/test_npc_palettes.py`:

```python
from tools.export_npc_palettes import OUT, render


def test_generated_palettes_match_the_approved_designs():
    assert OUT.read_text() == render(), "stale: run python -m tools.export_npc_palettes"


def test_palettes_include_an_approved_npc():
    assert '"Mama Sato"' in render()
```

Run: `.venv/bin/python -m pytest tests/test_npc_palettes.py -v`
Expected: FAIL, `ModuleNotFoundError: tools.export_npc_palettes`.

- [ ] **Step 2: Write the exporter and generate the file**

`tools/export_npc_palettes.py`:

```python
"""Write frontend/src/lib/nightwire/npcPalettes.ts from approved character designs.

The frontend has no design endpoint in step 1, so the palettes ship as a generated
file. tests/test_npc_palettes.py fails when it goes stale.
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESIGNS = ROOT / "narrator" / "worlds" / "designs"
OUT = ROOT / "frontend" / "src" / "lib" / "nightwire" / "npcPalettes.ts"


def render() -> str:
    palettes = {}
    for path in sorted(DESIGNS.glob("*.toml")):
        d = tomllib.loads(path.read_text())
        if d.get("kind") == "character" and d.get("status") == "approved" and d.get("palette"):
            palettes[d["name"]] = d["palette"]
    body = json.dumps(palettes, indent=2, ensure_ascii=False)
    return ("// Generated by tools/export_npc_palettes.py from approved character designs. Do not edit.\n"
            f"export const NPC_PALETTES: Record<string, string[]> = {body};\n")


if __name__ == "__main__":
    OUT.write_text(render())
```

Run: `.venv/bin/python -m tools.export_npc_palettes && .venv/bin/python -m pytest tests/test_npc_palettes.py -v`
Expected: 2 passed. `npcPalettes.ts` lists about 21 characters (Akira Sendo … Yuki Shirasagi).

- [ ] **Step 3: Write the failing node test**

`frontend/tests/nightwire/npcColour.test.ts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { GOLD, WORST_BG, contrast, npcColour } from "../../src/lib/nightwire/npcColour.ts";
import { NPC_PALETTES } from "../../src/lib/nightwire/npcPalettes.ts";

test("contrast matches WCAG reference values", () => {
  assert.equal(Math.round(contrast("#ffffff", "#000000")), 21);
  assert.equal(contrast("#777777", "#777777"), 1);
});

test("every approved NPC colour clears 4.5:1 on the brightest scrim", () => {
  for (const name of Object.keys(NPC_PALETTES)) {
    assert.ok(contrast(npcColour(name), WORST_BG) >= 4.5, name);
  }
});

test("unknown names fall back to gold", () => {
  assert.equal(npcColour("A Stranger"), GOLD);
});

test("a first or last name alone finds the design, case-insensitively", () => {
  assert.equal(npcColour("saeko"), npcColour("Saeko Kirigaya"));
  assert.notEqual(npcColour("Mama Sato"), GOLD); // her palette is all reds
});
```

Run: `cd frontend && npm run test:nightwire`
Expected: FAIL, cannot find `npcColour.ts`.

- [ ] **Step 4: Implement `npcColour.ts`**

```ts
import { NPC_PALETTES } from "./npcPalettes.ts";

export const GOLD = "#f9d066";
// 86% ink over pure white: the brightest background the scene scrim lets text sit on.
export const WORST_BG = "#2a2b2d";

const rgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);

function luminance(hex: string): number {
  const [r, g, b] = rgb(hex).map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

export function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

const chroma = (hex: string) => Math.max(...rgb(hex)) - Math.min(...rgb(hex));

function towardWhite(hex: string, t: number): string {
  return "#" + rgb(hex).map((c) => Math.round((c + (1 - c) * t) * 255).toString(16).padStart(2, "0")).join("");
}

// The palette's most vivid colour, lifted toward white until it is readable on the scrim.
export function npcColour(name: string): string {
  const key = name.trim().toLowerCase();
  const match = Object.entries(NPC_PALETTES).find(([full]) => {
    const f = full.toLowerCase();
    return f === key || f.split(" ").includes(key);
  });
  const vivid = match?.[1].filter((c) => chroma(c) >= 0.25).sort((a, b) => chroma(b) - chroma(a))[0];
  if (!vivid) return GOLD;
  for (let t = 0; t <= 1; t += 0.05) {
    const c = towardWhite(vivid, t);
    if (contrast(c, WORST_BG) >= 4.5) return c;
  }
  return "#ffffff";
}
```

In `npcColour.ts` the `.ts` extension is required, because Node loads this value import at runtime. `allowImportingTsExtensions` from Task 1 keeps tsc happy, and Next's bundler resolves it.

- [ ] **Step 5: Run the checks**

Run: `cd frontend && npm run test:nightwire && npx tsc --noEmit && npm run lint`
Expected: all node tests pass (4 + 4); tsc and lint clean.

- [ ] **Step 6: Commit**

```bash
git add tools/export_npc_palettes.py tests/test_npc_palettes.py frontend/src/lib/nightwire/npcPalettes.ts frontend/src/lib/nightwire/npcColour.ts frontend/tests/nightwire/npcColour.test.ts
git commit -m "feat(frontend): readable NPC name colours from approved design palettes"
```

---

### Task 3: Storage that never throws

**Files:**
- Create: `frontend/src/lib/nightwire/safeStorage.ts`
- Create: `frontend/tests/nightwire/safeStorage.test.ts`

**Interfaces:**
- Produces: `type KeyValueStore = { getItem(key: string): string | null; setItem(key: string, value: string): void }` (structurally matches the library's `LayoutStorage`); `safeStore(get: () => KeyValueStore | undefined): KeyValueStore`; `readFlag(store, key, fallback: boolean): boolean`; `writeFlag(store, key, value: boolean): void`; `browserStore: KeyValueStore` (wraps `window.localStorage`).

- [ ] **Step 1: Write the failing test**

`frontend/tests/nightwire/safeStorage.test.ts`:

```ts
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFlag, safeStore, writeFlag } from "../../src/lib/nightwire/safeStorage.ts";

const throwing = () => { throw new Error("SecurityError: storage blocked"); };

test("a store that throws reads as empty and swallows writes", () => {
  const store = safeStore(throwing);
  assert.equal(store.getItem("layout"), null);
  assert.doesNotThrow(() => store.setItem("layout", "{}"));
  assert.equal(readFlag(store, "sceneArt", true), true);
});

test("missing storage (server render) behaves like empty storage", () => {
  assert.equal(safeStore(() => undefined).getItem("x"), null);
});

test("flags round-trip through a working store", () => {
  const data = new Map<string, string>();
  const store = safeStore(() => ({ getItem: (k) => data.get(k) ?? null, setItem: (k, v) => void data.set(k, v) }));
  writeFlag(store, "sceneArt", false);
  assert.equal(readFlag(store, "sceneArt", true), false);
});
```

Run: `cd frontend && npm run test:nightwire`
Expected: FAIL, cannot find `safeStorage.ts`.

- [ ] **Step 2: Implement**

`frontend/src/lib/nightwire/safeStorage.ts`:

```ts
export type KeyValueStore = { getItem(key: string): string | null; setItem(key: string, value: string): void };

// Private windows, blocked site data and server rendering all make storage throw
// or vanish; the play screen must fall back to its defaults instead of crashing.
export function safeStore(get: () => KeyValueStore | undefined): KeyValueStore {
  return {
    getItem(key) {
      try { return get()?.getItem(key) ?? null; } catch { return null; }
    },
    setItem(key, value) {
      try { get()?.setItem(key, value); } catch { /* storage blocked: defaults stay */ }
    },
  };
}

export const browserStore = safeStore(() => window.localStorage);

export function readFlag(store: KeyValueStore, key: string, fallback: boolean): boolean {
  const value = store.getItem(key);
  return value === null ? fallback : value === "1";
}

export function writeFlag(store: KeyValueStore, key: string, value: boolean): void {
  store.setItem(key, value ? "1" : "0");
}
```

- [ ] **Step 3: Run the checks, then commit**

Run: `cd frontend && npm run test:nightwire && npx tsc --noEmit && npm run lint`
Expected: all pass.

```bash
git add frontend/src/lib/nightwire/safeStorage.ts frontend/tests/nightwire/safeStorage.test.ts
git commit -m "feat(frontend): storage wrapper that falls back to defaults when blocked"
```

---

### Task 4: Panel shell with saved layout, rails, reset and immersive view

The structure first: the three panels, with the existing feed moved into the centre unchanged. Styling comes in Tasks 6 and 7.

**Files:**
- Modify: `frontend/package.json` (dependency)
- Create: `frontend/src/app/nightwire/play/play.css`
- Create: `frontend/src/app/nightwire/play/Rail.tsx`
- Create: `frontend/src/app/nightwire/play/FeedPanel.tsx`
- Create: `frontend/src/app/nightwire/play/PlayScreen.tsx`
- Modify: `frontend/src/app/nightwire/page.tsx` (render `<PlayScreen>` once in play)

**Interfaces:**
- Consumes: `browserStore` (Task 3).
- Produces:
  - `PlayScreen` props: `{ view: StateView; playerId: string; send: (msg: ClientMessage) => void; readyLabel: string; error: string | null; errorSeq: number }`.
  - `FeedPanel` props: `{ view: StateView; playerId: string; send: (msg: ClientMessage) => void; error: string | null; errorSeq: number; sceneArt: boolean; onOpenGallery: (index: number) => void }`. Tasks 6 and 7 use `sceneArt` and `onOpenGallery`. Until then FeedPanel accepts them and ignores them.
  - `Rail` props: `{ label: string; side: "left" | "right"; onOpen: () => void; badge?: number }`.

- [ ] **Step 1: Install the pinned library**

```bash
cd frontend && npm install --save-exact react-resizable-panels@4.14.8
```

Confirm that `package.json` reads `"react-resizable-panels": "4.14.8"` with no caret.

- [ ] **Step 2: Move the feed into `FeedPanel.tsx`**

Create `play/FeedPanel.tsx` as a `"use client"` component holding everything inside `page.tsx`'s `{view && (<> … </>)}` play block (lines ~491-663 after Task 1): the log map, chrome offer, pending rolls, combat bar and composer. Move the state it uses with it:
- `composerMode` and `composerText`,
- `sending`, `rolling` and `combatActionPending`,
- the reset effect on `[view, errorSeq]`,
- `COMPOSER_MODES` and `formatComposerInput`,
- `SpeakerAvatar` and `isAiOf`,
- the roll, initiative, advance and end handlers.

Leave out `VitalsBand`, because Task 5 replaces it with the panels. Delete it from `page.tsx`.

Root element:

```tsx
<section aria-label="Conversation" className="relative flex h-full min-h-0 flex-col gap-3 p-4">
```

Make the log list `flex-1 min-h-0 overflow-y-auto`, so that it, and not the page, scrolls.

- [ ] **Step 3: Rail**

`play/Rail.tsx`:

```tsx
export function Rail({ label, side, onOpen, badge }: { label: string; side: "left" | "right"; onOpen: () => void; badge?: number }) {
  return (
    <button type="button" onClick={onOpen} aria-label={`Open ${label} panel`} className="nw-rail">
      <span aria-hidden="true">{side === "left" ? "›" : "‹"}</span>
      <span className="nw-rail-label">{label}</span>
      {badge ? <span className="nw-rail-badge">{badge}</span> : null}
    </button>
  );
}
```

A `<button>` handles Enter and Space natively, which covers the spec's keyboard requirement.

- [ ] **Step 4: Tokens and shell styles**

`play/play.css`:

```css
.nw-play {
  --nw-ink: #07080b;
  --nw-gold: #f9d066;
  --nw-cyan: #7aeaee;
  --nw-red: #d2453a;
  --nw-frame: #4a3a26;
  --nw-frame-cool: #2a4647;
  --nw-prose: #e6dccb;
  background: var(--nw-ink);
  color: #e6e8ec;
}
.nw-play *:focus-visible { outline: 2px solid var(--nw-cyan); outline-offset: 2px; }
.nw-play-header { display: flex; align-items: center; gap: 12px; height: 48px; padding: 0 16px; border-bottom: 1.5px solid var(--nw-frame); font-family: "Rajdhani", sans-serif; letter-spacing: .14em; }
.nw-chip { height: 32px; padding: 0 10px; border: 1px solid var(--nw-frame-cool); background: transparent; color: #c9ced6; font: 600 13px "Rajdhani", sans-serif; letter-spacing: .14em; text-transform: uppercase; cursor: pointer; }
.nw-chip[aria-pressed="true"] { border-color: var(--nw-cyan); color: var(--nw-cyan); }
.nw-separator { width: 8px; background: #0f1217; border-inline: 1px solid #1d2128; display: flex; align-items: center; justify-content: center; }
.nw-separator::after { content: ""; width: 2px; height: 36px; background: var(--nw-frame-cool); }
.nw-separator[data-separator="active"]::after, .nw-separator:focus-visible::after { background: var(--nw-cyan); }
.nw-side { height: 100%; overflow-y: auto; background: #0b0d11; scrollbar-width: thin; scrollbar-color: var(--nw-red) transparent; }
.nw-rail { width: 100%; height: 100%; display: flex; flex-direction: column; align-items: center; gap: 14px; padding-top: 18px; background: #0b0d11; border: 0; color: #9aa3ad; cursor: pointer; font-family: "Rajdhani", sans-serif; }
.nw-rail-label { writing-mode: vertical-rl; font-size: 13px; letter-spacing: .24em; text-transform: uppercase; }
.nw-rail-badge { min-width: 18px; height: 18px; background: var(--nw-red); color: var(--nw-ink); font-weight: 700; font-size: 12px; display: flex; align-items: center; justify-content: center; }
```

Look at how the separator exposes its drag state in the 4.14.8 DOM (`data-separator` value) during Step 6, and adjust the active selector to match.

- [ ] **Step 5: PlayScreen**

`play/PlayScreen.tsx`:

```tsx
"use client";

import { useRef, useState } from "react";
import { Group, Panel, Separator, useDefaultLayout, type GroupImperativeHandle, type PanelImperativeHandle } from "react-resizable-panels";
import type { ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { browserStore } from "@/lib/nightwire/safeStorage";
import { FeedPanel } from "./FeedPanel";
import { Rail } from "./Rail";
import "./play.css";

const RAIL_PX = 28;

export function PlayScreen({ view, playerId, send, readyLabel, error, errorSeq }: {
  view: StateView; playerId: string; send: (msg: ClientMessage) => void; readyLabel: string; error: string | null; errorSeq: number;
}) {
  const { defaultLayout, onLayoutChanged } = useDefaultLayout({ id: "nightwire-play", storage: browserStore });
  const groupRef = useRef<GroupImperativeHandle>(null);
  const statusRef = useRef<PanelImperativeHandle>(null);
  const worldRef = useRef<PanelImperativeHandle>(null);
  const [statusCollapsed, setStatusCollapsed] = useState(false);
  const [worldCollapsed, setWorldCollapsed] = useState(true);
  const beforeImmersive = useRef<Record<string, number> | null>(null);
  const immersive = beforeImmersive.current !== null && statusCollapsed && worldCollapsed;

  function resetLayout() {
    beforeImmersive.current = null;
    statusRef.current?.expand();
    statusRef.current?.resize("20");
    worldRef.current?.collapse();
  }

  function toggleImmersive() {
    if (immersive && beforeImmersive.current) {
      groupRef.current?.setLayout(beforeImmersive.current);
      beforeImmersive.current = null;
    } else {
      beforeImmersive.current = groupRef.current?.getLayout() ?? null;
      statusRef.current?.collapse();
      worldRef.current?.collapse();
    }
  }

  const collapsedWatcher = (set: (v: boolean) => void) => (size: { inPixels: number }) => set(size.inPixels <= RAIL_PX + 1);

  return (
    <div className="nw-play flex h-dvh w-full flex-col">
      <header className="nw-play-header">
        <span style={{ color: "var(--nw-cyan)", fontWeight: 700, letterSpacing: ".22em" }}>NIGHTWIRE</span>
        <span className="flex-1" />
        <button type="button" className="nw-chip" aria-pressed={immersive} onClick={toggleImmersive}>Immersive view</button>
        <button type="button" className="nw-chip" onClick={resetLayout}>Reset layout</button>
        <span className="nw-chip" style={{ cursor: "default" }}>{readyLabel}</span>
      </header>
      <Group orientation="horizontal" groupRef={groupRef} defaultLayout={defaultLayout} onLayoutChanged={onLayoutChanged} className="min-h-0 flex-1">
        <Panel id="status" panelRef={statusRef} defaultSize="20" minSize="14" collapsible collapsedSize={RAIL_PX} onResize={collapsedWatcher(setStatusCollapsed)}>
          {statusCollapsed ? <Rail label="Status" side="left" onOpen={() => statusRef.current?.expand()} /> : <aside aria-label="Status" className="nw-side" />}
        </Panel>
        <Separator className="nw-separator" aria-label="Resize status panel" />
        <Panel id="feed" defaultSize="58" minSize="40">
          <FeedPanel view={view} playerId={playerId} send={send} error={error} errorSeq={errorSeq} sceneArt={false} onOpenGallery={() => {}} />
        </Panel>
        <Separator className="nw-separator" aria-label="Resize world panel" />
        <Panel id="world" panelRef={worldRef} defaultSize={RAIL_PX} minSize="14" collapsible collapsedSize={RAIL_PX} onResize={collapsedWatcher(setWorldCollapsed)}>
          {worldCollapsed ? <Rail label="Party" side="right" onOpen={() => worldRef.current?.expand()} /> : <aside aria-label="World" className="nw-side" />}
        </Panel>
      </Group>
    </div>
  );
}
```

Notes for the implementer:
- `defaultSize={RAIL_PX}` (a number, so pixels) on World makes it start collapsed. `expand()` opens it to its last size, or to `minSize` the first time. If 4.14.8 rejects a pixel default below `minSize` for a collapsible panel, fall back to `defaultSize="22"` plus `worldRef.current?.collapse()` in a mount effect that runs only when `defaultLayout` is undefined (no saved layout).
- If `Separator` doesn't forward `aria-label`, put the label on a child element instead. Check the rendered DOM.
- `ClientMessage` is already exported from `protocol.ts` (the socket hook imports it).

- [ ] **Step 6: Wire it into page.tsx**

Replace the `{view && (<> … </>)}` play block with:

```tsx
{view && <PlayScreen view={view} playerId={playerId} send={send} readyLabel={READY_STATE_LABEL[readyState]} error={error} errorSeq={errorSeq} />}
```

Gate it so it shows only after the portrait step is resolved: the character has a `portrait_path`, or `portraitSkipped` is true.

The play screen needs the full window, not the 2xl column. When in play, render `<PlayScreen>` instead of the `<main className="nw-theme mx-auto … max-w-2xl …">` wrapper:

```tsx
const inPlay = view && "player_id" in view.characters[playerId] && ((view.characters[playerId] as CharacterSheet).portrait_path || portraitSkipped);
if (inPlay) return <PlayScreen … />;
```

Put that check just before the existing `return`. Keep the `CharacterSheetOverlay` render and the Ctrl+K effect for now; Task 5 removes them.

Check the `useNightwireSocket` return type for `error`/`errorSeq` and match the prop types to it.

- [ ] **Step 7: Verify by hand**

Run the server and frontend (`python -m server` from the repo root; `cd frontend && npm run dev`), open http://localhost:3000/nightwire, and join a session. This needs Ollama only once you send an action, and the layout can be checked without one.
- Drag both separators, reload: the sizes persist.
- Tab to a separator and press the arrow keys: it resizes.
- Collapse Status by dragging it below its minimum: the rail appears. Click the rail, or focus it and press Enter: it reopens.
- Immersive view collapses both sides. Press it again: the previous sizes return.
- Reset layout returns to 20/58/rail.
- In a private window with site data blocked, the page still loads with the defaults.

Then run `npx tsc --noEmit && npm run lint && npm run test:nightwire`.

- [ ] **Step 8: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/app/nightwire/play frontend/src/app/nightwire/page.tsx
git commit -m "feat(frontend): resizable status/feed/world panels with saved layout and immersive view"
```

---

### Task 5: Status and World panel contents

**Files:**
- Modify: `frontend/src/app/nightwire/CharacterSheetOverlay.tsx` (extract the body)
- Create: `frontend/src/app/nightwire/play/StatusPanel.tsx`
- Create: `frontend/src/app/nightwire/play/WorldPanel.tsx`
- Modify: `frontend/src/app/nightwire/play/PlayScreen.tsx` (render them; Ctrl+K)
- Modify: `frontend/src/app/nightwire/page.tsx` (drop the overlay and Ctrl+K effect)

**Interfaces:**
- Produces:
  - `CharacterSheetBody` props: `{ character: CharacterSheet; onAllocateSkill(skill: string): void; onAllocateAttribute(attribute: string): void; onRemoveChrome(item: string): void }`.
  - `StatusPanel` props: `{ view: StateView; playerId: string; send: (msg: ClientMessage) => void }`.
  - `WorldPanel` props: `{ view: StateView; playerId: string }`.

- [ ] **Step 1: Split the sheet**

In `CharacterSheetOverlay.tsx`, move lines 34-178 (from the portrait header `<div className="nw-divider flex items-center gap-3 …">` through the inventory section's closing `</div>`) into a new exported `CharacterSheetBody` that returns them inside a fragment. It takes the same props minus `onClose`, and keeps the `initials`/`colorClass`/`isAi` locals. `CharacterSheetOverlay` then renders `<CharacterSheetBody {...props} />` inside its existing panel, before the Close button, so its behaviour is unchanged.

- [ ] **Step 2: StatusPanel**

```tsx
import type { CharacterSheet, ClientMessage, StateView } from "@/lib/nightwire/protocol";
import { CharacterSheetBody } from "../CharacterSheetOverlay";

export function StatusPanel({ view, playerId, send }: { view: StateView; playerId: string; send: (msg: ClientMessage) => void }) {
  const me = view.characters[playerId] as CharacterSheet;
  return (
    <aside aria-label="Status" className="nw-side nw-theme flex flex-col gap-4 p-4" style={{ background: "#0b0d11" }}>
      <CharacterSheetBody
        character={me}
        onAllocateSkill={(skill) => send({ type: "allocate_skill_points", skill, amount: 1 })}
        onAllocateAttribute={(attribute) => send({ type: "allocate_attribute_points", attribute, amount: 1 })}
        onRemoveChrome={(item) => send({ type: "remove_chrome", item })}
      />
      <section aria-label="Objectives">
        <h2 className="nw-hud text-xs" style={{ color: "var(--nw-gold)", letterSpacing: ".16em" }}>OBJECTIVES</h2>
        {view.active_objectives.length === 0
          ? <p className="text-sm" style={{ color: "#9aa3ad" }}>None yet.</p>
          : <ul className="flex flex-col gap-1 text-sm">{view.active_objectives.map((o) => <li key={o}>◆ {o}</li>)}</ul>}
      </section>
    </aside>
  );
}
```

The sheet body already shows humanity, chrome and installments (check this in the moved JSX). If installments or the repo clock are missing, add one line under the body:

```tsx
<p className="nw-hud text-xs" style={{ color: "var(--nw-red)" }}>DEBT · {me.installments_owed} INSTALLMENTS OWED</p>
```

`.nw-theme` on the aside keeps the sheet's existing violet-era classes working inside the `.nw-play` screen. Restyling the sheet internals is out of scope.

- [ ] **Step 3: WorldPanel**

```tsx
import type { StateView } from "@/lib/nightwire/protocol";
import { portraitFor } from "@/lib/nightwire/portrait";
import { mediaUrl } from "@/lib/nightwire/media";

export function WorldPanel({ view, playerId }: { view: StateView; playerId: string }) {
  return (
    <aside aria-label="World" className="nw-side flex flex-col gap-4 p-4">
      <section aria-label="Scene">
        <h2 className="nw-hud text-xs" style={{ color: "var(--nw-gold)", letterSpacing: ".16em" }}>SCENE</h2>
        <p className="text-sm">{view.location ?? "Kuroshio"}{view.scene_mood ? ` · ${view.scene_mood}` : ""}</p>
        {view.in_combat && <p className="nw-hud text-xs" style={{ color: "var(--nw-red)" }}>IN COMBAT{view.current_turn ? ` · ${view.current_turn}'S TURN` : ""}</p>}
      </section>
      <section aria-label="Party">
        <h2 className="nw-hud text-xs" style={{ color: "var(--nw-gold)", letterSpacing: ".16em" }}>PARTY</h2>
        <ul className="flex flex-col gap-2">
          {Object.entries(view.characters).map(([id, c]) => {
            const portrait = "portrait_path" in c ? c.portrait_path : null;
            const { initials, colorClass } = portraitFor(c.role, c.name);
            return (
              <li key={id} className="flex items-center gap-2 text-sm" style={id === playerId ? { color: "var(--nw-cyan)" } : undefined}>
                {portrait
                  // eslint-disable-next-line @next/next/no-img-element
                  ? <img src={mediaUrl(portrait)} alt="" className="size-8 object-cover" style={{ border: "1.5px solid var(--nw-frame-cool)" }} />
                  : <span className={`flex size-8 items-center justify-center text-xs font-semibold ${colorClass}`}>{initials}</span>}
                <span>{c.name} · {c.health}/{c.max_health} HP{c.armor > 0 ? ` · ${c.armor} armor` : ""}{c.conditions.length ? ` · ${c.conditions.join(", ")}` : ""}</span>
              </li>
            );
          })}
        </ul>
      </section>
    </aside>
  );
}
```

This carries over everything `VitalsBand` showed.

- [ ] **Step 4: Render them and move Ctrl+K**

In `PlayScreen`, replace the two empty `<aside>` placeholders with `<StatusPanel view={view} playerId={playerId} send={send} />` and `<WorldPanel view={view} playerId={playerId} />`.

Add the shortcut, which now toggles the Status panel instead of the pop-over:

```tsx
useEffect(() => {
  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "k" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      const panel = statusRef.current;
      if (panel?.isCollapsed()) panel.expand(); else panel?.collapse();
    }
  }
  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}, []);
```

In `page.tsx`, delete `sheetOpen`, the Ctrl+K effect and the `CharacterSheetOverlay` render. Keep the overlay component file, because phones reuse the body.

- [ ] **Step 5: Verify, then commit**

Check by hand:
- Allocating a skill point from the Status panel updates the sheet.
- Objectives list.
- The World panel shows the party with HP.
- Ctrl+K collapses and reopens Status.

Then run `npx tsc --noEmit && npm run lint && npm run test:nightwire`.

```bash
git add frontend/src/app/nightwire
git commit -m "feat(frontend): character sheet and objectives in the status panel, party in the world panel"
```

---

### Task 6: Messenger lines, typing indicator, input and scroll

**Files:**
- Modify: `frontend/src/app/nightwire/play/FeedPanel.tsx`
- Modify: `frontend/src/app/nightwire/play/play.css`

**Interfaces:**
- Consumes: `classifyLine`, `speakerKey`, `groupStarts` (Task 1), `npcColour` (Task 2).

- [ ] **Step 1: Messenger styles**

Append to `play.css`:

```css
.nw-feed { display: flex; flex-direction: column; align-items: center; gap: 14px; }
.nw-feed > * { width: 100%; max-width: 660px; }
.nw-line-narrator { max-width: 62ch; font-family: var(--font-source-serif), Georgia, serif; font-size: 18px; line-height: 1.6; color: var(--nw-prose); white-space: pre-wrap; }
.nw-line-npc { display: flex; gap: 12px; }
.nw-line-own { display: flex; gap: 12px; flex-direction: row-reverse; text-align: right; }
.nw-speaker { font: 700 14px "Rajdhani", sans-serif; letter-spacing: .16em; text-transform: uppercase; }
.nw-speech { font-size: 17px; line-height: 1.55; white-space: pre-wrap; }
.nw-avatar-gap { width: 40px; flex-shrink: 0; }
.nw-system { border-block: 1px solid #6b2a25; padding: 6px 0; text-align: center; font: 600 13px "Rajdhani", sans-serif; letter-spacing: .12em; color: #ff8a80; }
.nw-scene-frame { border: 1.5px solid var(--nw-frame-cool); cursor: zoom-in; display: block; }
.nw-typing { display: flex; align-items: center; gap: 10px; font: 13px "Rajdhani", sans-serif; letter-spacing: .16em; color: #9aa3ad; }
.nw-typing i { width: 6px; height: 6px; background: var(--nw-prose); animation: nw-pulse 1.2s infinite; }
.nw-typing i:nth-child(2) { animation-delay: .2s; } .nw-typing i:nth-child(3) { animation-delay: .4s; }
@keyframes nw-pulse { 50% { opacity: .25; } }
.nw-new-lines { position: absolute; bottom: 96px; left: 50%; transform: translateX(-50%); height: 32px; padding: 0 12px; background: var(--nw-cyan); color: var(--nw-ink); border: 0; font: 700 13px "Rajdhani", sans-serif; letter-spacing: .14em; cursor: pointer; }
.nw-composer { border-top: 1.5px solid var(--nw-frame); background: rgba(11,13,17,.96); padding: 12px 16px 16px; }
.nw-composer textarea { flex: 1; resize: none; background: var(--nw-ink); border: 1.5px solid var(--nw-frame-cool); color: #e6e8ec; font-size: 16px; line-height: 1.5; padding: 10px 12px; max-height: calc(4 * 1.5em + 20px); }
.nw-composer textarea:focus { border-color: var(--nw-cyan); outline: none; }
.nw-send { height: 48px; padding: 0 22px; background: var(--nw-cyan); color: var(--nw-ink); border: 0; font: 700 16px "Rajdhani", sans-serif; letter-spacing: .16em; }
.nw-send:disabled { opacity: .5; }
@media (prefers-reduced-motion: reduce) { .nw-typing i { animation: none; } }
.nw-feed { scrollbar-width: thin; scrollbar-color: var(--nw-red) transparent; }
/* Roll cards and chrome offers keep their components; only the frame changes. */
.nw-play .nw-roll-card { max-width: none; border-radius: 0; border: 1.5px solid var(--nw-frame); background: rgba(15,13,10,.92); }
.nw-play .nw-roll-badge { border-radius: 0; }
```

Open `ChromeOfferCard.tsx`, find its outer element's class, and give it the same frame rule under `.nw-play`, with square corners and a `--nw-frame` border.

- [ ] **Step 2: Render the lines**

Inside FeedPanel's log map, compute the grouping once, before rendering:

```tsx
const entries = view.log.map((line) => classifyLine(line, view, playerId));
const starts = groupStarts(entries.map(speakerKey));
```

Keep the existing branches for pending rolls, roll results, images and audio, in that order, before using `entries[i]`. Replace the rest:

- `own`:

```tsx
<div key={i} className="nw-line-own">
  {starts[i] ? <SpeakerAvatar name={me.name} character={me} /> : <span className="nw-avatar-gap" />}
  <div>
    {starts[i] && <div className="nw-speaker" style={{ color: "var(--nw-cyan)" }}>{me.name}</div>}
    <div className="nw-speech" style={{ color: "#c9f6f7" }}>{entry.text}</div>
  </div>
</div>
```

- `speaking`: teammates (`entry.character` not null) use their own colour, `portraitFor`-style, and sit right-aligned like `own` with an outline. NPCs sit left-aligned:

```tsx
const colour = npcColour(entry.name);
<div key={i} className="nw-line-npc">
  {starts[i] ? <SpeakerAvatar name={entry.name} character={entry.character} /> : <span className="nw-avatar-gap" />}
  <div>
    {starts[i] && <div className="nw-speaker" style={{ color: colour }}>{entry.name}</div>}
    <div className="nw-speech" style={{ color: colour }}>{entry.text}</div>
  </div>
</div>
```

  For a teammate, wrap the `own` layout in `style={{ outline: "1.5px solid <their portraitFor colour>", outlineOffset: 4 }}`. Use a teal border from `--nw-frame-cool` if the class colour is hard to read as a value.
- torite, selfhood and utsusemi notices: `<p className="nw-system">…same text logic as now…</p>`.
- other meta lines: keep the faint HUD line.
- `[image prompt` lines: still hidden.
- narration: `<p className="nw-line-narrator">{entry.text}</p>`.
- images: `<button type="button" className="nw-scene-frame" onClick={() => onOpenGallery(imageIndex)} aria-label="Open in gallery"><img … className="w-full" /></button>`. Here `imageIndex` is the image's position in `sceneImages(view.log)`; count the image lines while mapping.

Give the list `className="nw-feed flex-1 min-h-0 overflow-y-auto"`. In `SpeakerAvatar`, make the avatars square (`rounded-none`, `size-10`) with a 1.5px border in the speaker colour (pass `colour` as a prop).

- [ ] **Step 3: Typing indicator**

Under the pending-roll cards:

```tsx
{sending && (
  <div className="nw-typing" role="status" aria-live="polite">
    <span>NARRATOR</span><i /><i /><i />
  </div>
)}
```

- [ ] **Step 4: Composer**

Keep the Do/Say/Think tabs: they set how the line is phrased and are unchanged. Restyle them with `.nw-chip`. Replace the textarea and button:

```tsx
const MAX = 1000;
// in the form, className="nw-composer flex flex-col gap-2"
<div className="flex items-end gap-2">
  <span aria-hidden="true" className="pb-3 font-bold" style={{ color: "var(--nw-cyan)", fontFamily: "Rajdhani" }}>&gt;</span>
  <textarea
    rows={1}
    maxLength={MAX}
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
{composerText.length > 800 && <p className="nw-hud text-xs text-right" style={{ color: composerText.length >= MAX ? "#ff8a80" : "#9aa3ad" }}>{composerText.length} / {MAX}</p>}
```

After a send, reset the height: `textareaRef.current.style.height = "auto"`, using a `useRef<HTMLTextAreaElement>(null)` on the textarea. The combat bar (Roll Initiative, End Turn, End Combat) stays directly above the composer, restyled with `.nw-chip`.

Note on the limit: the old composer had no `maxLength`. Check the server's own action-length limit in `server/` (grep `1000` or `max_length`). If the server limit differs, use the server's number and tell the reviewer.

- [ ] **Step 5: Stick to the bottom**

```tsx
const listRef = useRef<HTMLDivElement>(null);
const [pinned, setPinned] = useState(true);
const [unseen, setUnseen] = useState(false);

function onScroll() {
  const el = listRef.current!;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 48;
  setPinned(atBottom);
  if (atBottom) setUnseen(false);
}

useEffect(() => {
  const el = listRef.current;
  if (!el) return;
  if (pinned) el.scrollTop = el.scrollHeight;
  else setUnseen(true); // eslint-disable-line react-hooks/set-state-in-effect -- reacting to new socket lines
}, [view.log.length]); // eslint-disable-line react-hooks/exhaustive-deps -- only new lines matter
```

Put `ref={listRef}` and `onScroll={onScroll}` on the list. Render the chip inside the `relative` section:

```tsx
{unseen && <button type="button" className="nw-new-lines" onClick={() => { listRef.current!.scrollTop = listRef.current!.scrollHeight; }}>NEW LINES ↓</button>}
```

- [ ] **Step 6: Verify, then commit**

Play one turn with Ollama, with the GPU free of ComfyUI. Check:
- the narrator text is centred serif,
- NPC names are coloured (Mama Sato is red-toned, others gold),
- your lines are right-aligned cyan,
- repeated NPC lines show one label,
- torite lines show as red strips,
- the typing dots appear while waiting,
- Enter sends, Shift+Enter adds a line, and the box grows to 4 lines,
- the counter appears after 800 characters,
- scrolling up while a reply arrives shows "New lines ↓".

Then run `npx tsc --noEmit && npm run lint && npm run test:nightwire`.

```bash
git add frontend/src/app/nightwire/play
git commit -m "feat(frontend): messenger-style feed with grouped speakers, typing dots and growing input"
```

---

### Task 7: Scene art backdrop, Scene art toggle and Gallery overlay

**Files:**
- Create: `frontend/src/app/nightwire/play/GalleryOverlay.tsx`
- Modify: `frontend/src/app/nightwire/play/FeedPanel.tsx`
- Modify: `frontend/src/app/nightwire/play/PlayScreen.tsx`
- Modify: `frontend/src/app/nightwire/play/play.css`

**Interfaces:**
- Consumes: `sceneImages` (Task 1), `browserStore`, `readFlag` and `writeFlag` (Task 3).
- Produces: `GalleryOverlay` props: `{ images: string[]; openIndex: number | null; onClose: () => void }`. The images are in log order and shown newest first.

- [ ] **Step 1: Backdrop styles**

```css
.nw-scene-bg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; transition: opacity 600ms ease; }
.nw-scene-scrim { position: absolute; inset: 0; background: linear-gradient(180deg, rgba(7,8,11,.15) 0%, rgba(7,8,11,.25) 28%, rgba(7,8,11,.86) 46%, rgba(7,8,11,.93) 100%); }
.nw-scene-title { position: relative; height: 34%; min-height: 120px; max-height: 290px; padding: 22px 32px; display: flex; flex-direction: column; justify-content: flex-end; flex-shrink: 0; }
.nw-scene-title h1 { font: 700 28px "Rajdhani", sans-serif; letter-spacing: .14em; color: #fff; text-shadow: 0 0 8px #000, 0 0 2px #000; text-transform: uppercase; }
@media (prefers-reduced-motion: reduce) { .nw-scene-bg { transition: none; } }
```

- [ ] **Step 2: Backdrop in FeedPanel**

```tsx
const images = sceneImages(view.log);
const latest = images.at(-1) ?? null;
```

Inside the section, as the first children:

```tsx
{sceneArt && latest && <SceneBackdrop src={mediaUrl(latest)} />}
<div className="nw-scene-scrim" aria-hidden="true" style={!sceneArt || !latest ? { background: "var(--nw-ink)" } : undefined} />
<div className="nw-scene-title">
  <h1>{view.location ?? "Kuroshio"}</h1>
  <p className="nw-hud text-xs" style={{ color: "#ff8a80", textShadow: "0 0 4px #000", fontFamily: "monospace" }}>SES {view.session_id}</p>
</div>
```

Everything after that, the list and the composer, gets `position: relative` so it sits above the scrim.

`SceneBackdrop` crossfades by keeping the previous image under the new one until the new one has loaded:

```tsx
function SceneBackdrop({ src }: { src: string }) {
  const [shown, setShown] = useState(src);
  const [incoming, setIncoming] = useState<string | null>(null);
  if (src !== shown && src !== incoming) setIncoming(src); // derive-on-render, React-sanctioned
  return (
    <>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img className="nw-scene-bg" src={shown} alt="" />
      {incoming && (
        // eslint-disable-next-line @next/next/no-img-element
        <img className="nw-scene-bg" src={incoming} alt="" style={{ opacity: 0 }}
          onLoad={(e) => { e.currentTarget.style.opacity = "1"; }}
          onTransitionEnd={() => { setShown(incoming); setIncoming(null); }} />
      )}
    </>
  );
}
```

Under reduced motion, `transition: none` means `transitionend` never fires. Handle this in the `onLoad`: if `matchMedia("(prefers-reduced-motion: reduce)").matches`, call `setShown(incoming); setIncoming(null)` directly.

The section's background must stay `var(--nw-ink)` when scene art is off or no image exists yet. The scrim style override above covers that.

- [ ] **Step 3: Gallery overlay**

```tsx
"use client";
import * as Dialog from "@radix-ui/react-dialog";
import { mediaUrl } from "@/lib/nightwire/media";

export function GalleryOverlay({ images, openIndex, onClose }: { images: string[]; openIndex: number | null; onClose: () => void }) {
  const newestFirst = images.map((src, i) => ({ src, i })).reverse();
  return (
    <Dialog.Root open={openIndex !== null} onOpenChange={(open) => { if (!open) onClose(); }}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50" style={{ background: "rgba(7,8,11,.94)" }} />
        <Dialog.Content className="nw-play fixed inset-0 z-50 overflow-y-auto p-6" aria-describedby={undefined}>
          <div className="mb-4 flex items-center justify-between">
            <Dialog.Title className="nw-speaker" style={{ color: "var(--nw-cyan)" }}>Gallery · {images.length}</Dialog.Title>
            <Dialog.Close className="nw-chip">Close</Dialog.Close>
          </div>
          <div className="grid gap-4" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(min(100%, 360px), 1fr))" }}>
            {newestFirst.map(({ src, i }) => (
              // eslint-disable-next-line @next/next/no-img-element
              <img key={i} src={mediaUrl(src)} alt={`Scene image ${i + 1}`} className="w-full"
                style={{ border: `1.5px solid ${i === openIndex ? "var(--nw-cyan)" : "var(--nw-frame-cool)"}` }}
                ref={i === openIndex ? (el) => el?.scrollIntoView({ block: "center" }) : undefined} />
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
```

Radix provides Escape to close, a focus trap and focus return.

- [ ] **Step 4: Header buttons and state in PlayScreen**

```tsx
const [sceneArt, setSceneArt] = useState(() => readFlag(browserStore, "nightwire-scene-art", true));
const [galleryIndex, setGalleryIndex] = useState<number | null>(null);
const images = sceneImages(view.log);
```

`readFlag` runs during the first client render. The play screen only renders after a websocket view arrives, so it is never server-rendered with real storage. If Next warns about a hydration mismatch anyway, move the read into a mount effect.

Header, before Immersive view:

```tsx
<button type="button" className="nw-chip" aria-pressed={sceneArt}
  onClick={() => { setSceneArt(!sceneArt); writeFlag(browserStore, "nightwire-scene-art", !sceneArt); }}>
  Scene art {sceneArt ? "on" : "off"}
</button>
<button type="button" className="nw-chip" disabled={images.length === 0} onClick={() => setGalleryIndex(images.length - 1)}>
  Gallery · {images.length}
</button>
```

Pass `sceneArt={sceneArt}` and `onOpenGallery={setGalleryIndex}` to `FeedPanel`. Render `<GalleryOverlay images={images} openIndex={galleryIndex} onClose={() => setGalleryIndex(null)} />` at the end of the screen.

- [ ] **Step 5: Verify, then commit**

Check:
- After the first `[image: …]` line, the image fills the centre panel. The top third is clear with the location title over it, and the text below sits on dark ink.
- A second image crossfades in.
- Scene art off gives plain ink, and the setting survives a reload.
- The Gallery button and clicking an image in the feed both open the overlay, newest first, with the clicked image outlined.
- Escape closes it and focus returns to the button.

Then run `npx tsc --noEmit && npm run lint && npm run test:nightwire`.

```bash
git add frontend/src/app/nightwire/play
git commit -m "feat(frontend): scene art behind the conversation, scene art toggle and gallery overlay"
```

---

### Task 8: Phones and narrow windows

**Files:**
- Modify: `frontend/src/app/nightwire/play/PlayScreen.tsx`
- Modify: `frontend/src/app/nightwire/play/FeedPanel.tsx`
- Modify: `frontend/src/app/nightwire/play/play.css`

**Interfaces:**
- Produces: `FeedPanel` gains `compact: boolean` (banner mode).

- [ ] **Step 1: Narrow detection**

```tsx
const narrow = useSyncExternalStore(
  (cb) => { const m = matchMedia("(max-width: 1023.98px)"); m.addEventListener("change", cb); return () => m.removeEventListener("change", cb); },
  () => matchMedia("(max-width: 1023.98px)").matches,
  () => false,
);
const [tab, setTab] = useState<"feed" | "status" | "world">("feed");
```

- [ ] **Step 2: Narrow layout**

When `narrow` is true, render this instead of the `Group`, with the same header:

```tsx
<div className="min-h-0 flex-1">
  {tab === "feed" && <FeedPanel … compact />}
  {tab === "status" && <StatusPanel view={view} playerId={playerId} send={send} />}
  {tab === "world" && <WorldPanel view={view} playerId={playerId} />}
</div>
<nav aria-label="Panels" className="nw-tabs">
  {(["feed", "status", "world"] as const).map((t) => (
    <button key={t} type="button" aria-current={tab === t ? "page" : undefined} onClick={() => setTab(t)}>{t.toUpperCase()}</button>
  ))}
</nav>
```

Hide Immersive view and Reset layout in the header when `narrow`, since they only make sense with panels.

```css
.nw-tabs { flex-shrink: 0; height: 60px; display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); border-top: 1px solid #1d2128; background: #0b0d11; }
.nw-tabs button { background: none; border: 0; color: #9aa3ad; font: 14px "Rajdhani", sans-serif; letter-spacing: .14em; }
.nw-tabs button[aria-current="page"] { color: var(--nw-cyan); font-weight: 700; border-top: 2px solid var(--nw-cyan); }
@media (max-width: 1023.98px) { .nw-play-header { overflow-x: auto; } .nw-feed > * { max-width: none; } }
```

- [ ] **Step 3: Banner mode**

When `compact` is set, FeedPanel skips the full backdrop and scrim. It renders the latest image, if scene art is on, as a 150px banner, with the location title on the ink background beneath it:

```tsx
{compact && sceneArt && latest && (
  // eslint-disable-next-line @next/next/no-img-element
  <img src={mediaUrl(latest)} alt="" className="w-full object-cover" style={{ height: 150, border: "1.5px solid var(--nw-frame-cool)" }} />
)}
```

- [ ] **Step 4: Verify, then commit**

At 390×844 in the browser's device mode:
- There's no horizontal scroll (`document.documentElement.scrollWidth === 390`).
- The tabs switch.
- The banner shows.
- The input is reachable above the tab bar.

At 1024px and wider, the panels return.

```bash
git add frontend/src/app/nightwire/play
git commit -m "feat(frontend): tabbed single-column play screen on phones with a scene banner"
```

---

### Task 9: Full verification and owner review

- [ ] **Step 1: Static checks**

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:nightwire && npm run build
cd .. && .venv/bin/python -m pytest tests/ -q
```

Expected: all pass. The Python suite is the existing 765 tests (or more, depending on what's on main at the time) plus the 2 from Task 2.

- [ ] **Step 2: Live checks in a real browser**

Use Playwright (MCP) or Chrome against `npm run dev` and `python -m server`. Ollama must be running and ComfyUI idle: one GPU job at a time, on the 8 GB GPU box.
1. Drag the Status separator to about 30%, reload: still about 30%.
2. Use only the keyboard to collapse and reopen each side panel: Tab to the separator, arrow keys, Enter on the rail.
3. At 390px width: tabs visible, `scrollWidth === 390`.
4. Play a full turn that produces narration, an NPC line, your line and a scene image. All four render in the messenger style, the image becomes the backdrop, and the Gallery count increases and opens.
5. Contrast spot-check: in devtools, pick the NPC name, narrator text and system strip over the brightest part of the scene. Each must be ≥ 4.5:1.

- [ ] **Step 3: Screenshots for the owner**

Capture:
- desktop, default layout, with scene art,
- desktop, immersive view,
- desktop, Status widened and World open,
- the Gallery overlay,
- phone width on the Feed tab, and on the Status tab.

Show them to the owner beside the "A + B · Chosen" canvas board, and wait for their verdict before merging. Merging and pushing need the owner's go-ahead.
