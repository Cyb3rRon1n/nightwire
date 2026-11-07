import { test } from "node:test";
import assert from "node:assert/strict";
import { totalUnread, sortedContacts, trustLabel } from "../../src/lib/nightwire/phone.ts";

const c = (name: string, trust: number, unread: number) => ({ name, role: "x", trust, unread, portrait: null });
const view = (contacts: ReturnType<typeof c>[]) => ({ phone: { contacts, threads: {}, typing: [] } });

test("totalUnread sums unread across contacts", () => {
  assert.equal(totalUnread(view([c("A", 2, 1), c("B", 3, 2)])), 3);
  assert.equal(totalUnread(view([])), 0);
});

test("sortedContacts: unread first (more first), then trust high to low, then name", () => {
  const names = sortedContacts(view([c("Zed", 5, 0), c("Amy", 5, 0), c("Bo", 1, 1), c("Cy", 0, 2), c("Di", 4, 0)])).map((x) => x.name);
  assert.deepEqual(names, ["Cy", "Bo", "Amy", "Zed", "Di"]);
});

test("sortedContacts does not mutate the view", () => {
  const v = view([c("B", 1, 0), c("A", 2, 0)]);
  sortedContacts(v);
  assert.equal(v.phone.contacts[0].name, "B");
});

test("trustLabel names 0..5 and clamps", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5].map(trustLabel), ["burned", "wary", "neutral", "friendly", "trusted", "ride-or-die"]);
  assert.equal(trustLabel(-3), "burned");
  assert.equal(trustLabel(9), "ride-or-die");
});
