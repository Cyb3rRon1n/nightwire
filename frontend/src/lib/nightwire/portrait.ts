// Deliberately cheap placeholder avatar - initials + a color picked
// deterministically from role, not real art (that's Phase 5's job).
const PALETTE = [
  "bg-amber-200 text-stone-950",
  "bg-rose-300 text-stone-950",
  "bg-sky-300 text-stone-950",
  "bg-emerald-300 text-stone-950",
  "bg-violet-300 text-stone-950",
  "bg-orange-300 text-stone-950",
]

function hashString(value: string): number {
  let hash = 0
  for (let i = 0; i < value.length; i++) {
    hash = (hash * 31 + value.charCodeAt(i)) >>> 0
  }
  return hash
}

export function portraitFor(role: string, name: string): { initials: string; colorClass: string } {
  const initials = name.trim().slice(0, 2).toUpperCase() || "?"
  const colorClass = PALETTE[hashString(role) % PALETTE.length]
  return { initials, colorClass }
}
