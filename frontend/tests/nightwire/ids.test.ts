import { test } from "node:test";
import assert from "node:assert/strict";
import { normalizeId } from "../../src/lib/nightwire/ids.ts";

test("IDs ignore case, edge spaces and inner spacing", () => {
  assert.equal(normalizeId("  Friday Game "), "friday-game");
  assert.equal(normalizeId("Rin"), normalizeId("rin"));
  assert.equal(normalizeId("Rin #1"), "rin-#1"); // kept; the socket URL encodes it
});
