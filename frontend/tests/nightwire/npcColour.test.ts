import { test } from "node:test";
import assert from "node:assert/strict";
import { GOLD, WORST_BG, contrast, npcColour, npcPortrait } from "../../src/lib/nightwire/npcColour.ts";
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

test("named NPCs get their approved portrait, strangers none", () => {
  assert.equal(npcPortrait("Mama Sato"), "character-art/mama-sato.jpg");
  assert.equal(npcPortrait("saeko"), "character-art/saeko-kirigaya.jpg");
  assert.equal(npcPortrait("A Stranger"), null);
});
