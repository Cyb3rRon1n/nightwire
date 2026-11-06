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
