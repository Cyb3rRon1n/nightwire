# Messenger play screen and adjustable layout: design

Date: 2026-11-06. Status: for review.

Owner decisions:
- "Option 1", plus "the play screen adjustable or can be freely resized".
- From the design canvas: layout A, "with B's scene art primary to give the immersive area the player is in".
- "There doesn't need to be a permanent spot for the gallery."

The mockups are on the Nightwire Play Screens design canvas; the chosen board is "A + B".

## Goal

Make `/nightwire`'s play area feel like a cyber-phone chat journal. Lay it out as resizable panels, so each player decides how much room goes to the conversation and how much to their sheet and objectives. The current scene's art fills the conversation panel behind the text, for atmosphere.

## Research

- **Reference page:** https://rexxgta.github.io/cyberpunk2077chats/ by REXX, a static fan site imitating Cyberpunk 2077's phone journal. Repo: github.com/rexxgta/cyberpunk2077chats.
  - It has no license file, so it is all rights reserved, and it appears to use game images and the commercial BlenderPro font. **Nothing is copied.** Only the general ideas are used, rebuilt from scratch.
  - The design ideas:
    - NPC text is gold (`#f9d066`) and left-aligned. The player's text is cyan (`#7aeaee`) and right-aligned.
    - System text (chat ID, footer) is red (`#b93a31`) on near-black.
    - There are no bubbles, just a small speaker name above each run of lines.
    - Boxes have thin 1.5px brown (`#483723`) or teal (`#2a4647`) borders with square corners and a 4px scrollbar.
  - It has no animation, typing indicator, choices or images. Nightwire adds those.
- **Cyberpunk 2077 dialogue conventions** (gamesatlas.com and outsidergaming.com dialogue-colour guides): gold or yellow for main options, blue for optional ones, grey for locked ones. The game hands out gigs and check-ins by text message, which is the precedent for the phone panel below.
- **CD Projekt Red fan content guidelines** (cdprojektred.com/fan-content): no Cyberpunk names, logos or game assets in other products. Nightwire uses its own world, words and chrome. Fonts stay Rajdhani (licensed under the SIL Open Font License) and the narrator's serif.
- **Panels library:** `react-resizable-panels` (MIT), the engine behind shadcn/ui's Resizable component.
  - It provides drag handles, keyboard resizing on the handles, collapsible panels and a saved layout.
  - Pinned to an exact version at least two weeks old: **4.14.8**, released 2026-10-20. The 4.19.x releases came out today.
- **Play-screen survey** (researcher pass, 2026-11-06):
  - Text-heavy AI games settle on one stream with inline dice cards, because it's easiest for long reading and works the same on phones. Examples: AI Dungeon, Friends & Fables, and chat apps.
  - Disco Elysium's column over scene art is the most atmospheric. It's narrow, though, and becomes a single stream on phones anyway.
  - A visual-novel stage, such as SillyTavern's VN mode, pages one line at a time, which suits typed play poorly.
  - AI Dungeon players complained about small and hidden controls, so every control here is labelled and at least 44px.
  - Readability follows WCAG 1.4.8: lines of at most about 75 characters, line spacing of at least 1.5, left-aligned text, and 17px or larger body text.
  - Sources: w3.org/WAI/WCAG22/Understanding/visual-presentation, docs.sillytavern.app (Visual Novel mode), and r/AIDungeon threads on the Phoenix UI.
  - Only part of this was verified by search. The rest of the survey came from the researcher's general knowledge.
- **Considered and not chosen:**
  - Free-floating windows (dockview or react-rnd): heavier, and they overlap and work poorly on phones. They can be added later if players ask.
  - CSS `resize` on a grid: no collapsing, no saved layout and weak keyboard support.

## Layout

Desktop (≥1024px) is a horizontal panel group of three columns:

| Panel | Default | Min | Collapsible | Holds |
|---|---|---|---|---|
| Left: **Status** | 20% | 14% | yes | the character sheet (inline, replacing the pop-over), humanity, debt and installments, chrome, objectives |
| Centre: **Feed** (messenger) | 58% | 40% | no | the scene art, the conversation and the action input |
| Right: **World** | 22% | 14% | yes, collapsed by default | the party and who is in the scene; the Phone joins it in step 2 |

- **Collapsing:** a collapsed panel shrinks to a 28px rail showing its name vertically. Clicking it or pressing Enter reopens it.
- **Saving:** the layout is saved per browser (in `localStorage`, via the library's `autoSaveId`). If storage is blocked, the screen falls back to the defaults.
- **Reset:** a "Reset layout" item in the header restores the defaults.
- **Gallery:** no permanent panel. A "Gallery" button in the header (showing a count) opens a full-screen overlay of the session's scene images, newest first. Escape or the close button returns to play.
- **Immersive view:** a header toggle collapses both side panels at once, leaving the scene and the conversation. Pressing it again restores the saved sizes.
- **Phones and narrow windows (<1024px):** one column with a tab bar for Feed, Status, World and Phone, with Feed as the default. No drag handles. The scene art becomes a 150px banner at the top of the feed.
- **Pre-game screens** (connect, character creation, portrait) stay as they are. The panels appear once the character joins.

## Scene art (centre panel background)

- **Which image:** the newest scene image in the session log (the existing `[image: …]` lines). Before the first image arrives, the panel uses a plain ink background. Location art taken from the approved place designs comes later and needs a new `StateView` field.
- **Layout:** the image covers the whole panel. The top roughly third is left clear, with the location name over it (white Rajdhani with a dark text shadow). Below that, a vertical scrim fades from 15% to 93% ink, so all text sits on 86% ink or darker and keeps a contrast of at least 4.5:1.
- **Changing scenes:** when a new image arrives it crossfades over 600ms, or swaps instantly under `prefers-reduced-motion`.
- **Turning it off:** a "Scene art" toggle in the header switches to the plain ink background, for readability or low bandwidth. The choice is saved per browser.

## Messenger (centre panel)

- **Header bar:** the current location (`StateView.location`, or "Kuroshio" if empty) in Rajdhani, with the session ID beneath it in red monospace text. A small connection light uses the existing ready-state labels.
- **Lines:**
  - **Narrator:** a centred serif block at most 62ch wide, with no name label and a muted ivory colour.
  - **NPC:** left-aligned, with a 32px portrait and the name in small caps, then their lines. Consecutive lines from one speaker are grouped under one label.
  - **Player:** right-aligned cyan with their own portrait and name. Other players in the same session are also right-aligned, each with an outline in their own colour.
  - **System lines** (`[torite: …]`, `[selfhood: …]`, rolls): a full-width red-ruled strip in the HUD font.
- **NPC colour:** gold `#f9d066` is the default. A named NPC with an approved design gets a hue taken from its design palette, nudged to stay readable at a contrast of at least 4.5:1 against the panel. The colour is consistent for the whole session.
- **Scene images:** a full-width frame with a 1.5px teal border inside the feed, where the image arrived, and it also becomes the panel background. Clicking one opens it in the gallery overlay.
- **Roll cards and chrome offers:** the same components, restyled with the thin-border frame and square corners.
- **Typing indicator:** three pulsing dots under the speaker label "Narrator" while a turn is pending. It respects `prefers-reduced-motion`.
- **Input:** a single line that grows to 4 lines, with a "> " prompt in cyan. Enter sends and Shift+Enter adds a new line. The 1,000-character limit is kept, with a counter after 800.
- **Scroll:** the feed sticks to the bottom unless the player has scrolled up. A "New lines ↓" chip then appears.

## Colours and type

These are new `.nw-theme` tokens. The old violet tokens stay for pre-game screens.

| Token | Value | Use |
|---|---|---|
| `--nw-ink` | `#07080b` | panel background |
| `--nw-gold` | `#f9d066` | NPC default |
| `--nw-cyan` | `#7aeaee` | the player, links, focus ring |
| `--nw-red` | `#d2453a` | system and HUD text (lifted from `#b93a31` for contrast) |
| `--nw-frame` | `#4a3a26` | brown borders |
| `--nw-frame-cool` | `#2a4647` | teal borders and image frames |
| `--nw-prose` | `#e6dccb` | narrator text |

- **Shapes:** square corners and 1.5px borders. Scrollbars are 4px wide with a red thumb.
- **Fonts:** Rajdhani for chrome and names, the existing serif for narrator prose, and the system UI font for player and NPC lines, which keeps them readable at 16px.
- **Contrast check:** every text and background pair must reach 4.5:1 or higher. This is checked as part of the build.

## Phone (step 2, after the layout ships)

This adds a **Phone** panel, a fourth panel in the right group (and a tab on phones). It holds one thread per contact, with an unread badge.

- **Engine texts first:** the server sends a `phone` message when debt or gig state changes, so these never depend on the model volunteering them:
  - an installment is due,
  - a repossession is pending,
  - a gig is paid.

  Saeko's crew and the fixer are the senders, and the text comes from templates.
- **Narrator texts later:** the narrator may add flavour texts through a `send_text` tool, once the engine texts are proven in play.
- **Replies:** a reply in a thread is sent as a normal action, `I text <contact>: <text>`, so no new turn type is needed.
- **Status pop-ups:** big status changes (a status light turning red, a chrome throttle, a repo crew on the way) show as HUD toasts on the feed, not as texts.
- **Pop the phone out:** a phone button or hotkey floats the phone over the right side of the scene, so the conversation stays visible beside it. You can text one character while talking to another in the room. The phone has its own input. The main input is what you say or do aloud. Canvas board: "A + B · Phone popped out". **Owner approved this board (2026-11-06).**
- **Private texts in the feed:** each text you send also shows in the feed as a dim italic line marked "Private · only <contact> sees this", so the story log stays complete.
- **Who knows what:** the narrator is told which lines were aloud and which were texts. NPCs in the room never hear texts, but may notice you on your phone ("Mama Sato saw you typing under the counter"). A lie told by text is remembered per contact, so it can come back later.
- **Starting contact:** from the phone you can text or call any contact, which starts a scene with them. Calls play in the feed like a normal conversation, marked as a call.

**Owner decisions for step 2 (2026-11-06):**

- **Scope of version 1:** texts plus secrets. Engine texts from Saeko's crew and the fixer when debt or gigs change; you
  text any contact privately; each contact remembers what you told them, so a lie can come back. Calls come later.
- **Contacts:** the people you've met. Saeko's crew and Jun Arakawa from the start, plus anyone you talk to in play,
  added automatically.
- **Replies:** timing depends on the contact and on your relationship with them (owner, revised 2026-11-06). Each
  contact has a relationship (best friend, friend, coworker, boss, acquaintance, stranger) that sets how soon they answer,
  counted in your turns: a best friend answers at once, coworkers and the boss within a turn or two, an acquaintance
  later or not at all. Each character can shift it by their own pace (Saeko answers debtors instantly; Old Hara is
  slow). A late reply lands in the thread with an unread badge. Relationships start from how you met and can grow
  through play; the plan decides how.

**Relationship model (owner chose role + trust; researched 2026-11-06).** Prior art uses a banded value plus a
"what are they to you" label, with thresholds that change behaviour: Cyberpunk RED's lifepath Friends / Enemies /
Tragic Love Affairs (an enemy carries a cause and a way to retaliate), Persona's confidant ranks (hidden points, later
ranks harder, ranks unlock content), BioWare approval (high = warmer, low = confrontational or leaving), Cyberpunk 2077's
phone (calls and texts triggered by quest state; players complained about spam, so rate-limit), Monsterhearts Strings
(the value is spendable, not just a mood) and SillyTavern tracker extensions (re-inject the state into the prompt).
Nobody found ties the value to reply time; that part is ours. The engine owns every number; the model only writes
the words. Sources: rtalsoriangames.com Cyberpunk RED lifepath post; pcgamer.com Persona 4 Golden Social Links guide
and "Cyberpunk 2077, stop it with all the phone calls and texts"; thegamer.com Dragon Age: Origins approval guide;
Wikipedia "Monsterhearts"; github.com/prolix-oc/SillyTavern-SimTracker.

- **Roles (11):** family, partner, friend (with a `close` flag for a best friend), crew (includes coworkers), boss,
  fixer (includes clients), creditor, informant, rival, enemy, stranger. The role sets the *kind* of message.
- **Trust 0-5**, stored as a float and shown as a whole number: 0 burned, 1 wary, 2 neutral, 3 friendly, 4 trusted,
  5 ride-or-die. Strangers start at 2, enemies at 0, family and partner at 3. +1 for a kept promise or a finished
  favour, +1 for help that cost you something, +0.5 for a gift or an on-time reply (passive gains capped at +1 per
  in-game day), -1 for a broken promise, -2 for a betrayal. Going above 3 needs a big event, not small gains.
- **Reply delay in your turns:** `base(role) + (5 - trust) + pace + availability`, clamped to 0-6. Base: partner 0;
  family, friend, crew, creditor 1; boss, fixer, informant 2 (a fixer with your job open: 0); rival 3; enemy 4 and may
  never answer. Pace is -1, 0 or +1 per character (Saeko -1, Old Hara +1). Availability adds 2 when they are asleep or
  working the dinner rush, by a simple day schedule.
- **Tone** is a tag from trust band and role (warm, friendly, curt, guarded, hostile), handed to the model with a
  length cap and the facts it may use.
- **Texting first** is engine-triggered and rate-limited (at most one unprompted text every few turns): a job (fixer),
  a deadline (creditor), a threat (enemy), or a check-in from family or a partner at trust 3+ after you've been
  silent a while. Trust 5 can bring an unprompted tip or favour.
- **Lies** cost nothing until discovered. A discovered lie is -1, or -2 for trust 4+ or family and partner (-0.5 for
  a white lie), then a cold tone for a few turns; repeated lies can't push trust below 1. Rivals and enemies shrug.
  All numbers are starting values to tune in play.
- **Being noticed:** the narrator decides. It is told a text was sent (never its words) and may have someone in the
  room notice. No dice.

Step 2 gets its own short plan.

## Out of scope

- Free-floating windows.
- Sound.
- Any Cyberpunk 2077 names, assets or fonts.
- Changes to the backend protocol in step 1. Everything in step 1 uses fields `StateView` already sends.

## Testing

- **Unit tests:** the frontend has no test runner, so the pure logic lives in plain `.ts` modules run with Node's built-in `node --test --experimental-strip-types`. No new dependency.
  - Line grouping by speaker.
  - The NPC colour stays above the contrast floor for every approved palette.
  - The saved layout falls back to the defaults when storage throws.
- **Playwright on the live dev server:**
  - Drag a handle and reload: the layout persists.
  - Collapse and reopen each side panel with the keyboard.
  - The 390px phone width shows tabs and no horizontal scroll.
  - A full turn renders the narrator, NPC and player lines plus a scene image, which becomes the panel background and appears in the Gallery overlay.
- **Owner review:** screenshots on desktop and phone before merging.
