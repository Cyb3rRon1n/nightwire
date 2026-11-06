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
