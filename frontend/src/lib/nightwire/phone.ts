import type { PhoneContact, StateView } from "./protocol.ts";

type PhoneView = { phone: Pick<StateView["phone"], "contacts"> };

const TRUST = ["burned", "wary", "neutral", "friendly", "trusted", "ride-or-die"];

export const totalUnread = (view: PhoneView): number => view.phone.contacts.reduce((n, c) => n + c.unread, 0);

export function sortedContacts(view: PhoneView): PhoneContact[] {
  return [...view.phone.contacts].sort((a, b) => b.unread - a.unread || b.trust - a.trust || a.name.localeCompare(b.name));
}

export const trustLabel = (trust: number): string => TRUST[Math.min(5, Math.max(0, Math.round(trust)))];

// The shown contact stays put once picked; fall back to the first only when nothing is picked or it vanished.
export const resolveSelected = (contacts: PhoneContact[], picked: string | null): string | null =>
  contacts.find((c) => c.name === picked)?.name ?? contacts[0]?.name ?? null;
