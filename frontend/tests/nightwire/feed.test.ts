import { test } from "node:test";
import assert from "node:assert/strict";
import { classifyLine, groupStarts, isPlayerFacing, pickBackdrop, sceneImages, speakerKey } from "../../src/lib/nightwire/feed.ts";
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

test("own actions drop the '> ' the composer adds", () => {
  assert.deepEqual(classifyLine("p1: > I wait.", view, "p1"), { kind: "own", text: "I wait." });
  assert.deepEqual(classifyLine('p1: > You say "hi"', view, "p1"), { kind: "own", text: 'You say "hi"' });
});

test("only player-facing bracket lines are shown", () => {
  for (const line of ["[initiative: Rin rolled 14]", "[chrome installed: Rin — Kagerou]", "[chrome removed: Rin — Kagerou]",
    "[torite: final notice]", "[selfhood: +2]", "[utsusemi: Hachi wakes in a new shell]"]) {
    assert.equal(isPlayerFacing(line), true, line);
  }
  for (const line of ["[remember_npc: {'name': 'Mama Sato', 'facts': ['secretly pays protection']}]", "[audio error: tts failed]",
    "[image error: refused]", "[tool error: bad id]", "[image prompt (tags): rain]", "[referee: human_moment had no quote]",
    "[voice filtered: Rin]", "[redo: no body]", "[summary error: timeout]"]) {
    assert.equal(isPlayerFacing(line), false, line);
  }
});

test("lines that render nothing don't break a speaker's run", () => {
  // undefined = skipped (hidden meta, audio): the run carries on across it
  assert.deepEqual(groupStarts(["npc:mama sato", undefined, "npc:mama sato", null, "npc:mama sato"]), [true, false, false, false, true]);
});

test("place art shows on arrival until a new scene image comes in", () => {
  // 2 images existed when the player arrived here
  assert.deepEqual(pickBackdrop(["a.png", "b.png"], "place-art/izakaya.jpg", 2), { kind: "place", path: "place-art/izakaya.jpg" });
  assert.deepEqual(pickBackdrop(["a.png", "b.png", "c.png"], "place-art/izakaya.jpg", 2), { kind: "scene", path: "c.png" });
  assert.deepEqual(pickBackdrop(["a.png"], null, 1), { kind: "scene", path: "a.png" });
  assert.equal(pickBackdrop([], null, 0), null);
});
