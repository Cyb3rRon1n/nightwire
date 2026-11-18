import { test } from "node:test";
import assert from "node:assert/strict";
import { chipTag, chipTitle } from "../../src/lib/nightwire/chips.ts";

const plain = { id: "a", text: "I wait.", skill: null, attribute: null, difficulty: null, chance: null };
const tagged = { id: "b", text: "I talk him down.", skill: "ranged_combat", attribute: "reflexes",
                 difficulty: "moderate" as const, chance: 60 };

test("a tagged chip shows skill, difficulty and chance", () => {
  assert.equal(chipTag(tagged), "Ranged combat · Moderate · 60%");
  assert.equal(chipTitle(tagged), "Reflexes + Ranged combat");
});

test("a plain chip has no tag", () => {
  assert.equal(chipTag(plain), null);
  assert.equal(chipTitle(plain), undefined);
});
