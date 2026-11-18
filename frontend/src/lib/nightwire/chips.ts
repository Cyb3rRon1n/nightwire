import type { Suggestion } from "./protocol.ts";

const label = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export function chipTag(s: Suggestion): string | null {
  if (!s.skill || !s.difficulty || s.chance === null) return null;
  return `${label(s.skill)} · ${label(s.difficulty)} · ${s.chance}%`;
}

export function chipTitle(s: Suggestion): string | undefined {
  return s.skill && s.attribute ? `${label(s.attribute)} + ${label(s.skill)}` : undefined;
}
