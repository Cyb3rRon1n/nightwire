# Attribute Point-Buy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give players a real, server-validated attribute point-buy step in character creation, so `CharacterSheet.attributes` stops defaulting to a uniform placeholder and every skill's cap (`skill_cap = min(5, modifier(attribute_score)+3)`) becomes real instead of uniformly 3.

**Architecture:** Backend first — a `_validate_and_finalize_attributes` function in `server/dispatch.py`, same file and shape as the existing `_validate_and_finalize_skills` it sits beside, run before it in the `join` handler so skill-cap validation reads real attribute scores. Then frontend — a new `AttributePicker` component mirroring `SkillPicker`'s existing file/prop pattern exactly, wired into the pre-join character-creation form ahead of the existing `SkillPicker`.

**Tech Stack:** Python (pytest, existing `dispatch.py`/`ruleset/` modules), TypeScript/React (existing `page.tsx`/`SkillPicker.tsx` patterns), no new dependencies.

**Spec:** `docs/superpowers/specs/2026-08-25-attribute-point-buy-design.md` — read it first.

## Global Constraints

- Six attributes: `body`, `reflexes`, `tech`, `cool`, `intellect`, `presence` (`ruleset/attributes.py`'s `Attribute` enum) — no other names are valid.
- Base score 10 for every attribute; the selected role's `primary_attribute` (`ruleset/roles.py`'s `ROLES[role].primary_attribute`) starts at 11 instead. An unrecognized/missing role gets no bonus — every attribute stays at 10, not an error.
- Budget: 12 points, flat cost (1 point of budget per 1 point of score, in either direction — lowering an attribute below its starting value refunds budget).
- Range: 6-14 per attribute, absolute (the role bonus shifts where an attribute *starts*, not its ceiling — a primary attribute can still only reach 14, i.e. at most +3 more spendable on it than a non-primary attribute's +4).
- Missing attributes in a `join` payload default to their correct starting value (10, or 11 for the role's primary) — a player who never touches the allocator still gets a valid character.
- Validation is server-authoritative, same trust-boundary shape as the existing skill validation: reject unknown names, wrong types, out-of-range scores, and over-budget spends before any of it reaches `CharacterSheet`.

---

## File Structure

- Modify: `server/dispatch.py` — `_starting_attributes`, `_validate_and_finalize_attributes` (new), wired into the `join` branch of `handle_message` before `_validate_and_finalize_skills`.
- Create: `frontend/src/app/nightwire/AttributePicker.tsx` — `ATTRIBUTES`, `ATTRIBUTE_BASE_SCORE`/`ATTRIBUTE_BUDGET`/`ATTRIBUTE_MIN`/`ATTRIBUTE_MAX`, `startingAttributes()`, `AttributePicker` component. Mirrors `SkillPicker.tsx`'s existing shape exactly.
- Modify: `frontend/src/app/nightwire/page.tsx` — `ROLES` gains a `primaryAttribute` field per entry, new `attributes` state, `AttributePicker` inserted before the existing `SkillPicker`, `SkillPicker`'s `attributes` prop stops being hardcoded `{}`, `handleJoin` sends the real `attributes` state.
- Test: `tests/test_dispatch.py`.

---

### Task 1: Server-side attribute validation

**Files:**
- Modify: `server/dispatch.py`
- Test: `tests/test_dispatch.py`

**Interfaces:**
- Consumes: `ruleset.attributes.Attribute` (enum), `ruleset.roles.ROLES` (`dict[str, Role]`, `Role.primary_attribute: Attribute`) — both already exist, unmodified.
- Produces: `_validate_and_finalize_attributes(character_data: dict) -> None` — raises `ValueError` on any invalid input; on success, sets `character_data["attributes"]` to a complete 6-key `dict[str, int]`. Task 2 depends on the wire format this produces: a `join` message's `character.attributes` may be a *partial* dict (only touched attributes) and the server fills in the rest.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_dispatch.py`, after `test_join_missing_character_field_raises_value_error` and before `test_join_accepts_a_valid_starting_skill_allocation` (attributes must be validated before skills read them, so these tests belong just ahead of the skill tests):

```python
def test_join_with_no_attributes_field_uses_base_scores_and_role_bonus():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid"},
    }, "p1")

    assert session.characters["p1"].attributes == {
        "body": 10, "reflexes": 11, "tech": 10, "cool": 10, "intellect": 10, "presence": 10,
    }


def test_join_role_bonus_only_applies_to_the_selected_roles_primary_attribute():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Ghost", "role": "netrunner", "lifepath": "corpo"},
    }, "p1")

    attributes = session.characters["p1"].attributes
    assert attributes["tech"] == 11
    assert attributes["reflexes"] == 10


def test_join_with_unknown_role_uses_base_scores_for_all_attributes():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {"player_id": "p1", "name": "Zeta", "role": "diplomat", "lifepath": "spacer"},
    }, "p1")

    assert session.characters["p1"].attributes == {
        "body": 10, "reflexes": 10, "tech": 10, "cool": 10, "intellect": 10, "presence": 10,
    }


def test_join_accepts_a_valid_attribute_allocation():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "attributes": {"reflexes": 14, "tech": 12},  # (14-11) + (12-10) = 5 <= budget of 12
        },
    }, "p1")

    assert session.characters["p1"].attributes == {
        "body": 10, "reflexes": 14, "tech": 12, "cool": 10, "intellect": 10, "presence": 10,
    }


def test_join_rejects_an_attribute_allocation_over_budget():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="exceed the budget"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"reflexes": 14, "tech": 14, "cool": 14},  # 3 + 4 + 4 = 11... need >12
            },
        }, "p1")


def test_join_rejects_an_attribute_score_below_the_minimum():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="between 6 and 14"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"body": 5},
            },
        }, "p1")


def test_join_rejects_an_attribute_score_above_the_maximum():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="between 6 and 14"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"reflexes": 15},
            },
        }, "p1")


def test_join_rejects_an_unknown_attribute_name():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="unknown attribute"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"luck": 10},
            },
        }, "p1")


def test_join_rejects_a_non_dict_attributes_value():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="attributes must be a dict"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": "not-a-dict",
            },
        }, "p1")


def test_join_rejects_a_float_attribute_score():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="must be an int"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"body": 12.5},
            },
        }, "p1")


def test_join_rejects_a_string_attribute_score():
    session = Session(session_id="s1")
    with pytest.raises(ValueError, match="must be an int"):
        handle_message(session, {
            "type": "join",
            "character": {
                "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
                "attributes": {"body": "12"},
            },
        }, "p1")


def test_join_skill_cap_reflects_a_raised_attribute():
    session = Session(session_id="s1")
    handle_message(session, {
        "type": "join",
        "character": {
            "player_id": "p1", "name": "Rook", "role": "solo", "lifepath": "streetkid",
            "attributes": {"body": 14},  # modifier(14) == 2, cap == min(5, 2+3) == 5
            "skills": {"melee": 5},  # governed by body - was uniformly capped at 3 before this feature
        },
    }, "p1")

    character = session.characters["p1"]
    assert character.attributes["body"] == 14
    assert character.skills == {"melee": 5}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dispatch.py -v`
Expected: the new tests FAIL. Most fail on the `attributes` assertion (attribute stays `{}` since nothing populates it yet); `test_join_rejects_an_unknown_attribute_name` fails because nothing raises (unknown attribute keys are currently silently ignored); `test_join_skill_cap_reflects_a_raised_attribute` fails with the skill exceeding its (currently uniform-3) cap. All pre-existing tests in the file still PASS unchanged.

- [ ] **Step 3: Implement**

In `server/dispatch.py`, add these imports and constants after the existing imports:

```python
from ruleset.attributes import Attribute
from ruleset.roles import ROLES

ATTRIBUTE_BASE_SCORE = 10
ATTRIBUTE_BUDGET = 12
ATTRIBUTE_MIN = 6
ATTRIBUTE_MAX = 14
```

Add `_starting_attributes` and `_validate_and_finalize_attributes` right before `_validate_and_finalize_skills`:

```python
def _starting_attributes(role: str) -> dict[str, int]:
    starting = {attr.value: ATTRIBUTE_BASE_SCORE for attr in Attribute}
    if role in ROLES:
        starting[ROLES[role].primary_attribute.value] = ATTRIBUTE_BASE_SCORE + 1
    return starting


def _validate_and_finalize_attributes(character_data: dict) -> None:
    attributes = character_data.get("attributes") or {}
    if not isinstance(attributes, dict):
        raise ValueError(f"attributes must be a dict, got {type(attributes).__name__}")
    starting = _starting_attributes(character_data.get("role"))

    finalized = dict(starting)
    spent = 0
    for name, score in attributes.items():
        if name not in starting:
            raise ValueError(f"unknown attribute: {name!r}")
        if not isinstance(score, int) or isinstance(score, bool):
            raise ValueError(f"attribute {name!r} score {score!r} must be an int")
        if score < ATTRIBUTE_MIN or score > ATTRIBUTE_MAX:
            raise ValueError(
                f"attribute {name!r} score {score} must be between {ATTRIBUTE_MIN} and {ATTRIBUTE_MAX}"
            )
        finalized[name] = score
        spent += score - starting[name]

    if spent > ATTRIBUTE_BUDGET:
        raise ValueError(f"attribute points spent ({spent}) exceed the budget ({ATTRIBUTE_BUDGET})")

    character_data["attributes"] = finalized
```

Wire it into the `join` branch of `handle_message`, replacing:

```python
    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        _validate_and_finalize_skills(character_data)
        join(session, CharacterSheet(**character_data))
```

with:

```python
    if message_type == "join":
        character_data = message.get("character")
        if character_data is None:
            raise ValueError("missing 'character' in join message")
        _validate_and_finalize_attributes(character_data)
        _validate_and_finalize_skills(character_data)
        join(session, CharacterSheet(**character_data))
```

(Attributes must be finalized first — `_validate_and_finalize_skills` reads `character_data.get("attributes")` to compute skill caps, and needs the real, complete dict, not a possibly-empty one.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dispatch.py -v`
Expected: all tests PASS, including all 12 new ones and every pre-existing test in the file (skill-cap tests that relied on attributes defaulting to a bare `{}` now see a real starting-attributes dict instead — check this didn't change their outcome: `test_join_rejects_a_starting_allocation_over_the_governing_attribute_cap` uses role `solo` and skill `melee` governed by `body`, which is *not* Solo's primary attribute (`reflexes` is) — `body` still starts at 10, so that test's expected cap of 3 is unaffected).

- [ ] **Step 5: Run the full backend test suite**

Run: `pytest -q`
Expected: all tests pass, zero failures.

- [ ] **Step 6: Commit**

```bash
git add server/dispatch.py tests/test_dispatch.py
git commit -m "feat: server-validated attribute point-buy on character join"
```

---

### Task 2: Frontend attribute allocator

**Files:**
- Create: `frontend/src/app/nightwire/AttributePicker.tsx`
- Modify: `frontend/src/app/nightwire/page.tsx`

**Interfaces:**
- Consumes: the `join` message's `character.attributes` field validated in Task 1 (a partial `Record<string, number>` is enough — the server fills in the rest).
- Produces: `startingAttributes(primaryAttribute: string | null): Record<string, number>` and `ATTRIBUTE_MIN`/`ATTRIBUTE_MAX`/`ATTRIBUTE_BUDGET`/`ATTRIBUTE_BASE_SCORE` exported from `AttributePicker.tsx`, used both by the picker itself and by `page.tsx` to build the merged view `SkillPicker` needs. No automated frontend test infrastructure exists for this kind of UI in this repo (confirmed in the spec) — verified live against the real running stack, the same pattern every prior phase used.

- [ ] **Step 1: Create `AttributePicker.tsx`**

```typescript
"use client";

// Mirrors ruleset/attributes.py's Attribute enum and
// docs/superpowers/specs/2026-08-25-attribute-point-buy-design.md's
// numbers - same duplication pattern SkillPicker.tsx already uses for
// SKILLS/skillCap on a WebSocket-first backend with no REST endpoint
// for static ruleset content.
export interface AttributeInfo {
  name: string;
  label: string;
}

export const ATTRIBUTES: AttributeInfo[] = [
  { name: "body", label: "Body" },
  { name: "reflexes", label: "Reflexes" },
  { name: "tech", label: "Tech" },
  { name: "cool", label: "Cool" },
  { name: "intellect", label: "Intellect" },
  { name: "presence", label: "Presence" },
];

export const ATTRIBUTE_BASE_SCORE = 10;
export const ATTRIBUTE_BUDGET = 12;
export const ATTRIBUTE_MIN = 6;
export const ATTRIBUTE_MAX = 14;

// The role's primary attribute starts at +1 over base - mirrors
// server/dispatch.py's _starting_attributes exactly.
export function startingAttributes(primaryAttribute: string | null): Record<string, number> {
  const starting: Record<string, number> = {};
  for (const attr of ATTRIBUTES) {
    starting[attr.name] = attr.name === primaryAttribute ? ATTRIBUTE_BASE_SCORE + 1 : ATTRIBUTE_BASE_SCORE;
  }
  return starting;
}

export function AttributePicker({
  attributes,
  primaryAttribute,
  onIncrement,
  onDecrement,
}: {
  attributes: Record<string, number>;
  primaryAttribute: string | null;
  onIncrement: (attributeName: string) => void;
  onDecrement: (attributeName: string) => void;
}) {
  const starting = startingAttributes(primaryAttribute);
  const spent = ATTRIBUTES.reduce(
    (total, attr) => total + ((attributes[attr.name] ?? starting[attr.name]) - starting[attr.name]),
    0,
  );
  const remaining = ATTRIBUTE_BUDGET - spent;

  return (
    <div className="nw-hud flex flex-col gap-1 text-sm nw-text-body">
      <p className="nw-eyebrow">
        Attributes ({remaining} point{remaining === 1 ? "" : "s"} remaining)
      </p>
      {ATTRIBUTES.map((attr) => {
        const score = attributes[attr.name] ?? starting[attr.name];
        return (
          <div key={attr.name} className="flex items-center justify-between gap-2">
            <span>
              {attr.label} ({score}){attr.name === primaryAttribute ? " ★" : ""}
            </span>
            <div className="flex gap-1">
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onDecrement(attr.name)}
                disabled={score <= ATTRIBUTE_MIN}
              >
                −
              </button>
              <button
                type="button"
                className="nw-btn-ghost"
                onClick={() => onIncrement(attr.name)}
                disabled={score >= ATTRIBUTE_MAX || remaining <= 0}
              >
                +
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Add `primaryAttribute` to `page.tsx`'s `ROLES` array**

Replace:

```typescript
const ROLES: Array<{ value: string; label: string; description: string }> = [
  { value: "solo", label: "Solo", description: "Front-line combat specialist. Best attack rolls, highest Health, a passive Initiative/Awareness edge." },
  { value: "netrunner", label: "Netrunner", description: "Hacking specialist. Bypasses locks, pulls data, and disables weapons/cameras/drones mid-combat." },
  { value: "techie", label: "Techie", description: "Gear specialist. Repairs damaged equipment and cyberware, installs upgrades, crafts - keeps the party's equipment working, not a healer." },
  { value: "fixer", label: "Fixer", description: "Social specialist. Negotiation, contacts, contraband access - talks past trouble instead of shooting through it." },
];
```

with:

```typescript
const ROLES: Array<{ value: string; label: string; description: string; primaryAttribute: string }> = [
  { value: "solo", label: "Solo", description: "Front-line combat specialist. Best attack rolls, highest Health, a passive Initiative/Awareness edge.", primaryAttribute: "reflexes" },
  { value: "netrunner", label: "Netrunner", description: "Hacking specialist. Bypasses locks, pulls data, and disables weapons/cameras/drones mid-combat.", primaryAttribute: "tech" },
  { value: "techie", label: "Techie", description: "Gear specialist. Repairs damaged equipment and cyberware, installs upgrades, crafts - keeps the party's equipment working, not a healer.", primaryAttribute: "tech" },
  { value: "fixer", label: "Fixer", description: "Social specialist. Negotiation, contacts, contraband access - talks past trouble instead of shooting through it.", primaryAttribute: "presence" },
];
```

- [ ] **Step 3: Add the import and `attributes` state**

Add to the imports near the top of `page.tsx` (alongside the existing `SkillPicker` import):

```typescript
import { AttributePicker, startingAttributes } from "./AttributePicker";
```

Add this state declaration right after the existing `const [skills, setSkills] = useState<Record<string, number>>({});` line:

```typescript
  const [attributes, setAttributes] = useState<Record<string, number>>({});
```

- [ ] **Step 4: Reset attributes when role changes, and derive `primaryAttribute`**

Replace the role `<select>`'s `onChange`:

```typescript
              <select className="nw-field" value={role} onChange={(e) => setRole(e.target.value)}>
```

with:

```typescript
              <select className="nw-field" value={role} onChange={(e) => { setRole(e.target.value); setAttributes({}); }}>
```

(Changing role shifts which attribute gets the +1 starting bonus, so any in-progress attribute allocation is reset rather than left referencing the wrong baseline. Skill selections are untouched - out of scope for this change.)

Add these two derived-value lines in the component body, right after the `attributes` state declaration from Step 3 (both are needed before the JSX in Step 5, one by `AttributePicker`/`SkillPicker` directly and one by `SkillPicker` alone):

```typescript
  const [attributes, setAttributes] = useState<Record<string, number>>({});
  const primaryAttribute = ROLES.find((r) => r.value === role)?.primaryAttribute ?? null;
  const mergedAttributes = { ...startingAttributes(primaryAttribute), ...attributes };
```

- [ ] **Step 5: Insert the `AttributePicker` and fix `SkillPicker`'s `attributes` prop**

Replace:

```jsx
              <SkillPicker
                skills={skills}
                attributes={{}}
                remaining={STARTING_SKILL_POINTS - Object.values(skills).reduce((a, b) => a + b, 0)}
                onIncrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: (s[name] ?? 0) + 1 }))
                }
                onDecrement={(name) =>
                  setSkills((s) => ({ ...s, [name]: Math.max(0, (s[name] ?? 0) - 1) }))
                }
              />
```

with:

```jsx
              <AttributePicker
                attributes={attributes}
                primaryAttribute={primaryAttribute}
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
```

- [ ] **Step 6: Send `attributes` on join**

Replace:

```typescript
  function handleJoin() {
    send({
      type: "join",
      character: { player_id: playerId, name, role, lifepath, skills },
    });
  }
```

with:

```typescript
  function handleJoin() {
    send({
      type: "join",
      character: { player_id: playerId, name, role, lifepath, skills, attributes },
    });
  }
```

- [ ] **Step 7: Type-check and lint**

Run: `npx tsc --noEmit -p tsconfig.json` from `frontend/`
Expected: no output (clean).

Run: `npx eslint src/app/nightwire/page.tsx src/app/nightwire/AttributePicker.tsx` from `frontend/`
Expected: only the pre-existing `react-hooks/set-state-in-effect` warning (unrelated to this change) — no new errors.

- [ ] **Step 8: Live-verify against the real running stack**

Sync the changed/new files to the GPU box (no backend restart needed for this task — Task 1's backend changes should already be synced and the server already restarted from that task's own verification; if not, sync `server/dispatch.py` and restart `nightwire-server` first):

```bash
scp -i ~/.ssh/nightwire_remote frontend/src/app/nightwire/AttributePicker.tsx sentinel@100.67.87.32:~/projects/github/repos/nightwire/frontend/src/app/nightwire/AttributePicker.tsx
scp -i ~/.ssh/nightwire_remote frontend/src/app/nightwire/page.tsx sentinel@100.67.87.32:~/projects/github/repos/nightwire/frontend/src/app/nightwire/page.tsx
```

(Start the frontend dev server and open the SSH tunnel the same way established earlier this session if they aren't already running: `nohup npm run dev > /tmp/nightwire-frontend.log 2>&1 &` from `~/projects/github/repos/nightwire/frontend`, tunnel `-L 3000:localhost:3000 -L 8000:localhost:8000`.)

Using browser automation against the tunneled frontend, verify all of the following in one session:

1. Connect and pick role **Netrunner**. The new Attributes section appears above Skills, showing Tech starting at **11** (with a ★ marker) and all others at **10**, "12 points remaining".
2. Click Tech's `+` three times (→ 14) and Cool's `+` twice (→ 12). "Points remaining" reads **7** (12 − 3 − 2).
3. Confirm Tech's `+` button is now disabled (score 14 == `ATTRIBUTE_MAX`).
4. Click Body's `−` down to 6, confirm its `−` button then disables (score 6 == `ATTRIBUTE_MIN`), and "points remaining" increased accordingly (refund from lowering below its starting value of 10).
5. Confirm the Skills section's cap numbers reflect the raised Tech score — Hacking (governed by Tech) should show a cap of **5**, not the old uniform 3, since `modifier(14) == 2` and `min(5, 2+3) == 5`.
6. Patch `WebSocket.prototype.send` (same technique used for the photo-reference-portrait feature's live verification) before clicking Join, then click Join. Confirm the outgoing `join` message's `character.attributes` contains exactly the touched values (e.g. `{"tech": 14, "cool": 12, "body": 6}`) — not a padded 6-key dict, since the frontend sends the raw sparse state and the server fills in the rest.
7. Confirm the broadcast `StateView` that comes back shows the character's `attributes` fully populated with all six keys, matching what was sent plus server-filled defaults for the untouched ones (`reflexes`, `intellect`, `presence` at 10).

- [ ] **Step 9: Commit**

```bash
git add frontend/src/app/nightwire/AttributePicker.tsx frontend/src/app/nightwire/page.tsx
git commit -m "feat: attribute point-buy allocator in character creation"
```

---

## Self-review notes

- **Spec coverage**: base score/role bonus/budget/range/flat cost (Task 1's constants), server validation (Task 1), UI ordering before SkillPicker (Task 2 Step 5), missing-attributes-default (Task 1's `_starting_attributes` fallback, tested). Deferred items (post-creation growth, role-weighted budgets, wider later ranges) intentionally have no task — matches the spec's own "What's deliberately deferred" section.
- **Type consistency checked**: `Record<string, number>` (TypeScript, Task 2) ↔ `dict[str, int]` validated per-key against the same six names (Python, Task 1) ↔ wire field `attributes` — same name end to end, matching the `skills` field's existing precedent exactly.
- **No placeholders**: every step has real code, not a description of intent.
