# Character Creator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Players describe a character, see four candidates, redo until happy and lock it in. The owner creates NPCs and AI characters the same way and approves player suggestions.

**Architecture:** One standard-library service on the GPU box, in the same container pattern as Image Studio, with one page. Every character is a folder of JSON and images under the service's state directory, and a private link gives access to it. A single worker renders one batch at a time through ComfyUI, and only submits when ComfyUI's queue is empty.

**Tech Stack:** Python 3.12 standard library (no Pillow in the container), ComfyUI HTTP API, nginx, plain HTML/CSS/JS, pytest, Playwright for browser checks.

**Spec:** `docs/superpowers/specs/2026-11-01-character-creator-design.md`

**Scope:** spec build steps 1-3. Photos (step 4) need their own plan after the likeness trial and the owner's Tailscale restriction. Nothing in this plan accepts a photo. Phase 19c (step 5) is separate.

## Global Constraints

- Workspace rule: never add `Co-Authored-By` or any AI-attribution trailer to commits.
- Commit on the feature branch. Don't push or deploy unless the task says so.
- Standard library only inside the service. `narrator.design_sheets` imports Pillow lazily, so never call `expression_grid` or `extract_palette` in the service.
- The service binds to loopback. Character links use `secrets.token_urlsafe(24)` (32 characters).
- Writes need `Content-Type: application/json`, and any `Origin` header must match `Host`.
- Everyone rendered is an adult, using the existing adult tags and `CHARACTER_NEGATIVE_EXTRA`.
- Page rules: dark Nightwire look (`#07060d`, pink `#ff4fa3`, cyan `#3fd5ff`), no sideways scroll at 390 px, keyboard focus visible, every input labelled.
- The GPU may be busy with the owner's batches. Unit tests use a fake ComfyUI. Don't submit real renders until a task says so and `/queue` is empty.

---

### Task 1: Questions and answers to design

**Files:**
- Create: `tools/character_answers.py`
- Test: `tests/test_character_answers.py`

**Interfaces:**
- Produces: `QUESTIONS: list[dict]` (`id, label, kind` of `text|choice, step, required, choices?, max?`); `BadAnswers(ValueError)`; `clean_answers(raw: dict) -> dict[str, str]`; `to_design(answers: dict, kind: str, seed: int) -> Design`.

Steps are `basics`, `look`, `nightwire`, `final`. Question ids:

| Step | ids |
|---|---|
| basics | `name`\*, `presentation`\* (feminine, masculine, androgynous), `age` (20s, 30s, 40s, 50+), `role` (from `ruleset.roles.ROLES`), `lifepath` (from `ruleset.lifepaths.LIFEPATHS`), `personality` |
| look | `hair`, `eyes`, `skin`, `build`, `face_extras` |
| nightwire | `outfit`, `colours`, `marks`, `chrome`, `signature` |
| final | `never`, `extra`, `backstory` |

\* required. `world_role` and `home` are extra questions, asked by the page for NPCs and AI characters only.

- [ ] **Step 1: Write the failing tests**

```python
import pytest
from tools import character_answers as ca


def good(**k):
    return {"name": "Vex", "presentation": "feminine", **k}


def test_required_and_choices_are_enforced():
    with pytest.raises(ca.BadAnswers, match="name"):
        ca.clean_answers({"presentation": "feminine"})
    with pytest.raises(ca.BadAnswers, match="presentation"):
        ca.clean_answers({"name": "Vex", "presentation": "robot"})


def test_weight_syntax_and_refused_words():
    assert ca.clean_answers(good(hair="(silver hair:1.6), <lora:x:1>"))["hair"] == "silver hair"
    with pytest.raises(ca.BadAnswers, match="nude"):
        ca.clean_answers(good(outfit="nude"))


def test_unknown_fields_are_dropped_and_length_capped():
    got = ca.clean_answers(good(hacker="x", hair="a" * 999))
    assert "hacker" not in got and len(got["hair"]) == 120


def test_design_fields_go_where_the_sheets_expect():
    d = ca.to_design(ca.clean_answers(good(hair="silver hair", eyes="red eyes", marks="scar on left cheek",
                                           chrome="mechanical right arm", signature="katana", never="glasses",
                                           outfit="trench coat", lifepath="corpo", backstory="ignored words")),
                     "player", 42)
    assert d.required == ["silver hair", "red eyes", "scar on left cheek", "mechanical right arm"]
    assert d.held == ["katana"] and "glasses" in d.negative and d.seed == 42 and d.presentation == "feminine"
    assert "trench coat" in d.tags and "corporate" in d.tags and "ignored" not in d.tags
    assert "adult" in d.tags


def test_blank_marks_and_chrome_add_nothing():
    d = ca.to_design(ca.clean_answers(good()), "player", 1)
    assert d.required == [] and "tattoo" not in d.tags and "mechanical" not in d.tags
```

- [ ] **Step 2: Run, expect failure** `python -m pytest tests/test_character_answers.py -v` (module missing).

- [ ] **Step 3: Implement**

Follow these rules:
- `clean_answers`: keep known ids only. Strip `<...>` blocks with `re.sub(r"<[^>]*>", "", v)`, then turn `(x:1.4)` into `x` with `re.sub(r"\(([^():]*)(?::[\d.]+)?\)", r"\1", v)`. Collapse whitespace, trim trailing commas and spaces, cap at each question's `max` (default 120). Reject with `image_studio.refused_terms`, naming the words and the field. `backstory` is exempt from tagging but still screened. Check choices and required last.
- `to_design`: `required` is hair, eyes, then `marks` and `chrome` split on commas. `held` is `signature`. `negative` is `never`. `tags` joins: `mature, adult`, `{age} years old` style tag (`20s` gives `young adult`; never `young` alone, since that's in the negative list; `30s` gives `mature`; `40s` gives `middle-aged`; `50+` gives `old`), `skin`, `build`, `face_extras`, `outfit`, `colours`, and a lifepath style tag (`corpo`: `corporate attire`; `streetkid`: `street fashion`; `nomad`: `nomad gear`; `tsukumogami`: `android`).
- Role, personality, backstory, `world_role` and `home` stay out of the tags. Personality is kept in `notes` for the expression default later.
- Default `seed` handling belongs to the caller.

- [ ] **Step 4: Run, expect pass; run the whole suite** `python -m pytest tests -q`.

- [ ] **Step 5: Commit** `feat(creator): questionnaire and answers-to-design mapping`

### Task 2: Character store, render queue and worker

**Files:**
- Create: `tools/character_creator.py`
- Modify: `tools/image_studio.py` (add `Comfy.upload`)
- Test: `tests/test_character_creator.py`

**Interfaces:**
- Consumes: `clean_answers`, `to_design`; `image_studio.Comfy`; `design_sheets.candidate_prompt, candidate_workflow, sheet_prompt, sheet_workflow, expression_prompts, EXPRESSION_SIZE`; `design_picks.write_json_atomic`.
- Produces: `class Creator(root: Path, comfy, rng=random, now=None)` with `create(kind, answers, by_owner) -> dict`, `get(id) -> dict`, `update_answers`, `generate(id, note="")`, `vary(id, round, n, strength, note="")`, `pick(id, round, n)`, `favourite(id, round, n)`, `lock(id)`, `redo_sheet(id, sheet)`, `accept(id)`, `decline(id, note)`, `delete(id)`, `list_all()`, `image_path(id, name) -> Path`, `tick()`. Errors: `image_studio.BadRequest`, `Busy`, `KeyError`.

Record, at `<root>/characters/<id>/character.json`:

```python
{"id": token, "kind": "player|npc|ai", "status": "draft|suggested|declined|accepted|locked",
 "by_owner": bool, "answers": {...}, "note": "", "seed": int,
 "rounds": [{"n": 1, "type": "reroll|vary", "from": None, "note": "", "images": ["r1-c1-123.png", ...]}],
 "favourites": ["r1-c2-124.png"], "picked": None, "sheets": {"turnaround": None, "colorguide": None, "expressions": []},
 "created": iso, "updated": iso}
```

Jobs, at `<root>/queue.json`, oldest first:

```python
{"id": uuid, "character": token, "label": "candidates|variations|sheets", "round": 1, "status": "waiting|rendering|failed",
 "items": [{"name": "r1-c1-123.png", "workflow": {...}, "comfy_id": None, "done": False}], "error": ""}
```

- [ ] **Step 1: Write the failing tests** using a `FakeComfy` with `queue()`, `submit(wf)`, `history(id)`, `image(ref)`, `upload(name, data)`, `free_ollama()`, `free_comfy()`. Each test name states the rule:

```python
def test_generate_queues_four_and_tick_renders_one_at_a_time(creator, comfy): ...
def test_tick_waits_while_someone_elses_job_is_in_comfyui(creator, comfy):
    comfy.others_running = True
    cid = creator.create("player", GOOD, by_owner=False)["id"]
    creator.generate(cid)
    creator.tick()
    assert comfy.submitted == [] and creator.get(cid)["queue"]["position"] == 1
def test_one_batch_per_character_and_twelve_overall(creator, comfy): ...
def test_failed_render_marks_batch_failed_keeps_old_rounds_and_retry_works(creator, comfy): ...
def test_restart_requeues_a_render_that_comfyui_lost(tmp_path, comfy): ...
def test_vary_uploads_source_and_uses_image_to_image(creator, comfy):
    # wf has LoadImage -> VAEEncode -> KSampler latent, denoise 0.35 subtle, 0.6 strong, no EmptyLatentImage
    ...
def test_earlier_round_can_be_picked_and_unknown_image_refused(creator, comfy): ...
def test_lock_needs_a_pick_then_queues_all_sheets(creator, comfy):
    # turnaround, colorguide, six 1024x1024 expression panels
    ...
def test_suggestion_renders_nothing_until_accepted(creator, comfy):
    s = creator.create("npc", GOOD, by_owner=False)
    assert s["status"] == "suggested"
    with pytest.raises(BadRequest):
        creator.generate(s["id"])
    creator.accept(s["id"]); creator.generate(s["id"])
def test_player_cannot_create_npc_directly_as_owner(creator): ...
def test_image_path_refuses_traversal(creator, comfy):
    with pytest.raises(KeyError):
        creator.image_path(cid, "../character.json")
def test_ids_are_private_length_and_unknown_id_is_keyerror(creator): ...
def test_gpu_is_handed_back_when_queue_empties(creator, comfy): ...
```

Write each test body in full, following the two complete examples.

- [ ] **Step 2: Run, expect failure.**

- [ ] **Step 3: Implement.** Key code:

```python
TOKEN = re.compile(r"^[A-Za-z0-9_-]{32}$")
NAME = re.compile(r"^(r\d+-c\d+-\d+|turnaround|colorguide|expression-\d)\.png$")
DENOISE = {"subtle": 0.35, "strong": 0.6}  # starting values; tune on real renders in Task 6


def vary_workflow(wf: dict, image: str, denoise: float) -> dict:
    wf = dict(wf)
    wf["40"] = {"class_type": "LoadImage", "inputs": {"image": image}}
    wf["41"] = {"class_type": "VAEEncode", "inputs": {"pixels": ["40", 0], "vae": ["4", 2]}}
    wf["3"] = {**wf["3"], "inputs": {**wf["3"]["inputs"], "latent_image": ["41", 0], "denoise": denoise}}
    wf.pop("5")
    return wf
```

`Comfy.upload(name, data)` posts multipart to `/upload/image` with `subfolder=character_creator`, `overwrite=true`, and returns `character_creator/<name>`. `tick()` runs under one lock:

1. For the rendering item: poll `history`, save its image into the character folder via `comfy.image`, mark it done, and append the round or sheet to the record when the batch finishes. Handle errors and lost jobs the way `Studio.refresh` does.
2. If nothing is rendering and `comfy.queue()` is empty, submit the next item of the oldest non-failed job, and call `free_ollama` first (best effort).
3. If nothing is left and work just finished, call `free_comfy` (best effort).

`get()` returns the record plus `queue: {position, label, error}`. Records and the queue are written with `write_json_atomic`. `kind` other than `player` needs `by_owner=True` to skip `suggested`. A thread in `__main__` calls `tick()` every 2 seconds and logs errors without dying.

- [ ] **Step 4: Run, expect pass; run the whole suite.**

- [ ] **Step 5: Commit** `feat(creator): character store, render queue and worker`

### Task 3: HTTP API and permissions

**Files:**
- Modify: `tools/character_creator.py` (`make_server`, `__main__`)
- Test: `tests/test_character_creator_api.py`

**Interfaces:**
- Consumes: `Creator`.
- Produces, under `/create/api`: `GET /options`; `POST /characters {kind: player|npc|ai, answers}`; `GET|DELETE /characters/<id>`; `PUT /characters/<id>/answers`; `POST /characters/<id>/{generate,vary,pick,favourite,lock,sheet}`; `GET /characters/<id>/image/<name>`; and with an owner token `GET /owner/<tok>/characters`, `POST /owner/<tok>/characters {kind, answers}`, `POST /owner/<tok>/characters/<id>/{accept,decline,generate,vary,pick,favourite,lock,sheet}`, `DELETE /owner/<tok>/characters/<id>`.

Permissions: on the public route, `kind` other than `player` creates a suggestion. A character link can read its own record. Only `player` characters may be changed through the public route; NPCs and AI characters need the owner route, so a suggester can't re-roll an accepted NPC.

The owner token is created on first run at `<root>/owner.token` with mode `0o600`, and compared with `hmac.compare_digest`.

- [ ] **Step 1: Write failing tests** (real `ThreadingHTTPServer` on port 0, like `tests/test_image_studio.py`) covering:
  - create, generate and read a player character
  - 415 without JSON; 403 when `Origin` doesn't match `Host`; 413 over 16 KB
  - 404 for an unknown link, with no record leaked
  - one character's token can't read another's image
  - suggester can't `generate` after acceptance (403), owner can
  - owner routes 404 with a wrong token, and the response doesn't distinguish it from a missing route
  - `list_all` only through the owner route
  - `GET /characters` without an id is 404, so characters can't be listed
  - image responses use `image/png` and `Cache-Control: private`

- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement**, reusing the handler structure of `image_studio.make_server` (`_send`, `_bytes`, `_guarded`, the unread-body `close_connection`).
- [ ] **Step 4: Run, expect pass; run the whole suite.**
- [ ] **Step 5: Commit** `feat(creator): API with private links and an owner route`

### Task 4: The page

**Files:**
- Create: `tools/character_creator.html`
- Modify: `pyproject.toml` (package data)
- Test: `tests/test_character_creator_page.py`, then browser checks in Task 6

**Interfaces:**
- Consumes: the API above. The page reads its mode from the URL: `/create/` starts a player character; `/create/?suggest=npc|ai` starts a suggestion; `/create/c/<id>` shows a character; `/create/owner/<tok>/` shows the owner page; `/create/owner/<tok>/new/npc|ai` and `/create/owner/<tok>/c/<id>` use the owner route.

Behaviours required:
- **Form:** four steps built from `/options`, with a progress indicator, Back and Next, and answers kept when a request is refused. The refusal message appears next to the form. Tattoos, scars, piercings and chrome are clearly optional and default to none.
- **After starting:** moves to the private link and tells the player to bookmark it.
- **Review:** newest round first with older rounds and favourites below, each image with Pick, Favourite and "Like this one, but...", which opens subtle or strong and a note. Also Reroll, Edit answers and Delete. Status polling every 3 seconds shows place in line, stops when idle, and pauses when the tab is hidden.
- **Lock in:** only after a pick, with a confirmation step on the page, not a browser dialog. Then shows each sheet with a Redo button; expressions appear as a six-panel CSS grid.
- **Suggestion:** read-only status: waiting for review, accepted, or declined with the owner's note.
- **Owner page:** pending suggestions first with all answers visible, Accept, Decline with a note, then all characters by name with links, plus "New NPC" and "New AI character".

- [ ] **Step 1: Write a failing test** that the file exists in package data and its text contains no `window.claude`, no external `src=` or `href="http` URLs, and that each API path in the Interfaces block appears.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Write the page**, plain JS, no dependencies, and `textContent` for every value that came from a player, never `innerHTML`.
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** `feat(creator): form, review and owner page`

### Task 5: Export NPCs and AI characters into the world

**Files:**
- Modify: `tools/character_creator.py` (`export` CLI)
- Test: `tests/test_character_creator.py`

**Interfaces:**
- Produces: `python -m tools.character_creator export <id> --state <dir> --designs-dir narrator/worlds/designs --design-dir design-data`.

- [ ] **Step 1: Write failing tests:** a picked, non-player character writes `<slug>.toml` with `status="approved"`, its seed and a `source` of `creator:<kind>`, plus a note with `world_role` and `home`. It copies the picked image to `design-data/<slug>/candidates/r1-c1-<seed>.png`, so `gallery` and `sheets --approved-missing` work. It refuses player characters, characters without a pick, and any slug that already exists.
- [ ] **Step 2: Run, expect failure.**
- [ ] **Step 3: Implement** with `save_design`.
- [ ] **Step 4: Run, expect pass; run the whole suite.**
- [ ] **Step 5: Commit** `feat(creator): export approved NPCs and AI characters to the world`

### Task 6: Deploy and verify on the GPU box

Do this only when the owner's render batch has finished and `curl -s http://192.168.10.19:8188/queue` shows nothing running or waiting.

**Files:**
- GPU box: `~/anvil-deploy/stack/docker-compose.yml`, `nginx/nginx.conf`, `dashboard/index.html`, new `dashboard/create/index.html`, `character-creator/app`, `character-creator/state`
- Modify: `docs/image-generation-guide.md`, `docs/design-studio-resume.md`, `ROADMAP.md`

- [ ] **Step 1: Back up** those GPU box files as `*.bak-<date>`.
- [ ] **Step 2: Add the compose service,** copying `image-studio` with command `["python", "-m", "tools.character_creator", "--root", "/state", "--port", "8768"]`.
- [ ] **Step 3: Add nginx routes:** `location /create/ { root /usr/share/nginx/html; try_files $uri /create/index.html; add_header Cache-Control "no-cache"; }` and `location /create/api/ { proxy_pass http://127.0.0.1:8768; client_max_body_size 16k; proxy_read_timeout 120s; proxy_set_header Host $http_host; }`. Pass `Host` so the Origin check compares the real address.
- [ ] **Step 4: Add the AI Lab tile** "Create a character" linking to `/create/`, and a smaller "Suggest an NPC or AI character" link to `/create/?suggest=npc`. Don't add the owner link to the dashboard. Give it to the owner privately.
- [ ] **Step 5: Run a Playwright check over `http://100.67.87.32:8080/create/`** with real renders: full form; refused word keeps answers; four candidates; reroll; vary subtle and strong (compare the two and tune `DENOISE`); pick an earlier round; lock in and see all sheets; redo one sheet; phone width with no sideways scroll; a second browser context with a different link can't read the first; suggestion waits and renders nothing; owner accepts and generates; decline shows the note; no JS console errors.
- [ ] **Step 6: Update docs and ROADMAP,** with a 19b-follow-up line: what exists, that photos are not enabled, and the deploy steps.
- [ ] **Step 7: Commit** `docs(creator): deployment and how to use the character creator`, refresh the `homelab-ops/gpubox` backup without the character state, and ask the owner before pushing.
